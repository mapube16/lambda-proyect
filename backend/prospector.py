"""
prospector.py — B2B prospecting engine.

Pipeline:
  1. Buscador    — finds company URLs via Google Maps Places API (fallback: DuckDuckGo)
  2. Scraper     — fetches + cleans each page (parallel, max 3 concurrent)
  3. Analista B2B — runs the mega-prompt (personalidad.md)
  4. Motor de Scoring + Redactor — embedded in LLM output

Results are broadcast via WebSocket as they arrive.
"""
import os
import re
import asyncio
import logging
import httpx
from pathlib import Path
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS          # new package name
except ImportError:
    from duckduckgo_search import DDGS  # legacy fallback
from models import AgentRole, AgentState

logger = logging.getLogger(__name__)

# Load personalidad.md once at module level
_PERSONALIDAD_PATH = Path(__file__).parent.parent / "personalidad.md"
_SYSTEM_PROMPT_TEMPLATE = _PERSONALIDAD_PATH.read_text(encoding="utf-8")

DEFAULT_CAMPAIGN = {
    "nombre_remitente": "Maximiliano Pulido",
    "empresa_remitente": "Isomorph",
    "sector_propio_cliente": "",
    "industria_objetivo": "Logística y Transporte",
    "ciudad_objetivo": "Bogotá",
    "dolor_operativo": "gestión manual de rutas y despachos",
    "solucion_ofrecida": "automatización de operaciones logísticas con IA",
    "software_clave": "SAP, Excel, WhatsApp Business, TMS",
    "jerarquia_decisores": "Gerente General > Director de Operaciones > Jefe de Logística",
    "identidad_remitente": "Consultor de automatización B2B",
}

PIPELINE_AGENTS = [
    {"name": "Buscador",         "role": AgentRole.RESEARCHER},
    {"name": "Scraper",          "role": AgentRole.PLANNER},
    {"name": "Analista B2B",     "role": AgentRole.REVIEWER},
    {"name": "Redactor",         "role": AgentRole.WRITER},
]

# Max concurrent scrape+analyze tasks
_CONCURRENCY = 3

BLOCKED_DOMAINS = {
    "facebook.com", "instagram.com", "twitter.com", "x.com", "linkedin.com",
    "youtube.com", "wikipedia.org", "elempleo.com", "computrabajo.com",
    "reddit.com", "tripadvisor", "yelp.com", "google.com", "maps.google",
    "bing.com", "web.archive.org",
}

LOW_QUALITY_DISCOVERY_DOMAINS = {
    # Delivery / food
    "rappi.com", "ubereats.com", "restaurantguru.com", "carta.menu",
    # Directories / classifieds
    "paginasamarillas.com.co", "consultaamarillas.com", "yellowpages.ar",
    "tiendeo.com.co", "nexdu.com", "polomap.com",
    "infoisinfo.com.co", "latinoplaces.com", "co.latinoplaces.com",
    "empresite.eleconomistaamerica.co", "eleconomistaamerica.co",
    "enviotodo.com.co",
    "kompass.com", "merco.info", "encolombia.com", "hospitales.com.co",
    "enfermera.io", "clinica-web.com.ar",
    # Real estate portals / classifieds (not prospectable companies)
    "fincaraiz.com.co", "estrenarvivienda.com", "metrocuadrado.com",
    "vivienda.com.co", "finca-raiz.com.co", "habi.co",
    # Agency/vendor ranking directories (not prospectable companies)
    "clutch.co", "sortlist.com", "goodfirms.co", "designrush.com",
    "agenciasdemarketingdigital.com", "linkatomic.com",
    # Jobs
    "opcionempleo.com.co", "elempleo.com", "computrabajo.com",
    "saludjobs.com", "bumeran.com.co", "indeed.com",
    "empleocalihoy.com",
    # News / media (not companies)
    "elpais.com.co", "eltiempo.com", "semana.com", "portafolio.co",
    "dinero.com", "larepublica.co", "altonivel.com.mx",
    "monserratenoticias.co", "segurilatam.com",
    # Tourism / city guides
    "discoverbogota.city", "colombia.travel", "minube.com",
    # Low-signal misc
    "imigra.net", "wokiapp.com", "archivoespana.com",
    "colombiaguide.co", "fincasturisticasdelquindio.com", "tiktok.com",
    # Editorial / media / blogs about startups
    "socialgeek.co", "nicoramos.co", "entorno.vc", "lastopdelatam.com",
    "cidei.net", "tusdatos.co", "tiendanube.com",
    # Ecosystem orgs (not prospectable companies)
    "investinbogota.org", "ccb.org.co", "apps.co",
    # Medical/health job boards and directories
    "medicosdoc.com", "saludcolombia.com", "clinicasyhospitales.com.co",
    # Job boards
    "jooble.org", "mifuturoempleo.co",
    # Blogs / low-signal
    "blogspot.com", "blogger.com",
    # Health system portals
    "epsenlinea.com.co",
    # Foreign hospital groups / directories (not Colombian)
    "grupohla.com", "hcbhospitales.com", "achpm.es",
    # Foreign/non-Colombian B2B directories
    "adventuresincre.com",
    # Detected in live scan
    "pinterest.com", "ar.pinterest.com",      # social/ideas board
    "correosexpress.es",                       # Spanish courier, not Colombian
    "ccl.com.co",                              # Cámara Colombiana de la Logística (gremio, no empresa)
}

LOW_QUALITY_DOMAIN_SUFFIXES = (
    ".gov.co", ".gov", ".edu.co", ".edu", ".org.co",
)

# Subdomains or paths that indicate a portal/service, not a company homepage
LOW_QUALITY_SUBDOMAINS = (
    "virtual.", "banca.", "banking.", "app.", "portal.",
)

LOW_QUALITY_PATH_MARKERS = (
    # Generic noise
    "/restaurantes", "/restaurant", "/delivery", "/directorio", "/empleo",
    "/discover", "/noticias/", "/catalogo", "/tiendas/", "/metro/", "/phone-",
    # Blog / article paths
    "/blog/", "/blog-detalle/", "/articulo", "/articulos/", "/post/", "/posts/",
    "/emprendimiento/", "/informe-", "/ranking-", "/casos-de-exito",
    "/trabajo/", "/busqueda/", "/directorio-empresas/",
    "/oferta-de-empleo/", "/trabajo-empresas-", "/empleos/", "/vacantes/",
    # "Top N" list articles
    "/las-", "/los-", "/top-", "/mejores-", "/best-",
    # Startup ecosystem editorial
    "/startups-", "/startup-", "/ecosistema-",
    # Vendor directories
    "/agencias/", "/agencies/", "/marketing-online/", "/supply-chain-management/",
    "/logistics/supply", "/co/logistics",
)


