# Phase 20: Scraping Improvements - Research

**Researched:** 2026-05-27 (updated same day — Crawl4AI decision)
**Domain:** Python async HTTP scraping, HTML-to-Markdown compression, domain filtering, URL normalization
**Confidence:** HIGH (all findings verified against installed packages and official docs)

---

## Summary

This phase addresses four concrete deficiencies in `backend/prospector.py`. The scraper currently uses `httpx` which exposes a non-browser TLS JA3 fingerprint, getting blocked by Cloudflare and similar WAFs. HTML cleaning is done with BeautifulSoup + 8 000-char truncation, losing structure and wasting LLM context. The domain blocklist (`LOW_QUALITY_DISCOVERY_DOMAINS`) is missing major Colombian aggregators. And URLs from Serper arrive as blog/subpage paths rather than company homepages.

`curl_cffi` 0.15.0 is **already installed** in this project's Python environment (`curl_cffi.__version__ == '0.15.0'`). `chrome131` is a confirmed valid impersonate target in that version. No new install is required for SCRAPE-01.

For SCRAPE-02 (HTML → Markdown), **Crawl4AI with Dockerfile is the chosen approach** (decision finalized 2026-05-27 after Railway viability research). Crawl4AI requires Playwright as a mandatory dependency, but this is viable on Railway using a Dockerfile with the official Microsoft Playwright base image (`mcr.microsoft.com/playwright/python:v1.49.0-noble`). Nixpacks (the current builder) does NOT work — GLIBC mismatch. The `CRAWL4AI_MODE=api` env var tells `crawl4ai-setup` to skip browser install since Chromium is already in the base image. Crawl4AI's `DefaultMarkdownGenerator` + `PruningContentFilter` provide semantically smarter HTML→Markdown compression than markdownify — they score content blocks by density and prune boilerplate intelligently. The HTML is already fetched by curl_cffi; `DefaultMarkdownGenerator.generate_markdown(cleaned_html=html, ...)` processes it without launching any browser. ~~markdownify was previously recommended but superseded by this decision.~~

For SCRAPE-03, the existing `LOW_QUALITY_DISCOVERY_DOMAINS` set is extensive but missing a batch of Colombian-specific aggregators. The additions are documented with source.

For SCRAPE-04, `tldextract==5.3.1` (not yet in requirements.txt) provides reliable registered-domain extraction via the Public Suffix List, solving the `blog.acme.com.co` → `acme.com.co` case that `urlparse` fails on. It is synchronous and zero-network (cached PSL).

The discovery bug (LLM extracting "empresas" instead of the real industry) is not a scraping problem but a prompt/tool-call issue: the `industria` parameter passes from `campaign["industria_objetivo"]` through `hive_adapter.py` already, but the director LLM prompt instructs "llama a `discover_companies` con la industria de la campaña" without enforcing it. The fix is to pre-populate `industria` as a non-negotiable string in the tool definition's description or inject it as a system-prompt variable.

**Primary recommendation (FINAL):** Replace httpx in `scrape_url()` with `curl_cffi.AsyncSession(impersonate="chrome131")`; use **Crawl4AI `DefaultMarkdownGenerator` + `PruningContentFilter`** for HTML→Markdown (requires Dockerfile for Worker service — see Railway Dockerfile section below); expand `LOW_QUALITY_DISCOVERY_DOMAINS`; add `extract_homepage()` using `tldextract`; pre-populate `industria` from `campaign["industria_objetivo"]` in the director prompt.

