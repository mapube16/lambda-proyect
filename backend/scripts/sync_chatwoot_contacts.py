"""Carga manual completa de contactos de Chatwoot desde la cartera (DPG).

Uso:
  CHATWOOT_URL=... CHATWOOT_API_KEY=... python scripts/sync_chatwoot_contacts.py [user_id]

Sin argumento usa el tenant DPG. El mismo upsert corre solo tras cada sync
de SoftSeguros (ver softseguros/sync.py); este wrapper es para la carga
inicial o para forzar una pasada.
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from softseguros.chatwoot_contacts import sync_chatwoot_contacts

DPG_TENANT = "69bcd9bb6e35d53880364535"


async def main() -> None:
    user_id = sys.argv[1] if len(sys.argv) > 1 else DPG_TENANT
    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]
    out = await sync_chatwoot_contacts(db, user_id)
    print(out)
    db.client.close()


if __name__ == "__main__":
    asyncio.run(main())
