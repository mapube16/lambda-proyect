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
import httpx
from pathlib import Path
from openai import AsyncOpenAI
from bs4 import BeautifulSoup
try:
    from ddgs import DDGS          # new package name
except ImportError:
    from duckduckgo_search import DDGS  # legacy fallback
from models import AgentRole, AgentState

# Load personalidad.md once at module level
_PERSONALIDAD_PATH = Path(__file__).parent.parent / "personalidad.md"
_SYSTEM_PROMPT_TEMPLATE = _PERSONALIDAD_PATH.read_text(encoding="utf-8")

DEFAULT_CAMPAIGN = {
    "nombre_remitente": "Maximiliano Pulido",
    "empresa_remitente": "Isomorph",
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
}

LOW_QUALITY_DISCOVERY_DOMAINS = {
    "rappi.com", "ubereats.com", "restaurantguru.com", "minube.com", "paginasamarillas.com.co",
    "consultaamarillas.com", "opcionempleo.com.co", "tiendeo.com.co", "tiktok.com",
    "yellowpages.ar", "carta.menu", "nexdu.com", "imigra.net", "wokiapp.com",
    "archivoespana.com", "colombiaguide.co", "polomap.com", "fincasturisticasdelquindio.com",
}

LOW_QUALITY_PATH_MARKERS = (
    "/restaurantes", "/restaurant", "/delivery", "/list", "/directorio", "/empleo",
    "/discover", "/noticias/", "/catalogo", "/tiendas/", "/metro/", "/phone-",
)


def _is_low_quality_candidate(url: str, title: str = "") -> bool:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().replace("www.", "")
    path = (parsed.path or "").lower()
    title_l = (title or "").lower()

    if any(host.endswith(d) for d in LOW_QUALITY_DISCOVERY_DOMAINS):
        return True
    if any(marker in path for marker in LOW_QUALITY_PATH_MARKERS):
        return True
    if any(token in title_l for token in (
        "páginas amarillas", "consulta amarillas", "top restaurantes", "trabajo", "ofertas de empleo",
        "delivery", "domicilio", "directorio", "listado", "mejores restaurantes",
    )):
        return True
    return False


# ── Discovery: Google Maps Places API ────────────────────────────────────────