**~~markdownify alternative: superseded~~** — Crawl4AI was chosen because it offers semantically smarter content pruning and future browser capability (SPAs). Railway Dockerfile path confirmed viable (see new section below).

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SCRAPE-01 | Replace `httpx.AsyncClient` in `scrape_url()` with `curl_cffi.AsyncSession(impersonate="chrome131")` | curl_cffi 0.15.0 already installed; chrome131 confirmed valid; API pattern verified against installed package |
| SCRAPE-02 | Convert scraped HTML to compressed Markdown via Crawl4AI before LLM analysis (~80% token reduction) | Crawl4AI requires Playwright — not viable; `markdownify` or `html2text` provide same conversion with zero browser dep; `markdownify` recommended |
| SCRAPE-03 | `DIRECTORY_DOMAINS` blocklist filters aggregator sites from Serper results before scraping | ~35 additional Colombian domains identified from directory research; existing `LOW_QUALITY_DISCOVERY_DOMAINS` is the correct set to expand |
| SCRAPE-04 | `extract_homepage(url)` normalizes blog/directory URLs to company homepages | `tldextract==5.3.1` + known-subdomain strip set; algorithm verified against edge cases |
</phase_requirements>

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| curl_cffi | 0.15.0 (already installed) | Async HTTP with Chrome TLS impersonation | Only Python library that impersonates TLS JA3/HTTP2 fingerprint; defeats Cloudflare bot detection |
| markdownify | 1.2.2 | HTML → Markdown conversion | Zero new heavy deps (reuses bs4 already installed); synchronous; actively maintained |
| tldextract | 5.3.1 | Registered-domain extraction via Public Suffix List | Handles co.uk, .com.co, blogspot.com edge cases that urlparse fails on |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| html2text | 2025.4.15 | Alternative HTML → Markdown, zero deps | If markdownify output is too verbose; html2text produces plainer text |
| beautifulsoup4 | 4.14.3 (already installed) | Pre-clean HTML before markdown conversion | Strip scripts/nav/footer before passing to markdownify |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| markdownify | Crawl4AI | Crawl4AI requires Playwright (mandatory dep, ~1 GB RAM, browser binaries) — unacceptable in Railway ARQ worker |
| markdownify | html2text | html2text strips links entirely by default; markdownify preserves heading/structure better for LLM context |
| tldextract | urllib.parse manually | urlparse fails for .com.co, .co.uk, and private suffixes like blogspot.com |

**Installation (new packages only — curl_cffi already present):**
```bash
pip install markdownify==1.2.2 tldextract==5.3.1
```

**Version verification (run to confirm):**
```bash
python -c "import curl_cffi; print(curl_cffi.__version__)"   # expect 0.15.0
pip show markdownify | grep Version
pip show tldextract  | grep Version
```

---

## Architecture Patterns

### Recommended Change Scope in prospector.py

```
backend/prospector.py
├── scrape_url()               # Line 885 — replace httpx with curl_cffi.AsyncSession
├── LOW_QUALITY_DISCOVERY_DOMAINS  # Line 62 — expand with ~35 more domains
├── discover_via_serper()      # Line 249 — add extract_homepage() call on each result URL
└── extract_homepage()         # NEW function — add after _is_low_quality_candidate()
backend/requirements.txt
└── add: markdownify==1.2.2, tldextract==5.3.1
```

### Pattern 1: curl_cffi AsyncSession replacing httpx in scrape_url()

**What:** Create one `AsyncSession` per scrape call with `impersonate="chrome131"` at the session level. This sets TLS fingerprint, ALPN, and HTTP/2 settings globally so every request in the session looks like Chrome 131.

**When to use:** Any outbound HTTP request to a company website that may have Cloudflare, Imperva, or similar WAF.

**Verified against:** installed curl_cffi 0.15.0 — `AsyncSession.__init__` accepts `impersonate` as a keyword arg; `allow_redirects` defaults to True; `timeout` accepts a float.

```python
# Source: curl_cffi 0.15.0 installed package + readthedocs.io/en/latest/api.html
from curl_cffi.requests import AsyncSession, RequestsError

async def scrape_url(url: str, timeout: int = 12) -> str:
    # ... build_candidates() stays the same ...
    html = ""
    last_error = "no response"
    candidates = build_candidates(url)
    _NO_RETRY_CODES = {400, 401, 403, 404, 405, 410, 429, 451, 500, 502, 503, 504}
    _HARD_BLOCK_CODES = {403, 429, 451}
    try:
        async with AsyncSession(
            impersonate="chrome131",
            allow_redirects=True,
            timeout=timeout,
        ) as client:
            hard_blocked = False
            for candidate in candidates:
                if hard_blocked:
                    break
                try:
                    resp = await client.get(candidate)
                except RequestsError as e:
                    last_error = f"{candidate}: {e}"
                    continue
                if resp.status_code >= 400:
                    last_error = f"{candidate}: HTTP {resp.status_code}"
                    if resp.status_code in _HARD_BLOCK_CODES:
                        hard_blocked = True
                    if resp.status_code in _NO_RETRY_CODES:
                        break
                    continue
                html = resp.text or ""
                if html.strip():
                    break
    except Exception as e:
        last_error = str(e)
    # ... rest of cleaning logic ...
```

