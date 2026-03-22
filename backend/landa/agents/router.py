"""
router.py — Post-scoring routing for Landa leads.

Applies puntaje thresholds to determine lead destination:
  puntaje < 40   → system_state="REJECTED_BY_AI", no estado transition
  40 <= puntaje < 70 → update_lead_estado(→ "nurturing"), motivo_nurturing="score_bajo"
  puntaje >= 70  → update_lead_estado(→ "checkpoint")
"""
from __future__ import annotations

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from bson import ObjectId
from database import get_db
from landa.state_machine import update_lead_estado

logger = logging.getLogger("landa.agents.router")


async def route_after_scoring(
    lead_id: str,
    user_id: str,
    puntaje: int,
) -> str:
    """
    Route a lead based on its puntaje.

    Args:
        lead_id: MongoDB ObjectId string of the lead document.
        user_id: Owner user id (required by update_lead_estado).
        puntaje: Integer 0-100 from the Investigador scoring.

    Returns:
        str: The routing outcome — "REJECTED_BY_AI", "nurturing", or "checkpoint".
    """
    db = get_db()

    if puntaje < 40:
        # Mark as rejected — no estado transition
        await db.leads.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": {"system_state": "REJECTED_BY_AI"}},
        )
        logger.info("Lead %s REJECTED_BY_AI (puntaje=%d)", lead_id, puntaje)
        return "REJECTED_BY_AI"

    elif 40 <= puntaje < 70:
        # Set motivo first, then transition estado
        await db.leads.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": {"motivo_nurturing": "score_bajo"}},
        )
        try:
            await update_lead_estado(lead_id, user_id, "nurturing")
            logger.info("Lead %s → nurturing (puntaje=%d)", lead_id, puntaje)
        except ValueError as exc:
            logger.warning(
                "Could not transition lead %s → nurturing: %s (already processed?)",
                lead_id, exc,
            )
        return "nurturing"

    else:  # puntaje >= 70
        try:
            await update_lead_estado(lead_id, user_id, "checkpoint")
            logger.info("Lead %s → checkpoint (puntaje=%d)", lead_id, puntaje)
        except ValueError as exc:
            logger.warning(
                "Could not transition lead %s → checkpoint: %s (already processed?)",
                lead_id, exc,
            )
        return "checkpoint"
