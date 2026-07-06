"""
Seed del paquete de minutos de DPG (1500 min) + índices del ledger.

Idempotente: si ya existe una compra con la nota del paquete inicial, no duplica.

    python scripts/seed_dpg_minutos.py [user_id] [minutos]
"""
import asyncio
import os
import sys

import certifi
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import database  # noqa: E402
from cobranza import minutes  # noqa: E402

DPG_USER_ID = "69bcd9bb6e35d53880364535"
NOTA = "Paquete inicial contratado DPG Seguros"


async def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else DPG_USER_ID
    minutos_paquete = int(sys.argv[2]) if len(sys.argv) > 2 else 1500

    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
    database._client = client
    db = client[os.getenv("MONGODB_DB", "hive_office")]

    await minutes.ensure_indexes(db)

    existing = await db[minutes.COLLECTION].find_one(
        {"user_id": user_id, "tipo": "compra", "nota": NOTA}
    )
    if existing:
        print(f"Ya existe el paquete inicial ({existing['minutos']} min) — no se duplica.")
    else:
        await minutes.record_purchase(
            db, user_id, minutos_paquete, nota=NOTA, actor="seed_script"
        )
        print(f"Compra registrada: +{minutos_paquete} min")

    saldo = await minutes.get_saldo(db, user_id)
    print(f"SALDO user={user_id}: {saldo}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
