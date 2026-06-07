"""
secop.py — SECOP II discovery source for the B2B prospecting pipeline.

Queries the Colombian government's Open Data API (datos.gov.co) to find
companies that have won public contracts (proveedores adjudicados).

No authentication required — it's a public REST API (Socrata/SODA).

Endpoint: SECOP II — Contratos
  https://www.datos.gov.co/resource/jbjy-vk9h.json
"""
from __future__ import annotations

import asyncio
import logging
import re
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

SECOP_CONTRATOS_URL = "https://www.datos.gov.co/resource/jbjy-vk9h.json"

# Max records to fetch from SECOP before deduplication (over-fetch for better dedup)
_FETCH_MULTIPLIER = 6
_MAX_FETCH = 1000


async def fetch_secop_providers(
    keyword: str,
    ciudad: Optional[str] = None,
    max_results: int = 50,
) -> list[dict]:
    """
    Query SECOP II contracts and return unique winning companies (deduplicated by NIT).

    Args:
        keyword:     Industry or topic to match against contract descriptions
                     (e.g. 'transporte', 'software', 'consultoria tecnologia')
        ciudad:      Optional municipality to filter by (e.g. 'BOGOTA', 'MEDELLIN')
        max_results: Max unique companies to return

    Returns list of dicts:
        {
          "nombre":        str,   # proveedor_adjudicado
          "nit":           str,   # documento_proveedor
          "contratos":     int,   # number of contracts found
          "valor_total":   float, # sum of contract values (COP)
          "ultimo_objeto": str,   # latest contract description (truncated)
          "municipio":     str,
          "departamento":  str,
        }
    """
    limit = min(max_results * _FETCH_MULTIPLIER, _MAX_FETCH)

    params: dict = {
        "$limit": limit,
        "$order": "fecha_de_firma DESC",
        "$select": (
            "proveedor_adjudicado,"
            "documento_proveedor,"
            "objeto_del_contrato,"
            "valor_del_contrato,"
            "nombre_entidad,"
            "departamento,"
            "ciudad,"
            "nombre_representante_legal,"
            "domicilio_representante_legal"
        ),
    }

    conditions: list[str] = ["tipodocproveedor='NIT'"]
    if keyword and keyword.strip():
        kw = keyword.strip().upper()
        conditions.append(f"upper(objeto_del_contrato) like '%{kw}%'")
    if ciudad and ciudad.strip():
        c = ciudad.strip().upper()
        conditions.append(f"upper(ciudad) like '%{c}%'")

    if conditions:
        params["$where"] = " AND ".join(conditions)

    try:
        async with httpx.AsyncClient(timeout=45) as client:
            resp = await client.get(SECOP_CONTRATOS_URL, params=params)
            resp.raise_for_status()
            rows = resp.json()
    except Exception as e:
        print(f"[SECOP] API error: {e}")
        return []

    if not isinstance(rows, list):
        print(f"[SECOP] Unexpected response: {type(rows)}")
        return []

    # Deduplicate by NIT and accumulate contract stats
    seen: dict[str, dict] = {}
    for row in rows:
        nit    = (row.get("documento_proveedor") or "").strip()
        nombre = (row.get("proveedor_adjudicado") or "").strip()

        if not nombre or not nit:
            continue
        if _is_individual_person(nombre, nit):
            continue

        if nit not in seen:
            seen[nit] = {
                "nombre":               nombre,
                "nit":                  nit,
                "contratos":            0,
                "valor_total":          0.0,
                "ultimo_objeto":        "",
                "ciudad":               (row.get("ciudad") or "").strip().title(),
                "departamento":         (row.get("departamento") or "").strip().title(),
                "representante_legal":  (row.get("nombre_representante_legal") or "").strip().title(),
                "domicilio":            (row.get("domicilio_representante_legal") or "").strip(),
            }

        seen[nit]["contratos"] += 1

        try:
            valor = float(row.get("valor_del_contrato") or 0)
            seen[nit]["valor_total"] += valor
        except (ValueError, TypeError):
            pass

        if not seen[nit]["ultimo_objeto"]:
            obj = (row.get("objeto_del_contrato") or "").strip()
            seen[nit]["ultimo_objeto"] = obj[:250]
        # Keep most complete representative info
        if not seen[nit]["representante_legal"]:
            seen[nit]["representante_legal"] = (row.get("nombre_representante_legal") or "").strip().title()
        if not seen[nit]["domicilio"]:
            val = (row.get("domicilio_representante_legal") or "").strip()
            if val and val.lower() not in ("no definido", "sin descripcion"):
                seen[nit]["domicilio"] = val

    # Sort by number of contracts (most active contractors first)
    results = sorted(seen.values(), key=lambda x: x["contratos"], reverse=True)
    logger.info("[SECOP] keyword=%r ciudad=%r -> %d rows -> %d empresas unicas", keyword, ciudad, len(rows), len(results))
    return results[:max_results]