def _is_low_quality_candidate(url: str, title: str = "") -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = (parsed.path or "").lower()
    title_l = (title or "").lower()

    if any(host == d or host.endswith("." + d) for d in LOW_QUALITY_DISCOVERY_DOMAINS):
        return True
    if any(host.endswith(s) for s in LOW_QUALITY_DOMAIN_SUFFIXES):
        return True
    if any(host.startswith(sub) for sub in LOW_QUALITY_SUBDOMAINS):
        return True
    if any(marker in path for marker in LOW_QUALITY_PATH_MARKERS):
        return True
    if any(token in title_l for token in (
        "páginas amarillas", "consulta amarillas", "top restaurantes", "trabajo", "ofertas de empleo",
        "delivery", "domicilio", "directorio", "listado", "mejores restaurantes",
        "las mejores", "los mejores", "top 10", "top 5", "más prometedoras",
        "informe top", "ecosistema startup", "mejores startups",
    )):
        return True
    return False


# ── Discovery: Google Maps Places API ────────────────────────────────────────

async def _gmaps_place_details(
    client: httpx.AsyncClient, place_id: str, place_data: dict, api_key: str
) -> dict:
    """Fetch website + phone from old Place Details API for a single place_id."""
    try:
        resp = await client.get(
            "https://maps.googleapis.com/maps/api/place/details/json",
            params={
                "place_id": place_id,
                "fields": "name,website,formatted_phone_number,formatted_address",
                "language": "es",
                "key": api_key,
            },
        )
        result = resp.json().get("result", {})
        return {
            "title": result.get("name") or place_data.get("name", ""),
            "url": result.get("website", "").rstrip("/"),
            "phone": result.get("formatted_phone_number", ""),
            "address": result.get("formatted_address") or place_data.get("formatted_address", ""),
            "rating": place_data.get("rating"),
            "source": "google_maps",
        }
    except Exception:
        return {}


async def discover_companies_gmaps(
    industria: str, ciudad: str, max_results: int, api_key: str
) -> list[dict]:
    """
    Use Google Maps Places Text Search (legacy API) + Place Details to find real businesses.
    Returns list of {title, url, phone, address, rating}.
    """
    results = []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://maps.googleapis.com/maps/api/place/textsearch/json",
                params={
                    "query": f"{industria} en {ciudad}",
                    "language": "es",
                    "region": "co",
                    "key": api_key,
                },
            )
            data = resp.json()
            api_status = data.get("status", "ERROR")
            places = data.get("results", [])
            logger.info("[Google Maps] status=%d api_status=%s places=%d", resp.status_code, api_status, len(places))

            if resp.status_code != 200 or api_status not in ("OK", "ZERO_RESULTS"):
                return results

            # Fetch details in parallel (website + phone per place)
            detail_tasks = [
                _gmaps_place_details(client, p["place_id"], p, api_key)
                for p in places[:min(max_results, 20)]
                if p.get("place_id")
            ]
            details = await asyncio.gather(*detail_tasks, return_exceptions=True)
            for detail in details:
                if not isinstance(detail, dict):
                    continue
                url = detail.get("url", "")
                if not url:
                    continue
                if any(b in url.lower() for b in BLOCKED_DOMAINS):
                    continue
                results.append(detail)
    except Exception as e:
        logger.warning("[Google Maps error] %s", e)

    return results


# ── Discovery: Bing web search ────────────────────────────────────────────────

async def discover_companies_bing(
    industria: str, ciudad: str, max_results: int
) -> list[dict]:
    """
    Scrape Bing search results to find company websites.
    Uses 3 different query strategies in parallel for wider coverage.
    """
    queries = [
        f'empresas {industria} {ciudad} sitio web contacto',
        f'"{industria}" "{ciudad}" cotizar servicios empresa',
        f'{industria} {ciudad} "quienes somos" OR "nuestros servicios"',
    ]

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "es-CO,es;q=0.9",
        "Accept": "text/html,application/xhtml+xml",
    }

    seen_domains: set[str] = set()
    results: list[dict] = []

    async def search_query(q: str) -> list[dict]:
        found = []
        try:
            async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
                resp = await client.get("https://www.bing.com/search", params={"q": q, "count": "20", "setlang": "es"})
                if resp.status_code != 200:
                    logger.warning("[Bing] status=%d for query=%r", resp.status_code, q)
                    return found
                soup = BeautifulSoup(resp.text, "html.parser")
                # Try multiple selectors — Bing changes class names regularly
                candidates = (
                    soup.select("li.b_algo")
                    or soup.select("#b_results > li")
                    or soup.select(".b_algo")
                )
                if not candidates:
                    logger.warning("[Bing] 0 candidates — page snippet: %s", resp.text[:300].replace('\n', ' '))
                else:
                    logger.info("[Bing] query=%r status=%d candidates=%d", q, resp.status_code, len(candidates))
                for li in candidates:
                    a = li.select_one("h2 a") or li.select_one("a[href^='http']")
                    if not a:
                        continue
                    href = a.get("href", "")
                    if not href.startswith("http"):
                        continue
                    if any(b in href.lower() for b in BLOCKED_DOMAINS):
                        continue
                    from urllib.parse import urlparse
                    domain = urlparse(href).netloc.replace("www.", "")
                    if domain in seen_domains:
                        continue
                    seen_domains.add(domain)
                    title = a.get_text(strip=True)
                    found.append({
                        "title": title,
                        "url": href.split("?")[0],
                        "phone": "",
                        "address": "",
                        "rating": None,
                        "source": "bing",
                    })
        except Exception as e:
            logger.warning("[Bing error] %s", e)
        return found

    # Run 3 queries in parallel
    all_batches = await asyncio.gather(*[search_query(q) for q in queries])
    for batch in all_batches:
        for item in batch:
            if len(results) >= max_results:
                break
            results.append(item)
        if len(results) >= max_results:
            break

    return results


# ── Discovery: DuckDuckGo fallback ────────────────────────────────────────────

