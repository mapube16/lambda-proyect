"""
fincaraiz_signal.py — Fincaraíz rental listing discovery source.

Scrapes fincaraiz.com.co to find:
  - Inmobiliarias with active rental portfolios (B2B leads for insurance)
  - Individual propietarios (particulares) listing their own properties

Data extraction:
  All listing data is embedded in the Next.js __NEXT_DATA__ script tag on
  the search results page. No detail page fetching needed.

  Key fields per listing:
    owner.name      — agency or private owner name
    owner.type      — "inmobiliaria" | "particular"
    owner.particular — bool
    owner.address   — agency/owner address
    price.amount    — rent price in COP
    address         — property address
    locations.*     — neighborhood, city data
    m2Built         — area in m2
    bedrooms        — bedrooms count

  Phone numbers are masked in the listing data. For inmobiliarias, we
  resolve the actual phone via Serper (same as SECOP/RUES resolution).
  For particulares, the listing URL is the best contact point.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_BASE_URL = "https://www.fincaraiz.com.co"
_FETCH_TIMEOUT = 20

# Maps property type keywords to Fincaraíz URL segments
_TIPO_MAP: dict[str, str] = {
    "apartamento":  "apartamentos",
    "apartamentos": "apartamentos",
    "casa":         "casas",
    "casas":        "casas",
    "oficina":      "oficinas",
    "oficinas":     "oficinas",
    "local":        "locales",
    "locales":      "locales",
    "bodega":       "bodegas",
    "bodegas":      "bodegas",
    "lote":         "lotes",
    "lotes":        "lotes",
}

# Ciudad → URL slug used by Fincaraíz
_CIUDAD_SLUG: dict[str, str] = {
    "bogota":       "bogota",
    "bogotá":       "bogota",
    "medellin":     "medellin",
    "medellín":     "medellin",
    "cali":         "cali",
    "barranquilla": "barranquilla",
    "cartagena":    "cartagena",
    "bucaramanga":  "bucaramanga",
    "pereira":      "pereira",
    "manizales":    "manizales",
    "cucuta":       "cucuta",
    "cúcuta":       "cucuta",
    "ibague":       "ibague",
    "ibagué":       "ibague",
    "santa marta":  "santa-marta",
    "santa-marta":  "santa-marta",
}


def _city_slug(ciudad: str) -> str:
    key = (ciudad or "bogota").lower().strip()
    for src, tgt in [("á","a"),("é","e"),("í","i"),("ó","o"),("ú","u")]:
        key = key.replace(src, tgt)
    return _CIUDAD_SLUG.get(key, key.replace(" ", "-"))


def _search_url(ciudad: str, tipo: str = "apartamentos", page: int = 1) -> str:
    tipo_slug = _TIPO_MAP.get(tipo.lower(), "apartamentos")
    city_slug = _city_slug(ciudad)
    base = f"{_BASE_URL}/arriendo/{tipo_slug}/{city_slug}/"
    if page > 1:
        base += f"?pagina={page}"
    return base


async def _fetch_html(url: str, timeout: int = _FETCH_TIMEOUT) -> Optional[str]:
    try:
        from curl_cffi.requests import AsyncSession, RequestsError
        async with AsyncSession(impersonate="chrome131", allow_redirects=True, timeout=timeout) as s:
            resp = await s.get(url)
            if resp.status_code == 200:
                return resp.text
            logger.warning("[Fincaraíz] HTTP %d for %s", resp.status_code, url)
            return None
    except Exception as e:
        logger.warning("[Fincaraíz] fetch error %s: %s", url, e)
        return None


def _parse_search_page(html: str) -> tuple[list[dict], bool]:
    """
    Extract all listings and pagination info from a search results page.
    Returns (listings, has_more_pages).
    """
    try:
        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if not match:
            return [], False
        next_data = json.loads(match.group(1))
        search_fast = (
            next_data
            .get("props", {})
            .get("pageProps", {})
            .get("fetchResult", {})
            .get("searchFast", {})
        )
        raw_listings = search_fast.get("data") or []
        paginator = search_fast.get("paginatorInfo") or {}
        has_more = bool(paginator.get("hasMorePages", False))
        return raw_listings, has_more
    except Exception as e:
        logger.warning("[Fincaraíz] __NEXT_DATA__ parse error: %s", e)
        return [], False


def _normalize_listing(raw: dict, ciudad: str, tipo: str) -> dict:
    """Convert a raw Fincaraíz listing dict to a clean signal dict."""
    owner = raw.get("owner") or {}
    price_info = raw.get("price") or {}
    locations = raw.get("locations") or {}
    loc_main = locations.get("location_main") or {}

    listing_id = str(raw.get("id") or "")
    link = raw.get("link") or f"/{listing_id}"
    url = link if link.startswith("http") else f"{_BASE_URL}{link}"

    owner_name = (owner.get("name") or "").strip()
    owner_type = (owner.get("type") or "").lower().strip()
    is_particular = bool(owner.get("particular")) or owner_type == "particular"
    owner_address = (owner.get("address") or "").strip()

    neighborhood = (loc_main.get("name") or "").strip()

    price_amount = price_info.get("amount") or 0
    price_str = f"${price_amount:,.0f} COP" if price_amount else ""

    return {
        "listing_id":    listing_id,
        "url":           url,
        "owner_name":    owner_name,
        "owner_type":    owner_type,    # "inmobiliaria" | "particular" | ""
        "is_particular": is_particular,
        "owner_address": owner_address,
        "price":         price_str,
        "price_amount":  price_amount,
        "neighborhood":  neighborhood,
        "city":          ciudad,
        "property_type": tipo,
        "address":       (raw.get("address") or "").strip(),
        "area_m2":       raw.get("m2Built") or raw.get("m2") or 0,
        "bedrooms":      raw.get("bedrooms") or raw.get("rooms") or 0,
        "stratum":       raw.get("stratum") or 0,
        "source":        "fincaraiz",
    }


async def fetch_fincaraiz_listings(
    ciudad: str,
    tipo_inmueble: str = "apartamentos",
    only_particular: bool = False,
    max_listings: int = 42,
    max_pages: int = 3,
) -> list[dict]:
    """
    Fetch rental listings from Fincaraíz.

    All data is extracted from the __NEXT_DATA__ JSON on search result pages.
    No detail page fetching required.

    Args:
        ciudad:          City (e.g. 'bogota', 'medellin')
        tipo_inmueble:   Property type ('apartamentos', 'casas', 'oficinas', etc.)
        only_particular: If True, return only private owner listings
        max_listings:    Max listings to return
        max_pages:       Max search result pages to scrape (21 listings/page)

    Returns list of dicts with owner, price, location, property details.
    """
    results: list[dict] = []
    seen_ids: set[str] = set()

    for page_num in range(1, max_pages + 1):
        if len(results) >= max_listings:
            break

        url = _search_url(ciudad, tipo_inmueble, page_num)
        logger.info("[Fincaraíz] Fetching page %d: %s", page_num, url)

        html = await _fetch_html(url)
        if not html:
            logger.warning("[Fincaraíz] Empty response on page %d", page_num)
            break

        raw_listings, has_more = _parse_search_page(html)
        if not raw_listings:
            logger.info("[Fincaraíz] No listings on page %d — stopping", page_num)
            break

        for raw in raw_listings:
            listing_id = str(raw.get("id") or "")
            if listing_id in seen_ids:
                continue
            seen_ids.add(listing_id)

            listing = _normalize_listing(raw, ciudad, tipo_inmueble)

            if only_particular and not listing["is_particular"]:
                continue

            results.append(listing)
            if len(results) >= max_listings:
                break

        logger.info(
            "[Fincaraíz] Page %d: %d raw → %d kept (total: %d, has_more: %s)",
            page_num, len(raw_listings), len(results), len(results), has_more,
        )

        if not has_more:
            break
        await asyncio.sleep(1.0)  # polite rate limiting between pages

    logger.info(
        "[Fincaraíz] ciudad=%r tipo=%r only_particular=%s → %d listings",
        ciudad, tipo_inmueble, only_particular, len(results),
    )
    return results


def build_fincaraiz_context(listing: dict) -> str:
    """Human-readable summary for LLM analyst injection."""
    tipo = "Propietario particular" if listing.get("is_particular") else "Inmobiliaria"
    lines = [
        "[Fuente: Fincaraíz — Portal de Arrendamientos Colombia]",
        f"{tipo}: {listing.get('owner_name') or 'No identificado'}",
        f"Inmueble: {listing.get('property_type', '')} en {listing.get('neighborhood', '')} — {listing.get('city', '')}",
        f"Dirección: {listing.get('address') or listing.get('owner_address') or 'No disponible'}",
        f"Precio arriendo: {listing.get('price') or 'No disponible'}",
        f"Área: {listing.get('area_m2', 0)} m²  |  Habitaciones: {listing.get('bedrooms', 0)}  |  Estrato: {listing.get('stratum', 0)}",
        "",
        "Este anunciante tiene un inmueble activo en arriendo en Colombia.",
        "Alta probabilidad de necesitar póliza de arrendamiento.",
    ]
    return "\n".join(lines)


async def discover_via_fincaraiz(
    ciudad: str,
    tipo_inmueble: str = "apartamentos",
    only_particular: bool = False,
    max_results: int = 20,
) -> list[dict]:
    """
    Discovery source adapter for the prospector pipeline.

    For inmobiliarias: resolves their website via Serper for pipeline analysis.
    For particulares:  returns the Fincaraíz listing URL directly.
    """
    listings = await fetch_fincaraiz_listings(
        ciudad=ciudad,
        tipo_inmueble=tipo_inmueble,
        only_particular=only_particular,
        max_listings=max_results,
    )

    results = []
    for listing in listings:
        title = listing.get("owner_name") or f"Propietario en {listing.get('neighborhood', listing.get('city', ''))}"
        results.append({
            "title":             title,
            "url":               listing["url"],
            "phone":             "",  # masked in portal — resolved via Serper for agencies
            "address":           (listing.get("address") or listing.get("owner_address") or "").strip(),
            "rating":            None,
            "source":            "fincaraiz",
            "is_particular":     listing.get("is_particular"),
            "fincaraiz_context": build_fincaraiz_context(listing),
            "fincaraiz_data":    listing,
        })

    return results