def _is_individual_person(nombre: str, nit: str) -> bool:
    """Heuristic: filter out natural persons (cédula numbers, not NITs)."""
    # NITs are typically 9 digits; cédulas are shorter
    digits = re.sub(r"\D", "", nit)
    if len(digits) < 9:
        return True
    # Names with common person patterns (Comma = "Apellido, Nombre" format)
    if "," in nombre and len(nombre.split(",")) == 2:
        parts = nombre.split(",")
        # If both parts are single words it's likely a person
        if all(len(p.strip().split()) <= 2 for p in parts):
            return True
    return False


def build_secop_context(provider: dict) -> str:
    """
    Build a human-readable summary of SECOP data for injection into the
    analyst prompt. This supplements (or replaces) web scrape content.
    """
    valor_fmt = f"${provider['valor_total']:,.0f} COP" if provider["valor_total"] else "N/D"
    lines = [
        f"[Fuente: SECOP II — Contratación Pública Colombia]",
        f"Empresa: {provider['nombre']}",
        f"NIT: {provider['nit']}",
        f"Contratos públicos ganados: {provider['contratos']}",
        f"Valor total contratado: {valor_fmt}",
        f"Último objeto de contrato: {provider['ultimo_objeto']}",
        f"Ciudad: {provider['ciudad']}, {provider['departamento']}",
        f"Representante legal: {provider.get('representante_legal') or 'No disponible'}",
        f"Domicilio: {provider.get('domicilio') or 'No disponible'}",
        "",
        "Esta empresa es un proveedor verificado del Estado colombiano.",
        "Tiene capacidad presupuestaria y experiencia en licitaciones.",
    ]
    return "\n".join(lines)


async def discover_companies_secop(
    industria: str,
    ciudad: str,
    max_results: int,
) -> list[dict]:
    """
    Discovery source for the prospector pipeline.
    Returns company dicts in the same format as discover_companies_gmaps/bing,
    with an extra 'secop_context' key for analyst enrichment.

    NOTE: SECOP doesn't have website URLs, so 'url' is set to a placeholder.
    The caller (prospector) should attempt URL resolution via Bing/DDG before
    passing to analyze_company.
    """
    providers = await fetch_secop_providers(
        keyword=industria,
        ciudad=ciudad if ciudad.lower() not in ("colombia", "") else None,
        max_results=max_results,
    )

    results = []
    for p in providers:
        results.append({
            "title":         p["nombre"],
            "url":           "",          # resolved later via Bing/DDG
            "phone":         "",
            "address":       f"{p['ciudad']}, {p['departamento']}",
            "rating":        None,
            "source":        "secop",
            "nit":           p["nit"],
            "secop_context": build_secop_context(p),
            "secop_data":    p,
        })

    return results


async def resolve_secop_urls(
    companies: list[dict],
    max_concurrent: int = 3,
) -> list[dict]:
    """
    For SECOP companies without a URL, attempt to find their website via Bing.
    Companies where no URL is found get a synthetic URL pointing to their
    SECOP profile page so the pipeline can still process them.
    """
    from prospector import discover_companies_bing

    sem = asyncio.Semaphore(max_concurrent)
    resolved = []

    async def _resolve_one(company: dict) -> dict:
        async with sem:
            nombre = company["title"]
            nit    = company.get("nit", "")
            query  = f'"{nombre}" NIT {nit} Colombia empresa sitio web'
            try:
                hits = await discover_companies_bing(query, "", 3)
                if hits:
                    company["url"] = hits[0]["url"]
                    company["title_override"] = hits[0].get("title", nombre)
            except Exception as e:
                print(f"[SECOP URL resolve] {nombre}: {e}")

            if not company["url"]:
                # Fallback: encode a SECOP search URL so analyst at least has NIT
                company["url"] = (
                    f"https://www.datos.gov.co/resource/jbjy-vk9h.json"
                    f"?documento_proveedor={nit}"
                )
                company["url_is_secop_fallback"] = True

            return company

    tasks = [_resolve_one(c) for c in companies]
    resolved = await asyncio.gather(*tasks, return_exceptions=True)
    return [r for r in resolved if isinstance(r, dict)]