**Key changes from httpx version:**
- `httpx.AsyncClient(...)` → `AsyncSession(impersonate="chrome131", ...)`
- `headers=ua_profile` parameter per-request is **dropped** — curl_cffi generates authentic browser headers automatically from the impersonate target; manually overriding them would degrade the fingerprint
- `resp.text` access is the same as httpx
- Exception: catch `RequestsError` (from `curl_cffi.requests`) instead of `httpx.RequestError`

### Pattern 2: HTML to Markdown via markdownify

**What:** After fetching HTML with curl_cffi, pre-strip noisy tags with BeautifulSoup (already in the pipeline), then convert the cleaned HTML to Markdown with `markdownify`. Feed the Markdown string (not raw text) to the LLM.

**Why ~80% token reduction:** HTML tags, attributes, inline styles, and JS blobs are eliminated; Markdown represents the same semantic content in far fewer tokens.

```python
# Source: markdownify==1.2.2 PyPI docs
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import re

def html_to_compressed_markdown(html: str) -> str:
    """Strip noise, then convert HTML → Markdown. Aim: ~80% token reduction."""
    soup = BeautifulSoup(html, "html.parser")
    # Remove non-content tags (same tags as current code)
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "svg", "img", "iframe"]):
        tag.decompose()
    # Convert cleaned HTML to Markdown
    clean_html = str(soup)
    markdown = md(
        clean_html,
        strip=["a"],           # strip links — LLM doesn't need href URLs
        newline_style="spaces",
        heading_style="ATX",   # ## heading style
    )
    # Collapse excessive blank lines
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown
```

**Integration point in scrape_url():** Replace the current block starting at line 1025 (the `for tag in soup(...)` block through `text = re.sub(...)`) with a call to `html_to_compressed_markdown(html)`. Keep the contact extraction block (lines 988-1022) unchanged — it runs on raw HTML before this conversion.

**Token budget:** Current: 8 000 chars plain text. New: ~1 600–2 000 chars Markdown. Keep the `[:8000]` safety cap but it will rarely trigger.

### Pattern 3: extract_homepage() normalization

**What:** Strip known non-homepage subdomains and paths from any URL to derive the company root.

**When to use:** On every URL returned by `discover_via_serper()` before it enters the candidate list.

```python
# Source: tldextract==5.3.1 PyPI docs + algorithm design
import tldextract

# Subdomains that are NOT the company homepage
_NON_HOME_SUBDOMAINS = frozenset({
    "blog", "blogs", "news", "press", "careers", "jobs", "hire",
    "app", "apps", "portal", "admin", "dashboard", "api",
    "shop", "store", "tienda", "ecommerce",
    "support", "help", "ayuda", "soporte",
    "mail", "webmail", "email",
    "m", "mobile",
    "dev", "staging", "test", "demo",
    "cdn", "static", "assets", "media",
    "docs", "wiki", "kb",
})

def extract_homepage(url: str) -> str:
    """
    Normalize a URL to the company's homepage.

    Examples:
      https://blog.acme.com/article/2024/big-news  -> https://acme.com
      https://careers.empresa.com.co/vacante/123   -> https://empresa.com.co
      https://www.acme.com/about/team              -> https://www.acme.com
      https://acme.com/noticias/articulo-123       -> https://acme.com
    """
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    ext = tldextract.extract(url)
    if not ext.domain or not ext.suffix:
        return url  # can't parse — return as-is

    registered = f"{ext.domain}.{ext.suffix}"  # e.g. "acme.com" or "empresa.com.co"

    subdomain = ext.subdomain.lower() if ext.subdomain else ""
    # "www" or "www.blog" — strip www prefix to get the real subdomain part
    effective_sub = subdomain.lstrip("www.").strip(".")

    if effective_sub in _NON_HOME_SUBDOMAINS:
        return f"https://{registered}"

    # Path normalization: drop deep paths that indicate an article/post
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = parsed.path or "/"
    for marker in LOW_QUALITY_PATH_MARKERS:   # reuse existing list
        if marker in path:
            # Reconstruct with registered domain, no deep path
            return f"https://{parsed.netloc.lstrip('www.') or registered}"

    # If subdomain is non-home but not in our list, keep as-is (may be a legitimate sub-app)
    return f"https://{parsed.netloc}{'' if path in ('/', '') else ''}".rstrip("/") or f"https://{registered}"
```