def _discover_ddg_multi(industria: str, ciudad: str, max_results: int) -> list[dict]:
    """3 sequential DDG queries for wider coverage."""
    queries = [
        f'{industria} {ciudad} empresa web oficial',
        f'empresa "{industria}" en {ciudad} contacto',
        f'"{industria}" "{ciudad}" servicios corporativos',
    ]
    seen: set[str] = set()
    results = []
    _log = logging.getLogger(__name__)
    _log.info("[DDG] Starting discovery: industria=%r ciudad=%r max=%d", industria, ciudad, max_results)
    try:
        ddgs = DDGS()
        for query in queries:
            try:
                hits = list(ddgs.text(query, max_results=max_results))
                _log.info("[DDG] query=%r → %d hits", query, len(hits))
            except Exception as qe:
                _log.warning("[DDG] query=%r failed: %s", query, qe)
                continue
            for r in hits:
                url = r.get("href", "") or r.get("url", "")
                if not url or not url.startswith("http"):
                    continue
                if any(b in url.lower() for b in BLOCKED_DOMAINS):
                    continue
                from urllib.parse import urlparse
                domain = urlparse(url).netloc.replace("www.", "")
                if domain in seen:
                    continue
                seen.add(domain)
                results.append({
                    "title": r.get("title", ""),
                    "url": url,
                    "phone": "",
                    "address": "",
                    "rating": None,
                    "source": "duckduckgo",
                })
                if len(results) >= max_results:
                    _log.info("[DDG] Reached max_results=%d", max_results)
                    return results
    except Exception as e:
        _log.warning("[DDG] Fatal error: %s", e)
    _log.info("[DDG] Total results: %d", len(results))
    return results


async def discover_companies(
    industria: str,
    ciudad: str,
    max_results: int,
    gmaps_key: str = "",
    excluded_domains: set[str] | None = None,
    use_secop: bool = False,
) -> list[dict]:
    """
    Multi-source discovery:
    1. Google Maps (local businesses with contact info)
    2. Bing web search (companies with web presence)
    3. SECOP II (Colombian government contractors) — optional, enabled via use_secop=True
    4. DuckDuckGo (fallback)
    Deduplicates by domain and merges up to max_results.
    """
    from urllib.parse import urlparse

    seen_domains: set[str] = set()
    excluded_domains = {d.lower().strip() for d in (excluded_domains or set()) if d}
    merged: list[dict] = []
    skipped_history = 0
    skipped_low_quality = 0

    def add(items: list[dict]):
        nonlocal skipped_history, skipped_low_quality
        for item in items:
            if len(merged) >= max_results:
                return
            domain = urlparse(item["url"]).netloc.replace("www.", "")
            if not domain:
                continue
            if _is_low_quality_candidate(item.get("url", ""), item.get("title", "")):
                skipped_low_quality += 1
                continue
            if domain in excluded_domains:
                skipped_history += 1
                continue
            if domain and domain not in seen_domains:
                seen_domains.add(domain)
                merged.append(item)

    def add_secop(items: list[dict]):
        """Add SECOP companies (may not have URLs yet — kept as-is for URL resolution step)."""
        nonlocal skipped_history
        seen_nits: set[str] = set()
        for item in items:
            if len(merged) >= max_results:
                return
            nit = item.get("nit", "")
            if nit in seen_nits:
                continue
            seen_nits.add(nit)
            merged.append(item)

    loop = asyncio.get_event_loop()
    per_source = max(10, max_results // 2)

    # Run Bing + DDG in parallel from the start (DDG is more reliable than Bing in 2026)
    bing_task = discover_companies_bing(industria, ciudad, per_source)
    ddg_task = loop.run_in_executor(None, _discover_ddg_multi, industria, ciudad, per_source)

    extra_tasks = [bing_task, ddg_task]
    if gmaps_key:
        extra_tasks.append(discover_companies_gmaps(industria, ciudad, per_source, gmaps_key))

    results_list = await asyncio.gather(*extra_tasks, return_exceptions=True)

    bing_results = results_list[0] if isinstance(results_list[0], list) else []
    ddg_results = results_list[1] if isinstance(results_list[1], list) else []
    gmaps_results = results_list[2] if (gmaps_key and len(results_list) > 2 and isinstance(results_list[2], list)) else []

    # Prefer Google Maps (has phone/address), then Bing, then DDG
    add(gmaps_results)
    add(bing_results)
    add(ddg_results)

    logger.info(
        "[Discovery] GMaps=%d Bing=%d DDG=%d → %d únicos (saltados_historial=%d, saltados_baja_calidad=%d)",
        len(gmaps_results), len(bing_results), len(ddg_results), len(merged), skipped_history, skipped_low_quality
    )

    # SECOP source: government contractors
    if use_secop and len(merged) < max_results:
        from secop import discover_companies_secop, resolve_secop_urls
        secop_needed = max_results - len(merged)
        secop_raw = await discover_companies_secop(industria, ciudad, secop_needed * 2)
        secop_resolved = await resolve_secop_urls(secop_raw, max_concurrent=3)
        add_secop(secop_resolved[:secop_needed])
        logger.info("[Discovery] SECOP: %d raw → %d resueltas → %d total", len(secop_raw), len(secop_resolved), len(merged))

    # If still under target, run a second DDG pass with more queries
    if len(merged) < max_results:
        missing = max_results - len(merged)
        ddg_extra = await loop.run_in_executor(None, _discover_ddg_multi, industria, ciudad, missing * 3)
        add(ddg_extra)
        logger.info("[Discovery] DDG refill: +%d raw → %d final", len(ddg_extra), len(merged))

    return merged


# ── Scraping ──────────────────────────────────────────────────────────────────

async def scrape_url(url: str, timeout: int = 12) -> str:
    from urllib.parse import urlparse, urlunparse

    ua_profiles = [
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/123.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) "
                "Gecko/20100101 Firefox/124.0"
            ),
            "Accept-Language": "es-419,es;q=0.9,en;q=0.8",
        },
        {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
            ),
            "Accept-Language": "es-ES,es;q=0.9,en;q=0.7",
        },
    ]

    def build_candidates(raw_url: str) -> list[str]:
        value = (raw_url or "").strip()
        if not value:
            return []
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"

        parsed = urlparse(value)
        host = parsed.netloc
        if not host:
            return [value]

        host_variants = [host]
        bare_host = host[4:] if host.startswith("www.") else host
        if bare_host not in host_variants:
            host_variants.append(bare_host)
        www_host = f"www.{bare_host}"
        if www_host not in host_variants:
            host_variants.append(www_host)

        schemes = [parsed.scheme or "https", "https", "http"]
        path_variants = [parsed.path or "/"]
        if (parsed.path or "/") != "/":
            path_variants.append("/")

        candidates: list[str] = []
        for scheme in schemes:
            for h in host_variants:
                for p in path_variants:
                    candidate = urlunparse((scheme, h, p, "", "", ""))
                    if candidate not in candidates:
                        candidates.append(candidate)
        return candidates

    html = ""
    last_error = "no response"
    candidates = build_candidates(url)
    # Status codes where retrying with a different User-Agent is pointless
    _NO_RETRY_CODES = {400, 401, 403, 404, 405, 410, 429, 451, 500, 502, 503, 504}
    # Status codes that mean the whole domain is blocked — skip remaining candidates too
    _HARD_BLOCK_CODES = {403, 429, 451}
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            hard_blocked = False
            for candidate in candidates:
                if hard_blocked:
                    break
                for headers in ua_profiles:
                    try:
                        resp = await client.get(candidate, headers=headers)
                    except Exception as e:
                        last_error = f"{candidate}: {e}"
                        continue

                    if resp.status_code >= 400:
                        last_error = f"{candidate}: HTTP {resp.status_code}"
                        if resp.status_code in _HARD_BLOCK_CODES:
                            hard_blocked = True
                        if resp.status_code in _NO_RETRY_CODES:
                            break  # don't try other UA profiles for this candidate
                        continue

                    html = resp.text or ""
                    if html.strip():
                        break
                if html.strip():
                    break
    except Exception as e:
        last_error = str(e)

    if not html.strip():
        return f"[SCRAPING_ERROR: {last_error}]"

    soup = BeautifulSoup(html, "html.parser")

    # ── Extract contact signals from raw HTML before stripping ────────────────
    contact_emails: list[str] = []
    contact_phones: list[str] = []

    # mailto: links
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("mailto:"):
            email = href[7:].split("?")[0].strip()
            if email and email not in contact_emails:
                contact_emails.append(email)
        elif href.startswith("tel:"):
            phone = re.sub(r"[^\d+]", "", href[4:])
            if len(phone) >= 7 and phone not in contact_phones:
                contact_phones.append(phone)

    # Regex scan of full HTML for emails and Colombian phones
    html_emails = re.findall(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}", html)
    for e in html_emails:
        if e not in contact_emails and not e.endswith((".png", ".jpg", ".gif", ".css", ".js")):
            contact_emails.append(e)
    html_phones = re.findall(r"(?:\+57[\s\-]?)?(?:3\d{2}[\s\-]?\d{3}[\s\-]?\d{4}|[1-9]\d{6,7})", html)
    for p in html_phones:
        cleaned = re.sub(r"[\s\-]", "", p)
        if len(cleaned) >= 7 and cleaned not in contact_phones:
            contact_phones.append(cleaned)

    contact_section = ""
    if contact_emails or contact_phones:
        parts = []
        if contact_emails:
            parts.append("Emails encontrados: " + ", ".join(contact_emails[:5]))
        if contact_phones:
            parts.append("Teléfonos encontrados: " + ", ".join(contact_phones[:5]))
        contact_section = "[CONTACTOS]\n" + "\n".join(parts) + "\n\n"
    # ──────────────────────────────────────────────────────────────────────────

    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "svg", "img"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return (contact_section + text)[:8000]


