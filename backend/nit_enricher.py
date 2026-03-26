"""
nit_enricher.py — Enriquecedor de NITs colombianos para el agente de seguros.

Pipeline por NIT:
  1. RUES (rues.org.co)        — razón social, rep. legal, estado, dirección
  2. SECOP histórico           — contratos ganados, valor total, entidades
  3. Supersociedades           — capacidad financiera (si existe)
  4. Bing web search           — sitio web, email de contacto

Salida: expediente consolidado listo para que la aseguradora llame hoy mismo.

Cache en memoria (TTL 24h) — la primera búsqueda enriquece, las siguientes son instantáneas.
"""
from __future__ import annotations

import asyncio
import re
import time
import logging
from typing import Optional

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ── Cache simple en memoria (nit → {data, ts}) ────────────────────────────────
_CACHE: dict[str, dict] = {}
_CACHE_TTL = 60 * 60 * 24  # 24 horas


def _cached(nit: str) -> Optional[dict]:
    entry = _CACHE.get(nit)
    if entry and (time.time() - entry["ts"]) < _CACHE_TTL:
        return entry["data"]
    return None


def _cache_set(nit: str, data: dict):
    _CACHE[nit] = {"data": data, "ts": time.time()}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean_nit(raw: str) -> str:
    """Normaliza NIT: quita puntos, guiones, espacios. Devuelve solo dígitos."""
    return re.sub(r"[^0-9]", "", (raw or "").strip())


def _fmt_cop(value: float) -> str:
    if not value:
        return "N/D"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.1f}B COP"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.0f}M COP"
    return f"${value:,.0f} COP"


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "es-CO,es;q=0.9",
}


# ── Helper: Reintento con backoff exponencial ────────────────────────────────

async def _retry_async(
    coro_fn,
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff: float = 2.0,
    timeout: float = 15,
) -> Optional[dict]:
    """
    Reintenta una corrutina con backoff exponencial.
    Retorna el resultado o None si todos los reintentos fallan.
    """
    import asyncio
    delay = initial_delay
    last_error = None
    
    for attempt in range(max_retries):
        try:
            return await asyncio.wait_for(coro_fn(), timeout=timeout)
        except asyncio.TimeoutError as e:
            last_error = f"timeout (attempt {attempt+1}/{max_retries})"
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= backoff
        except Exception as e:
            last_error = f"{type(e).__name__}: {str(e)[:80]}"
            if attempt < max_retries - 1:
                await asyncio.sleep(delay)
                delay *= backoff
    
    return None


# ── Fuente 1: RUES ────────────────────────────────────────────────────────────