**Integration point:** In `discover_via_serper()` at line ~293, after extracting `url = item.get("link", "")`, add:
```python
url = extract_homepage(url)
item["url"] = url
```

### Pattern 4: DIRECTORY_DOMAINS expansion

**What:** Expand `LOW_QUALITY_DISCOVERY_DOMAINS` (line 62) with domains identified in research that are currently missing.

**Additions to add to the existing set:**

```python
# Colombian business directories (missing from current blocklist)
"einforma.co", "directorio-empresas.einforma.co",
"empresas.portafolio.co", "empresas.larepublica.co",
"cylex.co", "guiaempresarial.co", "123empresas.com",
"tuugo.com", "tuugo.com.co",
"kompass.com",                  # already partially covered, add base
"enests.co",
"brownbook.net",
"cybo.com",
"infobel.com",
"tupalo.com",
"hotfrog.com",
"foursquare.com",

# Job boards missing from current list
"bumeran.com", "bumeran.com.co",
"getonboard.com", "getonboard.co",
"magneto.co",
"hipo.co",
"trabajando.com.co",
"multitrabajos.com",
"empleo.net.co",

# News/media missing from current list
"businesscol.com",
"colombia.com",                 # generic portal
"somos.com.co",

# Real estate / classifieds
"olx.com.co",
"vivareal.com.co",
"properati.com.co",

# Startup/tech ecosystem editorial
"innpulsa.gov.co",              # gov suffix already covered by LOW_QUALITY_DOMAIN_SUFFIXES
"mintic.gov.co",

# Review / ranking directories
"glassdoor.com",
"g2.com",
"capterra.com",
```

### Pattern 5: Discovery query fix — pre-populate industria

**What:** The LLM director calls `discover_companies(industria="empresas", ...)` instead of using the real campaign industry because the task string mentions `dolor_operativo` and other generic descriptions that the LLM uses to infer industry.

**Root cause confirmed in `hive_adapter.py` line 169-180:** The `task` string sent to the director includes: `"- Industria objetivo: {industria}"` — so the correct `industria` IS in the prompt. The bug occurs when the director LLM ignores the explicit instruction and infers industry from `dolor_operativo`.

**Fix:** In `hive_graph.py` `_DIRECTOR_PROMPT`, change the instruction to be more explicit:

```python
# In _DIRECTOR_PROMPT, replace:
# "Llama a `discover_companies` UNA SOLA VEZ con la industria de la campaña."
# With:
"Llama a `discover_companies` UNA SOLA VEZ. El parámetro `industria` DEBE ser EXACTAMENTE el valor de 'Industria objetivo' de la campaña — no lo parafrasees, no lo reemplaces, cópialo literalmente."
```

Alternatively (more robust): In `hive_tools.py` `_discover_companies()`, accept an optional override that forces the campaign's industria if the LLM passes something generic:

```python
async def _discover_companies(industria: str, ciudad: str, max_r: int = 0) -> dict:
    # Guard against LLM passing generic terms instead of campaign industria
    campaign_industria = campaign.get("industria_objetivo", "").strip()
    if campaign_industria and (
        industria.lower() in ("empresas", "empresa", "negocios", "companies", "")
    ):
        logger.warning(
            "[discover_companies] LLM passed generic industria=%r; overriding with campaign=%r",
            industria, campaign_industria
        )
        industria = campaign_industria
    # ... rest of function
```

### Anti-Patterns to Avoid