# ── Prompt building ───────────────────────────────────────────────────────────

_CONTENT_FOOTER = """

=======================================================================
EMPRESA A ANALIZAR: {{input_empresa_url}}
CONTENIDO DEL SITIO WEB:
{{contenido_scrapeado}}
=======================================================================

⚠ PARÁMETROS ACTIVOS DE CAMPAÑA (tienen prioridad sobre cualquier criterio anterior):
- Industria objetivo: {{industria_objetivo}} → es_sector_correcto=true SOLO si la empresa opera en esta industria o equivalente cercano
- Sector propio del cliente (excluir): {{sector_propio_cliente}} → es_competidor_directo=true si la empresa VENDE este tipo de producto/servicio como negocio principal; false si lo USA como herramienta
- Ciudad objetivo: {{ciudad_objetivo}}

Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código ni texto adicional:
{
  "analisis_previo": "1-2 líneas sobre a qué se dedica la empresa",
  "nombre_empresa": "nombre extraído o null",
  "es_sector_correcto": true,
  "razon_sector": "por qué encaja o no en {{industria_objetivo}}",
  "es_competidor_directo": false,
  "tamano_estimado": "micro|pequeña|mediana|grande|desconocido",
  "sintomas_de_dolor": true,
  "evidencia_dolor": "indicador concreto o null",
  "decisor": {"nombre": null, "cargo": null, "email": null},
  "en_ciudad_objetivo": true,
  "datos_extra": null
}"""


def _build_prompt(url: str, scraped: str, campaign: dict, override_template: str = "") -> str:
    variables = {**DEFAULT_CAMPAIGN, **campaign,
                 "input_empresa_url": url,
                 "contenido_scrapeado": scraped}
    if override_template.strip():
        # If the custom template doesn't include the content placeholder, append a standard footer
        template = override_template
        if "{{contenido_scrapeado}}" not in template:
            template = template + _CONTENT_FOOTER
    else:
        template = _SYSTEM_PROMPT_TEMPLATE
    for key, value in variables.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


# ── Agent prompts ─────────────────────────────────────────────────────────────

