"""
rues.py — RUES (Registro Único Empresarial y Social) discovery source.

Queries Colombia's open data portal (datos.gov.co) to find recently
registered companies filtered by sector (CIIU code) and city.

No authentication required — public Socrata/SODA REST API.

Endpoint: RUES — Cámara de Comercio
  https://www.datos.gov.co/resource/c82u-588k.json

Useful for finding:
  - Empresas recién creadas (fecha_matricula recent) → high-intent leads
  - Empresas en sector específico (cod_ciiu_act_econ_pri)
  - Personas naturales con matrícula activa (inmobiliarios independientes, etc.)
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, timedelta
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

RUES_URL = "https://www.datos.gov.co/resource/c82u-588k.json"

_FETCH_MULTIPLIER = 4
_MAX_FETCH = 500

# ── CIIU sector code mapping ──────────────────────────────────────────────────
# Maps Spanish industry keywords to CIIU primary economic activity codes.
# Source: DANE CIIU Rev. 4 A.C. Colombia
CIIU_MAP: dict[str, list[str]] = {
    # Real estate / arrendamiento
    "inmobiliaria":   ["6810", "6820", "6831", "6832"],
    "inmobiliarias":  ["6810", "6820", "6831", "6832"],
    "arrendamiento":  ["6810", "6820", "6831"],
    "finca raiz":     ["6810", "6820"],
    "propiedad raiz": ["6810", "6820"],
    # Construction
    "construccion":   ["4111", "4112", "4290", "4311", "4321"],
    "constructora":   ["4111", "4112", "4290"],
    "obras":          ["4290", "4210", "4220"],
    # Insurance
    "seguros":        ["6511", "6512", "6513", "6521", "6522"],
    "aseguradora":    ["6511", "6512", "6513"],
    "corredores":     ["6621", "6622"],
    # Financial / fintech
    "financiero":     ["6491", "6492", "6499", "6419"],
    "fintech":        ["6491", "6499", "6612"],
    "credito":        ["6492", "6491"],
    # Tech / software
    "software":       ["6201", "6202", "6209"],
    "tecnologia":     ["6201", "6202", "6209", "4651"],
    "sistemas":       ["6201", "6202", "6311"],
    # Commerce
    "comercio":       ["4711", "4719", "4731", "4741"],
    "retail":         ["4711", "4719"],
    # Transport / logistics
    "transporte":     ["4911", "4921", "4930", "5210", "5229"],
    "logistica":      ["5210", "5229", "4923"],
    "carga":          ["4923", "5210"],
    # Health
    "salud":          ["8610", "8621", "8622", "8691"],
    "clinica":        ["8610", "8621"],
    "hospital":       ["8610"],
    # Education
    "educacion":      ["8510", "8520", "8530", "8541"],
    "colegio":        ["8520"],
    # Food / restaurants
    "restaurante":    ["5611", "5612", "5619"],
    "alimentos":      ["1011", "1020", "1040", "5611"],
    # Hospitality
    "hotel":          ["5511", "5512", "5513"],
    "turismo":        ["7911", "7912", "7990"],
    # Manufacturing
    "manufactura":    ["1310", "2211", "2310", "2410"],
    "industria":      ["2410", "2310", "2511"],
    # Agriculture
    "agro":           ["0111", "0112", "0113", "0114"],
    "agricultura":    ["0111", "0112", "0113"],
    # Services
    "servicios":      ["8010", "8020", "8110", "9609"],
    "consultoria":    ["7020", "7010", "6920"],
    "juridico":       ["6910", "6920"],
    "contable":       ["6920"],
}


def _resolve_ciiu(industria: str) -> list[str]:
    """Map industry keyword to list of CIIU codes. Returns [] if no match
    or if no industry given (→ sin filtro CIIU = todas las recién creadas)."""
    lower = (industria or "").lower().strip()
    if not lower:
        return []
    for keyword, codes in CIIU_MAP.items():
        if keyword in lower or lower in keyword:
            return codes
    return []


def _is_person(nombre: str, id_number: str) -> bool:
    """Heuristic: detect natural persons (cédula) vs companies (NIT)."""
    digits = re.sub(r"\D", "", id_number or "")
    if len(digits) < 9:
        return True
    if "," in nombre:
        parts = nombre.split(",")
        if all(len(p.strip().split()) <= 2 for p in parts):
            return True
    return False


async def fetch_rues_companies(
    industria: str,
    ciudad: Optional[str] = None,
    dias_recientes: int = 180,
    max_results: int = 50,
    include_personas_naturales: bool = False,
) -> list[dict]:
    """
    Query RUES dataset and return recently registered companies.

    Args:
        industria:               Industry keyword (e.g. 'inmobiliarias', 'seguros')
        ciudad:                  Chamber of commerce city (e.g. 'BOGOTA', 'MEDELLIN')
        dias_recientes:          How many days back to look for new registrations
        max_results:             Max unique companies to return
        include_personas_naturales: Include natural persons (not just companies)

    Returns list of dicts:
        {
          "razon_social":       str,
          "numero_id":          str,   # NIT or cédula
          "ciiu":               str,   # primary CIIU code
          "fecha_matricula":    str,   # "YYYY-MM-DD"
          "camara_comercio":    str,   # city/region
          "organizacion":       str,   # SAS, PERSONA NATURAL, etc.
          "estado":             str,   # ACTIVA, CANCELADA, etc.
          "dias_desde_registro": int,
        }
    """
    limit = min(max_results * _FETCH_MULTIPLIER, _MAX_FETCH)
    fecha_desde = (date.today() - timedelta(days=dias_recientes)).strftime("%Y%m%d")

    conditions = [
        f"estado_matricula='ACTIVA'",
        f"fecha_matricula >= '{fecha_desde}'",
    ]

    # Filter by city via camara_comercio
    if ciudad and ciudad.strip():
        c = ciudad.strip().upper()
        # Remove accents for matching
        for src, tgt in [("Á","A"),("É","E"),("Í","I"),("Ó","O"),("Ú","U")]:
            c = c.replace(src, tgt).replace(tgt, tgt)
        conditions.append(f"upper(camara_comercio) like '%{c}%'")

    # Filter by CIIU if we can resolve the industry
    ciiu_codes = _resolve_ciiu(industria)
    if ciiu_codes:
        ciiu_filter = " OR ".join(f"cod_ciiu_act_econ_pri='{code}'" for code in ciiu_codes)
        conditions.append(f"({ciiu_filter})")

    if not include_personas_naturales:
        conditions.append("organizacion_juridica != 'PERSONA NATURAL'")

    params: dict = {
        "$limit": limit,
        "$order": "fecha_matricula DESC",
        "$select": (
            "razon_social,"
            "numero_identificacion,"
            "cod_ciiu_act_econ_pri,"
            "fecha_matricula,"
            "camara_comercio,"
            "organizacion_juridica,"
            "estado_matricula"
        ),
        "$where": " AND ".join(conditions),
    }

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(RUES_URL, params=params)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        logger.error("[RUES] API error: %s", e)
        return []

    if not isinstance(rows, list):
        logger.warning("[RUES] Unexpected response type: %s", type(rows))
        return []

    today = date.today()
    results = []
    seen_ids: set[str] = set()

    for row in rows:
        nombre = (row.get("razon_social") or "").strip()
        numero_id = (row.get("numero_identificacion") or "").strip()

        if not nombre or not numero_id:
            continue
        if numero_id in seen_ids:
            continue
        if not include_personas_naturales and _is_person(nombre, numero_id):
            continue

        seen_ids.add(numero_id)

        fecha_raw = (row.get("fecha_matricula") or "")[:8]
        try:
            fecha_dt = date(int(fecha_raw[:4]), int(fecha_raw[4:6]), int(fecha_raw[6:8]))
            fecha_str = fecha_dt.isoformat()
            dias_desde = (today - fecha_dt).days
        except (ValueError, IndexError):
            fecha_str = fecha_raw
            dias_desde = -1

        results.append({
            "razon_social":        nombre,
            "numero_id":           numero_id,
            "ciiu":                (row.get("cod_ciiu_act_econ_pri") or "").strip(),
            "fecha_matricula":     fecha_str,
            "camara_comercio":     (row.get("camara_comercio") or "").strip().title(),
            "organizacion":        (row.get("organizacion_juridica") or "").strip().title(),
            "estado":              (row.get("estado_matricula") or "").strip().title(),
            "dias_desde_registro": dias_desde,
        })

        if len(results) >= max_results:
            break

    logger.info(
        "[RUES] industria=%r ciudad=%r dias=%d ciiu=%s → %d rows → %d empresas",
        industria, ciudad, dias_recientes, ciiu_codes, len(rows), len(results),
    )
    return results


def build_rues_context(company: dict) -> str:
    """Human-readable summary for LLM analyst injection."""
    lines = [
        "[Fuente: RUES — Registro Único Empresarial y Social de Colombia]",
        f"Empresa: {company['razon_social']}",
        f"ID: {company['numero_id']}",
        f"Código CIIU: {company['ciiu']}",
        f"Fecha de registro: {company['fecha_matricula']} ({company['dias_desde_registro']} días de antigüedad)",
        f"Cámara de Comercio: {company['camara_comercio']}",
        f"Tipo: {company['organizacion']}",
        "",
        "Esta empresa está registrada activamente en Cámara de Comercio.",
        "Fue creada recientemente — alta probabilidad de estar evaluando proveedores y servicios.",
    ]
    return "\n".join(lines)


async def discover_companies_rues(
    industria: str,
    ciudad: str,
    max_results: int,
    dias_recientes: int = 180,
    include_personas_naturales: bool = False,
) -> list[dict]:
    """
    Discovery source for the prospector pipeline.
    Returns company dicts in the same format as other discovery sources,
    with extra 'rues_context' key for analyst enrichment.

    NOTE: RUES has no website URLs — caller must resolve via Serper/Bing.
    """
    companies = await fetch_rues_companies(
        industria=industria,
        ciudad=ciudad if ciudad.lower() not in ("colombia", "") else None,
        dias_recientes=dias_recientes,
        max_results=max_results,
        include_personas_naturales=include_personas_naturales,
    )

    results = []
    for c in companies:
        results.append({
            "title":        c["razon_social"],
            "url":          "",   # resolved later via Serper
            "phone":        "",
            "address":      c["camara_comercio"],
            "rating":       None,
            "source":       "rues",
            "nit":          c["numero_id"],
            "rues_context": build_rues_context(c),
            "rues_data":    c,
        })

    return results


async def resolve_rues_urls(
    companies: list[dict],
    max_concurrent: int = 3,
) -> list[dict]:
    """
    Resolve website URLs for RUES companies via Bing search.
    Same pattern as resolve_secop_urls() in secop.py.
    """
    from prospector import discover_companies_bing

    sem = asyncio.Semaphore(max_concurrent)

    async def _resolve_one(company: dict) -> dict:
        async with sem:
            nombre = company["title"]
            nit = company.get("nit", "")
            query = f'"{nombre}" Colombia empresa sitio web'
            try:
                hits = await discover_companies_bing(query, "", 3)
                if hits:
                    company["url"] = hits[0]["url"]
            except Exception as e:
                logger.debug("[RUES URL resolve] %s: %s", nombre, e)

            if not company["url"]:
                company["url"] = f"https://www.rues.org.co/RM?NIT={nit}"
                company["url_is_rues_fallback"] = True

            return company

    tasks = [_resolve_one(c) for c in companies]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in resolved if isinstance(r, dict)]
