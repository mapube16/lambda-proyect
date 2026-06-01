"""
test_fincaraiz_pipeline.py — Integration tests for the Fincaraíz discovery pipeline.

Run:
    cd backend
    python -m pytest tests/test_fincaraiz_pipeline.py -v -s

Tests go from innermost layer (HTTP fetch) to outermost (discover_companies()).
Each stage tells you exactly where a failure is.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pytest_asyncio


# ── Stage 1: Raw HTTP fetch ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fincaraiz_fetch_returns_html():
    """Stage 1 — curl_cffi can reach fincaraiz.com.co and get a 200."""
    from fincaraiz_signal import _fetch_html
    html = await _fetch_html("https://www.fincaraiz.com.co/arriendo/apartamentos/bogota/", timeout=20)
    assert html is not None, "fetch returned None — curl_cffi blocked or timeout"
    assert len(html) > 1000, f"HTML suspiciously short: {len(html)} bytes"
    print(f"\n  OK HTML received: {len(html):,} bytes")


# ── Stage 2: __NEXT_DATA__ parse ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fincaraiz_parse_extracts_listings():
    """Stage 2 — __NEXT_DATA__ JSON is present and contains listings."""
    from fincaraiz_signal import _fetch_html, _parse_search_page
    html = await _fetch_html("https://www.fincaraiz.com.co/arriendo/apartamentos/bogota/", timeout=20)
    assert html, "fetch failed — can't test parsing"
    listings, has_more = _parse_search_page(html)
    print(f"\n  OK Parsed {len(listings)} listings, has_more={has_more}")
    assert len(listings) > 0, (
        "__NEXT_DATA__ present but no listings found — "
        "site structure may have changed"
    )
    first = listings[0]
    print(f"  OK First listing keys: {list(first.keys())}")
    # Check expected fields exist
    assert "owner" in first or "id" in first, f"Unexpected listing shape: {first}"


# ── Stage 3: Full fetch_fincaraiz_listings ────────────────────────────────────

@pytest.mark.asyncio
async def test_fetch_fincaraiz_listings_bogota():
    """Stage 3 — fetch_fincaraiz_listings returns normalized dicts."""
    from fincaraiz_signal import fetch_fincaraiz_listings
    results = await fetch_fincaraiz_listings(
        ciudad="bogota",
        tipo_inmueble="apartamentos",
        max_listings=5,
        max_pages=1,
    )
    print(f"\n  OK Got {len(results)} listings")
    assert len(results) > 0, "No listings returned — check scraper logic"
    for r in results:
        print(f"    [{r['owner_type']}] {r['owner_name']} | {r['price']} | {r['neighborhood']}")
        assert "owner_name" in r
        assert "url" in r
        assert r["source"] == "fincaraiz"


# ── Stage 4: discover_via_fincaraiz (pipeline adapter) ───────────────────────

@pytest.mark.asyncio
async def test_discover_via_fincaraiz_returns_pipeline_format():
    """Stage 4 — discover_via_fincaraiz returns dicts compatible with add()."""
    from fincaraiz_signal import discover_via_fincaraiz
    results = await discover_via_fincaraiz(
        ciudad="bogota",
        tipo_inmueble="apartamentos",
        max_results=5,
    )
    print(f"\n  OK Pipeline adapter: {len(results)} results")
    assert len(results) > 0, "No results from discover_via_fincaraiz"
    for r in results:
        print(f"    {r['title']} → {r['url'][:60]}")
        # These fields are required by add() in discover_companies()
        assert "title" in r, "Missing 'title'"
        assert "url" in r,   "Missing 'url'"
        assert "source" in r, "Missing 'source'"
        assert r["source"] == "fincaraiz"


# ── Stage 5: discover_companies() with use_fincaraiz=True ────────────────────

@pytest.mark.asyncio
async def test_discover_companies_fincaraiz_only():
    """Stage 5 — discover_companies() with source_priority=signal_only + use_fincaraiz."""
    from prospector import discover_companies
    results = await discover_companies(
        industria="arrendamiento",
        ciudad="bogota",
        max_results=5,
        use_fincaraiz=True,
        source_priority="signal_only",  # skip Serper
    )
    print(f"\n  OK discover_companies() signal_only+fincaraiz: {len(results)} results")
    assert len(results) > 0, (
        "discover_companies() returned 0 results with use_fincaraiz=True.\n"
        "Check: is use_fincaraiz being passed? Is add() hitting the max_results cap?"
    )
    sources = {r.get("source") for r in results}
    print(f"  OK Sources in results: {sources}")
    assert "fincaraiz" in sources, f"Expected fincaraiz in sources, got: {sources}"


# ── Stage 6: discover_companies() Serper + Fincaraíz combined ────────────────

@pytest.mark.asyncio
async def test_discover_companies_serper_plus_fincaraiz():
    """Stage 6 — Fincaraíz supplements Serper results (default mode)."""
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        pytest.skip("SERPER_API_KEY not set — skipping combined test")

    from prospector import discover_companies
    results = await discover_companies(
        industria="arrendamiento",
        ciudad="bogota",
        max_results=10,
        use_fincaraiz=True,
        source_priority="serper",
    )
    print(f"\n  OK Combined Serper+Fincaraíz: {len(results)} results")
    sources = {r.get("source", "unknown") for r in results}
    print(f"  OK Sources present: {sources}")
    assert len(results) > 0
