"""
campaign_scheduler.py — APScheduler jobs for the automated cobranza call campaign.

Three periodic jobs:
  - pre_vencimiento_job:      fires every 60 min — reminds pendiente debtors 3 days before due
  - post_vencimiento_job:     fires every 60 min — retries sin_contacto/pendiente debtors after due
  - rescue_stuck_llamando_job: fires every 10 min — rescues debtors stuck in 'llamando' > 15 min

All jobs respect Ley 2300 compliance via is_contact_allowed_now() and has_been_contacted_today().

Usage:
    from cobranza.campaign_scheduler import register_cobranza_jobs
    register_cobranza_jobs(scheduler)   # called in main.py lifespan
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

from database import get_db
from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today
from cobranza.vapi_client import initiate_call

logger = logging.getLogger("cobranza.campaign_scheduler")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def safe_initiate_call(debtor: dict, config: dict) -> None:
    """
    Fire-and-forget wrapper around initiate_call().
    On success: stores vapi_call_id on the debtor document.
    On failure: resets estado to 'pendiente' so the next job run can retry.
    """
    try:
        call_id = await initiate_call(debtor, config)
        await get_db().debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"vapi_call_id": call_id, "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.error("[scheduler] Call failed for debtor %s: %s", debtor["_id"], e)
        await get_db().debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
        )


# ---------------------------------------------------------------------------
# Job 1: Pre-vencimiento reminder (3 days before due, pendiente debtors)
# ---------------------------------------------------------------------------

async def pre_vencimiento_job() -> None:
    """
    Contacts debtors in estado='pendiente' whose vencimiento is within the next
    3 days (exclusive of past-due). Fires once per debtor per day (Ley 2300).
    """
    if not is_contact_allowed_now():
        logger.debug("[pre_vencimiento_job] Outside allowed hours — skipping")
        return

    now = datetime.now(timezone.utc)
    in_3_days = now + timedelta(days=3)

    db = get_db()
    cursor = db.debtors.find(
        {
            "estado": "pendiente",
            "vencimiento": {"$lte": in_3_days, "$gt": now},
        }
    )
    debtors = await cursor.to_list(length=None)
    logger.info("[pre_vencimiento_job] Found %d pre-vencimiento debtors", len(debtors))

    for debtor in debtors:
        if has_been_contacted_today(debtor):
            logger.debug("[pre_vencimiento_job] Debtor %s already contacted today — skip", debtor["_id"])
            continue

        user_id = debtor.get("user_id")
        config_doc = await db.cobranza_config.find_one({"user_id": user_id})
        if not config_doc:
            logger.debug("[pre_vencimiento_job] No config for user_id=%s — skip debtor %s", user_id, debtor["_id"])
            continue
        config = config_doc.get("estrategia", {})

        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "llamando", "updated_at": datetime.now(timezone.utc)}},
        )
        asyncio.create_task(safe_initiate_call(debtor, config))


# ---------------------------------------------------------------------------
# Job 2: Post-vencimiento retry (sin_contacto / pendiente, past due)
# ---------------------------------------------------------------------------

async def post_vencimiento_job() -> None:
    """
    Retries debtors in estado='pendiente' or 'sin_contacto' whose vencimiento
    has already passed. Respects max_intentos, frecuencia_dias, and Ley 2300.
    """
    if not is_contact_allowed_now():
        logger.debug("[post_vencimiento_job] Outside allowed hours — skipping")
        return

    now = datetime.now(timezone.utc)

    db = get_db()
    cursor = db.debtors.find(
        {
            "estado": {"$in": ["pendiente", "sin_contacto"]},
            "vencimiento": {"$lte": now},
        }
    )
    debtors = await cursor.to_list(length=None)
    logger.info("[post_vencimiento_job] Found %d post-vencimiento debtors", len(debtors))

    for debtor in debtors:
        intentos = debtor.get("intentos", 0)
        max_intentos = debtor.get("max_intentos", 5)

        # Exhaused attempts → set agotado and move on
        if intentos >= max_intentos:
            logger.info("[post_vencimiento_job] Debtor %s exhausted (%d/%d) — marking agotado", debtor["_id"], intentos, max_intentos)
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "agotado", "updated_at": datetime.now(timezone.utc)}},
            )
            continue

        if has_been_contacted_today(debtor):
            logger.debug("[post_vencimiento_job] Debtor %s already contacted today — skip", debtor["_id"])
            continue

        user_id = debtor.get("user_id")
        config_doc = await db.cobranza_config.find_one({"user_id": user_id})
        if not config_doc:
            logger.debug("[post_vencimiento_job] No config for user_id=%s — skip debtor %s", user_id, debtor["_id"])
            continue
        config = config_doc.get("estrategia", {})

        # Respect frecuencia_dias: days since last contact
        frecuencia_dias = config.get("frecuencia_dias", 1)
        ultimo = debtor.get("ultimo_contacto_fecha")
        if ultimo is not None:
            if hasattr(ultimo, "tzinfo") and ultimo.tzinfo is None:
                import pytz
                ultimo = pytz.utc.localize(ultimo)
            days_since = (now - ultimo).days
            if days_since < frecuencia_dias:
                logger.debug(
                    "[post_vencimiento_job] Debtor %s last contacted %d days ago (frecuencia=%d) — skip",
                    debtor["_id"], days_since, frecuencia_dias,
                )
                continue

        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "llamando", "updated_at": datetime.now(timezone.utc)}},
        )
        asyncio.create_task(safe_initiate_call(debtor, config))


# ---------------------------------------------------------------------------
# Job 3: Rescue stuck 'llamando' debtors (Vapi end-of-call-report intermittent)
# ---------------------------------------------------------------------------

async def rescue_stuck_llamando_job() -> None:
    """
    Resets debtors stuck in estado='llamando' for more than 15 minutes back to
    'sin_contacto' so they are eligible for retry by the next job run.

    Handles Pitfall 7: Vapi end-of-call-report webhook may not always arrive.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    db = get_db()
    cursor = db.debtors.find(
        {
            "estado": "llamando",
            "updated_at": {"$lte": cutoff},
        }
    )
    stuck = await cursor.to_list(length=None)

    if stuck:
        logger.warning("[rescue_stuck_llamando_job] Rescuing %d debtors stuck in 'llamando'", len(stuck))

    for debtor in stuck:
        logger.warning(
            "[rescue_stuck_llamando_job] Debtor %s stuck in llamando since %s — resetting to sin_contacto",
            debtor["_id"], debtor.get("updated_at"),
        )
        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "sin_contacto", "updated_at": datetime.now(timezone.utc)}},
        )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

def register_cobranza_jobs(scheduler) -> None:
    """
    Register all 3 cobranza campaign jobs on the given APScheduler instance.

    Call this from main.py lifespan *after* scheduler.start() has been called.
    Does NOT import scheduler at module level to avoid circular imports.

    Args:
        scheduler: AsyncIOScheduler instance from landa.scheduler
    """
    scheduler.add_job(
        pre_vencimiento_job,
        "interval",
        minutes=60,
        id="cobr_pre_vencimiento",
        replace_existing=True,
    )
    scheduler.add_job(
        post_vencimiento_job,
        "interval",
        minutes=60,
        id="cobr_post_vencimiento",
        replace_existing=True,
    )
    scheduler.add_job(
        rescue_stuck_llamando_job,
        "interval",
        minutes=10,
        id="cobr_rescue_llamando",
        replace_existing=True,
    )
    logger.info(
        "[register_cobranza_jobs] Registered: cobr_pre_vencimiento (60m), "
        "cobr_post_vencimiento (60m), cobr_rescue_llamando (10m)"
    )
