"""
minutes.py — paquete de minutos de voz por tenant (ledger append-only).

Landa vende paquetes de minutos (DPG: 1500). Fuente de verdad =
db.cobranza_minutos_ledger, una entrada por movimiento:

    {user_id, tipo: "compra"|"consumo"|"ajuste", minutos: +N | -N,
     segundos?, call_sid?, debtor_id?, nota?, actor?, created_at}

Saldo = suma de `minutos` del tenant. Consumo = ceil(CallDuration/60) por
llamada (redondeo al minuto por llamada, estándar telco), capturado del status
callback de Twilio e idempotente por call_sid (índice único parcial — un
callback reenviado no descuenta dos veces).

Las COMPRAS/AJUSTES son staff-only (el tenant nunca escribe su propio saldo).
"""
import asyncio
import logging
import math
import os
from datetime import datetime, timezone
from typing import Optional

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger("cobranza.minutes")

COLLECTION = "cobranza_minutos_ledger"


def call_status_kwargs() -> dict:
    """kwargs de Twilio calls.create() para que reporte la duración al colgar
    (alimenta el consumo del ledger vía POST /api/cobranza/voice/call-status)."""
    webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
    return {
        "status_callback": f"{webhook_url}/api/cobranza/voice/call-status",
        "status_callback_method": "POST",
    }