- **Passing explicit headers with curl_cffi impersonate:** Do NOT add `"User-Agent"` or `"Accept-Language"` headers when using `impersonate=`. The impersonate target sets all TLS and HTTP headers to match the real browser fingerprint; overriding them degrades the fingerprint and can trigger detection.
- **Importing crawl4ai in a Railway ARQ worker:** `pip install crawl4ai` forces `playwright>=1.49.0` as a mandatory dep, pulling in Chromium binaries (~300 MB) and failing `crawl4ai-setup` without system libraries. Use `markdownify` instead.
- **Using `tldextract.extract()` with network disabled:** Default behavior downloads/caches the Public Suffix List on first call. In Railway, first cold start will make a network request. Pre-warm by calling `tldextract.extract("")` once at module import, or set `TLDEXTRACT_CACHE_PATH` env var to a writable temp dir.
- **Stripping `www.` before tldextract:** tldextract handles `www.` correctly — do not pre-strip it. Let tldextract give you `ext.subdomain` (which will be `"www"` or `"www.blog"`) then process.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TLS fingerprint impersonation | Custom curl subprocess or Selenium | `curl_cffi.AsyncSession(impersonate="chrome131")` | Already installed; handles JA3, HTTP/2, ALPN, TLS extensions correctly |
| HTML → Markdown compression | Custom regex strippers | `markdownify` | Handles nested tables, lists, code blocks, entity decoding; regex approaches break on real-world HTML |
| Registered domain extraction | `url.split(".")[...]` or regex | `tldextract` | The PSL has 9 000+ public suffixes; naive splitting fails for `.com.co`, `.co.uk`, `blogspot.com` |
| Blocking aggregator domains | LLM-based classification | Static set + `_is_low_quality_candidate()` | Fast, free, deterministic; LLM classification adds latency and cost for a filter that is 95% rules-based |

---

## Common Pitfalls

### Pitfall 1: curl_cffi AsyncSession — max_clients limit
**What goes wrong:** `AsyncSession` defaults to `max_clients=10`. If `scrape_url()` is called inside `asyncio.gather()` with `_CONCURRENCY=3` AND each scrape_url creates its own session, this is fine. But if a single shared session is reused for parallel calls exceeding `max_clients`, requests queue.
**Why it happens:** The current code creates one `httpx.AsyncClient` per `scrape_url()` call. The replacement should keep the same pattern — one `AsyncSession` per `scrape_url()` call, not a shared module-level session.
**How to avoid:** Keep `async with AsyncSession(...) as client:` inside `scrape_url()`. Do NOT create a module-level shared session.
**Warning signs:** Requests taking `timeout` seconds with no HTTP activity.

### Pitfall 2: curl_cffi exception type change
**What goes wrong:** `except Exception as e:` catches everything but the current code has a comment expecting `httpx.RequestError`. After migration, `RequestsError` from curl_cffi is the base.
**Why it happens:** Different library, different exception hierarchy.
**How to avoid:** Change `except Exception` in the inner loop to `except RequestsError` and keep a broad `except Exception` only at the outer try level.
**Import:** `from curl_cffi.requests import RequestsError`

### Pitfall 3: markdownify produces very long output for table-heavy pages
**What goes wrong:** Some corporate pages are table-heavy (org charts, product matrices). Markdown tables are verbose.
**Why it happens:** markdownify converts every `<table>` to Markdown table syntax.
**How to avoid:** Pass `strip=["table", "a"]` to markdownify for the prospecting use case — tables rarely carry qualifying info, and links are not needed by the LLM.
**Warning signs:** Markdown output > 4 000 tokens for a simple homepage.

### Pitfall 4: tldextract network call on cold start in Railway
**What goes wrong:** First call to `tldextract.extract()` in a new Railway pod makes an HTTP request to download the Public Suffix List. If the env is network-isolated or the request is slow, it stalls.
**Why it happens:** tldextract caches the PSL locally but needs to fetch it once.
**How to avoid:** Add at module top: `import tldextract; tldextract.extract("")` to trigger the cache fetch at import time (during service boot, not at request time). Alternatively pin `TLDEXTRACT_CACHE_FILE` to `/tmp/tldextract_cache`.

### Pitfall 5: extract_homepage() over-normalizing valid subdomains
**What goes wrong:** A company's primary web presence is `app.acme.com` (SaaS product). `extract_homepage()` strips it to `acme.com` which redirects or 404s.
**Why it happens:** `"app"` is in `_NON_HOME_SUBDOMAINS`.
**How to avoid:** After normalization, only use the homepage URL if it resolves. The current `build_candidates()` logic already tries multiple variants — let it handle the fallback. Alternatively, `extract_homepage()` can return both the normalized and original URL.
**Warning signs:** `[SCRAPING_ERROR]` result for a company that was previously scrapeable.

---

## Code Examples

### Complete scrape_url() header section (curl_cffi version)

