"""
explore_pagopoliza.py — deep-dive on /api/pagopoliza/ (the cuotas endpoint).

The first recon showed it ReadTimeout's (not 504) — consistent with "slow, not
broken". This probes whether it responds when:
  (a) given a long timeout (90s), and
  (b) scoped with filter params (by póliza / by cliente) so it doesn't try to
      page the cuotas of all 52k pólizas at once.

Dumps anything that comes back to c:/tmp/pagopoliza_probe.json.

Usage:
    python scripts/explore_pagopoliza.py 69bcd9bb6e35d53880364535
"""
import asyncio
import json
import os
import sys
from datetime import date, datetime

try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from softseguros import credentials as _credentials
from softseguros.adapter import SoftSegurosAdapter

OUT = "c:/tmp/pagopoliza_probe.json"


def _jd(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


async def _try(adapter, label, path, params, timeout):
    """One probe attempt. Returns a result dict (never raises)."""
    print(f"\n[{label}] GET {path} params={params} timeout={timeout}s")
    try:
        # Bypass the adapter's 30s client by issuing the request directly with a
        # per-call timeout override.
        if not adapter.token:
            await adapter.authenticate()
        headers = adapter._auth_headers()
        resp = await adapter._client.request(
            "GET", path, headers=headers, params=params, timeout=timeout
        )
        ctype = resp.headers.get("content-type", "")
        print(f"  -> status={resp.status_code} ctype={ctype!r} bytes={len(resp.content)}")
        out = {"label": label, "path": path, "params": params,
               "status": resp.status_code, "content_type": ctype}
        if "json" in ctype.lower():
            data = resp.json()
            if isinstance(data, dict):
                out["count"] = data.get("count")
                results = data.get("results") or []
                out["page1_len"] = len(results)
                out["sample_keys"] = sorted(results[0].keys()) if results else None
                out["sample"] = results[0] if results else data
            else:
                out["sample"] = data
        else:
            out["body_head"] = resp.text[:400]
        return out
    except Exception as exc:  # noqa: BLE001
        print(f"  -> FAILED {type(exc).__name__}: {exc}")
        return {"label": label, "path": path, "params": params,
                "error": f"{type(exc).__name__}: {exc}"}


async def main():
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "hive_office")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]

    user_id = sys.argv[1] if len(sys.argv) > 1 else None
    if not user_id:
        doc = await db[_credentials.COLLECTION].find_one({})
        user_id = doc and doc["user_id"]
    creds = await _credentials.get_credentials(db, user_id)
    if not creds:
        print(f"No usable creds for {user_id}")
        return
    username, password = creds
    print(f"user_id={user_id} username={username!r}")

    # Grab a real póliza id + cliente id to scope the cuotas query.
    adapter = SoftSegurosAdapter(username, password, timeout=95.0)
    probes = []
    try:
        await adapter.authenticate()
        # Bootstrap: fetch one póliza to scope the cuotas query. Retry — the list
        # endpoint occasionally returns a transient non-JSON body.
        first = {}
        for attempt in range(1, 6):
            listing = await adapter._client.request(
                "GET", "/api/poliza/", headers=adapter._auth_headers(),
                params={"page": 1}, timeout=60.0,
            )
            ctype = listing.headers.get("content-type", "")
            if "json" in ctype.lower():
                try:
                    first = (listing.json().get("results") or [{}])[0]
                    break
                except Exception:
                    pass
            print(f"  bootstrap attempt {attempt}: status={listing.status_code} "
                  f"ctype={ctype!r} bytes={len(listing.content)} — retrying")
            await asyncio.sleep(3 * attempt)
        if not first:
            print("Could not bootstrap a póliza after retries; aborting probe.")
            return
        poliza_id = first.get("id")
        cliente_id = first.get("cliente")
        numero_poliza = first.get("numero_poliza")
        print(f"scoping with poliza_id={poliza_id} cliente_id={cliente_id} numero_poliza={numero_poliza}")

        # Probe matrix — broad page1 (long timeout), then several scoping params.
        probes.append(await _try(adapter, "page1_longtimeout",
                                 "/api/pagopoliza/", {"page": 1}, 90.0))
        probes.append(await _try(adapter, "by_poliza",
                                 "/api/pagopoliza/", {"poliza": poliza_id}, 90.0))
        probes.append(await _try(adapter, "by_poliza_id",
                                 "/api/pagopoliza/", {"poliza_id": poliza_id}, 90.0))
        probes.append(await _try(adapter, "by_cliente",
                                 "/api/pagopoliza/", {"cliente": cliente_id}, 90.0))
        probes.append(await _try(adapter, "by_numero_poliza",
                                 "/api/pagopoliza/", {"numero_poliza": numero_poliza}, 90.0))
    finally:
        await adapter.close()
        client.close()

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump({"user_id": user_id, "probes": probes}, f,
                  indent=2, ensure_ascii=False, default=_jd)
    print(f"\nWritten {OUT}")
    for p in probes:
        tag = p.get("error") or f"status={p.get('status')} count={p.get('count')} len={p.get('page1_len')}"
        print(f"  {p['label']}: {tag}")


if __name__ == "__main__":
    asyncio.run(main())
