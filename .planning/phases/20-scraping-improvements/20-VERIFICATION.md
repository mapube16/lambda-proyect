---
phase: 20-scraping-improvements
verified: 2026-05-28T00:00:00Z
status: gaps_found
score: 7/8 must-haves verified
gaps:
  - truth: "railway-worker.toml points to the correct Dockerfile path"
    status: failed
    reason: "railway-worker.toml at repo root specifies dockerfilePath = \"Dockerfile.worker\" but the file lives at backend/Dockerfile.worker. Railway resolves paths from the repo root, so the build would fail to find the Dockerfile."
    artifacts:
      - path: "railway-worker.toml"
        issue: "dockerfilePath = \"Dockerfile.worker\" should be \"backend/Dockerfile.worker\""
    missing:
      - "Either move Dockerfile.worker to the repo root, OR change railway-worker.toml to dockerfilePath = \"backend/Dockerfile.worker\""
---

# Phase 20: Scraping Improvements Verification Report

**Phase Goal:** Replace httpx with curl_cffi Chrome131 TLS impersonation in scrape_url(), compress scraped HTML to Markdown via Crawl4AI DefaultMarkdownGenerator + PruningContentFilter before LLM analysis, add Dockerfile.worker for Railway Worker service, expand LOW_QUALITY_DISCOVERY_DOMAINS with Colombian aggregators, add extract_homepage() normalization via tldextract, and fix the LLM director discovery query bug.
**Verified:** 2026-05-28T00:00:00Z
**Status:** gaps_found
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth                                                                              | Status     | Evidence                                                                                                        |
|----|------------------------------------------------------------------------------------|------------|-----------------------------------------------------------------------------------------------------------------|
| 1  | scrape_url() uses AsyncSession(impersonate="chrome131"), not httpx.AsyncClient      | VERIFIED   | Line 1070-1074: `async with AsyncSession(impersonate="chrome131", ...)` in scrape_url(); httpx preserved for other functions |
| 2  | html_to_compressed_markdown() defined with DefaultMarkdownGenerator+PruningContentFilter and called in scrape_url() | VERIFIED   | Lines 222-253: function defined; line 1141: `content = html_to_compressed_markdown(html)` replaces soup.get_text() |
| 3  | LOW_QUALITY_DISCOVERY_DOMAINS expanded with >= 10 new Colombian/LATAM domains      | VERIFIED   | 33 new entries added (lines 119-149), clearly commented "added Phase 20"                                        |
| 4  | extract_homepage() defined using tldextract and called in discover_via_serper()    | VERIFIED   | Lines 256-304: function defined with tldextract.extract(); line 421: `url = extract_homepage(url)` in discover_via_serper() |
| 5  | _DIRECTOR_PROMPT contains literal-copy instruction for industria parameter         | VERIFIED   | Line 43: "El argumento `industria` DEBE ser el valor LITERAL de 'Industria objetivo' de la campaña — cópialo exactamente" |
| 6  | hive_tools.py has _GENERIC_INDUSTRIA_TERMS guard in _discover_companies()          | VERIFIED   | Lines 165-175: `_GENERIC_INDUSTRIA_TERMS = frozenset({...})` guard overrides generic industry terms with campaign value |
| 7  | backend/Dockerfile.worker exists and uses playwright base image with CRAWL4AI_MODE=api | VERIFIED   | File confirmed: `FROM mcr.microsoft.com/playwright/python:v1.49.0-noble`, `ENV CRAWL4AI_MODE=api`              |
| 8  | railway-worker.toml has dockerfilePath = "Dockerfile.worker" pointing to actual file | FAILED     | railway-worker.toml at repo root has `dockerfilePath = "Dockerfile.worker"` but Dockerfile.worker is at `backend/Dockerfile.worker`; no root-level Dockerfile.worker exists |

**Score:** 7/8 truths verified

---

### Required Artifacts

| Artifact                             | Expected                                    | Status   | Details                                                                   |
|--------------------------------------|---------------------------------------------|----------|---------------------------------------------------------------------------|
| `backend/prospector.py`              | curl_cffi AsyncSession in scrape_url()      | VERIFIED | AsyncSession(impersonate="chrome131") at line 1070; import curl_cffi line 17 |
| `backend/prospector.py`              | html_to_compressed_markdown() defined       | VERIFIED | Lines 222-253, imports DefaultMarkdownGenerator + PruningContentFilter    |
| `backend/prospector.py`              | extract_homepage() using tldextract         | VERIFIED | Lines 256-304; tldextract imported at line 21                             |
| `backend/prospector.py`              | LOW_QUALITY_DISCOVERY_DOMAINS expanded      | VERIFIED | 33 new Phase 20 entries across 5 comment-tagged blocks                    |
| `backend/hive_graph.py`              | _DIRECTOR_PROMPT literal-copy instruction   | VERIFIED | Line 43 contains explicit "cópialo exactamente" instruction               |
| `backend/hive_tools.py`              | _GENERIC_INDUSTRIA_TERMS guard              | VERIFIED | Lines 165-175                                                             |
| `backend/Dockerfile.worker`          | Playwright base image + CRAWL4AI_MODE=api   | VERIFIED | All required env vars and base image confirmed                             |
| `railway-worker.toml`                | dockerfilePath pointing to correct path     | FAILED   | Points to "Dockerfile.worker" at root; actual file is at "backend/Dockerfile.worker" |
| `backend/requirements.txt`           | crawl4ai, tldextract, curl_cffi present     | VERIFIED | curl_cffi==0.15.0 (line 28), crawl4ai>=0.4.21 (line 29), tldextract==5.3.1 (line 30) |

---