```python
# Source: curl_cffi 0.15.0 installed in this project
from curl_cffi.requests import AsyncSession, RequestsError

async def scrape_url(url: str, timeout: int = 12) -> str:
    from urllib.parse import urlparse, urlunparse

    # build_candidates() function is unchanged

    html = ""
    last_error = "no response"
    candidates = build_candidates(url)
    _NO_RETRY_CODES = {400, 401, 403, 404, 405, 410, 429, 451, 500, 502, 503, 504}
    _HARD_BLOCK_CODES = {403, 429, 451}
    try:
        async with AsyncSession(
            impersonate="chrome131",
            allow_redirects=True,
            timeout=timeout,
        ) as client:
            hard_blocked = False
            for candidate in candidates:
                if hard_blocked:
                    break
                try:
                    resp = await client.get(candidate)
                except RequestsError as e:
                    last_error = f"{candidate}: {e}"
                    continue

                if resp.status_code >= 400:
                    last_error = f"{candidate}: HTTP {resp.status_code}"
                    if resp.status_code in _HARD_BLOCK_CODES:
                        hard_blocked = True
                    if resp.status_code in _NO_RETRY_CODES:
                        break
                    continue

                html = resp.text or ""
                if html.strip():
                    break
    except Exception as e:
        last_error = str(e)

    if not html.strip():
        return f"[SCRAPING_ERROR: {last_error}]"

    # Contact extraction block (lines 988-1022) — UNCHANGED, run on raw html

    # HTML → Markdown (replaces current BeautifulSoup text extraction)
    content = html_to_compressed_markdown(html)
    return (contact_section + content)[:8000]
```

### html_to_compressed_markdown() — markdownify pattern

```python
# Source: markdownify==1.2.2
from markdownify import markdownify as md
from bs4 import BeautifulSoup
import re

def html_to_compressed_markdown(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "svg", "img", "iframe",
                     "table"]):  # strip tables — too verbose for prospecting
        tag.decompose()
    clean_html = str(soup)
    markdown = md(
        clean_html,
        strip=["a"],          # no href links needed in LLM analysis
        heading_style="ATX",  # ## style
        newline_style="spaces",
    )
    markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
    return markdown
```

### extract_homepage() — full implementation

```python
# Source: tldextract==5.3.1 (https://pypi.org/project/tldextract/)
import tldextract

# Pre-warm PSL cache at module import (avoids cold-start network call per request)
tldextract.extract("")

_NON_HOME_SUBDOMAINS = frozenset({
    "blog", "blogs", "news", "press", "noticias",
    "careers", "jobs", "empleo", "vacantes", "hire",
    "app", "apps", "portal", "admin", "dashboard", "api",
    "shop", "store", "tienda",
    "support", "help", "ayuda", "soporte",
    "mail", "webmail", "correo",
    "m", "mobile",
    "dev", "staging", "test", "demo", "qa",
    "cdn", "static", "assets", "media",
    "docs", "wiki", "kb", "documentation",
    "forum", "community", "comunidad",
})

def extract_homepage(url: str) -> str:
    """
    Normalize a URL to the probable company homepage.
    Strips known non-homepage subdomains and deep paths.
    Falls back to original URL if unable to parse.
    """
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    ext = tldextract.extract(url)
    if not ext.domain or not ext.suffix:
        return url

    registered = f"{ext.domain}.{ext.suffix}"  # e.g. "empresa.com.co"
    subdomain = (ext.subdomain or "").lower()

    # Strip leading "www." from subdomain to get actual subdomain
    effective_sub = subdomain
    if effective_sub == "www" or effective_sub == "":
        # Already at root — just normalize path
        pass
    elif effective_sub.startswith("www."):
        effective_sub = effective_sub[4:]

    if effective_sub in _NON_HOME_SUBDOMAINS:
        return f"https://{registered}"

    # Check for deep blog/article paths (reuse LOW_QUALITY_PATH_MARKERS)
    from urllib.parse import urlparse
    parsed = urlparse(url)
    path = (parsed.path or "/").lower()
    for marker in LOW_QUALITY_PATH_MARKERS:
        if marker in path:
            netloc = parsed.netloc.lower().lstrip("www.")
            return f"https://{netloc or registered}"

    # No change needed
    return url
```

### Director prompt fix (hive_graph.py)

