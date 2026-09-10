"""Restaura las alertas 'sin_contacto_agotado' de DPG desde un cluster restaurado.

Contexto: el 2026-08-08 ~22:21 UTC un delete_many mal acotado borro 850 alertas
de tipo sin_contacto_agotado del tenant DPG (el filtro no restringia al deudor
de prueba). El resto de alertas y toda la cartera quedaron intactas.

Copia SOLO esos documentos, y SOLO los que no existan ya en destino (upsert por
_id) — no toca ninguna otra coleccion ni pisa nada creado despues del incidente.

Requiere en .env:
  MONGODB_URI          -> cluster de PRODUCCION (destino)
  MONGODB_RESTORE_URI  -> cluster temporal restaurado del snapshot (origen)

  python scripts/restaurar_alertas.py            # simulacro, no escribe
  python scripts/restaurar_alertas.py --aplicar  # escribe de verdad
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

try:
    import dns.resolver
    dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
    dns.resolver.default_resolver.nameservers = ["8.8.8.8", "1.1.1.1"]
except Exception:
    pass

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import UpdateOne

USER_ID = "69bcd9bb6e35d53880364535"
TIPO = "sin_contacto_agotado"
DB_NAME = os.getenv("MONGODB_DB", "hive_office")


async def main() -> int:
    aplicar = "--aplicar" in sys.argv
    origen_uri = os.getenv("MONGODB_RESTORE_URI")
    if not origen_uri:
        return print("falta MONGODB_RESTORE_URI en .env (cluster restaurado)", file=sys.stderr) or 1

    origen = AsyncIOMotorClient(origen_uri, tlsCAFile=certifi.where())[DB_NAME]
    destino = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[DB_NAME]

    filtro = {"user_id": USER_ID, "tipo": TIPO}
    docs = await origen.cobranza_alertas.find(filtro).to_list(length=None)
    ya_estan = await destino.cobranza_alertas.count_documents(filtro)
    total_destino = await destino.cobranza_alertas.count_documents({"user_id": USER_ID})

    print(f"origen  : {len(docs)} alertas '{TIPO}'")
    print(f"destino : {ya_estan} de ese tipo · {total_destino} alertas en total")
    if not docs:
        print("el snapshot no tiene esas alertas — punto de restauracion demasiado nuevo?")
        return 1

    atendidas = sum(1 for d in docs if d.get("atendida"))
    print(f"          {atendidas} venian marcadas como atendidas (se conserva ese estado)")

    if not aplicar:
        print("\nSIMULACRO — nada escrito. Repetir con --aplicar para restaurar.")
        return 0

    # upsert por _id: idempotente y no pisa nada que exista en destino
    res = await destino.cobranza_alertas.bulk_write(
        [UpdateOne({"_id": d["_id"]}, {"$setOnInsert": d}, upsert=True) for d in docs],
        ordered=False,
    )
    final = await destino.cobranza_alertas.count_documents(filtro)
    print(f"\nrestauradas {res.upserted_count} · ya existian {len(docs) - res.upserted_count}")
    print(f"destino ahora tiene {final} alertas '{TIPO}'")
    return 0


sys.exit(asyncio.run(main()))
