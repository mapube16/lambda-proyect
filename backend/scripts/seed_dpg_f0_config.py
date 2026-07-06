"""
Aplica las decisiones F0 del operador (2026-07-05) a la config del tenant DPG.

Decisiones (respondidas por Landa en sesión):
  - Ventana rodante: hoy + 1 día hábil (la cola de régimen se rellena sola).
  - Corte de mora: compromisos desde 2026-06-15 (informe, sin cambios).
  - Franjas: 9-12 + 14-16 L-V · cupo 30/día (informe §2; arranque se sube aparte).
  - Secuencia: L1/L2/L3 = -1/0/+2 hábiles, máx 3 intentos, ancla = compromiso.
  - Alertas: WhatsApp al responsable según tabla §11 (cargada tal cual, editable).
  - Identidad en voz: por NOMBRE (ya es el comportamiento del saludo de ARIA).
  - Número: dos números en v1 (voz Twilio + WA Meta). Gemini tier: antes de prod.

Idempotente — se puede re-correr. Todo editable después desde la UI/config.
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

# Tabla §11 del informe, tal cual (config editable — NO hardcode en código).
TABLA_11 = [
    {"area": "salud_rcp", "responsable": "Annie", "telefono": "+573158708756",
     "keywords": ["rcp", "salud", "cotizacion", "precio", "valor asegurado", "profesion",
                  "plan de salud", "seguro medico", "medicina prepagada"]},
    {"area": "cartera_pagos", "responsable": "Paola Andrea", "telefono": "+573146316003",
     "keywords": ["pago", "cartera", "estado de cuenta", "cupon de pago", "link de pago",
                  "factura", "saldo pendiente", "vencimiento", "acuerdo de pago"]},
    {"area": "coberturas_tecnicos", "responsable": "Juan Diego", "telefono": "+573108813559",
     "keywords": ["cobertura", "indice variable", "sismorresistente", "seguro de cumplimiento",
                  "amparos", "exclusiones"]},
    {"area": "empresarial", "responsable": "Diana Paola", "telefono": "+573206943518",
     "keywords": ["empresa", "empresarial", "licitacion", "entidad estatal",
                  "cliente inconforme", "queja", "reclamo comercial", "programa de seguros"]},
    {"area": "siniestros", "responsable": "Jorge", "telefono": "+573155743590",
     "keywords": ["siniestro", "reclamo", "indemnizacion", "accidente", "choque", "dano",
                  "asistencia", "grua", "cerrajeria", "plomeria", "vidrios", "tejas", "fractura"]},
    {"area": "generales_vida", "responsable": "Liliana Vargas / Heidy", "telefono": "+573152525588",
     "keywords": ["vida", "medicina prepagada", "plan complementario", "accidente personal",
                  "accidente escolar", "viajes", "copropiedad", "vigencia", "deducible",
                  "incapacidad", "areas comunes", "muebles y enseres"]},
    {"area": "automoviles", "responsable": "Stefanía", "telefono": "+573185385333",
     "keywords": ["vehiculo", "automovil", "carro", "moto", "placa", "seguro de automovil"]},
    {"area": "cumplimiento", "responsable": "Jimena", "telefono": "+573186006610",
     "keywords": ["contrato", "cumplimiento", "garantia", "licitacion", "entidad contratante",
                  "valor de poliza", "prima", "tomador", "asegurado"]},
]

F0_CONFIG = {
    "softseguros_cartera": {
        # Solo lo que cambia: el techo pasa de fijo a RODANTE (hoy + 1 hábil).
        # fecha_desde (15-jun) y el resto del scope quedan como están.
        "fecha_hasta_rodante_dias": 1,
    },
    "timings": {
        "offsets_intentos_dias_habiles": [-1, 0, 2],
        "max_intentos": 3,
        "agendar_por": "fecha_compromiso",
        "frecuencia_dias": 1,
        "pre_vencimiento_dias": 1,
    },
    "horarios": {
        "timezone": "America/Bogota",
        "dias_habiles": [1, 2, 3, 4, 5],
        "franjas": [["09:00", "12:00"], ["14:00", "16:00"]],
        "franjas_sabado": [],
        "festivos": [],
        "max_contactos_dia": 1,
    },
    "volumen": {
        "llamadas_por_dia": 30,   # régimen (informe §2.1); jornada de arranque se sube temporal
        "distribucion": "uniforme",
    },
    "alertas": {
        "canales": ["whatsapp_responsable"],
        "routing": TABLA_11,
        "fallback_responsable": "cartera_pagos",  # sin match de área → cartera (Paola)
    },
}


async def main():
    client = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())
    database._client = client
    db = client[os.getenv("MONGODB_DB", "hive_office")]

    # Merge por bloque, PRESERVANDO las claves existentes de softseguros_cartera
    # (sede/estados/ramos/fecha_desde) — set_cobranza_config reemplaza el bloque
    # completo, así que leemos y fusionamos primero.
    doc = await db.tenant_configs.find_one({"user_id": DPG_USER_ID}, {"cobranza": 1}) or {}
    actual = (doc.get("cobranza") or {})
    cartera_merged = {**(actual.get("softseguros_cartera") or {}), **F0_CONFIG["softseguros_cartera"]}
    block = {**F0_CONFIG, "softseguros_cartera": cartera_merged}

    from cobranza.tenant_config import set_cobranza_config
    await set_cobranza_config(DPG_USER_ID, block)

    check = await db.tenant_configs.find_one({"user_id": DPG_USER_ID}, {"cobranza": 1})
    cz = check["cobranza"]
    print("CONFIG F0 APLICADA:")
    print("  rodante_dias:", cz["softseguros_cartera"].get("fecha_hasta_rodante_dias"),
          "| fecha_desde:", cz["softseguros_cartera"].get("fecha_desde"),
          "| sede:", cz["softseguros_cartera"].get("sede"))
    print("  franjas:", cz["horarios"]["franjas"], "| cupo:", cz["volumen"]["llamadas_por_dia"])
    print("  timings:", cz["timings"]["offsets_intentos_dias_habiles"], "max", cz["timings"]["max_intentos"])
    print("  alertas:", cz["alertas"]["canales"], "| responsables:", len(cz["alertas"]["routing"]))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