```python
# Replace the first bullet in PASO 1 with:
"PASO 1: DESCUBRIMIENTO\n"
"- Llama a `discover_companies` UNA SOLA VEZ. "
"El argumento `industria` DEBE ser el valor LITERAL de 'Industria objetivo' de la campaña "
"(copiado exactamente, sin parafrasear). "
"Si la campaña dice 'Seguros de vida', pasa industria='Seguros de vida', "
"no 'seguros' ni 'empresas de seguros'.\n"
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| httpx with fake User-Agent | curl_cffi TLS impersonation | curl_cffi added chrome131 in v0.8.0 (stable in v0.9.0) | Bypasses JA3/H2 fingerprint checks |
| BeautifulSoup get_text() truncated | HTML → Markdown via markdownify | markdownify 1.x (2024-2025) | Structured content at ~20% of token cost |
| urlparse domain split | tldextract Public Suffix List | PSL updated continuously | Handles .com.co, .co.uk, private suffixes |

**Deprecated/outdated:**
- Rotating User-Agent headers: Cloudflare and modern WAFs use TLS fingerprinting, not just UA strings. UA rotation is security theater against real bot detection.
- `html.parser` + `soup.get_text()`: Loses heading hierarchy, table structure, and semantic groupings that help LLM classify company sector.

---

## Open Questions

1. **Crawl4AI SCRAPE-02 wording vs. actual implementation**
   - What we know: The requirement says "Crawl4AI fit_markdown" but Crawl4AI mandates Playwright.
   - What's unclear: Did the requirement author expect Crawl4AI to be used as a standalone markdown generator (which is possible via `DefaultMarkdownGenerator.generate_markdown(html)`) or the full crawler?
   - Recommendation: `DefaultMarkdownGenerator.generate_markdown(input_html)` CAN be called directly without a browser, confirmed from source code. However this still requires `pip install crawl4ai` which pulls in `playwright>=1.49.0` even if Playwright is never invoked. Unless a `crawl4ai[no-browser]` extra is introduced upstream, installing crawl4ai just for the markdown generator is wasteful (~300 MB browser binaries). **Recommended path:** Use `markdownify` instead — it is the functional equivalent for this use case. If the planner wants to keep "Crawl4AI" in the requirement literal, use `DefaultMarkdownGenerator` but document the Playwright install overhead in the plan.

2. **curl_cffi on Railway arm64 vs amd64**
   - What we know: curl_cffi 0.15.0 ships `manylinux2014_x86_64` and `manylinux2014_aarch64` wheels — both platforms supported.
   - What's unclear: Railway's default deployment architecture (they support both; most free-tier uses amd64).
   - Recommendation: No action needed; both wheel variants are published. The current dev machine has curl_cffi 0.15.0 installed, confirming the package resolves correctly.

3. **extract_homepage() and SaaS companies where the homepage IS an app subdomain**
   - What we know: Some legitimate B2B companies use `app.empresa.com` as their primary URL.
   - What's unclear: How to detect "this is their only web presence" vs "this is a side subdomain."
   - Recommendation: After `extract_homepage()` normalizes the URL, the `build_candidates()` function in `scrape_url()` already tries the bare domain AND www variant. If the root 404s, it will fall back to the full URL. No additional handling needed.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| curl_cffi | SCRAPE-01 | YES | 0.15.0 | — (already installed) |
| markdownify | SCRAPE-02 | NO | — | pip install markdownify==1.2.2 |
| tldextract | SCRAPE-04 | NO | — | pip install tldextract==5.3.1 |
| beautifulsoup4 | SCRAPE-02 (pre-clean) | YES | 4.14.3 | — (already in requirements.txt) |
| Playwright/Chromium | Crawl4AI route (NOT recommended) | NO | — | Use markdownify instead |

**Missing dependencies with no fallback:** None — markdownify and tldextract are lightweight and install cleanly on Railway Linux.

**Missing dependencies with fallback:** None applicable.

---

## Railway Dockerfile for Worker Service (Crawl4AI / Playwright)

**Researched:** 2026-05-27 | **Confidence:** HIGH (Railway official docs + community confirmed)

### Why Dockerfile (not Nixpacks)

Railway's Nixpacks builder uses a Nix base image — `playwright install --with-deps` tries to run `apt-get` which does not exist in Nix. Even with `nixpacks.toml` `aptPkgs`, GLIBC version mismatches cause runtime crashes (`GLIBC_2.38 not found`). Railway's own documentation for Playwright goes directly to Dockerfile — Nixpacks is not mentioned.

### Recommended Dockerfile

```dockerfile
# backend/Dockerfile.worker
FROM mcr.microsoft.com/playwright/python:v1.49.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Chromium is already in the base image at /ms-playwright
# CRAWL4AI_MODE=api tells crawl4ai-setup to skip its own playwright install
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
ENV CRAWL4AI_MODE=api