async def discover_companies_gmaps(
    industria: str, ciudad: str, max_results: int, api_key: str
) -> list[dict]:
    """
    Use Google Maps Places Text Search (new API v1) to find real businesses.
    Returns list of {title, url, phone, address, rating}.
    """
    endpoint = "https://places.googleapis.com/v1/places:searchText"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": (
            "places.displayName,places.websiteUri,"
            "places.nationalPhoneNumber,places.formattedAddress,places.rating"
        ),
    }
    body = {
        "textQuery": f"{industria} en {ciudad}",
        "languageCode": "es",
        "maxResultCount": min(max_results, 20),
        "regionCode": "CO",
    }

    results = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(endpoint, json=body, headers=headers)
            data = resp.json()
            print(f"[Google Maps] status={resp.status_code} places={len(data.get('places', []))} keys={list(data.keys())}")

            for place in data.get("places", []):
                url = place.get("websiteUri", "")
                if not url:
                    continue
                if any(b in url.lower() for b in BLOCKED_DOMAINS):
                    continue
                results.append({
                    "title": place.get("displayName", {}).get("text", ""),
                    "url": url.rstrip("/"),
                    "phone": place.get("nationalPhoneNumber", ""),
                    "address": place.get("formattedAddress", ""),
                    "rating": place.get("rating"),
                    "source": "google_maps",
                })
    except Exception as e:
        print(f"[Google Maps error] {e}")

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
            url = f"https://www.bing.com/search?q={httpx.URL(path='').params.merge({'q': q})}&count=20&setlang=es"
            async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
                resp = await client.get(f"https://www.bing.com/search", params={"q": q, "count": "20", "setlang": "es"})
                if resp.status_code != 200:
                    return found
                soup = BeautifulSoup(resp.text, "html.parser")
                for li in soup.select("li.b_algo"):
                    a = li.select_one("h2 a")
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
                        "url": href.split("?")[0],  # strip tracking params
                        "phone": "",
                        "address": "",
                        "rating": None,
                        "source": "bing",
                    })
        except Exception as e:
            print(f"[Bing error] {e}")
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
    """3 parallel DDG queries for wider coverage."""
    queries = [
        f'{industria} {ciudad} empresa web oficial',
        f'empresa "{industria}" en {ciudad} contacto',
        f'"{industria}" "{ciudad}" servicios corporativos',
    ]
    seen: set[str] = set()
    results = []
    try:
        with DDGS() as ddgs:
            for query in queries:
                for r in ddgs.text(query, max_results=max_results):
                    url = r.get("href", "")
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
                        return results
    except Exception as e:
        print(f"[DuckDuckGo error] {e}")
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

    # Run Google Maps + Bing in parallel
    per_source = max(10, max_results // 2)
    tasks = [discover_companies_bing(industria, ciudad, per_source)]
    if gmaps_key:
        tasks.append(discover_companies_gmaps(industria, ciudad, per_source, gmaps_key))

    results_list = await asyncio.gather(*tasks, return_exceptions=True)

    gmaps_results = []
    bing_results = []
    if gmaps_key and len(results_list) == 2:
        bing_results = results_list[0] if isinstance(results_list[0], list) else []
        gmaps_results = results_list[1] if isinstance(results_list[1], list) else []
    else:
        bing_results = results_list[0] if isinstance(results_list[0], list) else []

    # Prefer Google Maps (has phone/address) then supplement with Bing
    add(gmaps_results)
    add(bing_results)
    print(
        f"[Discovery] GMaps={len(gmaps_results)} Bing={len(bing_results)} → {len(merged)} únicos "
        f"(saltados_historial={skipped_history}, saltados_baja_calidad={skipped_low_quality})"
    )

    # SECOP source: government contractors
    if use_secop and len(merged) < max_results:
        from secop import discover_companies_secop, resolve_secop_urls
        secop_needed = max_results - len(merged)
        secop_raw = await discover_companies_secop(industria, ciudad, secop_needed * 2)
        # Resolve URLs for SECOP companies before adding
        secop_resolved = await resolve_secop_urls(secop_raw, max_concurrent=3)
        add_secop(secop_resolved[:secop_needed])
        print(f"[Discovery] SECOP: {len(secop_raw)} raw → {len(secop_resolved)} resueltas → {len(merged)} total")

    # If exclusions removed many companies, try supplementary DDG search to refill.
    if len(merged) < max_results:
        missing = max_results - len(merged)
        if missing > 0:
            loop = asyncio.get_event_loop()
            ddg_extra = await loop.run_in_executor(None, _discover_ddg_multi, industria, ciudad, min(max_results * 3, max_results + missing * 2))
            add(ddg_extra)
            print(f"[Discovery] Supplementary DDG refill: +{len(ddg_extra)} raw → {len(merged)} final")

    # DDG fallback if still empty
    if not merged:
        print("[Discovery] Falling back to DuckDuckGo")
        loop = asyncio.get_event_loop()
        ddg = await loop.run_in_executor(None, _discover_ddg_multi, industria, ciudad, max_results)
        add(ddg)
        print(f"[Discovery] DuckDuckGo: {len(ddg)} empresas")

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
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            for candidate in candidates:
                for headers in ua_profiles:
                    try:
                        resp = await client.get(candidate, headers=headers)
                    except Exception as e:
                        last_error = f"{candidate}: {e}"
                        continue

                    if resp.status_code >= 400:
                        last_error = f"{candidate}: HTTP {resp.status_code}"
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
    for tag in soup(["script", "style", "nav", "footer", "header",
                     "aside", "form", "noscript", "svg", "img"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    text = re.sub(r"\s{2,}", " ", text)
    return text[:8000]


# ── Prompt building ───────────────────────────────────────────────────────────

def _build_prompt(url: str, scraped: str, campaign: dict, override_template: str = "") -> str:
    variables = {**DEFAULT_CAMPAIGN, **campaign,
                 "input_empresa_url": url,
                 "contenido_scrapeado": scraped}
    prompt = override_template if override_template.strip() else _SYSTEM_PROMPT_TEMPLATE
    for key, value in variables.items():
        prompt = prompt.replace("{{" + key + "}}", str(value))
    return prompt


# ── Agent prompts ─────────────────────────────────────────────────────────────

def _analista_prompt(url: str, scraped: str, c: dict) -> str:
    return f"""Eres un analista Senior de inteligencia comercial B2B. Tu objetivo es auditar el contenido extraído del sitio web de una empresa y calificar si es un prospecto válido para nuestra campaña de ventas.

PERFIL DE LA CAMPAÑA:
- Industria Objetivo: {c.get('industria_objetivo')} (INTERPRETA CON AMPLITUD: busca sinónimos, sub-nichos o modelos de negocio equivalentes. Ej: si buscamos "clínicas", un "centro odontológico" es válido).
- Dolor que resolvemos: {c.get('dolor_operativo')}
- Nuestra Solución: {c.get('solucion_ofrecida')}
- Señales Tecnológicas / Presupuesto: uso de {c.get('software_clave')} o equivalentes.
- Decisores Clave: {c.get('jerarquia_decisores')}
- Ciudad/Región: {c.get('ciudad_objetivo')}

REGLAS ESTRICTAS DE EXTRACCIÓN:
1. NO INVENTES DATOS. Si un nombre, email, o cargo no está explícitamente en el texto, el valor debe ser estrictamente null.
2. El dolor operativo rara vez se menciona explícitamente. Busca "síntomas" u oportunidades de mejora relacionadas con el dolor que resolvemos.
3. El texto proporcionado es un scrape en bruto, puede contener ruido o estar cortado. Haz tu mejor esfuerzo con la información disponible.

EMPRESA A ANALIZAR: {url}
CONTENIDO DEL SITIO WEB:
{scraped[:6000]}

Devuelve ÚNICAMENTE un objeto JSON válido, sin bloques de código (```json), sin markdown y sin texto previo o posterior. Usa esta estructura exacta:
{{
  "analisis_previo": "1-2 líneas razonando sobre a qué se dedica la empresa y si hay indicios de que sufren el dolor operativo",
  "nombre_empresa": "nombre real extraído, o null",
  "es_sector_correcto": true,
  "razon_sector": "justificación breve de por qué encaja o no en la industria objetivo",
  "tech_stack": ["lista", "de", "software", "detectado"] o null,
  "tamano_estimado": "micro|pequeña|mediana|grande|desconocido",
  "razon_tamano": "evidencia concreta (ej: 'menciona 3 sedes', 'lista 50 empleados') o null",
  "sintomas_de_dolor": true,
  "evidencia_dolor": "indicador encontrado en la web que sugiere que necesitan nuestra solución, o null",
  "decisor": {{
    "nombre": "nombre real o null",
    "cargo": "cargo extraído o null",
    "email": "email encontrado o null"
  }},
  "en_ciudad_objetivo": true,
  "datos_extra": "sedes, años de experiencia, clientes mencionados, o null"
}}"""

def _motor_scoring_prompt(analysis: dict, c: dict) -> str:
    import json as _json
    nombre = c.get('nombre_remitente', '')
    empresa = c.get('empresa_remitente', '')
    return f"""Eres el Motor de Scoring y Redactor Comercial B2B. Recibes el análisis de una empresa y debes:
1. Calcular el score de calificación
2. Si aprueba, redactar un correo de prospección que realmente convierta

═══════════════════════════════════════
REGLAS DE SCORING (máx 100 pts):
- B2B válido: +20 si es_sector_correcto = true
- Tensión operativa: +30 si dolor_detectado = true con evidencia real, +15 si solo probable
- Escala y presupuesto: +30 grande/mediana con tech, +20 mediana sin tech, 0 micro
- Poder de decisión: +10 email nominal, +5 email genérico, 0 sin contacto
- Bono geográfico: +10 si en_ciudad_objetivo = true

VETOS AUTOMÁTICOS (rechazo inmediato):
- tamano = "micro" → MICRO_BUSINESS_LOW_BUDGET
- es_sector_correcto = false → WRONG_SECTOR_OR_NO_DATA
- Score < 60 → LOW_SCORE_QUALIFICATION
═══════════════════════════════════════

CAMPAÑA:
- Vendemos: {c.get('solucion_ofrecida')}
- A quién: {c.get('industria_objetivo')} en {c.get('ciudad_objetivo')}
- El dolor: {c.get('dolor_operativo')}
- Firmante: {nombre} de {empresa}

ANÁLISIS DEL ANALISTA B2B:
{_json.dumps(analysis, ensure_ascii=False, indent=2)}

═══════════════════════════════════════
INSTRUCCIONES DE CORREO (solo si aprueba):
- Abre con una observación ESPECÍFICA del sitio (usa datos_extra o evidencia_dolor del análisis)
- Conecta esa observación con el dolor operativo de la campaña
- Explica la solución en 1 oración concreta, no genérica
- Cierra con una pregunta de 10 minutos
- Tono: directo, humano, sin bullshit corporativo
- Longitud: 4-5 párrafos cortos
- Firma: {nombre} / {empresa}
═══════════════════════════════════════

Si RECHAZADO → responde SOLO con este JSON exacto:
{{"system_state": "REJECTED_BY_AI", "empresa": "nombre", "score": 0, "motivo_descalificacion": "CODIGO", "evidencia_encontrada": "frase corta específica", "resumen_empresa": "a qué se dedica en 1 línea"}}

Si APROBADO → responde SOLO con este JSON exacto:
{{"system_state": "SUCCESS_READY_FOR_REVIEW", "empresa": "nombre", "score": 85, "es_visitable_zona_objetivo": true, "decisor": {{"nombre": "nombre o null", "cargo": "cargo", "email": "email o null"}}, "datos_tecnicos": {{"tech_stack": "software detectado o null", "perfil": "A_REZAGO o B_FRICCION"}}, "borradores": {{"email_asuntos": ["Asunto directo y específico 1", "Asunto alternativo 2"], "email_cuerpo": "Correo completo. Usa \\n\\n entre párrafos."}}}}

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


def _normalize_openai_model_name(model_name: str, fallback: str = "gpt-4o-mini") -> str:
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
    analista_model = _normalize_openai_model_name(merged.get("llm_analista", ""), "gpt-4o-mini")
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
            max_tokens=600,
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
    redactor_model = _normalize_openai_model_name(merged.get("llm_redactor", ""), "gpt-4o-mini")
    try:
        r2 = await client.chat.completions.create(
            model=redactor_model,
            messages=[{"role": "user", "content": _motor_scoring_prompt(analysis, merged)}],
            temperature=0.15,
            max_tokens=1200,
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
                    print(f"[prospector] save_lead error: {_e}")

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
