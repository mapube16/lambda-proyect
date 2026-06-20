"""
test_call_aria.py — fire ONE real test call to a given number using a real DPG
policy's data, so ARIA speaks with the new prompt over the live local server.

It:
  1. Clones a real cobrable debtor (keeps its policy fields) into a NEW test
     debtor whose `telefono` is the target number — never overwrites a real
     debtor's phone.
  2. Mints a JWT for the owning user_id with the server's SECRET_KEY.
  3. POSTs /api/cobranza/voice/call/initiate-v2 against the local server.

Usage:
    python scripts/test_call_aria.py <user_id> <source_debtor_id> <to_phone>
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

from auth import create_access_token  # same module the server uses

LOCAL = "http://localhost:8002"


async def main():
    user_id = sys.argv[1]
    source_id = sys.argv[2]
    to_phone = sys.argv[3]

    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]

    # Clean up prior test debtors so the non-sparse (user_id, softseguros_poliza_id)
    # unique index doesn't collide on null.
    deleted = await db.debtors.delete_many({"user_id": user_id, "is_test": True})
    if deleted.deleted_count:
        print(f"Removed {deleted.deleted_count} prior test debtor(s)")

    src = await db.debtors.find_one({"_id": ObjectId(source_id), "user_id": user_id})
    if not src:
        print(f"Source debtor {source_id} not found for user {user_id}")
        return

    # Clone, strip identity/_id, override phone + flag as test.
    clone = dict(src)
    clone.pop("_id", None)
    clone["telefono"] = to_phone
    # Keep the REAL debtor name so ARIA greets correctly ("Hola, Juan Pablo...").
    # The test flag lives in is_test, NOT in the name.
    clone["nombre"] = str(src.get("nombre", ""))
    clone["is_test"] = True
    clone["historial_llamadas"] = []
    clone["estado"] = "pendiente"
    clone.pop("vapi_call_id", None)
    # Drop the SoftSeguros unique-index keys so the clone doesn't collide with the
    # source on (user_id, softseguros_poliza_id). It's a throwaway test debtor.
    clone.pop("softseguros_poliza_id", None)
    clone.pop("status_softseguros", None)
    # Ensure not flagged as already-contacted-today.
    for k in ("ultima_llamada", "last_called_at", "contacted_at"):
        clone.pop(k, None)

    res = await db.debtors.insert_one(clone)
    test_id = str(res.inserted_id)
    print(f"Created test debtor {test_id}: {clone['nombre']} | "
          f"ramo={clone.get('ramo_nombre')} monto={clone.get('monto')} -> {to_phone}")

    token = create_access_token(data={"sub": user_id, "role": "client"})

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            f"{LOCAL}/api/cobranza/voice/call/initiate-v2",
            json={"debtor_id": test_id},
            headers={"Authorization": f"Bearer {token}"},
        )
        print(f"initiate-v2 -> {r.status_code}")
        print(r.text)

    db.client.close()


if __name__ == "__main__":
    asyncio.run(main())
