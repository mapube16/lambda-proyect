"""
debtor_updater.py — Sub-agent for updating debtor status and payment confirmation.

Threat: T-25-03 — All db.debtors writes filter by {_id, user_id} to prevent
cross-tenant writes (Elevation of Privilege). Cross-tenant attempts return ok=False.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId

logger = logging.getLogger("cobranza.sub_agents.debtor_updater")


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    """Convert MongoDB document: _id ObjectId -> str, return None if None."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def update_debtor_status(db, user_id: str, debtor_id: str, fields: dict) -> dict:
    """
    Update a debtor document — ONLY when {_id, user_id} match (tenant isolation).

    Args:
        db: Motor database instance.
        user_id: Authenticated tenant's user_id (from call session).
        debtor_id: String representation of the debtor ObjectId.
        fields: Fields to $set on the debtor document.

    Returns:
        {"ok": True, "debtor": {...}}  — on success.
        {"ok": False, "error": "invalid_id"}  — when debtor_id is not a valid ObjectId.
        {"ok": False, "error": "not_found"}   — when no debtor matches {_id, user_id}
                                                 (cross-tenant write blocked).
    """
    try:
        oid = ObjectId(debtor_id)
    except (InvalidId, Exception):
        logger.warning("[debtor_updater] invalid_id: %s", debtor_id)
        return {"ok": False, "error": "invalid_id"}

    update_payload = {**fields, "updated_at": _utcnow()}

    try:
        result = await db.debtors.find_one_and_update(
            {"_id": oid, "user_id": user_id},   # user_id always in filter (T-25-03)
            {"$set": update_payload},
            return_document=True,
        )
    except Exception as e:
        logger.error("[debtor_updater] DB error: %s", e, exc_info=True)
        return {"ok": False, "error": str(e)[:100]}

    if result is None:
        logger.warning("[debtor_updater] not_found: debtor=%s user=%s (cross-tenant blocked)", debtor_id, user_id)
        return {"ok": False, "error": "not_found"}

    serialized = _serialize(result)
    new_estado = serialized.get("estado", "")

    # Push WS event to dashboard (non-fatal — per PATTERNS Shared Pattern)
    try:
        from main import manager
        await manager.send_to_user(
            str(user_id),
            {"type": "debtor_update", "debtor_id": debtor_id, "estado": new_estado},
        )
    except Exception as ws_exc:
        logger.warning("[debtor_updater] WS push failed (non-fatal): %s", ws_exc)

    logger.info("[debtor_updater] updated debtor=%s user=%s estado=%s", debtor_id, user_id, new_estado)
    return {"ok": True, "debtor": serialized}