class MinutesExhaustedError(Exception):
    """El tenant no tiene minutos disponibles — no se puede marcar."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def ensure_indexes(db) -> None:
    """Índice único parcial por call_sid (idempotencia del consumo) + lookup por tenant."""
    await db[COLLECTION].create_index(
        [("call_sid", 1)],
        unique=True,
        partialFilterExpression={"tipo": "consumo"},
        name="uniq_consumo_call_sid",
    )
    await db[COLLECTION].create_index([("user_id", 1), ("created_at", -1)])


async def get_saldo(db, user_id: str) -> dict:
    """Resumen del paquete: comprados, consumidos, ajustes y restantes (en minutos)."""
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$tipo",
            "minutos": {"$sum": "$minutos"},
            "n": {"$sum": 1},
        }},
    ]
    by_tipo = {r["_id"]: r async for r in db[COLLECTION].aggregate(pipeline)}
    comprados = int(by_tipo.get("compra", {}).get("minutos", 0))
    consumidos = -int(by_tipo.get("consumo", {}).get("minutos", 0))  # guardados en negativo
    ajustes = int(by_tipo.get("ajuste", {}).get("minutos", 0))
    restantes = comprados + ajustes - consumidos
    return {
        "minutos_comprados": comprados,
        "minutos_consumidos": consumidos,
        "minutos_ajustes": ajustes,
        "minutos_restantes": restantes,
        "llamadas_registradas": int(by_tipo.get("consumo", {}).get("n", 0)),
    }


async def require_saldo(db, user_id: str) -> int:
    """
    Guard pre-marcación: lanza MinutesExhaustedError si el saldo es <= 0.
    Devuelve los minutos restantes. Un tenant sin NINGÚN movimiento en el ledger
    también bloquea (saldo 0): sin paquete cargado no hay servicio de voz.
    """
    saldo = await get_saldo(db, user_id)
    restantes = saldo["minutos_restantes"]
    if restantes <= 0:
        raise MinutesExhaustedError(
            f"Paquete de minutos agotado (restantes={restantes}). "
            "Contacte a Landa Tech para una recarga."
        )
    return restantes


async def record_purchase(
    db, user_id: str, minutos: int, *, nota: str = "", actor: str = "staff",
    tipo: str = "compra",
) -> dict:
    """Registra una compra/recarga (o un 'ajuste', que admite minutos negativos)."""
    if tipo not in ("compra", "ajuste"):
        raise ValueError(f"tipo inválido: {tipo!r}")
    if tipo == "compra" and minutos <= 0:
        raise ValueError("una compra debe ser de minutos > 0")
    doc = {
        "user_id": user_id, "tipo": tipo, "minutos": int(minutos),
        "nota": nota, "actor": actor, "created_at": _utcnow(),
    }
    await db[COLLECTION].insert_one(doc)
    logger.info("[minutes] %s user=%s minutos=%+d actor=%s", tipo, user_id, minutos, actor)
    return await get_saldo(db, user_id)


# Referencias fuertes a las tareas de reembolso diferidas (anti-GC).
_refund_tasks: set = set()


def refund_uncontacted_call(db, call_sid: str, *, delay_seconds: int = 20) -> None:
    """
    Regla de negocio (DPG): una llamada SIN contacto real (buzón de voz, nadie
    habló) no se le cobra al cliente. El consumo lo registra el status-callback
    de Twilio, que puede llegar DESPUÉS del post-call — por eso el reembolso
    corre diferido en background: espera, busca el consumo por call_sid y lo
    revierte con un 'ajuste' idempotente (refund_call_sid único por llamada).
    """
    if not call_sid:
        return

    async def _do():
        try:
            await asyncio.sleep(delay_seconds)
            consumo = await db[COLLECTION].find_one({"call_sid": call_sid, "tipo": "consumo"})
            if not consumo:
                return  # nunca se cobró (no-answer/busy → duration=0)
            if await db[COLLECTION].find_one({"refund_call_sid": call_sid}):
                return  # ya reembolsada (reintento del post-call)
            minutos = abs(int(consumo.get("minutos") or 0))
            if minutos <= 0:
                return
            await db[COLLECTION].insert_one({
                "user_id": consumo["user_id"], "tipo": "ajuste", "minutos": minutos,
                "refund_call_sid": call_sid, "debtor_id": consumo.get("debtor_id"),
                "nota": "reembolso: llamada sin contacto (buzón / no contestó)",
                "actor": "sistema", "created_at": _utcnow(),
            })
            logger.info("[minutes] reembolso user=%s call=%s +%dmin (sin contacto)",
                        consumo["user_id"], call_sid, minutos)
        except Exception:
            logger.exception("[minutes] reembolso falló call=%s", call_sid)

    task = asyncio.create_task(_do())
    _refund_tasks.add(task)
    task.add_done_callback(_refund_tasks.discard)


async def record_call_consumption(
    db, call_sid: str, duration_seconds: int,
    *, user_id: Optional[str] = None, debtor_id: Optional[str] = None,
) -> bool:
    """
    Descuenta una llamada terminada: ceil(segundos/60), mínimo 1 min si conectó.
    Idempotente por call_sid (índice único) — reintentos de Twilio no duplican.
    Si no viene user_id, lo resuelve del mapping de la llamada (calls_in_progress
    o el deudor con ese vapi_call_id). Devuelve True si registró, False si ya
    existía o no se pudo atribuir.
    """
    if not call_sid:
        return False
    duration_seconds = max(0, int(duration_seconds or 0))
    if duration_seconds == 0:
        # no-answer/busy/failed: Twilio no cobra y nosotros tampoco.
        return False

    if user_id is None:
        mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})
        if mapping:
            user_id = mapping.get("user_id")
            debtor_id = debtor_id or mapping.get("debtor_id")
        else:
            # el mapping tiene TTL — fallback al deudor que guardó el sid
            debtor = await db.debtors.find_one(
                {"vapi_call_id": call_sid}, {"user_id": 1}
            )
            if debtor:
                user_id = debtor.get("user_id")
                debtor_id = debtor_id or str(debtor["_id"])
    if not user_id:
        logger.error("[minutes] consumo NO atribuible: call_sid=%s dur=%ss", call_sid, duration_seconds)
        return False

    minutos = math.ceil(duration_seconds / 60)
    try:
        await db[COLLECTION].insert_one({
            "user_id": user_id, "tipo": "consumo", "minutos": -minutos,
            "segundos": duration_seconds, "call_sid": call_sid,
            "debtor_id": debtor_id, "created_at": _utcnow(),
        })
    except DuplicateKeyError:
        return False
    logger.info("[minutes] consumo user=%s call=%s %ss -> -%dmin", user_id, call_sid, duration_seconds, minutos)
    return True
