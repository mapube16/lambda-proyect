"""
vertical_arrendamiento.py — Aggregator for the "arrendamiento" prospecting vertical.

Activated automatically when industria_objetivo contains rental keywords.

Portal status (2026-05-31):
  WORKING:
    Fincaraíz      — curl_cffi + __NEXT_DATA__ JSON. Inmobiliarias dominan; particulares <5%.
    Ciencuadras    — curl_cffi + BeautifulSoup card parser. Agencies only.
    OLX            — curl_cffi scraper. Best source of particulares. DNS blocked in local
                     Windows dev (asyncio Proactor); works fine on Railway (Linux).

  BLOCKED (require auth / SPA):
    Mercado Libre  — Pure React CSR. Public API requires OAuth since 2025-Q4.
                     Implemented as Serper-based fallback: search site:inmuebles.mercadolibre.com.co
                     via Serper and parse the individual SSR listing pages.
    Metro Cuadrado — Next.js App Router + REST API requires x-api-key (El Tiempo Group).
                     Disabled — returns 401 without a partner key.

Never import this from other pipelines.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
import os

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
    Mercado Libre inmuebles — via Serper site-search fallback.

    ML's public API requires OAuth (blocked since 2025-Q4) and their search
    results page is pure React CSR with no SSR data. Strategy:
    1. Use Serper to search site:inmuebles.mercadolibre.com.co for rental listings.
    2. Each result URL is a listing page that IS server-rendered (SSR) with ld+json.
    3. Scrape 3-5 listing pages in parallel to extract owner + price.

    Requires SERPER_API_KEY. Returns empty list if key not set.
    """
    import os
    serper_key = os.getenv("SERPER_API_KEY", "")
    if not serper_key:
        logger.info("[ML] SERPER_API_KEY not set — skipping ML via Serper")
        return []

    try:
        from curl_cffi.requests import AsyncSession
        from bs4 import BeautifulSoup
    except ImportError:
        return []

    ciudad_q = (ciudad or "Bogota").strip().title()
    query = f'site:inmuebles.mercadolibre.com.co departamento arriendo {ciudad_q}'
    results: list[dict] = []

    # Step 1: Serper search for ML listing URLs
    try:
        async with AsyncSession(impersonate="chrome131", timeout=15) as s:
            serper_resp = await s.post(
                "https://google.serper.dev/search",
                json={"q": query, "gl": "co", "hl": "es", "num": min(max_results * 2, 20)},
                headers={"X-API-KEY": serper_key, "Content-Type": "application/json"},
            )
            serper_resp.raise_for_status()
            serper_data = serper_resp.json()
    except Exception as e:
        logger.warning("[ML/Serper] search failed: %s", e)
        return []

    listing_urls = [
        r["link"] for r in serper_data.get("organic", [])
        if "inmuebles.mercadolibre.com.co" in r.get("link", "")
        and "/MLM-" in r.get("link", "") or "/MCO-" in r.get("link", "")
    ][:min(max_results, 8)]

    if not listing_urls:
        logger.info("[ML/Serper] no listing URLs from Serper")
        return []

    # Step 2: Scrape individual listing pages (SSR, have ld+json data)
    sem = asyncio.Semaphore(3)

    async def _scrape_listing(url: str) -> Optional[dict]:
        async with sem:
            try:
                async with AsyncSession(impersonate="chrome131", timeout=12) as s:
                    r = await s.get(url)
                    if r.status_code != 200:
                        return None
                    soup = BeautifulSoup(r.text, "html.parser")

                # Extract from ld+json Product schema
                for sc in soup.find_all("script", type="application/ld+json"):
                    try:
                        d = json.loads(sc.string or "{}")
                        if d.get("@type") in ("Product", "Offer", "RealEstateListing"):
                            offer = d.get("offers") or {}
                            price = offer.get("price", 0)
                            seller = d.get("seller") or d.get("brand") or {}
                            return {
                                "title":        d.get("name", "Departamento en arriendo"),
                                "url":          url,
                                "owner_name":   seller.get("name", ""),
                                "owner_type":   "particular",
                                "is_particular": True,
                                "price":        f"${float(price):,.0f} COP" if price else "",
                                "price_amount": float(price) if price else 0,
                                "neighborhood": "",
                                "city":         ciudad.title(),
                                "source":       "mercadolibre",
                            }
                    except Exception:
                        continue

                # Fallback: extract from page title + meta
                title_el = soup.find("h1")
                price_el = soup.find(class_=re.compile(r"price", re.I))
                return {
                    "title":        title_el.get_text(strip=True) if title_el else "Departamento en arriendo",
                    "url":          url,
                    "owner_name":   "",
                    "owner_type":   "particular",
                    "is_particular": True,
                    "price":        price_el.get_text(strip=True) if price_el else "",
                    "price_amount": 0,
                    "neighborhood": "",
                    "city":         ciudad.title(),
                    "source":       "mercadolibre",
                }
            except Exception as e:
                logger.debug("[ML] listing scrape failed %s: %s", url, e)
                return None

    scraped = await asyncio.gather(*[_scrape_listing(u) for u in listing_urls])
    results = [r for r in scraped if r is not None][:max_results]

    logger.info("[ML/Serper] ciudad=%r → %d listings from %d URLs", ciudad, len(results), len(listing_urls))
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
    Metro Cuadrado — DISABLED.
    REST API requires x-api-key (El Tiempo Group partner key).
    HTML search results page is Next.js App Router with no SSR data (skeleton placeholders).
    Re-enable when API key is available via partner agreement.
    """
    logger.debug("[MC] disabled — requires partner API key")
    return []


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
    all_sources = sources or ["fincaraiz", "mercadolibre", "olx", "ciencuadras"]
    # metrocuadrado excluded by default — requires partner API key
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
