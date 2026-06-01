"""
vertical_arrendamiento.py — Aggregator for the "arrendamiento" prospecting vertical.

Activated automatically when industria_objetivo contains rental keywords.
Aggregates results from:
  1. Fincaraíz   — curated portal, inmobiliarias + particulares
  2. Mercado Libre — API-based, highest coverage of particulares
  3. OLX           — classifieds, best source for private landlords
  4. Metro Cuadrado — agency-heavy, El Tiempo Group
  5. Ciencuadras   — regional agencies

Never import this from other pipelines — use discover_arrendamiento() only
when the arrendamiento vertical is detected.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# ── Keyword detection ─────────────────────────────────────────────────────────

_ARRENDAMIENTO_KEYWORDS = {
    "arriendo", "arrendamiento", "arrendar", "arrenda",
    "inmobiliaria", "inmobiliarias", "finca raiz", "finca raíz",
    "propiedad raiz", "propiedad raíz", "propietario", "arrendador",
    "alquiler", "alquilar",
}


def is_arrendamiento_vertical(industria: str) -> bool:
    """Return True if industria_objetivo targets the rental market."""
    lower = (industria or "").lower()
    return any(kw in lower for kw in _ARRENDAMIENTO_KEYWORDS)


# ── Mercado Libre (API) ───────────────────────────────────────────────────────

_ML_SEARCH_URL = "https://api.mercadolibre.com/sites/MCO/search"
_ML_CATEGORY_RENT = "MCO1459"   # Inmuebles en arriendo — Colombia


async def _fetch_ml_listings(ciudad: str, max_results: int) -> list[dict]:
    """
    Scrape Mercado Libre inmuebles en arriendo via curl_cffi.
    ML public API requires OAuth; HTML scraping is the fallback.
    Targets: inmuebles.mercadolibre.com.co — SSR page with embedded JSON.
    """
    try:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    ciudad_slug = (ciudad or "bogota").lower().replace(" ", "-").replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u")
    url = f"https://inmuebles.mercadolibre.com.co/departamentos/arriendo/{ciudad_slug}-dc/"
    results: list[dict] = []

    try:
        async with AsyncSession(impersonate="chrome131", timeout=20) as s:
            resp = await s.get(url)
            if resp.status_code != 200:
                logger.warning("[ML] HTTP %d", resp.status_code)
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # ML embeds listing data in <script type="application/ld+json"> ItemList
        for sc in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(sc.string or "{}")
                if data.get("@type") == "ItemList":
                    for el in (data.get("itemListElement") or [])[:max_results]:
                        item = el.get("item") or {}
                        offer = (item.get("offers") or {})
                        price = offer.get("price", 0)
                        price_str = f"${price:,.0f} COP" if price else ""
                        results.append({
                            "title":        item.get("name", "Departamento en arriendo"),
                            "url":          item.get("url", ""),
                            "owner_name":   "",
                            "owner_type":   "particular",   # ML skews toward particulares
                            "is_particular": True,
                            "price":        price_str,
                            "price_amount": price,
                            "neighborhood": "",
                            "city":         ciudad.title(),
                            "source":       "mercadolibre",
                        })
                    if results:
                        break
            except Exception:
                continue

        # Fallback: parse listing cards from HTML
        if not results:
            for card in soup.find_all(class_=re.compile(r"ui-search-result", re.I))[:max_results]:
                title_el = card.find(class_=re.compile(r"title", re.I))
                price_el = card.find(class_=re.compile(r"price", re.I))
                link_el = card.find("a", href=True)
                if not link_el:
                    continue
                results.append({
                    "title":        title_el.get_text(strip=True) if title_el else "Departamento en arriendo",
                    "url":          link_el["href"],
                    "owner_name":   "",
                    "owner_type":   "particular",
                    "is_particular": True,
                    "price":        price_el.get_text(strip=True) if price_el else "",
                    "price_amount": 0,
                    "neighborhood": "",
                    "city":         ciudad.title(),
                    "source":       "mercadolibre",
                })

    except Exception as e:
        logger.warning("[ML] scrape failed: %s", e)

    logger.info("[ML] ciudad=%r → %d listings", ciudad, len(results))
    return results


def _build_ml_context(listing: dict) -> str:
    tipo = "Propietario particular" if listing.get("is_particular") else "Inmobiliaria/agencia"
    return "\n".join([
        "[Fuente: Mercado Libre Inmuebles Colombia]",
        f"{tipo}: {listing.get('owner_name') or 'No identificado'}",
        f"Inmueble en arriendo: {listing.get('neighborhood', '')} — {listing.get('city', '')}",
        f"Precio: {listing.get('price') or 'No disponible'}",
        "",
        "Anunciante activo en Mercado Libre Colombia — potencial comprador de póliza de arrendamiento.",
    ])


# ── OLX ──────────────────────────────────────────────────────────────────────

_OLX_SEARCH_URL = "https://www.olx.com.co/inmuebles_cat-501"


async def _fetch_olx_listings(ciudad: str, max_results: int) -> list[dict]:
    """
    Scrape OLX Colombia rental listings via curl_cffi.
    OLX has significant bot protection; we get as much as we can.
    """
    try:
        from curl_cffi.requests import AsyncSession
    except ImportError:
        logger.warning("[OLX] curl_cffi not available")
        return []

    ciudad_slug = (ciudad or "bogota").lower().strip()
    # OLX uses query params for city filter
    url = f"{_OLX_SEARCH_URL}/arriendo?location={ciudad_slug}"

    results: list[dict] = []
    try:
        async with AsyncSession(impersonate="chrome131", timeout=20) as s:
            resp = await s.get(url)
            if resp.status_code != 200:
                logger.warning("[OLX] HTTP %d", resp.status_code)
                return []
            html = resp.text

        # OLX embeds listing data in window.__PRELOADED_STATE__ JSON
        match = re.search(r'window\.__PRELOADED_STATE__\s*=\s*(\{.*?\});\s*</script>', html, re.DOTALL)
        if not match:
            # Fallback: parse visible listing cards from HTML
            results = _parse_olx_html_cards(html, ciudad)
            logger.info("[OLX] HTML parse fallback → %d listings", len(results))
            return results[:max_results]

        state = json.loads(match.group(1))
        listings_raw = (
            state.get("listing", {})
                 .get("listingProps", {})
                 .get("pageProps", {})
                 .get("items") or []
        )
        for item in listings_raw[:max_results]:
            title = item.get("title", "")
            item_url = item.get("url") or item.get("permalink", "")
            price_info = item.get("price") or {}
            price_value = price_info.get("value") or price_info.get("amount", 0)
            price_str = f"${price_value:,.0f} COP" if price_value else ""
            location = item.get("location") or {}

            results.append({
                "title":        title,
                "url":          f"https://www.olx.com.co{item_url}" if item_url.startswith("/") else item_url,
                "owner_name":   item.get("user", {}).get("name", ""),
                "owner_type":   "particular",   # OLX is mostly private landlords
                "is_particular": True,
                "price":        price_str,
                "price_amount": price_value,
                "neighborhood": location.get("neighbourhood", ""),
                "city":         location.get("city", ciudad),
                "source":       "olx",
            })

    except Exception as e:
        logger.warning("[OLX] scrape failed: %s", e)

    logger.info("[OLX] ciudad=%r → %d listings", ciudad, len(results))
    return results


def _parse_olx_html_cards(html: str, ciudad: str) -> list[dict]:
    """Fallback HTML parser for OLX when __PRELOADED_STATE__ is absent."""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    results = []
    # OLX listing cards have data-aut-id="itemBox"
    for card in soup.find_all(attrs={"data-aut-id": "itemBox"}):
        title_el = card.find(attrs={"data-aut-id": "itemTitle"})
        price_el = card.find(attrs={"data-aut-id": "itemPrice"})
        link_el = card.find("a", href=True)
        if not title_el or not link_el:
            continue
        title = title_el.get_text(strip=True)
        price = price_el.get_text(strip=True) if price_el else ""
        url = link_el["href"]
        if not url.startswith("http"):
            url = f"https://www.olx.com.co{url}"
        results.append({
            "title":        title,
            "url":          url,
            "owner_name":   "",
            "owner_type":   "particular",
            "is_particular": True,
            "price":        price,
            "price_amount": 0,
            "neighborhood": "",
            "city":         ciudad,
            "source":       "olx",
        })
    return results


def _build_olx_context(listing: dict) -> str:
    return "\n".join([
        "[Fuente: OLX Colombia — Clasificados de arriendo]",
        f"Anunciante: {listing.get('owner_name') or 'Particular'}",
        f"Inmueble: {listing.get('title', '')} en {listing.get('city', '')}",
        f"Precio: {listing.get('price') or 'No disponible'}",
        "",
        "Anuncio en OLX — alta probabilidad de ser propietario particular sin póliza.",
    ])


# ── Metro Cuadrado ────────────────────────────────────────────────────────────

_MC_API = "https://www.metrocuadrado.com/rest-search/search"


async def _fetch_metrocuadrado_listings(ciudad: str, max_results: int) -> list[dict]:
    """
    Scrape Metro Cuadrado via curl_cffi.
    Their REST API requires an API key; HTML scraping is the public path.
    """
    try:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    ciudad_slug = (ciudad or "bogota").lower().replace(" ", "-")
    url = f"https://www.metrocuadrado.com/arriendo/apartamentos/{ciudad_slug}/"
    results: list[dict] = []

    try:
        async with AsyncSession(impersonate="chrome131", timeout=20) as s:
            resp = await s.get(url)
            if resp.status_code != 200:
                logger.warning("[MC] HTTP %d", resp.status_code)
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")

        # Metro Cuadrado uses data-id or class patterns for listing cards
        for card in soup.find_all(class_=re.compile(r"result-card|listing-card|property-card", re.I))[:max_results]:
            title_el = card.find(class_=re.compile(r"title", re.I)) or card.find(["h2", "h3"])
            price_el = card.find(class_=re.compile(r"price|valor", re.I))
            link_el = card.find("a", href=True)
            agency_el = card.find(class_=re.compile(r"agency|company|inmobiliaria", re.I))
            if not link_el:
                continue
            href = link_el["href"]
            full_url = f"https://www.metrocuadrado.com{href}" if href.startswith("/") else href
            results.append({
                "title":        title_el.get_text(strip=True) if title_el else "Inmueble en arriendo",
                "url":          full_url,
                "owner_name":   agency_el.get_text(strip=True) if agency_el else "",
                "owner_type":   "inmobiliaria",
                "is_particular": False,
                "price":        price_el.get_text(strip=True) if price_el else "",
                "price_amount": 0,
                "neighborhood": "",
                "city":         ciudad.title(),
                "source":       "metrocuadrado",
            })

    except Exception as e:
        logger.warning("[MC] scrape failed: %s", e)

    logger.info("[MC] ciudad=%r → %d listings", ciudad, len(results))
    return results


# ── Ciencuadras ───────────────────────────────────────────────────────────────

_CC_URL = "https://www.ciencuadras.com/arriendo"


async def _fetch_ciencuadras_listings(ciudad: str, max_results: int) -> list[dict]:
    """
    Scrape Ciencuadras listings via Angular SSR HTML.
    Cards are <article class="detach card result" data-qa-id="cc-rs-rs-card_property_{id}">.
    """
    try:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    ciudad_slug = (ciudad or "bogota").lower().replace(" ", "-")
    url = f"{_CC_URL}/{ciudad_slug}"
    results: list[dict] = []

    try:
        async with AsyncSession(impersonate="chrome131", timeout=20) as s:
            resp = await s.get(url)
            if resp.status_code != 200:
                logger.warning("[CC] HTTP %d", resp.status_code)
                return []
            html = resp.text

        soup = BeautifulSoup(html, "html.parser")
        for card in soup.find_all("article", class_=re.compile("result"))[:max_results]:
            qa_id = card.get("data-qa-id", "")
            prop_id_m = re.search(r"(\d+)$", qa_id)
            prop_id = prop_id_m.group(1) if prop_id_m else ""

            title_el = card.find(class_=re.compile(r"title", re.I)) or card.find(["h2", "h3", "h4"])
            price_raw = ""
            price_el = card.find(class_=re.compile(r"price", re.I))
            if price_el:
                price_raw = price_el.get_text(strip=True)
            else:
                pm = re.search(r"\$[\d.,]+", card.get_text())
                if pm:
                    price_raw = pm.group(0)

            results.append({
                "title":        title_el.get_text(strip=True) if title_el else "Inmueble en arriendo",
                "url":          f"https://www.ciencuadras.com/arriendo/{ciudad_slug}/{prop_id}" if prop_id else url,
                "owner_name":   "",
                "owner_type":   "inmobiliaria",
                "is_particular": False,
                "price":        price_raw,
                "price_amount": 0,
                "neighborhood": "",
                "city":         ciudad.title(),
                "source":       "ciencuadras",
            })

    except Exception as e:
        logger.warning("[CC] failed: %s", e)

    logger.info("[CC] ciudad=%r → %d listings", ciudad, len(results))
    return results


# ── Main aggregator ───────────────────────────────────────────────────────────

_SOURCE_QUOTA = 0.4   # each portal gets up to 40% of max_results to ensure diversity


async def discover_arrendamiento(
    ciudad: str,
    max_results: int = 20,
    include_particulares: bool = True,
    include_inmobiliarias: bool = True,
    sources: Optional[list[str]] = None,
) -> list[dict]:
    """
    Aggregate rental leads from all arrendamiento portals.

    Args:
        ciudad:                  Target city
        max_results:             Total results cap across all sources
        include_particulares:    Include private landlord listings
        include_inmobiliarias:   Include real estate agency listings
        sources:                 Subset of sources to use (default: all)

    Returns list of dicts with unified schema + portal-specific context field.
    """
    all_sources = sources or ["fincaraiz", "mercadolibre", "olx", "metrocuadrado", "ciencuadras"]
    per_source = max(5, int(max_results * _SOURCE_QUOTA))

    tasks = {}
    if "fincaraiz" in all_sources:
        from fincaraiz_signal import fetch_fincaraiz_listings
        tasks["fincaraiz"] = fetch_fincaraiz_listings(
            ciudad=ciudad,
            tipo_inmueble="apartamentos",
            max_listings=per_source,
            max_pages=2,
        )
    if "mercadolibre" in all_sources:
        tasks["mercadolibre"] = _fetch_ml_listings(ciudad, per_source)
    if "olx" in all_sources and include_particulares:
        tasks["olx"] = _fetch_olx_listings(ciudad, per_source)
    if "metrocuadrado" in all_sources and include_inmobiliarias:
        tasks["metrocuadrado"] = _fetch_metrocuadrado_listings(ciudad, per_source)
    if "ciencuadras" in all_sources and include_inmobiliarias:
        tasks["ciencuadras"] = _fetch_ciencuadras_listings(ciudad, per_source)

    raw_results: dict[str, list[dict]] = {}
    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for source_name, result in zip(tasks.keys(), gathered):
        if isinstance(result, Exception):
            logger.warning("[arrendamiento] %s failed: %s", source_name, result)
            raw_results[source_name] = []
        else:
            raw_results[source_name] = result or []

    # Merge, deduplicate by owner_name+neighborhood, respect filters
    merged: list[dict] = []
    seen_keys: set[str] = set()

    for source_name, items in raw_results.items():
        for item in items:
            is_p = item.get("is_particular", False)
            if is_p and not include_particulares:
                continue
            if not is_p and not include_inmobiliarias:
                continue

            # Dedup key: owner_name + neighborhood (loose dedup across portals)
            owner = (item.get("owner_name") or "").strip().lower()
            barrio = (item.get("neighborhood") or "").strip().lower()
            url = (item.get("url") or "").strip()
            dedup_key = f"{owner}|{barrio}" if owner else url
            if dedup_key and dedup_key in seen_keys:
                continue
            if dedup_key:
                seen_keys.add(dedup_key)

            # Normalize to pipeline-compatible format
            title = item.get("owner_name") or item.get("title") or f"Arrendador en {item.get('neighborhood', ciudad)}"
            context_fn = {
                "fincaraiz":     lambda i: _build_fincaraiz_context(i),
                "mercadolibre":  lambda i: _build_ml_context(i),
                "olx":           lambda i: _build_olx_context(i),
                "metrocuadrado": lambda i: _build_generic_context(i, "Metro Cuadrado"),
                "ciencuadras":   lambda i: _build_generic_context(i, "Ciencuadras"),
            }.get(source_name, lambda i: "")

            merged.append({
                "title":                  title,
                "url":                    url,
                "phone":                  "",
                "address":                item.get("neighborhood", ""),
                "rating":                 None,
                "source":                 source_name,
                "is_particular":          is_p,
                "arrendamiento_context":  context_fn(item),
                "arrendamiento_data":     item,
            })

            if len(merged) >= max_results:
                break
        if len(merged) >= max_results:
            break

    particulares = sum(1 for r in merged if r.get("is_particular"))
    logger.info(
        "[arrendamiento] ciudad=%r total=%d particulares=%d inmobiliarias=%d sources=%s",
        ciudad, len(merged), particulares, len(merged) - particulares,
        {s: len(v) for s, v in raw_results.items()},
    )
    return merged


def _build_fincaraiz_context(item: dict) -> str:
    from fincaraiz_signal import build_fincaraiz_context
    data = item.get("arrendamiento_data") or item
    return build_fincaraiz_context(data)


def _build_generic_context(item: dict, portal: str) -> str:
    tipo = "Propietario particular" if item.get("is_particular") else "Inmobiliaria"
    return "\n".join([
        f"[Fuente: {portal}]",
        f"{tipo}: {item.get('owner_name') or 'No identificado'}",
        f"Inmueble en {item.get('neighborhood', '')} — {item.get('city', '')}",
        f"Precio: {item.get('price') or 'No disponible'}",
        "",
        f"Anunciante activo en {portal} — prospecto para póliza de arrendamiento.",
    ])