def _analista_prompt(url: str, scraped: str, c: dict) -> str:
    sector_propio = c.get("sector_propio_cliente", "").strip()
    competitor_context = (
        f"\n- Nuestro sector (NO PROSPECTAR — son competidores): {sector_propio}"
        f"\n  REGLA CRÍTICA: La pregunta clave es ¿esta empresa VENDE el mismo tipo de producto/servicio que nosotros, compitiendo por los mismos clientes? Si sí → es_competidor_directo=true. Si la empresa es un CLIENTE POTENCIAL que usa o necesita nuestros servicios → no es competidor. Busca señales en el contenido aunque no usen exactamente las mismas palabras (ej: si nuestro sector es 'seguros' y la empresa es corredora de pólizas → competidor; si nuestro sector es 'desarrollo de software' y la empresa vende plataformas SaaS → competidor)."
        if sector_propio else ""
    )
    competitor_field = (
        f'\n  "es_competidor_directo": true si la empresa VENDE (como negocio principal) el mismo tipo de producto/servicio que "{sector_propio}", compitiendo por los mismos clientes; poner también es_sector_correcto=false. false si la empresa es un cliente potencial que usa/necesita nuestros servicios,'
        if sector_propio else ""
    )
    return f"""Eres un analista Senior de inteligencia comercial B2B para el mercado colombiano. \
Tu único objetivo es determinar si una empresa es un prospecto calificado y, si lo es, extraer los datos necesarios para iniciar contacto comercial.

═══════════════════════════════════════
PERFIL DE LA CAMPAÑA
═══════════════════════════════════════
- Industria Objetivo: {c.get('industria_objetivo')}
  INTERPRETA CON AMPLITUD — acepta sinónimos, sub-nichos y modelos de negocio equivalentes.
  Ej: si buscamos "clínicas", un centro odontológico, IPS o centro de medicina estética es válido.
  Si buscamos "logística", una transportadora, operador 3PL, agencia de carga o empresa de última milla es válida.{competitor_context}
- Dolor que resolvemos: {c.get('dolor_operativo')}
- Nuestra Solución: {c.get('solucion_ofrecida')}
- Señales de presupuesto / tech: {c.get('software_clave')} o equivalentes
- Decisores clave a buscar: {c.get('jerarquia_decisores')}
- Ciudad / Región objetivo: {c.get('ciudad_objetivo')}

═══════════════════════════════════════
REGLAS DE EXTRACCIÓN
═══════════════════════════════════════
1. NO INVENTES DATOS. Nombre, email y cargo deben estar explícitamente en el texto — si no están, null.
2. El dolor rara vez se menciona explícitamente. Busca SÍNTOMAS: menciones de procesos manuales, crecimiento acelerado sin tecnología, quejas implícitas, escala que implica el problema.
3. El scraping puede estar incompleto o cortado — haz tu mejor esfuerzo con lo disponible.

CONTENIDO INSUFICIENTE: Si el scraping tiene < 200 palabras útiles o es solo menú de navegación sin contexto de negocio → tamano_estimado="desconocido", sintomas_de_dolor=false, razon_sector="contenido insuficiente para determinar".

CALIBRACIÓN DE TAMAÑO (Colombia):
- micro: emprendimiento, negocio familiar, freelancer, solo WhatsApp como contacto, sin sedes mencionadas
- pequeña: <50 empleados, una sede, estructura comercial básica
- mediana: 50-200 empleados, varias sedes o cobertura regional, usa software como Siigo/World Office/sectorial
- grande: >200 empleados, cobertura nacional/internacional, menciona SAP/Oracle/tecnología enterprise o gran infraestructura

GEOGRAFÍA: en_ciudad_objetivo=true si la empresa OPERA en la región objetivo, aunque su sede principal esté en otra ciudad. false si la empresa es claramente de otro país (Argentina, España, México) sin operaciones en Colombia.

CALIBRACIÓN DE DOLOR (sintomas_de_dolor):
- true CON evidencia real: menciona proceso manual, problema específico, busca solución, tiene escala que implica el dolor
- true SIN evidencia directa: tamaño y sector indican que probablemente sufre el dolor, aunque no lo mencione
- false: empresa demasiado pequeña, sector incorrecto, o contenido insuficiente para inferir

═══════════════════════════════════════
EMPRESA A ANALIZAR: {url}
CONTENIDO DEL SITIO WEB:
{scraped[:6000]}
═══════════════════════════════════════

Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código, sin markdown y sin texto adicional:
{{
  "analisis_previo": "2-3 líneas: a qué se dedica la empresa, escala estimada, y si hay señales del dolor que resolvemos",
  "nombre_empresa": "nombre real extraído, o null",
  "es_sector_correcto": true,
  "razon_sector": "por qué encaja en la industria objetivo — o por qué no",{competitor_field}
  "tech_stack": ["software detectado"] o null,
  "tamano_estimado": "micro|pequeña|mediana|grande|desconocido",
  "razon_tamano": "evidencia concreta: 'menciona 3 sedes', '50+ empleados en equipo', 'cobertura nacional' — o null",
  "sintomas_de_dolor": true,
  "evidencia_dolor": "cita o paráfrasis del indicador que sugiere el dolor — o null si no hay",
  "decisor": {{
    "nombre": "nombre real extraído o null",
    "cargo": "cargo exacto extraído o null",
    "email": "email encontrado o null",
    "telefono": "teléfono del decisor extraído del sitio o null"
  }},
  "nit": "NIT de la empresa si aparece en el sitio, sin puntos ni guion verificacion, o null",
  "en_ciudad_objetivo": true,
  "datos_extra": "sedes adicionales, años en el mercado, clientes mencionados, certificaciones — o null"
}}"""

