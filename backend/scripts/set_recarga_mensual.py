"""
Activa la recarga mensual de minutos de un tenant (cron cobr_recarga_mensual).

Setea tenant_configs.cobranza.facturacion.recarga_mensual_minutos y
recarga_mensual_desde (YYYY-MM: primer mes que se carga — evita retro-cargar
el mes en curso si se contrata después del día 15). Update con dotted paths:
no pisa el resto de `facturacion` (p.ej. reembolso_sin_contacto_pct).

    python scripts/set_recarga_mensual.py [user_id] [minutos] [desde]
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

DPG_USER_ID = "69bcd9bb6e35d53880364535"


async def main():
    user_id = sys.argv[1] if len(sys.argv) > 1 else DPG_USER_ID
    minutos = int(sys.argv[2]) if len(sys.argv) > 2 else 1500
    desde = sys.argv[3] if len(sys.argv) > 3 else "2026-09"

    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
    database._client = client
    db = client[os.getenv("MONGODB_DB", "hive_office")]

    res = await db.tenant_configs.update_one(
        {"user_id": user_id},
        {"$set": {
            "cobranza.facturacion.recarga_mensual_minutos": minutos,
            "cobranza.facturacion.recarga_mensual_desde": desde,
        }},
    )
    if not res.matched_count:
        print(f"ERROR: no existe tenant_configs para user_id={user_id} — no se creó nada.")
        client.close()
        sys.exit(1)

    try:  # refleja el cambio ya (si Redis no responde, el TTL de 5 min lo hace solo)
        from cobranza.config_cache import invalidate_tenant_config
        await invalidate_tenant_config(user_id)
    except Exception:
        pass

    doc = await db.tenant_configs.find_one({"user_id": user_id}, {"cobranza.facturacion": 1})
    print(f"OK user={user_id} facturacion={doc.get('cobranza', {}).get('facturacion')}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
