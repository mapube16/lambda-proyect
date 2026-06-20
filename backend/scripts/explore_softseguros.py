"""
explore_softseguros.py — Phase 1 reconnaissance of the SOFTSEGUROS API.

Goal: discover the REAL field schema the API exposes so we can design the new
`softseguros_policies` collection and the enriched debtor mapping. Writes a full
JSON dump to c:/tmp/softseguros_schema_dump.json for inspection.

What it does (read-only, no writes to Mongo):
  1. Connect to the real Mongo (MONGODB_URI from backend/.env), list users that
     have SOFTSEGUROS credentials.
  2. For the chosen user, decrypt creds and authenticate against SOFTSEGUROS.
  3. GET /api/poliza/ (list) → take the first póliza id → GET /api/poliza/{id}
     (detail) and dump the COMPLETE JSON (all keys, not just the ones we map).
  4. RETRY /api/pagopoliza/ with backoff to test whether the 504 was a transient
     availability issue (as suspected) rather than a permanently broken endpoint.
     If it responds, dump a cuota's full schema too.

Usage:
    python -m scripts.explore_softseguros            # picks the first user with creds
    python -m scripts.explore_softseguros <user_id>  # explicit tenant
"""
import asyncio
import json
import os
import sys
from datetime import date, datetime

# Make `softseguros` importable when run as `python scripts/explore_softseguros.py`
# from the backend/ dir (scripts/ is not a package).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load backend/.env so MONGODB_URI / SOFTSEGUROS_ENCRYPTION_KEY are present.
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv()
except Exception:
    pass

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

# softseguros.credentials raises at import if SOFTSEGUROS_ENCRYPTION_KEY is unset,
# so the .env load above must run first.
from softseguros import credentials as _credentials
from softseguros.adapter import SoftSegurosAdapter, SoftSegurosAPIError

DUMP_PATH = "c:/tmp/softseguros_schema_dump.json"


def _json_default(o):
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    return str(o)


async def _retry_pagopoliza(adapter: SoftSegurosAdapter, attempts: int = 4):
    """Retry /api/pagopoliza/ a few times — the 504 may be availability, not a
    permanently broken endpoint. Returns (ok, payload_or_error_str)."""
    delay = 2.0
    last_err = None
    for i in range(1, attempts + 1):
        try:
            data = await adapter.list_pagopoliza(page=1)
            return True, data
        except Exception as exc:  # noqa: BLE001 — we want to see the actual failure
            last_err = f"{type(exc).__name__}: {exc}"
            print(f"  [pagopoliza] attempt {i}/{attempts} failed: {last_err}")
            if i < attempts:
                await asyncio.sleep(delay)
                delay *= 2
    return False, last_err


async def main():
    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "hive_office")
    client = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db = client[db_name]

    # ── Pick the user ────────────────────────────────────────────────────────
    arg_user = sys.argv[1] if len(sys.argv) > 1 else None
    cred_docs = await db[_credentials.COLLECTION].find(
        {}, {"user_id": 1, "username": 1}
    ).to_list(length=50)
    print(f"Users with SOFTSEGUROS credentials: {len(cred_docs)}")
    for d in cred_docs:
        print(f"  - user_id={d.get('user_id')} username={d.get('username')!r}")

    if not cred_docs:
        print("No credentials found. Aborting.")
        return

    user_id = arg_user or cred_docs[0]["user_id"]
    print(f"\nUsing user_id={user_id}")

    creds = await _credentials.get_credentials(db, user_id)
    if not creds:
        print(f"Could not load/decrypt credentials for user_id={user_id}. Aborting.")
        return
    username, password = creds

    dump = {
        "user_id": user_id,
        "username": username,
        "explored_at": datetime.utcnow().isoformat(),
        "poliza_list_keys": None,
        "poliza_detail_keys": None,
        "poliza_detail_sample": None,
        "pagopoliza_ok": False,
        "pagopoliza_sample": None,
        "pagopoliza_error": None,
    }

    adapter = SoftSegurosAdapter(username, password)
    try:
        await adapter.authenticate()
        print("Authenticated OK against SOFTSEGUROS.")

        # ── /api/poliza/ list → first id ─────────────────────────────────────
        listing = await adapter.list_polizas(page=1)
        results = listing.get("results") or []
        print(f"/api/poliza/ count={listing.get('count')} page1_results={len(results)}")
        if results:
            dump["poliza_list_keys"] = sorted(results[0].keys())
            # Always dump the FULL first list row — the list is the real source
            # of fields (detail endpoint may not return JSON).
            dump["poliza_list_sample"] = results[0]
            first_id = results[0].get("id")
            print(f"First póliza id={first_id}")
            print(f"/api/poliza/ list row keys: {len(results[0])} fields")

            # ── /api/poliza/{id} detail (often richer than list) ─────────────
            # Use the raw request so a non-JSON body (HTML error page) doesn't
            # blow up — we just record what came back.
            try:
                resp = await adapter._request("GET", f"/api/poliza/{first_id}")
                ctype = resp.headers.get("content-type", "")
                if "json" in ctype.lower():
                    detail = resp.json()
                    dump["poliza_detail_keys"] = sorted(detail.keys())
                    dump["poliza_detail_sample"] = detail
                    print(f"/api/poliza/{first_id} keys: {len(detail)} fields")
                else:
                    print(f"/api/poliza/{first_id} returned non-JSON ({resp.status_code}, {ctype!r})")
                    dump["poliza_detail_sample"] = {
                        "_status": resp.status_code,
                        "_content_type": ctype,
                        "_body_head": resp.text[:500],
                    }
            except Exception as exc:  # noqa: BLE001
                print(f"Detail fetch failed: {type(exc).__name__}: {exc}")
                dump["poliza_detail_sample"] = {"_error": f"{type(exc).__name__}: {exc}"}

        # ── /api/pagopoliza/ retry (504 → availability?) ─────────────────────
        print("\nRetrying /api/pagopoliza/ (testing the 504 hypothesis)...")
        ok, payload = await _retry_pagopoliza(adapter)
        dump["pagopoliza_ok"] = ok
        if ok:
            cuotas = payload.get("results") or []
            print(f"  pagopoliza RESPONDED. count={payload.get('count')} page1={len(cuotas)}")
            dump["pagopoliza_sample"] = cuotas[0] if cuotas else payload
        else:
            print(f"  pagopoliza still failing after retries: {payload}")
            dump["pagopoliza_error"] = payload

    finally:
        await adapter.close()
        client.close()

    os.makedirs(os.path.dirname(DUMP_PATH), exist_ok=True)
    with open(DUMP_PATH, "w", encoding="utf-8") as f:
        json.dump(dump, f, indent=2, ensure_ascii=False, default=_json_default)
    print(f"\nDump written to {DUMP_PATH}")

    # Console summary of the keys (the bit we actually need to design the schema).
    print("\n── poliza LIST keys ──")
    print(dump["poliza_list_keys"])
    print("\n── poliza DETAIL keys ──")
    print(dump["poliza_detail_keys"])


if __name__ == "__main__":
    asyncio.run(main())