def _motor_scoring_prompt(analysis: dict, c: dict) -> str:
    import json as _json
    nombre = c.get('nombre_remitente', '')
    empresa = c.get('empresa_remitente', '')
    return f"""Eres el Motor de Scoring y Redactor Comercial B2B para el mercado colombiano. \
Recibes el análisis de una empresa y debes:
1. Calcular el score de calificación con criterio comercial real
2. Si aprueba, redactar un correo de prospección que la persona realmente abra y responda

═══════════════════════════════════════
SCORING (máx 100 pts)
═══════════════════════════════════════
- Sector válido:          +20 si es_sector_correcto = true
- Tensión operativa:      +30 con evidencia concreta de dolor | +15 si es probable por escala
- Escala y presupuesto:   +30 grande/mediana con tech stack | +20 mediana sin tech | +0 micro o pequeña sin señales
- Poder de decisión:      +10 email nominal de decisor | +5 email genérico | +0 sin contacto
- Bono geográfico:        +10 si en_ciudad_objetivo = true

VETOS AUTOMÁTICOS (en orden de prioridad — no calcules score si aplica):
- es_competidor_directo = true  → KILL_DIRECT_COMPETITOR
- tamano = "micro"              → MICRO_BUSINESS_LOW_BUDGET
- es_sector_correcto = false    → WRONG_SECTOR_OR_NO_DATA
- Score < 60                    → LOW_SCORE_QUALIFICATION

═══════════════════════════════════════
CONTEXTO DE CAMPAÑA
═══════════════════════════════════════
- Vendemos: {c.get('solucion_ofrecida')}
- A quién: {c.get('industria_objetivo')} en {c.get('ciudad_objetivo')}
- El dolor: {c.get('dolor_operativo')}
- Firmante: {nombre} de {empresa}

ANÁLISIS DEL ANALISTA B2B:
{_json.dumps(analysis, ensure_ascii=False, indent=2)}

═══════════════════════════════════════
INSTRUCCIONES DE CORREO (solo si aprueba el scoring)
═══════════════════════════════════════
OPENER — Empieza con UNA observación específica sobre LA EMPRESA, no sobre ti.
  PROHIBIDO comenzar con: "Espero que estés bien", "Mi nombre es", "Le escribo para presentarme",
  "Quisiera presentarte", "Soy X de Y", "Me permito contactarte", "Hola, soy".
  CORRECTO: "Vi que [empresa] maneja X rutas de distribución / tiene Y sedes / trabaja con Z clientes..."
  Conecta la observación con una CONSECUENCIA de negocio concreta: "eso usualmente implica...", "lo que significa que..."

PÁRRAFO 2 — El dolor específico que genera ESA situación. En términos de plata, tiempo perdido o riesgo operativo. Nada abstracto.

PÁRRAFO 3 — Cómo lo resolvemos (1 oración máximo, sin jerga: nada de "sinergias", "potenciar", "soluciones integrales", "ecosistema").

CIERRE — Una sola pregunta corta y sin presión. Propón una conversación de 15 min en la que tú llevas algo útil, no solo "quiero presentarme".
  Ejemplo bueno: "¿Tiene sentido hablar 15 min esta semana para mostrarte cómo lo estamos haciendo con [empresa-similar]?"
  Ejemplo malo: "¿Estarías dispuesto a considerar una reunión para explorar posibles sinergias?"

ASUNTO — Específico, no genérico. El receptor debe entender de qué trata sin abrir el correo.
  PROHIBIDO: "Una idea para [empresa]", "Oportunidad de mejora", "Optimización de procesos".
  CORRECTO: "X rutas manuales → eso tiene un costo escondido", "[empresa]: cómo [cliente-similar] redujo el tiempo de despacho 40%"

REGLAS GENERALES:
- Tono: directo, conversacional, como alguien que sabe del tema — no corporativo, no robótico
- Longitud: 4 párrafos cortos. Sin saludo largo. Sin firma corporativa extendida.
- Firma: {nombre} / {empresa}
- Si hay nombre del decisor en el análisis, úsalo en el saludo de apertura
═══════════════════════════════════════

Si RECHAZADO → responde SOLO con este JSON exacto:
{{"system_state": "REJECTED_BY_AI", "empresa": "nombre", "score": 0, "motivo_descalificacion": "CODIGO", "evidencia_encontrada": "frase corta específica", "resumen_empresa": "a qué se dedica en 1 línea"}}

Si APROBADO → responde SOLO con este JSON exacto:
{{"system_state": "SUCCESS_READY_FOR_REVIEW", "empresa": "nombre", "score": 85, "es_visitable_zona_objetivo": true, "decisor": {{"nombre": "nombre o null", "cargo": "cargo", "email": "email o null", "telefono": "telefono del decisor extraído o null"}}, "datos_tecnicos": {{"tech_stack": "software detectado o null", "perfil": "A_REZAGO o B_FRICCION"}}, "borradores": {{"email_asuntos": ["Asunto directo y específico 1", "Asunto alternativo 2"], "email_cuerpo": "Correo completo. Usa \\n\\n entre párrafos."}}}}

SOLO JSON. Cero texto antes o después."""


def _parse_json_safe(raw: str) -> dict | None:
    import json as _json
    raw = raw.strip()
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        return _json.loads(raw)
    except Exception:
        try:
            start = raw.index("{")
            end = raw.rindex("}") + 1
            return _json.loads(raw[start:end])
        except Exception:
            return None


def _normalize_openai_model_name(model_name: str, fallback: str = "gpt-5.4-2026-03-05") -> str:
    value = str(model_name or "").strip()
    if not value:
        return fallback
    if value.startswith("openai/"):
        return value.split("/", 1)[1]
    if value.startswith("openrouter/"):
        candidate = value.split("/", 1)[1]
        if candidate.startswith("gpt-"):
            return candidate
        return fallback
    if value.startswith(("anthropic/", "google/", "meta/")):
        return fallback
    return value


def _first_text(*values) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def _enrich_rejection_payload(result_json: dict, analysis: dict, company: dict) -> dict:
    reason_labels = {
        "MICRO_BUSINESS_LOW_BUDGET": "Empresa demasiado pequeña o con baja señal de presupuesto",
        "LOW_SCORE_QUALIFICATION": "No alcanzó el puntaje mínimo de calificación",
        "WRONG_SECTOR_OR_NO_DATA": "No coincide con la industria objetivo o no hay datos suficientes",
        "SCRAPING_BLOCKED": "No fue posible acceder al sitio web para evaluarlo",
        "KILL_DIRECT_COMPETITOR": "Parece ser competidor directo",
        "KILL_INFORMAL_BUSINESS": "Negocio informal o sin señales B2B confiables",
        "NO_B2B_PROFILE": "No se detectó un perfil B2B claro",
        "KILL_TOO_SMALL": "Tamaño insuficiente para el perfil objetivo",
        "NO_CLEAR_OPERATIONAL_PAIN": "No se detectó dolor operativo relevante",
        "NO_DECISION_MAKER_CONTACT": "No se encontró contacto de decisor",
        "PARSE_ERROR": "La respuesta del motor no fue parseable y se descartó por seguridad",
    }

    reason_code = _first_text(
        result_json.get("motivo_descalificacion"),
        result_json.get("motivo"),
    )

    if not reason_code:
        if analysis.get("es_sector_correcto") is False:
            reason_code = "WRONG_SECTOR_OR_NO_DATA"
        elif str(analysis.get("tamano_estimado") or "").strip().lower() == "micro":
            reason_code = "MICRO_BUSINESS_LOW_BUDGET"
        elif not bool(analysis.get("sintomas_de_dolor")):
            reason_code = "NO_CLEAR_OPERATIONAL_PAIN"
        elif not _first_text((analysis.get("decisor") or {}).get("email")):
            reason_code = "NO_DECISION_MAKER_CONTACT"
        else:
            reason_code = "LOW_SCORE_QUALIFICATION"

    evidence = _first_text(
        result_json.get("evidencia_encontrada"),
        result_json.get("evidencia"),
        analysis.get("razon_sector"),
        analysis.get("razon_tamano"),
        analysis.get("evidencia_dolor"),
        analysis.get("analisis_previo"),
        result_json.get("detalle"),
    )

    if not evidence:
        company_name = _first_text(result_json.get("empresa"), analysis.get("nombre_empresa"), company.get("title"))
        evidence = f"{company_name}: no se encontraron señales suficientes para justificar contacto comercial."

    reason_text = reason_labels.get(reason_code, reason_code)

    result_json["motivo_descalificacion"] = reason_code
    result_json["motivo_descalificacion_texto"] = reason_text
    result_json["evidencia_encontrada"] = evidence
    result_json["resumen_empresa"] = _first_text(
        result_json.get("resumen_empresa"),
        analysis.get("analisis_previo"),
        analysis.get("datos_extra"),
        f"{_first_text(analysis.get('nombre_empresa'), company.get('title'))}: perfil detectado con información limitada.",
    )
    result_json["tamano_estimado"] = _first_text(
        result_json.get("tamano_estimado"),
        analysis.get("tamano_estimado"),
    )
    result_json["senal_dolor"] = _first_text(
        result_json.get("senal_dolor"),
        analysis.get("evidencia_dolor"),
    )
    result_json.setdefault("score", 0)
    result_json.setdefault("empresa", _first_text(analysis.get("nombre_empresa"), company.get("title")))
    return result_json


