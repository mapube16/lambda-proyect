"""
scheduler.py — APScheduler AsyncIOScheduler for Landa lead actions.

Architecture note: APScheduler MongoDB jobstore requires pymongo sync driver which
conflicts with this project's Motor async stack. Instead we use MemoryJobStore for
the APScheduler instance (job dispatch) and store durable action records manually in
db.scheduled_actions (MongoDB via Motor). On app restart, pending actions are reloaded
via _bootstrap_pending_jobs() called from start_scheduler().
"""
import os
import sys
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger("landa.scheduler")

scheduler = AsyncIOScheduler()


async def start_scheduler() -> None:
    """Start the scheduler and reload any pending actions from MongoDB."""
    if not scheduler.running:
        scheduler.start()
        logger.info("Landa scheduler started")
    await _bootstrap_pending_jobs()


def shutdown_scheduler() -> None:
    """Graceful shutdown — called in lifespan teardown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Landa scheduler stopped")


async def _bootstrap_pending_jobs() -> int:
    """
    On startup, reload scheduled_actions with estado='pendiente' and
    fecha_programada in the future, re-registering them with APScheduler.
    Jobs that are past due are marked 'vencido' (to be handled by Phase 13 agents).
    Returns count of reloaded jobs.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    pending = await db.scheduled_actions.find(
        {"estado": "pendiente"}
    ).to_list(length=10_000)

    reloaded = 0
    for action in pending:
        fecha = action.get("fecha_programada")
        if not fecha:
            continue
        if fecha <= now:
            await db.scheduled_actions.update_one(
                {"_id": action["_id"]},
                {"$set": {"estado": "vencido"}},
            )
        else:
            action_id = str(action["_id"])
            scheduler.add_job(
                _noop_stub,
                "date",
                run_date=fecha,
                id=action_id,
                replace_existing=True,
                args=[action_id, action.get("tipo", "unknown")],
            )
            reloaded += 1

    logger.info("Landa scheduler bootstrap: %d pending jobs reloaded", reloaded)
    return reloaded


async def _noop_stub(action_id: str, tipo: str) -> None:
    """
    Stub job function for Phase 12. Phase 13 will replace this with real agent dispatch.
    Marks the scheduled_action as 'ejecutado' when triggered.
    """
    logger.info("Landa scheduled action triggered: action_id=%s tipo=%s", action_id, tipo)
    db = get_db()
    from bson import ObjectId
    try:
        await db.scheduled_actions.update_one(
            {"_id": ObjectId(action_id)},
            {"$set": {"estado": "ejecutado", "executed_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.error("Failed to mark action %s as ejecutado: %s", action_id, e)


async def schedule_retry(
    lead_id: str,
    canal: str,
    days: int = 7,
    mensaje: Optional[str] = None,
) -> str:
    """
    Schedule a retry action for a lead in `days` days on `canal`.
    Returns the new scheduled_actions document _id as str.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    fecha = now + timedelta(days=days)
    doc = {
        "tipo": "reintento",
        "lead_id": lead_id,
        "estado": "pendiente",
        "fecha_programada": fecha,
        "contexto": {
            "canal": canal,
            "dias": days,
            "mensaje": mensaje,
        },
        "created_at": now,
    }
    result = await db.scheduled_actions.insert_one(doc)
    action_id = str(result.inserted_id)

    if scheduler.running:
        scheduler.add_job(
            _noop_stub,
            "date",
            run_date=fecha,
            id=action_id,
            replace_existing=True,
            args=[action_id, "reintento"],
        )
    logger.info("Scheduled retry: lead_id=%s canal=%s days=%d action_id=%s", lead_id, canal, days, action_id)
    return action_id


async def schedule_nurturing(
    lead_id: str,
    mes: int,
    motivo: Optional[str] = None,
) -> str:
    """
    Schedule a nurturing touchpoint for a lead in `mes` months.
    Returns the new scheduled_actions document _id as str.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    fecha = now + timedelta(days=mes * 30)
    doc = {
        "tipo": "nurturing",
        "lead_id": lead_id,
        "estado": "pendiente",
        "fecha_programada": fecha,
        "contexto": {
            "mes": mes,
            "motivo": motivo,
        },
        "created_at": now,
    }
    result = await db.scheduled_actions.insert_one(doc)
    action_id = str(result.inserted_id)

    if scheduler.running:
        scheduler.add_job(
            _noop_stub,
            "date",
            run_date=fecha,
            id=action_id,
            replace_existing=True,
            args=[action_id, "nurturing"],
        )
    logger.info("Scheduled nurturing: lead_id=%s mes=%d action_id=%s", lead_id, mes, action_id)
    return action_id


async def cancel_lead_actions(lead_id: str) -> int:
    """
    Cancel all pending scheduled actions for a lead.
    Sets estado='cancelado' in MongoDB and removes from in-memory scheduler.
    Returns count of cancelled actions.
    """
    db = get_db()
    pending = await db.scheduled_actions.find(
        {"lead_id": lead_id, "estado": "pendiente"}
    ).to_list(length=1000)

    if not pending:
        return 0

    ids = [doc["_id"] for doc in pending]
    result = await db.scheduled_actions.update_many(
        {"_id": {"$in": ids}},
        {"$set": {"estado": "cancelado", "cancelled_at": datetime.now(timezone.utc)}},
    )

    if scheduler.running:
        for doc in pending:
            job_id = str(doc["_id"])
            try:
                scheduler.remove_job(job_id)
            except Exception:
                pass

    logger.info("Cancelled %d actions for lead_id=%s", result.modified_count, lead_id)
    return result.modified_count
