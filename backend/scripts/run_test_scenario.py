"""
run_test_scenario.py — dispara UN escenario de la guía de pruebas de ARIA contra
PRODUCCIÓN real (my.landatech.org), clonando un deudor real de DPG y sobreescribiendo
solo lo necesario para el escenario.

Correr SIEMPRE vía `railway run --service lambda-proyect` (no local) — el SECRET_KEY
local no coincide con el de Railway, así que un JWT minteado local no autentica
contra prod.

Uso:
    python scripts/run_test_scenario.py <accion> [opciones]

Acciones:
    setup-only   — solo crea/actualiza el deudor de prueba, NO dispara llamada
                   (para los escenarios de llamada ENTRANTE, donde el evaluador
                   marca directo a DPG).
    call         — crea el deudor de prueba Y dispara initiate-v2 (para los
                   escenarios de llamada SALIENTE, donde ARIA llama al evaluador).
    llamar-ahora — crea el deudor de prueba Y dispara POST .../llamar-ahora
                   (para el escenario de entidad estatal / no_llamar, espera 403).
    delete       — borra el deudor de prueba (para el escenario "sin match").
    cleanup      — borra TODOS los deudores is_test=True del tenant (al final).

Opciones (todas con default sensato):
    --phone       teléfono del evaluador, default +573173717828
    --vencimiento YYYY-MM-DD, override de la fecha de vencimiento
    --intentos    entero, override de debtor.intentos
    --source      ObjectId del deudor real a clonar (default: Víctor Hugo Arenas)
    --no-llamar   marca el deudor de prueba con no_llamar=True (Escenario 12)
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

from auth import create_access_token

PROD = "https://my.landatech.org"
USER_ID = "69bcd9bb6e35d53880364535"  # DPG
DEFAULT_SOURCE = "6a494f31d431734615eb4766"  # Víctor Hugo Arenas Ríos, ALLIANZ, Autos
DEFAULT_PHONE = "+573173717828"


async def _get_db():
    return AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]


async def _make_test_debtor(
    db, phone: str, source: str, vencimiento: str | None, intentos: int | None,
    no_llamar: bool = False, documento: str | None = None,
) -> str:
    await db.debtors.delete_many({"user_id": USER_ID, "is_test": True})

    src = await db.debtors.find_one({"_id": ObjectId(source), "user_id": USER_ID})
    if not src:
        raise SystemExit(f"Source debtor {source} not found")

    clone = dict(src)
    clone.pop("_id", None)
    clone["telefono"] = phone
    clone["nombre"] = str(src.get("nombre", ""))
    clone["is_test"] = True
    clone["historial_llamadas"] = []
    clone["estado"] = "pendiente"
    clone["intentos"] = intentos if intentos is not None else 0
    clone.pop("vapi_call_id", None)
    clone.pop("softseguros_poliza_id", None)
    clone.pop("softseguros_pago_id", None)
    clone.pop("status_softseguros", None)
    clone.pop("proximo_intento_at", None)
    clone.pop("proximo_intento_numero", None)
    for k in ("ultima_llamada", "last_called_at", "contacted_at", "ultimo_contacto_fecha"):
        clone.pop(k, None)
    if vencimiento:
        clone["vencimiento"] = vencimiento
        clone["fecha_pago"] = vencimiento
    if documento:
        # Un clon SIEMPRE hereda el documento real del deudor origen, lo que
        # SIEMPRE crea un "duplicado" con ese registro real (mismo documento,
        # 2 dueños) — confuso para probar Escenario 1 en limpio (observado:
        # el clon de Victor Hugo con su documento real 16233741 disparó el
        # flujo de "2 pólizas" contra su propio registro de producción, con
        # descripciones identicas). Override a un documento sintetico que no
        # existe en la base evita el choque.
        clone["cliente_documento"] = documento
    if no_llamar:
        clone["no_llamar"] = True
        clone["no_llamar_motivo"] = "prueba_entidad_estatal"

    res = await db.debtors.insert_one(clone)
    test_id = str(res.inserted_id)
    print(f"Deudor de prueba creado: {test_id}")
    print(f"  nombre={clone['nombre']} ramo={clone.get('ramo_nombre')} monto={clone.get('monto')}")
    print(f"  telefono={phone} vencimiento={clone.get('vencimiento')} intentos={clone['intentos']}")
    return test_id


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("accion", choices=["setup-only", "call", "llamar-ahora", "delete", "cleanup"])
    ap.add_argument("--phone", default=DEFAULT_PHONE)
    ap.add_argument("--vencimiento", default=None)
    ap.add_argument("--intentos", type=int, default=None)
    ap.add_argument("--source", default=DEFAULT_SOURCE)
    ap.add_argument("--no-llamar", action="store_true")
    ap.add_argument("--documento", default=None, help="override cliente_documento (evita choque con el real del source)")
    args = ap.parse_args()

    db = await _get_db()

    if args.accion == "cleanup":
        result = await db.debtors.delete_many({"user_id": USER_ID, "is_test": True})
        print(f"Borrados {result.deleted_count} deudores de prueba")
        db.client.close()
        return

    if args.accion == "delete":
        result = await db.debtors.delete_many({"user_id": USER_ID, "is_test": True})
        print(f"Deudor(es) de prueba borrado(s): {result.deleted_count} — el número ya no está identificado")
        db.client.close()
        return

    test_id = await _make_test_debtor(
        db, args.phone, args.source, args.vencimiento, args.intentos,
        no_llamar=args.no_llamar, documento=args.documento,
    )

    if args.accion == "setup-only":
        print("Listo — el evaluador ya puede marcar a +57 606 347 0078")
        db.client.close()
        return

    token = create_access_token(data={"sub": USER_ID, "role": "client"})
    async with httpx.AsyncClient(timeout=30, verify=certifi.where()) as client:
        if args.accion == "llamar-ahora":
            r = await client.post(
                f"{PROD}/api/cobranza/debtors/{test_id}/llamar-ahora",
                headers={"Authorization": f"Bearer {token}"},
            )
            print(f"llamar-ahora -> {r.status_code}")
            print(r.text)
        else:
            r = await client.post(
                f"{PROD}/api/cobranza/voice/call/initiate-v2",
                json={"debtor_id": test_id},
                headers={"Authorization": f"Bearer {token}"},
            )
            print(f"initiate-v2 -> {r.status_code}")
            print(r.text)

    db.client.close()


if __name__ == "__main__":
    asyncio.run(main())