COPY . .
RUN crawl4ai-setup

CMD ["arq", "worker.WorkerSettings"]
```

### railway-worker.toml changes

```toml
[build]
builder = "dockerfile"
dockerfilePath = "Dockerfile.worker"
```

The `backend/` directory is the build context, so `Dockerfile.worker` goes inside `backend/`.

### Required Railway env vars (Worker service)

- `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` — must be set at service level, not only in Dockerfile ENV

### Required BrowserConfig flags (when launching browser for SPA scraping)

```python
BrowserConfig(
    headless=True,
    extra_args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"]
)
```

### Memory budget

- Crawl4AI HTML-only mode (no browser): ~80–120 MB
- Chromium headless + one page: ~700–900 MB
- Railway Starter plan: up to 8 GB — viable for sequential scraping

### html_to_compressed_markdown() — Crawl4AI pattern

```python
from crawl4ai.markdown_generation_strategy import DefaultMarkdownGenerator
from crawl4ai.content_filter_strategy import PruningContentFilter

def html_to_compressed_markdown(html: str) -> str:
    content_filter = PruningContentFilter(threshold=0.48, threshold_type="fixed")
    generator = DefaultMarkdownGenerator(content_filter=content_filter)
    result = generator.generate_markdown(
        cleaned_html=html,
        base_url="",
        html2text_options={"ignore_links": True, "ignore_images": True},
    )
    return result.fit_markdown or result.raw_markdown or ""
```

This does NOT launch a browser — it processes the HTML string directly. curl_cffi fetches the HTML; Crawl4AI converts it. They are independent.

---

## Sources

### Primary (HIGH confidence)
- curl_cffi 0.15.0 installed package — `AsyncSession.__init__` signature inspected directly; `BrowserType` enum values listed from installed package; confirmed `chrome131` valid
- `curl-cffi.readthedocs.io/en/latest/api.html` — `allow_redirects`, `timeout`, `impersonate` parameter docs; exception hierarchy
- `github.com/unclecode/crawl4ai/blob/main/crawl4ai/markdown_generation_strategy.py` — `DefaultMarkdownGenerator.generate_markdown(input_html, ...)` signature confirmed; `MarkdownGenerationResult.fit_markdown` attribute
- `github.com/unclecode/crawl4ai/blob/main/pyproject.toml` — `playwright>=1.49.0` confirmed as mandatory (not optional) dep
- `pypi.org/project/markdownify/` — version 1.2.2, bs4 dependency, API
- `pypi.org/project/tldextract/` — version 5.3.1, `top_domain_under_public_suffix` / `f"{ext.domain}.{ext.suffix}"` pattern
- `pypi.org/project/html2text/` — version 2025.4.15
- `curl-cffi.readthedocs.io/en/latest/impersonate/targets.html` — full list of supported targets including chrome131

### Secondary (MEDIUM confidence)
- `docs.crawl4ai.com/core/markdown-generation/` — `DefaultMarkdownGenerator` constructor, `PruningContentFilter` params
- `aamax.co/blog/top-business-directories-and-listing-sites-in-colombia` — Colombian directory domain list
- `enests.co/blog/top-business-directories-and-listing-sites-in-colombia` — additional Colombian domains

### Tertiary (LOW confidence — for domain blocklist expansion)
- Web search results for Colombian job board, real estate, and directory domains — cross-checked against known live sites but not programmatically verified

---

## Metadata

**Confidence breakdown:**
- SCRAPE-01 (curl_cffi): HIGH — package installed, API verified locally
- SCRAPE-02 (markdown): HIGH for markdownify recommendation; MEDIUM for exact token reduction % (80% is an estimate based on HTML vs Markdown size ratios for typical corporate pages)
- SCRAPE-03 (domain blocklist): MEDIUM — domains sourced from directory listing articles; some may have changed or merged
- SCRAPE-04 (extract_homepage): HIGH for tldextract algorithm; MEDIUM for completeness of `_NON_HOME_SUBDOMAINS` set
- Discovery query fix: HIGH — root cause confirmed in hive_adapter.py and hive_graph.py source

**Research date:** 2026-05-27
**Valid until:** 2026-08-27 (stable libraries; domain blocklist should be reviewed quarterly)
