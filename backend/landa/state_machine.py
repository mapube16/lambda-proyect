"""
state_machine.py — Landa lead state machine.
8 states, hardcoded transitions per Documento B Sección 5.5.
"""
import sys
import os
# Allow importing from parent backend/ directory
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from typing import Literal
from datetime import datetime, timezone
from bson import ObjectId
from database import get_db

LeadEstado = Literal[
    "investigando", "checkpoint", "pausado", "outreach",
    "handover", "nurturing", "congelado", "archivado"
]

# Source of truth — hardcoded per Documento B Sección 5.5.
# Keys are current states; values are the set of reachable next states.
VALID_TRANSITIONS: dict[str, set[str]] = {
    "investigando": {"checkpoint", "nurturing"},
    "checkpoint":   {"outreach", "pausado", "nurturing"},
    "pausado":      {"outreach", "nurturing"},
    "outreach":     {"handover", "nurturing", "congelado"},
    "congelado":    {"outreach"},
    "nurturing":    {"checkpoint", "archivado"},
    "handover":     {"nurturing"},
    "archivado":    set(),
}

ALL_ESTADOS: frozenset[str] = frozenset(VALID_TRANSITIONS.keys())


async def update_lead_estado(
    lead_id: str,
    user_id: str,
    new_estado: str,
) -> dict:
    """
    Transition a lead to new_estado. Validates against VALID_TRANSITIONS.
    Raises ValueError on invalid transition or missing lead.
    Returns the updated lead document (with _id as str).
    """
    if new_estado not in ALL_ESTADOS:
        raise ValueError(f"Unknown estado '{new_estado}'. Valid: {sorted(ALL_ESTADOS)}")

    db = get_db()
    try:
        oid = ObjectId(lead_id)
    except Exception:
        raise ValueError(f"Invalid lead_id: {lead_id!r}")

    doc = await db.leads.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise ValueError(f"Lead not found: lead_id={lead_id!r} user_id={user_id!r}")

    current = doc.get("estado", "investigando")

    allowed = VALID_TRANSITIONS.get(current, set())
    if new_estado not in allowed:
        raise ValueError(
            f"Invalid transition: '{current}' → '{new_estado}'. "
            f"Allowed from '{current}': {sorted(allowed) or 'none (terminal state)'}"
        )

    now = datetime.now(timezone.utc)
    await db.leads.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"estado": new_estado, "estado_updated_at": now}},
    )
    updated = await db.leads.find_one({"_id": oid, "user_id": user_id})
    updated["_id"] = str(updated["_id"])
    return updated
