"""
test_call_prod.py — fire ONE real test call via PRODUCTION (Railway, no ngrok).

Same as test_call_aria.py but POSTs to the live prod host so we measure the REAL
latency without the local ngrok / Colombia<->USA round-trip. Mints a JWT with the
prod SECRET_KEY for the SoftSeguros tenant.

Usage:
    python scripts/test_call_prod.py <user_id> <source_debtor_id> <to_phone>
"""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from auth import create_access_token

PROD = "https://my.landatech.org"


async def main():
    user_id = sys.argv[1]
    source_id = sys.argv[2]
    to_phone = sys.argv[3]

    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]

    # Clean prior test debtors (non-sparse unique index collides on null).
    deleted = await db.debtors.delete_many({"user_id": user_id, "is_test": True})
    if deleted.deleted_count:
        print(f"Removed {deleted.deleted_count} prior test debtor(s)")

    src = await db.debtors.find_one({"_id": ObjectId(source_id), "user_id": user_id})
    if not src:
        print(f"Source debtor {source_id} not found for user {user_id}")
        return

    clone = dict(src)
    clone.pop("_id", None)
    clone["telefono"] = to_phone
    clone["nombre"] = str(src.get("nombre", ""))
    clone["is_test"] = True
    clone["historial_llamadas"] = []
    clone["estado"] = "pendiente"
    clone.pop("vapi_call_id", None)
    clone.pop("softseguros_poliza_id", None)
    clone.pop("status_softseguros", None)
    for k in ("ultima_llamada", "last_called_at", "contacted_at", "ultimo_contacto_fecha"):
        clone.pop(k, None)

    res = await db.debtors.insert_one(clone)
    test_id = str(res.inserted_id)
    print(f"Created test debtor {test_id}: {clone['nombre']} | "
          f"ramo={clone.get('ramo_nombre')} aseguradora={clone.get('aseguradora_nombre')} "
          f"monto={clone.get('monto')} -> {to_phone}")

    token = create_access_token(data={"sub": user_id, "role": "client"})

    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        r = await client.post(
            f"{PROD}/api/cobranza/voice/call/initiate-v2",
            json={"debtor_id": test_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"PROD initiate-v2 -> {r.status_code}")
        print(r.text)

    db.client.close()


if __name__ == "__main__":
    asyncio.run(main())
