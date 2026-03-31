"""
Reset del agente de voz de cobranza para DPG Seguros.

Qué hace:
  1. Borra todos los deudores del usuario dpg.seguros@gmail.com
  2. Borra su cobranza_config (estrategia guardada)
  3. Re-seedea deudores demo con fechas realistas

Uso:
  cd backend
  python reset_cobranza_dpg.py
"""
import asyncio
import os
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Deudores demo
# ---------------------------------------------------------------------------

def _make_debtors(now: datetime) -> list[dict]:
    """
    Genera deudores con fechas relativas a 'now' para que el scheduler
    los tome de inmediato en la siguiente corrida.
    """
    return [
        # ── Pre-vencimiento (vence en 2 días — activa pre_vencimiento_job) ──
        {
            "nombre": "María Salcedo",
            "telefono": "+573001234567",
            "monto": 1_850_000,
            "vencimiento": now + timedelta(days=2),
            "notas": "Cuota 3/6 plan de pagos. Acordó pago antes del vencimiento.",
            "max_intentos": 5,
        },
        {
            "nombre": "Carlos Herrera",
            "telefono": "+573109876543",
            "monto": 450_000,
            "vencimiento": now + timedelta(days=1),
            "notas": "Póliza SOAT vence mañana. Sin cobertura renovada.",
            "max_intentos": 5,
        },
        # ── Post-vencimiento (ya venció — activa post_vencimiento_job) ──
        {
            "nombre": "Luis Ríos",
            "telefono": "+573155551234",
            "monto": 3_200_000,
            "vencimiento": now - timedelta(days=5),
            "notas": "Prima de RC vehículos vencida hace 5 días. Sin contacto aún.",
            "max_intentos": 5,
        },
        {
            "nombre": "Transportes Rápido Ltda",
            "telefono": "+576012223344",
            "monto": 12_400_000,
            "vencimiento": now - timedelta(days=2),
            "notas": "Póliza de flota. Contacto: Adriana Vargas – Directora Administrativa.",
            "max_intentos": 6,
        },
        # ── Pendiente sin vencimiento inmediato (estado inicial limpio) ──
        {
            "nombre": "Jorge Ospina",
            "telefono": "+573204445566",
            "monto": 750_000,
            "vencimiento": now + timedelta(days=15),
            "notas": "Renovación anual. Primera llamada de aviso.",
            "max_intentos": 5,
        },
    ]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient

    uri     = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = os.getenv("MONGODB_DB", "hive_office")
    client  = AsyncIOMotorClient(uri, tlsCAFile=certifi.where())
    db      = client[db_name]

    # 1. Encontrar usuario DPG
    user = await db.users.find_one({"email": "dpg.seguros@gmail.com"})
    if not user:
        print("ERROR: dpg.seguros@gmail.com no encontrado en la DB")
        client.close()
        return

    user_id = str(user["_id"])
    print(f"Usuario encontrado: {user_id}")

    # 2. Borrar deudores existentes
    result = await db.debtors.delete_many({"user_id": user_id})
    print(f"Deudores eliminados: {result.deleted_count}")

    # 3. Borrar cobranza_config
    result = await db.cobranza_config.delete_many({"user_id": user_id})
    print(f"Configuraciones eliminadas: {result.deleted_count}")

    # 4. Seedear deudores frescos
    now = datetime.now(timezone.utc)
    debtors_data = _make_debtors(now)

    count = 0
    for data in debtors_data:
        doc = {
            "user_id": user_id,
            "nombre": data["nombre"],
            "telefono": data["telefono"],
            "monto": float(data["monto"]),
            "vencimiento": data["vencimiento"],
            "estado": "pendiente",
            "vapi_call_id": None,
            "intentos": 0,
            "max_intentos": data.get("max_intentos", 5),
            "historial_llamadas": [],
            "escalado": False,
            "notas": data.get("notas"),
            "ultimo_contacto_fecha": None,
            "created_at": now,
            "updated_at": now,
        }
        await db.debtors.insert_one(doc)
        count += 1
        monto_fmt = f"${data['monto']:,.0f}"
        venc = data["vencimiento"].strftime("%d/%m/%Y")
        print(f"  OK  {data['nombre']:<35} {monto_fmt:<15} vence {venc}")

    print(f"\nListo. {count} deudores seeded para dpg.seguros@gmail.com")
    print("\nPróximos pasos:")
    print("  1. Loguéate como dpg.seguros@gmail.com (pass: seguros2026)")
    print("  2. Ve a Cobranza → configura estrategia desde el onboarding")
    print("  3. Usa 'Llamar Ahora' en cualquier deudor para probar el agente de voz")
    print("  4. El scheduler automático ya tiene deudores pre y post vencimiento listos")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
