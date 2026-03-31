"""
Crea un cliente demo completamente configurado para mostrar el agente de voz.

Qué crea:
  - Usuario: demo.cobranza@empresa.com / demo2026
  - company_voice con cobranza_enabled=True
  - cobranza_config con estrategia lista (sin onboarding)
  - client_profile con datos de empresa
  - 6 deudores en distintos estados para mostrar todo el flujo

Uso:
  cd backend
  python seed_demo_client.py
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

DEMO_EMAIL    = "demo.cobranza@empresa.com"
DEMO_PASSWORD = "demo2026"
EMPRESA       = "Servicios Ágil Colombia"


def _make_debtors(user_id: str, now: datetime) -> list[dict]:
    base = {
        "user_id": user_id,
        "vapi_call_id": None,
        "historial_llamadas": [],
        "escalado": False,
        "ultimo_contacto_fecha": None,
        "created_at": now,
        "updated_at": now,
    }
    return [
        # 1. Pre-vencimiento — activa pre_vencimiento_job
        {**base,
         "nombre": "Valentina Ríos",
         "telefono": "+573001112233",
         "monto": 980_000.0,
         "vencimiento": now + timedelta(days=2),
         "estado": "pendiente",
         "intentos": 0, "max_intentos": 5,
         "notas": "Cuota 2/4. Acordó pagar antes del vencimiento."},

        # 2. Pre-vencimiento — vence mañana
        {**base,
         "nombre": "Ricardo Montoya",
         "telefono": "+573112223344",
         "monto": 2_450_000.0,
         "vencimiento": now + timedelta(days=1),
         "estado": "pendiente",
         "intentos": 0, "max_intentos": 5,
         "notas": "Contrato de servicio anual. Primera llamada de recordatorio."},

        # 3. Post-vencimiento — vencido hace 3 días
        {**base,
         "nombre": "Almacenes Bolívar SAS",
         "telefono": "+576013334455",
         "monto": 8_700_000.0,
         "vencimiento": now - timedelta(days=3),
         "estado": "pendiente",
         "intentos": 1, "max_intentos": 6,
         "notas": "Factura #2024-089. Contacto: Pedro Alvarado – Gerente Administrativo."},

        # 4. Sin contacto — vencido hace 7 días, un intento fallido
        {**base,
         "nombre": "Inversiones Palma Real",
         "telefono": "+573204445566",
         "monto": 15_300_000.0,
         "vencimiento": now - timedelta(days=7),
         "estado": "sin_contacto",
         "intentos": 2, "max_intentos": 5,
         "notas": "Dos intentos sin respuesta. Número correcto verificado."},

        # 5. Promesa de pago — ya acordó
        {**base,
         "nombre": "Transportes El Cóndor Ltda",
         "telefono": "+576024445566",
         "monto": 4_200_000.0,
         "vencimiento": now - timedelta(days=10),
         "estado": "promesa_de_pago",
         "intentos": 3, "max_intentos": 5,
         "notas": "Prometió pago el viernes 4 de abril. Hacer seguimiento."},

        # 6. Pagado — ejemplo de cierre exitoso
        {**base,
         "nombre": "Clínica Santa Lucía",
         "telefono": "+574035556677",
         "monto": 1_800_000.0,
         "vencimiento": now - timedelta(days=15),
         "estado": "pagado",
         "intentos": 1, "max_intentos": 5,
         "notas": "Pagó en línea el día siguiente de la llamada."},
    ]


async def main() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient
    from auth import hash_password

    uri     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "hive_office")
    client  = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db      = client[db_name]
    now     = datetime.now(timezone.utc)

    # ── 1. Crear / obtener usuario ────────────────────────────────────────────
    existing = await db.users.find_one({"email": DEMO_EMAIL})
    if existing:
        user_id = str(existing["_id"])
        print(f"Usuario ya existe: {user_id} — limpiando datos anteriores...")
        await db.debtors.delete_many({"user_id": user_id})
        await db.cobranza_config.delete_many({"user_id": user_id})
        print("  Deudores y config eliminados.")
    else:
        result = await db.users.insert_one({
            "email": DEMO_EMAIL,
            "hashed_password": hash_password(DEMO_PASSWORD),
            "role": "client",
            "created_at": now,
        })
        user_id = str(result.inserted_id)
        print(f"Usuario creado: {user_id}")

    # ── 2. Habilitar cobranza (simula staff_enable_cobranza) ─────────────────
    await db.company_voice.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "cobranza_enabled": True,
                "cobranza_enabled_at": now,
                "notification_channel": "web",
                "updated_at": now,
            },
            "$setOnInsert": {"user_id": user_id, "created_at": now},
        },
        upsert=True,
    )
    print("  cobranza_enabled = True OK")

    print(f"\nListo.")
    print(f"  Login: {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print(f"  cobranza_enabled: True")
    print(f"  Sin estrategia ni deudores -> onboarding arranca desde cero")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