async def _lookup_rues(nit_digits: str) -> dict:
    """
    Consulta el Registro Único Empresarial y Social (rues.org.co).
    Devuelve razón social, representante legal, estado, dirección, objeto social.
    Reintenta ambas estrategias si la primera falla.
    """
    result = {
        "razon_social": None,
        "representante_legal": None,
        "estado": None,
        "direccion": None,
        "municipio": None,
        "objeto_social": None,
        "tipo_sociedad": None,
        "fecha_matricula": None,
        "camara_comercio": None,
        "fuente_rues": False,
    }

    # Strategy 1: datos.gov.co RUES dataset — Confecámaras (c82u-588k)
    async def _strategy_1():
        url = "https://www.datos.gov.co/resource/c82u-588k.json"
        params = {
            "$where": f"nit='{nit_digits}'",
            "$limit": 1,
            "$select": (
                "razon_social,representante_legal,estado_matricula,"
                "camara_comercio,tipo_sociedad,fecha_matricula,"
                "fecha_renovacion,organizacion_juridica"
            ),
        }
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            rows = resp.json()
            if rows and isinstance(rows, list):
                r = rows[0]
                result.update({
                    "razon_social":        r.get("razon_social", "").strip().title() or None,
                    "representante_legal": r.get("representante_legal", "").strip().title() or None,
                    "estado":              r.get("estado_matricula", "").strip().title() or None,
                    "tipo_sociedad":       r.get("tipo_sociedad") or r.get("organizacion_juridica") or None,
                    "fecha_matricula":     (r.get("fecha_matricula") or "")[:10] or None,
                    "camara_comercio":     r.get("camara_comercio", "").strip().title() or None,
                    "fuente_rues":         True,
                })
                logger.info("[RUES datos.gov] NIT %s → %s ✓", nit_digits, result["razon_social"])
                return result
        return None

    try:
        res = await _retry_async(_strategy_1, max_retries=2, initial_delay=0.3, timeout=12)
        if res and res.get("fuente_rues"):
            return res
    except Exception as e:
        logger.warning("[RUES datos.gov] NIT %s failed after retries: %s", nit_digits, e)

    # Strategy 2: scrape rues.org.co portal directamente (fallback)
    async def _strategy_2():
        portal_url = f"https://www.rues.org.co/RM"
        params = {"nit": nit_digits, "pag": "1"}
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(portal_url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            def _td(label: str) -> str:
                """Busca contenido en tabla HTML."""
                for td in soup.find_all("td"):
                    if label.lower() in td.get_text(strip=True).lower():
                        nxt = td.find_next_sibling("td")
                        if nxt:
                            return nxt.get_text(strip=True)
                return ""

            razon = _td("Razón Social") or _td("Nombre")
            if razon:
                result.update({
                    "razon_social":        razon.title(),
                    "representante_legal": _td("Representante Legal").title() or None,
                    "estado":              _td("Estado") or None,
                    "direccion":           _td("Dirección") or None,
                    "municipio":           _td("Municipio").title() or None,
                    "tipo_sociedad":       _td("Tipo Empresa") or None,
                    "fuente_rues":         True,
                })
                logger.info("[RUES portal] NIT %s → %s ✓", nit_digits, razon)
                return result
        return None

    try:
        res = await _retry_async(_strategy_2, max_retries=2, initial_delay=0.5, timeout=15)
        if res and res.get("fuente_rues"):
            return res
    except Exception as e:
        logger.warning("[RUES portal] NIT %s failed after retries: %s", nit_digits, e)

    # Si ambas fallan, log de diagnóstico
    logger.error("[RUES] NIT %s: NO ENCONTRADO en datos.gov ni rues.org.co", nit_digits)
    return result


# ── Fuente 2: SECOP histórico ─────────────────────────────────────────────────

async def _lookup_secop_history(nit_digits: str) -> dict:
    """
    Busca en SECOP II todos los contratos ganados por este NIT.
    Devuelve: nro contratos, valor total, entidades, último objeto, adjudicado.
    Con reintentos automáticos si SECOP no responde.
    """
    result = {
        "contratos_secop": 0,
        "valor_total_contratado": 0.0,
        "entidades_contratantes": [],
        "ultimo_contrato": None,
        "proveedor_nombre_secop": None,
    }

    async def _fetch_secop():
        url = "https://www.datos.gov.co/resource/jbjy-vk9h.json"
        params = {
            "$where": f"documento_proveedor='{nit_digits}'",
            "$limit": 500,
            "$order": "fecha_de_firma DESC",
            "$select": (
                "proveedor_adjudicado,objeto_del_contrato,"
                "valor_del_contrato,nombre_entidad,fecha_de_firma"
            ),
        }
        async with httpx.AsyncClient(timeout=18) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            rows = resp.json()
            if not isinstance(rows, list) or not rows:
                return None

            entidades: dict[str, int] = {}
            valor_total = 0.0

            for r in rows:
                try:
                    valor_total += float(r.get("valor_del_contrato") or 0)
                except (ValueError, TypeError):
                    pass
                entidad = (r.get("nombre_entidad") or "").strip()
                if entidad:
                    entidades[entidad] = entidades.get(entidad, 0) + 1

            # Top 5 entidades por frecuencia
            top_entidades = sorted(entidades, key=lambda k: -entidades[k])[:5]

            primer_row = rows[0]
            result.update({
                "contratos_secop":       len(rows),
                "valor_total_contratado": valor_total,
                "entidades_contratantes": top_entidades,
                "ultimo_contrato":        (primer_row.get("objeto_del_contrato") or "")[:200],
                "proveedor_nombre_secop": (primer_row.get("proveedor_adjudicado") or "").strip().title(),
            })
            logger.info("[SECOP] NIT %s → %d contratos / %s ✓", nit_digits, len(rows), _fmt_cop(valor_total))
            return result

    try:
        res = await _retry_async(_fetch_secop, max_retries=2, initial_delay=0.5, timeout=18)
        if res:
            return res
    except Exception as e:
        logger.warning("[SECOP history] NIT %s failed after retries: %s", nit_digits, e)

    logger.debug("[SECOP] NIT %s: No contratos encontrados o error de conexión", nit_digits)
    return result


# ── Fuente 3: Supersociedades ─────────────────────────────────────────────────

async def _lookup_supersociedades(nit_digits: str) -> dict:
    """
    Busca en el dataset de Supersociedades (datos.gov.co).
    Devuelve indicadores financieros básicos si la empresa reporta.
    Solo medianas/grandes empresas están aquí.
    """
    result = {
        "supersociedades": False,
        "ingresos_operacionales": None,
        "activos_totales": None,
        "anio_reporte": None,
    }
    try:
        # 10.000 Empresas más Grandes — Supersociedades (6cat-2gcs)
        url = "https://www.datos.gov.co/resource/6cat-2gcs.json"
        params = {
            "$where": f"nit='{nit_digits}'",
            "$limit": 1,
            "$order": "a_o_de_corte DESC",
            "$select": "nit,raz_n_social,ingresos_operacionales,total_activos,total_pasivos,total_patrimonio,a_o_de_corte,ciudad_domicilio,macrosector",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            if resp.status_code == 200:
                rows = resp.json()
                if rows and isinstance(rows, list):
                    r = rows[0]
                    result.update({
                        "supersociedades":        True,
                        "ingresos_operacionales": float(r.get("ingresos_operacionales") or 0) or None,
                        "activos_totales":        float(r.get("total_activos") or 0) or None,
                        "total_pasivos":          float(r.get("total_pasivos") or 0) or None,
                        "total_patrimonio":       float(r.get("total_patrimonio") or 0) or None,
                        "macrosector":            r.get("macrosector"),
                        "anio_reporte":           r.get("a_o_de_corte"),
                    })
                    logger.info("[Supersociedades] NIT %s encontrado", nit_digits)
    except Exception as e:
        logger.warning("[Supersociedades] NIT %s error: %s", nit_digits, e)

    return result


# ── Fuente 3b: SECOP II Proveedores Registrados — contacto directo ───────────

async def _lookup_secop_proveedor(nit_digits: str) -> dict:
    """
    Consulta el dataset qmzu-gj57 — SECOP II Proveedores Registrados.
    1.5M empresas colombianas con teléfono, email, dirección, web y rep. legal.
    100% gratis, sin API key. CON REINTENTOS automáticos.
    """
    result = {
        "proveedor_telefono":        None,
        "proveedor_email":           None,
        "proveedor_direccion":       None,
        "proveedor_web":             None,
        "proveedor_municipio":       None,
        "rep_legal_nombre":          None,
        "rep_legal_telefono":        None,
        "rep_legal_email":           None,
        "es_pyme":                   None,
        "categoria_principal":       None,
        "fuente_secop_proveedor":    False,
    }
    
    async def _fetch_proveedor():
        url = "https://www.datos.gov.co/resource/qmzu-gj57.json"
        params = {
            "$where": f"nit='{nit_digits}'",
            "$limit": 1,
            "$select": (
                "nit,nombre,telefono,correo,direccion,municipio,departamento,"
                "sitio_web,espyme,descripcion_categoria_principal,"
                "nombre_representante_legal,telefono_representante_legal,"
                "correo_representante_legal,esta_activa"
            ),
        }
        async with httpx.AsyncClient(timeout=14) as client:
            resp = await client.get(url, params=params, headers=_HEADERS)
            resp.raise_for_status()
            rows = resp.json()
            if rows and isinstance(rows, list):
                r = rows[0]
                result.update({
                    "proveedor_telefono":     (r.get("telefono") or "").strip() or None,
                    "proveedor_email":        (r.get("correo") or "").strip().lower() or None,
                    "proveedor_direccion":    (r.get("direccion") or "").strip() or None,
                    "proveedor_web":          (r.get("sitio_web") or "").strip() or None,
                    "proveedor_municipio":    (r.get("municipio") or "").strip().title() or None,
                    "rep_legal_nombre":       (r.get("nombre_representante_legal") or "").strip().title() or None,
                    "rep_legal_telefono":     (r.get("telefono_representante_legal") or "").strip() or None,
                    "rep_legal_email":        (r.get("correo_representante_legal") or "").strip().lower() or None,
                    "es_pyme":                r.get("espyme"),
                    "categoria_principal":    (r.get("descripcion_categoria_principal") or "").strip() or None,
                    "fuente_secop_proveedor": True,
                })
                logger.info("[SECOP Proveedor] NIT %s → tel=%s email=%s ✓",
                            nit_digits, result["proveedor_telefono"], result["proveedor_email"])
                return result
            return None
    
    try:
        res = await _retry_async(_fetch_proveedor, max_retries=3, initial_delay=0.4, timeout=14)
        if res:
            return res
    except Exception as e:
        logger.warning("[SECOP Proveedor] NIT %s failed after retries: %s", nit_digits, e)
    
    logger.debug("[SECOP Proveedor] NIT %s: No encontrado en SECOP proveedores", nit_digits)
    return result


# ── Fuente 3c: Apitude — teléfono + dirección oficial ────────────────────────

async def _lookup_apitude(nit_raw: str) -> dict:
    """
    Consulta Apitude identity-business-co API.
    Devuelve teléfono, dirección, coordenadas y actividades económicas.
    Requiere APITUDE_API_KEY en .env
    """
    result = {"apitude_phone": None, "apitude_direccion": None, "apitude_ok": False}

    api_key = os.environ.get("APITUDE_API_KEY", "")
    if not api_key:
        return result  # Silencioso — key no configurada

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            # Paso 1: crear solicitud
            resp = await client.post(
                "https://apitude.co/api/v1.0/requests/identity-business-co/",
                json={"document_number": nit_raw},
                headers={"x-api-key": api_key, "Content-Type": "application/json"},
            )
            if resp.status_code not in (200, 201):
                logger.warning("[Apitude] POST status=%d nit=%s", resp.status_code, nit_raw)
                return result

            data = resp.json()
            # Puede ser respuesta directa o asíncrona (GET para resultado)
            result_data = (
                data.get("result", {}).get("data")
                or data.get("data")
                or {}
            )

            # Si es asíncrono, hacer GET
            if not result_data and data.get("id"):
                request_id = data["id"]
                get_resp = await client.get(
                    f"https://apitude.co/api/v1.0/requests/identity-business-co/{request_id}/",
                    headers={"x-api-key": api_key},
                )
                if get_resp.status_code == 200:
                    result_data = get_resp.json().get("result", {}).get("data") or {}

            if result_data:
                phone = result_data.get("phone") or result_data.get("telefono") or ""
                direccion = result_data.get("formatted_address") or result_data.get("direccion") or ""
                result.update({
                    "apitude_phone":    phone or None,
                    "apitude_direccion": direccion or None,
                    "apitude_ok":       True,
                })
                logger.info("[Apitude] NIT %s → phone=%s dir=%s", nit_raw, phone, direccion)

    except Exception as e:
        logger.warning("[Apitude] NIT %s error: %s", nit_raw, e)

    return result


# ── Fuente 4: Bing — web + email ──────────────────────────────────────────────

_SKIP_DOMAINS = {
    "facebook", "linkedin", "secop", "datos.gov", "supersociedades",
    "rues.org", "bing.com", "google.com", "instagram", "twitter",
    "youtube", "wikipedia", "elempleo", "computrabajo",
}

_CONTACT_PATHS = ["/contacto", "/contactenos", "/contactenos.html",
                  "/contact", "/quienes-somos", "/nosotros", "/about"]


def _extract_emails(text: str, prefer_corporate: bool = True) -> list[str]:
    emails = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text)
    # Filtrar emails claramente falsos o de dominios de imagen/asset
    emails = [e for e in emails if "." in e.split("@")[-1] and len(e) < 80]
    if prefer_corporate:
        corp = [e for e in emails if not any(
            g in e.lower() for g in ("gmail", "hotmail", "yahoo", "outlook", "live.com")
        )]
        return corp or emails
    return emails


async def _scrape_contact_page(base_url: str, client: httpx.AsyncClient) -> str:
    """Intenta scrapear la página de contacto del sitio para extraer email/teléfono."""
    from urllib.parse import urlparse, urljoin
    parsed = urlparse(base_url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    for path in _CONTACT_PATHS:
        try:
            resp = await client.get(urljoin(base, path), timeout=8)
            if resp.status_code == 200 and len(resp.text) > 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for tag in soup(["script", "style", "nav", "footer"]):
                    tag.decompose()
                return soup.get_text(separator=" ", strip=True)[:4000]
        except Exception:
            continue
    return ""


async def _lookup_web_contact(nombre: str, nit_digits: str) -> dict:
    """
    1. Busca en Bing el sitio web oficial (query simple por nombre)
    2. Scrape homepage + página de contacto para extraer email y teléfono
    """
    result = {"website": None, "email": None, "phone": None}
    if not nombre:
        return result

    # Query más simple — el NIT a veces confunde a Bing
    nombre_short = nombre.split(" S.A")[0].split(" LTDA")[0].split(" SAS")[0].strip()
    query = f'"{nombre_short}" Colombia empresa sitio web oficial'

    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            # Paso 1: Bing para encontrar el website
            resp = await client.get(
                "https://www.bing.com/search",
                params={"q": query, "count": "8", "setlang": "es"},
                headers=_HEADERS,
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for li in soup.select("li.b_algo"):
                    a = li.select_one("h2 a")
                    if not a:
                        continue
                    href = a.get("href", "")
                    if not href.startswith("http"):
                        continue
                    from urllib.parse import urlparse
                    domain = urlparse(href).netloc.lower().replace("www.", "")
                    if any(skip in domain for skip in _SKIP_DOMAINS):
                        continue
                    result["website"] = href.split("?")[0]
                    break

                # Email en snippets de Bing (rápido, sin costo extra)
                snippet_emails = _extract_emails(soup.get_text())
                if snippet_emails:
                    result["email"] = snippet_emails[0].lower()

            # Paso 2: Si encontramos web, scrapeamos la página de contacto
            if result["website"] and not result["email"]:
                contact_text = await _scrape_contact_page(result["website"], client)
                if contact_text:
                    contact_emails = _extract_emails(contact_text)
                    if contact_emails:
                        result["email"] = contact_emails[0].lower()

                    # Teléfono colombiano: +57, 601, 300-350 (móviles), 1-8 (fijos)
                    phones = re.findall(
                        r"(?:\+57[\s-]?)?(?:60[1-9]|3[0-9]{2})[\s.-]?\d{3}[\s.-]?\d{4}", contact_text
                    )
                    if phones:
                        result["phone"] = re.sub(r"[\s.-]", "", phones[0])

            logger.info("[Web] NIT %s → %s / email=%s / phone=%s",
                        nit_digits, result["website"], result["email"], result["phone"])
    except Exception as e:
        logger.warning("[Web contact] NIT %s error: %s", nit_digits, e)

    return result


# ── Orquestador principal ─────────────────────────────────────────────────────

async def enrich_nit(nit_raw: str) -> dict:
    """
    Enriquece un NIT colombiano con todas las fuentes disponibles.

    Retorna un expediente consolidado:
    {
      nit, razon_social, representante_legal, estado,
      direccion, municipio, tipo_sociedad, objeto_social,
      website, email,
      contratos_secop, valor_total_contratado, entidades_contratantes,
      ingresos_operacionales, activos_totales,
      fuentes_consultadas: [...],
      advertencia_poliza: str,   # resumen ejecutivo para la aseguradora
    }
    """
    nit = _clean_nit(nit_raw)
    if not nit:
        return {"error": "NIT inválido", "nit_raw": nit_raw}

    # Cache hit
    cached = _cached(nit)
    if cached:
        logger.info("[NIT enricher] Cache hit para NIT %s", nit)
        return cached

    logger.info("[NIT enricher] Enriqueciendo NIT %s — consultando 4 fuentes en paralelo...", nit)

    # Todas las fuentes en paralelo
    rues_task      = _lookup_rues(nit)
    secop_task     = _lookup_secop_history(nit)
    super_task     = _lookup_supersociedades(nit)
    proveedor_task = _lookup_secop_proveedor(nit)
    apitude_task   = _lookup_apitude(nit_raw)

    rues, secop, supersoc, proveedor, apitude = await asyncio.gather(
        rues_task, secop_task, super_task, proveedor_task, apitude_task,
        return_exceptions=True
    )

    # Manejar excepciones individuales sin romper el pipeline
    if isinstance(rues, Exception):
        logger.error("[RUES] %s", rues); rues = {}
    if isinstance(secop, Exception):
        logger.error("[SECOP] %s", secop); secop = {}
    if isinstance(supersoc, Exception):
        logger.error("[Supersociedades] %s", supersoc); supersoc = {}
    if isinstance(proveedor, Exception):
        logger.error("[SECOP Proveedor] %s", proveedor); proveedor = {}
    if isinstance(apitude, Exception):
        logger.error("[Apitude] %s", apitude); apitude = {}

    # Nombre más completo entre fuentes
    nombre = (
        rues.get("razon_social")
        or secop.get("proveedor_nombre_secop")
        or ""
    )

    # Buscar web solo si tenemos nombre
    web = {}
    if nombre:
        web = await _lookup_web_contact(nombre, nit)
        if isinstance(web, Exception):
            web = {}

    # ── Advertencia para la aseguradora ───────────────────────────────────────
    valor_fmt = _fmt_cop(secop.get("valor_total_contratado", 0))
    contratos = secop.get("contratos_secop", 0)
    rep_legal = rues.get("representante_legal") or "No encontrado"

    if contratos > 0:
        advertencia = (
            f"{nombre or 'Esta empresa'} tiene {contratos} contratos públicos ganados "
            f"por un total de {valor_fmt}. "
            f"Representante legal: {rep_legal}. "
            f"Alta probabilidad de necesitar póliza de cumplimiento."
        )
    else:
        advertencia = (
            f"{nombre or 'Esta empresa'} no tiene contratos en SECOP II registrados, "
            f"pero puede estar participando en procesos nuevos."
        )

    fuentes: list[str] = []
    if rues.get("fuente_rues"):              fuentes.append("RUES")
    if contratos > 0:                        fuentes.append("SECOP II")
    if supersoc.get("supersociedades"):      fuentes.append("Supersociedades")
    if proveedor.get("fuente_secop_proveedor"): fuentes.append("SECOP Proveedores")
    if apitude.get("apitude_ok"):            fuentes.append("Apitude")
    if web.get("website"):                   fuentes.append("Web")

    expediente = {
        # Identificación
        "nit":                      nit,
        "nit_raw":                  nit_raw,
        "razon_social":             nombre or None,

        # Datos RUES
        "representante_legal":      rues.get("representante_legal"),
        "estado":                   rues.get("estado"),
        "tipo_sociedad":            rues.get("tipo_sociedad"),
        "fecha_matricula":          rues.get("fecha_matricula"),
        "camara_comercio":          rues.get("camara_comercio"),
        "direccion":                rues.get("direccion"),
        "municipio":                rues.get("municipio"),
        "objeto_social":            rues.get("objeto_social"),

        # Contacto — prioridad: SECOP Proveedor > Apitude > Web
        "website":                  proveedor.get("proveedor_web") or web.get("website"),
        "email":                    proveedor.get("proveedor_email") or web.get("email"),
        "phone":                    proveedor.get("proveedor_telefono") or apitude.get("apitude_phone") or web.get("phone"),
        "direccion_oficial":        proveedor.get("proveedor_direccion") or apitude.get("apitude_direccion"),
        "municipio":                proveedor.get("proveedor_municipio") or rues.get("municipio"),
        # Rep legal enriquecido
        "rep_legal_telefono":       proveedor.get("rep_legal_telefono"),
        "rep_legal_email":          proveedor.get("rep_legal_email"),
        "es_pyme":                  proveedor.get("es_pyme"),
        "categoria_secop":          proveedor.get("categoria_principal"),

        # SECOP
        "contratos_secop":          contratos,
        "valor_total_contratado":   secop.get("valor_total_contratado", 0),
        "valor_total_fmt":          valor_fmt,
        "entidades_contratantes":   secop.get("entidades_contratantes", []),
        "ultimo_contrato":          secop.get("ultimo_contrato"),

        # Supersociedades
        "ingresos_operacionales":   supersoc.get("ingresos_operacionales"),
        "activos_totales":          supersoc.get("activos_totales"),
        "anio_reporte_financiero":  supersoc.get("anio_reporte"),

        # Meta
        "fuentes_consultadas":      fuentes,
        "advertencia_poliza":       advertencia,
    }

    _cache_set(nit, expediente)
    logger.info("[NIT enricher] NIT %s completo — fuentes: %s", nit, fuentes)
    return expediente


async def enrich_nits_batch(nits: list[str], max_concurrent: int = 5) -> list[dict]:
    """Enriquece una lista de NITs en paralelo (útil para procesar proponentes de una licitación)."""
    sem = asyncio.Semaphore(max_concurrent)

    async def _one(nit: str) -> dict:
        async with sem:
            return await enrich_nit(nit)

    return await asyncio.gather(*[_one(n) for n in nits], return_exceptions=False)
