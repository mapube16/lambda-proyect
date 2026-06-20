"""
backfill_aseguradora.py — fill aseguradora_nombre on already-synced debtors.

The sync now maps ramo_aseguradora_nombre, but the 50 debtors synced earlier
only have aseguradora_nit. /api/poliza/{id} is broken (404), so we can't fetch a
single policy. Instead we scan policy pages to build a NIT -> insurer-name map,
then update active debtors by their aseguradora_nit.

Also backfills forma_pago_texto / objeto_asegurado / numero_de_cuotas per debtor
when we encounter the debtor's exact policy (matched by numero_poliza) on a page.

Usage:
    python scripts/backfill_aseguradora.py <user_id> [max_pages]
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from softseguros import credentials as _credentials
from softseguros.adapter import SoftSegurosAdapter


async def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else "69bcd9bb6e35d53880364535"
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 300

    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]
    creds = await _credentials.get_credentials(db, user_id)
    if not creds:
        print("no creds"); return
    username, password = creds

    # The NITs we still need names for (active debtors missing aseguradora_nombre).
    debtors = await db.debtors.find(
        {"user_id": user_id, "is_active": True,
         "$or": [{"aseguradora_nombre": None}, {"aseguradora_nombre": {"$exists": False}}]},
        {"aseguradora_nit": 1, "numero_poliza": 1},
    ).to_list(length=5000)
    needed_nits = {d.get("aseguradora_nit") for d in debtors if d.get("aseguradora_nit")}
    needed_polizas = {d.get("numero_poliza") for d in debtors if d.get("numero_poliza")}
    print(f"{len(debtors)} debtors need backfill; {len(needed_nits)} distinct NITs")

    nit_to_name: dict = {}
    poliza_extra: dict = {}  # numero_poliza -> {forma_pago_texto, objeto, cuotas}

    adapter = SoftSegurosAdapter(username, password, timeout=60.0)
    try:
        await adapter.authenticate()
        page = 1
        while page <= max_pages and (needed_nits - set(nit_to_name)):
            try:
                payload = await adapter.list_polizas(page=page)
            except Exception as exc:
                print(f"page {page} failed: {exc}; stopping"); break
            results = payload.get("results") or []
            if not results:
                break
            for p in results:
                nit = p.get("aseguradora_nit")
                name = p.get("ramo_aseguradora_nombre")
                if nit and name and nit not in nit_to_name:
                    nit_to_name[nit] = name
                npol = p.get("numero_poliza")
                if npol in needed_polizas and npol not in poliza_extra:
                    poliza_extra[npol] = {
                        "forma_pago_texto": p.get("forma_pago_texto"),
                        "objeto_asegurado": p.get("codio_objeto_asegurado") or p.get("datos_objeto_asegurado"),
                        "valor_asegurado_riesgo": p.get("valor_asegurado_riesgo"),
                        "numero_de_cuotas": p.get("numero_de_cuotas"),
                    }
            if page % 25 == 0:
                print(f"  page {page}: mapped {len(nit_to_name)}/{len(needed_nits)} NITs")
            page += 1
    finally:
        await adapter.close()

    print(f"Resolved {len(nit_to_name)} NIT->name; {len(poliza_extra)} exact-policy extras")

    # Apply updates.
    updated = 0
    for d in debtors:
        nit = d.get("aseguradora_nit")
        npol = d.get("numero_poliza")
        upd = {}
        if nit and nit in nit_to_name:
            upd["aseguradora_nombre"] = nit_to_name[nit]
        extra = poliza_extra.get(npol)
        if extra:
            upd.update({k: v for k, v in extra.items() if v is not None})
        if upd:
            await db.debtors.update_one({"_id": d["_id"]}, {"$set": upd})
            updated += 1
    print(f"Updated {updated} debtors")
    db.client.close()


if __name__ == "__main__":
    asyncio.run(main())