### Key Link Verification

| From                                | To                               | Via                                              | Status   | Details                                                        |
|-------------------------------------|----------------------------------|--------------------------------------------------|----------|----------------------------------------------------------------|
| `scrape_url()`                      | `AsyncSession(chrome131)`        | curl_cffi import + context manager               | WIRED    | Import at line 17; used exclusively in scrape_url() block      |
| `scrape_url()`                      | `html_to_compressed_markdown()`  | Direct call at line 1141                         | WIRED    | `content = html_to_compressed_markdown(html)` replaces soup.get_text() |
| `discover_via_serper()`             | `extract_homepage()`             | Direct call at line 421                          | WIRED    | `url = extract_homepage(url)` applied to each organic result   |
| `hive_graph._DIRECTOR_PROMPT`       | literal-copy industria rule      | Inline prompt text                               | WIRED    | Rule present and explicit in the prompt                        |
| `hive_tools._discover_companies()`  | `_GENERIC_INDUSTRIA_TERMS` guard | Lines 165-175                                    | WIRED    | Guard fires before calling prospector.discover_companies()     |
| `railway-worker.toml`               | `backend/Dockerfile.worker`      | dockerfilePath directive                         | NOT_WIRED | Path "Dockerfile.worker" does not resolve to "backend/Dockerfile.worker" at repo root |

---

### Data-Flow Trace (Level 4)

Not applicable — this phase delivers utility functions (scraping, filtering) rather than new UI components that render dynamic data. The data flow is: scrape_url() -> html_to_compressed_markdown() -> LLM analysis, which is a synchronous transformation pipeline, not a render layer.

---

### Behavioral Spot-Checks

| Behavior                                         | Check                                                          | Result                                                          | Status |
|--------------------------------------------------|----------------------------------------------------------------|-----------------------------------------------------------------|--------|
| `html_to_compressed_markdown` is importable      | Module-level import chain in prospector.py                     | crawl4ai in requirements.txt; lazy import inside function       | PASS   |
| `extract_homepage` strips non-home subdomain     | Logic trace: tldextract + _NON_HOME_SUBDOMAINS check           | Function strips blog., careers., etc. subdomains correctly      | PASS   |
| `_GENERIC_INDUSTRIA_TERMS` guard overrides "empresas" | Logic trace: frozenset includes "empresas","empresa","negocios" | Override fires when LLM passes generic term; campaign value used | PASS   |
| `Dockerfile.worker` base image has playwright    | File contents verified                                         | mcr.microsoft.com/playwright/python:v1.49.0-noble confirmed     | PASS   |
| railway-worker.toml path resolves at repo root   | Checked for Dockerfile.worker at repo root                     | File not found at root; only at backend/Dockerfile.worker       | FAIL   |

---

### Requirements Coverage

| Requirement | Description                                                                 | Status    | Evidence                                                              |
|-------------|-----------------------------------------------------------------------------|-----------|-----------------------------------------------------------------------|
| SCRAPE-01   | curl_cffi Chrome131 TLS impersonation in scrape_url()                       | SATISFIED | AsyncSession(impersonate="chrome131") lines 1070-1074; httpx preserved for Maps/Serper |
| SCRAPE-02   | html_to_compressed_markdown() with crawl4ai; called in scrape_url()         | SATISFIED | Function defined lines 222-253; called line 1141                      |
| SCRAPE-03   | LOW_QUALITY_DISCOVERY_DOMAINS expanded with 10+ Colombian/LATAM domains     | SATISFIED | 33 new domains added with Phase 20 comments                           |
| SCRAPE-04   | extract_homepage() via tldextract called in discover_via_serper()           | SATISFIED | Function defined lines 256-304; called line 421                       |

---

### Anti-Patterns Found

| File                      | Line | Pattern                                        | Severity | Impact                                              |
|---------------------------|------|------------------------------------------------|----------|-----------------------------------------------------|
| `railway-worker.toml`     | 3    | `dockerfilePath = "Dockerfile.worker"` (wrong path) | Blocker  | Railway build would fail to find Dockerfile.worker at repo root |

No stub/placeholder anti-patterns found in the implementation code. The crawl4ai import is lazily loaded inside `html_to_compressed_markdown()` with a proper bs4 fallback — this is intentional defensive design, not a stub.

---

### Human Verification Required

None — all phase deliverables are verifiable through static code analysis. The railway-worker.toml path mismatch is a concrete file path issue, not a behavior requiring runtime observation.

---

### Gaps Summary

Phase 20 achieves 7 of 8 must-haves. All core technical features are correctly implemented and wired:

- curl_cffi AsyncSession with chrome131 impersonation is live in scrape_url()
- crawl4ai DefaultMarkdownGenerator + PruningContentFilter is wired and called
- 33 new Colombian/LATAM low-quality domains have been added
- extract_homepage() is defined and called in the Serper discovery loop
- The LLM director prompt explicitly instructs literal-copy of the industria parameter
- The _GENERIC_INDUSTRIA_TERMS guard in hive_tools.py is a defense-in-depth fix
- Dockerfile.worker exists with the correct Playwright base image and CRAWL4AI_MODE=api
- All three new dependencies (curl_cffi, crawl4ai, tldextract) are in requirements.txt

**Single blocker:** `railway-worker.toml` specifies `dockerfilePath = "Dockerfile.worker"` but the Dockerfile lives at `backend/Dockerfile.worker`. Railway resolves paths from the repository root, so the Worker service build would fail on Railway. The fix is one line: change the path to `"backend/Dockerfile.worker"`.

---

_Verified: 2026-05-28T00:00:00Z_
_Verifier: Claude (gsd-verifier)_