# ── Multi-agent analysis pipeline ─────────────────────────────────────────────

async def analyze_company(
    company: dict,
    campaign: dict,
    client: AsyncOpenAI,
    on_stage: callable = None,   # async callback(stage: str, status: str)
    personality_prompt: str = "",  # client-specific analyst prompt (from Queen onboarding)
) -> dict:
    """
    3-stage multi-agent pipeline per company:
      Stage 1 (Scraper)      — fetch + clean HTML
      Stage 2 (Analista B2B) — LLM analyzes company profile
      Stage 3 (Motor/Redactor) — LLM scores + writes email
    """
    url = company["url"]
    base = {
        "url": url,
        "title": company["title"],
        "phone": company.get("phone", ""),
        "address": company.get("address", ""),
        "rating": company.get("rating"),
    }
    merged = {**DEFAULT_CAMPAIGN, **campaign}

    async def stage(name: str, status: str):
        if on_stage:
            await on_stage(name, status)

    # ── Stage 1: Scraper ──────────────────────────────────────────────────────
    secop_context = company.get("secop_context", "")
    is_secop = company.get("source") == "secop"
    is_secop_fallback_url = company.get("url_is_secop_fallback", False)

    if is_secop and is_secop_fallback_url:
        # No real URL found — use SECOP data as the scraped content directly
        await stage("scraper", f"✓ Datos SECOP — {company['title'][:30]}")
        scraped = secop_context
    else:
        await stage("scraper", f"Scrapeando {company['title'][:35]}...")
        scraped = await scrape_url(url)
        if scraped.startswith("[SCRAPING_ERROR"):
            if secop_context:
                # SECOP companies can fall back to their government data
                await stage("scraper", f"✓ Fallback SECOP — {company['title'][:30]}")
                scraped = secop_context
            else:
                await stage("scraper", f"✗ Acceso bloqueado: {company['title'][:30]}")
                reason = scraped.replace("[SCRAPING_ERROR:", "").rstrip("]").strip()
                rejected_json = {
                    "system_state": "REJECTED_BY_AI",
                    "empresa": company.get("title", ""),
                    "score": 0,
                    "motivo_descalificacion": "SCRAPING_BLOCKED",
                    "motivo_descalificacion_texto": "No fue posible acceder al sitio web para evaluar esta empresa",
                    "evidencia_encontrada": reason or "El sitio devolvió error al intentar extraer contenido",
                    "resumen_empresa": f"{company.get('title', '')}: se detectó como posible candidato, pero no se pudo obtener contenido verificable del sitio.",
                    "fuentes_consultadas": [url],
                }
                return {**base, "status": "rejected", "markdown": None, "json_payload": rejected_json}
        # Prepend SECOP context if available (enriches analyst even when URL scraped OK)
        if secop_context:
            scraped = f"{secop_context}\n\n---\n\nContenido web:\n{scraped}"

    await stage("scraper", f"✓ {len(scraped)} chars — {company['title'][:30]}")

    # ── Stage 2: Analista B2B ─────────────────────────────────────────────────
    await stage("analista", f"Analizando perfil: {company['title'][:30]}...")
    analista_model = _normalize_openai_model_name(merged.get("llm_analista", ""), "gpt-5.4-2026-03-05")
    if personality_prompt and personality_prompt.strip():
        # Use client-specific analyst prompt from Queen onboarding
        analista_content = _build_prompt(url, scraped, merged, override_template=personality_prompt)
    else:
        analista_content = _analista_prompt(url, scraped, merged)
    try:
        r1 = await client.chat.completions.create(
            model=analista_model,
            messages=[{"role": "user", "content": analista_content}],
            temperature=0.15,
            extra_body={"max_completion_tokens": 1200},
        )
        analysis = _parse_json_safe(r1.choices[0].message.content or "")
        if not analysis:
            analysis = {"es_sector_correcto": False, "tamano": "micro",
                        "razon_sector": "Error al parsear análisis"}
    except Exception as e:
        return {**base, "status": "error", "error": str(e)}

    nombre = analysis.get("nombre_empresa") or company["title"]
    match = "✓ sector OK" if analysis.get("es_sector_correcto") else "✗ sector incorrecto"
    await stage("analista", f"{match} — {nombre[:30]}")

    # ── Stage 3: Motor de Scoring + Redactor ──────────────────────────────────
    await stage("redactor", f"Evaluando y calificando: {nombre[:30]}...")
    redactor_model = _normalize_openai_model_name(merged.get("llm_redactor", ""), "gpt-5.4-2026-03-05")
    try:
        r2 = await client.chat.completions.create(
            model=redactor_model,
            messages=[{"role": "user", "content": _motor_scoring_prompt(analysis, merged)}],
            temperature=0.15,
            extra_body={"max_completion_tokens": 1200},
        )
        result_json = _parse_json_safe(r2.choices[0].message.content or "")
        if not result_json:
            result_json = {"system_state": "REJECTED_BY_AI", "empresa": nombre,
                           "motivo_descalificacion": "PARSE_ERROR",
                           "evidencia_encontrada": "No se pudo parsear la respuesta del motor"}
    except Exception as e:
        return {**base, "status": "error", "error": str(e)}

    is_approved = result_json.get("system_state") == "SUCCESS_READY_FOR_REVIEW"
    if not is_approved:
        result_json = _enrich_rejection_payload(result_json, analysis, company)
    result_json.setdefault("fuentes_consultadas", [url])
    score = result_json.get("score", 0) if is_approved else 0
    status_label = f"✓ Aprobado {score}pts — {nombre[:25]}" if is_approved else f"✗ Descartado — {nombre[:25]}"
    await stage("redactor", status_label)

    if is_approved:
        return {**base, "status": "success", "markdown": None, "json_payload": result_json}
    else:
        return {**base, "status": "rejected", "markdown": None, "json_payload": result_json}


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_prospect(
    campaign: dict,
    openai_api_key: str,
    max_results: int = 20,
    orchestrator=None,
    send_to_user=None,
    user_id: str = None,
    run_id: str = None,
    save_lead: callable = None,
) -> dict:
    client = AsyncOpenAI(api_key=openai_api_key)
    gmaps_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    merged = {**DEFAULT_CAMPAIGN, **campaign}

    async def ws(msg: dict):
        if send_to_user and user_id:
            await send_to_user(user_id, msg)

    async def notify(agent_id: str, state: AgentState, tool: str = None, status: str = None):
        if orchestrator:
            await orchestrator.update_agent_state(agent_id, state, tool, status)

    # ── Spawn visual agents ───────────────────────────────────────────────────
    agent_ids = []
    if orchestrator:
        for spec in PIPELINE_AGENTS:
            agent = await orchestrator.create_agent(spec["name"], spec["role"])
            agent_ids.append(agent.id)
            await ws({"type": "agent_created", "agent": {
                "id": agent.id, "name": agent.name, "role": agent.role.value,
                "state": "idle", "current_tool": None, "tool_status": None,
                "palette": agent.palette, "seat_id": None,
                "is_subagent": False, "parent_agent_id": None,
            }})
            await asyncio.sleep(0.25)

    buscador_id = agent_ids[0] if len(agent_ids) > 0 else "buscador"
    scraper_id  = agent_ids[1] if len(agent_ids) > 1 else "scraper"
    analista_id = agent_ids[2] if len(agent_ids) > 2 else "analista"
    redactor_id = agent_ids[3] if len(agent_ids) > 3 else "redactor"

    # ── Step 1: Discovery ─────────────────────────────────────────────────────
    source_label = "Google Maps" if gmaps_key else "DuckDuckGo"
    await notify(buscador_id, AgentState.THINKING, status="Diseñando búsqueda...")
    await asyncio.sleep(0.6)
    await notify(buscador_id, AgentState.TOOL_USE, tool="web_search",
                 status=f"{source_label}: {merged['industria_objetivo']} en {merged['ciudad_objetivo']}")

    companies = await discover_companies(
        merged["industria_objetivo"], merged["ciudad_objetivo"], max_results, gmaps_key,
        use_secop=bool(merged.get("use_secop", False)),
    )

    if not companies:
        await notify(buscador_id, AgentState.ERROR, status="No se encontraron empresas")
        _cleanup_agents(orchestrator, agent_ids)
        return {"status": "error", "error": "No se encontraron empresas"}

    await notify(buscador_id, AgentState.WAITING,
                 status=f"✓ {len(companies)} empresas vía {source_label}")
    await ws({
        "type": "discovery_complete",
        "count": len(companies),
        "source": source_label,
        "companies": [{"title": c["title"], "url": c["url"]} for c in companies],
    })
    await asyncio.sleep(0.4)

    # ── Step 2-4: Parallel analysis ───────────────────────────────────────────
    await notify(scraper_id, AgentState.THINKING,
                 status=f"Procesando {len(companies)} empresas ({_CONCURRENCY} en paralelo)...")
    await notify(analista_id, AgentState.THINKING, status="En espera...")

    semaphore = asyncio.Semaphore(_CONCURRENCY)
    results = []
    completed = 0

    async def process_one(i: int, company: dict):
        nonlocal completed
        async with semaphore:
            async def on_stage(stage: str, status: str):
                if stage == "scraper":
                    await notify(scraper_id, AgentState.TOOL_USE,
                                 tool="web_scrape", status=f"[{i+1}/{len(companies)}] {status}")
                elif stage == "analista":
                    await notify(analista_id, AgentState.TOOL_USE,
                                 tool="analyze", status=f"[{i+1}/{len(companies)}] {status}")
                elif stage == "redactor":
                    await notify(redactor_id, AgentState.TOOL_USE,
                                 tool="score_and_write", status=f"[{i+1}/{len(companies)}] {status}")

            result = await analyze_company(company, campaign, client, on_stage=on_stage)
            result["index"] = i
            result["total"] = len(companies)
            completed += 1

            # Silently drop — don't save or broadcast to the user
            motivo = (result.get("json_payload") or {}).get("motivo_descalificacion", "")
            if motivo in ("SCRAPING_BLOCKED", "KILL_DIRECT_COMPETITOR"):
                return result

            # Persist FIRST — include lead_id in WebSocket message
            if save_lead and run_id:
                json_payload = result.get("json_payload") or {}
                try:
                    lead_id = await save_lead(run_id, user_id, {
                        "company_name": company.get("title", ""),
                        "url": result.get("url", company.get("url", "")),
                        "phone": company.get("phone", ""),
                        "address": company.get("address", ""),
                        "score": json_payload.get("score_total") if json_payload else None,
                        "system_state": json_payload.get("system_state", "REJECTED_BY_AI") if json_payload else "ERROR",
                        "expediente_markdown": result.get("markdown"),
                        "expediente_json": json_payload,
                    })
                    result["lead_id"] = lead_id  # MongoDB _id — frontend uses this for HITL
                except Exception as _e:
                    logger.warning("[prospector] save_lead error: %s", _e)

            await ws({"type": "lead_result", **result})

            return result

    tasks = [process_one(i, c) for i, c in enumerate(companies)]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    for r in raw_results:
        if isinstance(r, dict):
            results.append(r)

    # ── Summary ───────────────────────────────────────────────────────────────
    approved = [r for r in results if r["status"] == "success"]
    rejected = [r for r in results if r["status"] == "rejected"]

    for aid in agent_ids:
        await notify(aid, AgentState.WAITING, status=f"✓ Campaña completa — {len(approved)} leads aprobados")

    await ws({
        "type": "campaign_complete",
        "total_analyzed": len(results),
        "total_approved": len(approved),
        "total_rejected": len(rejected),
        "source": source_label,
    })

    await asyncio.sleep(1.5)
    _cleanup_agents(orchestrator, agent_ids)

    return {
        "status": "complete",
        "total_analyzed": len(results),
        "total_approved": len(approved),
        "results": results,
    }


def _cleanup_agents(orchestrator, agent_ids: list):
    if not orchestrator:
        return
    for aid in agent_ids:
        if aid in orchestrator.agents:
            agent = orchestrator.agents[aid]
            agent.state = AgentState.IDLE
            agent.current_tool = None
            agent.tool_status = None
