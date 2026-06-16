"""
escalation_handler.py — Sub-agent for escalation decisions.

Sets debtor estado="escalado", records historial entry, and pushes a dashboard WS event.

Threat: T-25-03 — filter includes {_id, user_id} (tenant isolation).
"""
import logging
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId

logger = logging.getLogger("cobranza.sub_agents.escalation_handler")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _push_ws_event(user_id: str, debtor_id: str, estado: str) -> None:
    """
    Push real-time WebSocket event to the dashboard.
    Extracted as a named function so tests can monkeypatch it cleanly.
    Non-fatal: errors are logged as warnings, not re-raised.
    """
    try:
        from services.connection_manager import manager
        await manager.send_to_user(
            str(user_id),
            {"type": "debtor_update", "debtor_id": debtor_id, "estado": estado},
        )
    except Exception as ws_exc:
        logger.warning("[escalation_handler] WS push failed (non-fatal): %s", ws_exc)


async def escalate(db, user_id: str, debtor_id: str, reason: str) -> dict:
    """
    Escalate a debtor: set estado="escalado", increment intentos, push WS event.

    Args:
        db: Motor database instance.
        user_id: Authenticated tenant's user_id (enforces tenant isolation).
        debtor_id: String representation of the debtor ObjectId.
        reason: Human-readable escalation reason (stored in historial_llamadas).

    Returns:
        {"ok": True, "estado": "escalado"}          — on success.
        {"ok": False, "error": "invalid_id"}         — invalid ObjectId.
        {"ok": False, "error": "not_found"}          — debtor not owned by user_id.
        {"ok": False, "error": "..."}                — unexpected DB error.
    """
    try:
        oid = ObjectId(debtor_id)
    except (InvalidId, Exception):
        logger.warning("[escalation_handler] invalid_id: %s", debtor_id)
        return {"ok": False, "error": "invalid_id"}

    now = _utcnow()
    historial_entry = {
        "tipo": "escalacion",
        "reason": reason,
        "ts": now,
    }

    try:
        result = await db.debtors.update_one(
            {"_id": oid, "user_id": user_id},   # user_id always in filter (T-25-03)
            {
                "$set": {"estado": "escalado", "updated_at": now},
                "$inc": {"intentos": 1},
                "$push": {"historial_llamadas": historial_entry},
            },
        )
    except Exception as e:
        logger.error("[escalation_handler] DB error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)[:100]}

    if result.matched_count == 0:
        logger.warning("[escalation_handler] not_found: debtor=%s user=%s (cross-tenant blocked)", debtor_id, user_id)
        return {"ok": False, "error": "not_found"}

    logger.info("[escalation_handler] escalated debtor=%s user=%s reason=%s", debtor_id, user_id, reason)

    # Push WS event (non-fatal) — patchable for tests
    await _push_ws_event(user_id, debtor_id, "escalado")

    return {"ok": True, "estado": "escalado"}
