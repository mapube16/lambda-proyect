"""
scan_domains.py — Domain quality scanner for the prospecting pipeline.

Runs a discovery query, quick-tests each URL (1 request, no retries),
classifies the result, and prints a table + ready-to-paste blacklist snippet.

Usage (from backend/):
    python scan_domains.py --industria "marketing digital" --ciudad "Bogotá"
    python scan_domains.py --industria "logistica" --ciudad "Medellin" --max 30
"""
import argparse
import asyncio
import os
import sys
from urllib.parse import urlparse

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# ── Pull blacklists from prospector without running the full pipeline ──────────
sys.path.insert(0, os.path.dirname(__file__))
from prospector import (
    BLOCKED_DOMAINS,
    LOW_QUALITY_DISCOVERY_DOMAINS,
    LOW_QUALITY_DOMAIN_SUFFIXES,
    LOW_QUALITY_PATH_MARKERS,
    _is_low_quality_candidate,
    discover_companies,
)

GMAPS_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")

# How long to wait for a single status-check request
_CHECK_TIMEOUT = 8

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/123.0.0.0 Safari/537.36"
)


async def _quick_status(client: httpx.AsyncClient, url: str) -> int:
    """Return HTTP status code for url with a single HEAD (fallback GET)."""
    try:
        r = await client.head(url, headers={"User-Agent": _UA}, follow_redirects=True)
        if r.status_code == 405:
            r = await client.get(url, headers={"User-Agent": _UA}, follow_redirects=True)
        return r.status_code
    except Exception:
        return 0


def _domain_of(url: str) -> str:
    return urlparse(url).netloc.lower().replace("www.", "")


def _already_blocked(domain: str, url: str) -> bool:
    if any(domain == d or domain.endswith("." + d) for d in BLOCKED_DOMAINS):
        return True
    if any(domain == d or domain.endswith("." + d) for d in LOW_QUALITY_DISCOVERY_DOMAINS):
        return True
    if any(domain.endswith(s) for s in LOW_QUALITY_DOMAIN_SUFFIXES):
        return True
    return False


def _path_filtered(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(m in path for m in LOW_QUALITY_PATH_MARKERS)


# ── Verdict logic ──────────────────────────────────────────────────────────────

def _verdict(domain: str, url: str, status: int) -> tuple[str, str]:
    """Return (symbol, reason)."""
    if _already_blocked(domain, url):
        return "⚫", "ya bloqueado"
    if _path_filtered(url):
        return "🟡", "path filtrado"
    if _is_low_quality_candidate(url):
        return "🟠", "baja calidad (filtro actual)"
    if status == 0:
        return "🔴", "timeout / sin respuesta"
    if status in (403, 429, 451):
        return "🔴", f"HTTP {status} — bloquear"
    if status == 404:
        return "🟡", "HTTP 404 — sin contenido"
    if status >= 500:
        return "🟡", f"HTTP {status} — servidor caído"
    if status == 200:
        return "🟢", "OK"
    return "🟡", f"HTTP {status}"


# ── Main ───────────────────────────────────────────────────────────────────────

async def main(industria: str, ciudad: str, max_results: int):
    print(f"\n🔍  Descubriendo: '{industria}' en '{ciudad}' (max={max_results})...\n")

    companies = await discover_companies(
        industria, ciudad, max_results,
        gmaps_key=GMAPS_KEY,
        excluded_domains=set(),
        use_secop=False,
    )

    if not companies:
        print("❌  Sin resultados de discovery.")
        return

    print(f"✓  {len(companies)} URLs encontradas. Chequeando estado...\n")

    # Quick-check all URLs in parallel
    async with httpx.AsyncClient(timeout=_CHECK_TIMEOUT) as client:
        statuses = await asyncio.gather(
            *[_quick_status(client, c["url"]) for c in companies],
            return_exceptions=True,
        )

    # Build rows
    rows: list[dict] = []
    for company, status in zip(companies, statuses):
        url = company.get("url", "")
        domain = _domain_of(url)
        code = status if isinstance(status, int) else 0
        symbol, reason = _verdict(domain, url, code)
        rows.append({
            "symbol": symbol,
            "domain": domain,
            "status": code or "—",
            "source": company.get("source", "?"),
            "title": (company.get("title") or "")[:40],
            "reason": reason,
            "url": url,
        })

    # Sort: blocked first, then by verdict
    order = {"🔴": 0, "🟠": 1, "🟡": 2, "⚫": 3, "🟢": 4}
    rows.sort(key=lambda r: order.get(r["symbol"], 5))

    # Print table
    col_d = max(len(r["domain"]) for r in rows) + 2
    col_t = max(len(r["title"]) for r in rows) + 2
    header = f"{'':2}  {'Domain':<{col_d}}  {'Status':>6}  {'Source':<10}  {'Empresa':<{col_t}}  Veredicto"
    print(header)
    print("─" * len(header))
    for r in rows:
        print(
            f"{r['symbol']}   {r['domain']:<{col_d}}  {str(r['status']):>6}  "
            f"{r['source']:<10}  {r['title']:<{col_t}}  {r['reason']}"
        )

    # Collect new domains to block (red = 403/429, not already blocked)
    to_block = [
        r["domain"] for r in rows
        if r["symbol"] == "🔴" and not _already_blocked(r["domain"], r["url"])
        and str(r["status"]) not in ("0", "—")  # skip pure timeouts
    ]

    print()
    if to_block:
        print("━" * 50)
        print("📋  Dominios sugeridos para añadir a LOW_QUALITY_DISCOVERY_DOMAINS:\n")
        for d in to_block:
            print(f'    "{d}",')
        print()
        print("Agrega estas líneas en backend/prospector.py → LOW_QUALITY_DISCOVERY_DOMAINS")
    else:
        print("✅  Sin dominios nuevos para bloquear.")

    # Summary
    by_symbol = {}
    for r in rows:
        by_symbol[r["symbol"]] = by_symbol.get(r["symbol"], 0) + 1
    summary = "  ".join(f"{s} {n}" for s, n in sorted(by_symbol.items(), key=lambda x: order.get(x[0], 9)))
    print(f"\nResumen: {summary}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Escanear calidad de dominios descubiertos")
    parser.add_argument("--industria", default="marketing digital", help="Industria a buscar")
    parser.add_argument("--ciudad", default="Bogotá", help="Ciudad objetivo")
    parser.add_argument("--max", type=int, default=20, dest="max_results", help="Máximo de resultados")
    args = parser.parse_args()

    asyncio.run(main(args.industria, args.ciudad, args.max_results))
