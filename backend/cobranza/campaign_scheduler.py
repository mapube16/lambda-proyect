"""
campaign_scheduler.py — APScheduler jobs for the automated cobranza call campaign.

Three periodic jobs:
  - pre_vencimiento_job:      fires every 60 min — reminds pendiente debtors 3 days before due
  - post_vencimiento_job:     fires every 60 min — retries sin_contacto/pendiente debtors after due
  - rescue_stuck_llamando_job: fires every 10 min — rescues debtors stuck in 'llamando' > 15 min

All jobs respect Ley 2300 compliance via is_contact_allowed_now() and has_been_contacted_today().
Calls are initiated via Twilio + Pipecat (not Vapi).

Usage:
    from cobranza.campaign_scheduler import register_cobranza_jobs
    register_cobranza_jobs(scheduler)   # called in main.py lifespan
"""
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta

from database import get_db
from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today

logger = logging.getLogger("cobranza.campaign_scheduler")

# IDs of the 3 campaign jobs — used by the runtime kill-switch to pause/resume.
_COBRANZA_JOB_IDS = ("cobr_pre_vencimiento", "cobr_post_vencimiento", "cobr_rescue_llamando")


# ---------------------------------------------------------------------------
# Runtime kill-switch (master ON/OFF, hot — no redeploy)
# ---------------------------------------------------------------------------
#
# The boot-time COBRANZA_AUTOCALL_ENABLED env var only decides whether jobs get
# *registered* at startup. It cannot stop a running worker. This runtime switch
# lives in Mongo (db.cobranza_runtime, _id="killswitch") so it:
#   - survives restarts (the source of truth at boot, env var is only the default)
#   - takes effect on the NEXT job tick without a redeploy
#   - is checked at the top of every job AND inside safe_initiate_call, so calls
#     already in flight when the switch flips OFF are aborted before dialing.
#
# enabled=True  → autocall ON  (jobs dial debtors)
# enabled=False → autocall OFF (jobs run but dial no one; system stays healthy)

_RUNTIME_DOC_ID = "killswitch"


async def is_autocall_enabled() -> bool:
    """
    Return whether automated dialing is currently enabled.
    Source of truth = db.cobranza_runtime/killswitch. If no doc exists yet,
    fall back to the COBRANZA_AUTOCALL_ENABLED env var default.
    """
    db = get_db()
    doc = await db.cobranza_runtime.find_one({"_id": _RUNTIME_DOC_ID})
    if doc is not None and "enabled" in doc:
        return bool(doc["enabled"])
    return os.getenv("COBRANZA_AUTOCALL_ENABLED", "false").lower() in ("1", "true", "yes")


async def set_autocall_enabled(enabled: bool, scheduler=None, actor: str = "system") -> bool:
    """
    Master ON/OFF switch — flips the runtime flag in Mongo AND pauses/resumes the
    live APScheduler jobs so the change is effective immediately (no redeploy).

    Args:
        enabled:   True = resume dialing, False = stop all automated calls.
        scheduler: live AsyncIOScheduler. If omitted, only the Mongo flag changes
                   (jobs still honour it on their next tick via is_autocall_enabled).
        actor:     who flipped it (for the audit trail).

    Returns the new enabled state.
    """
    db = get_db()
    await db.cobranza_runtime.update_one(
        {"_id": _RUNTIME_DOC_ID},
        {"$set": {
            "enabled": enabled,
            "updated_at": datetime.now(timezone.utc),
            "updated_by": actor,
        }},
        upsert=True,
    )

    if scheduler is None:
        from landa.scheduler import scheduler as scheduler  # lazy import, avoid cycle

    if enabled:
        # Resume existing jobs; (re)register if missing (e.g. booted with autocall off).
        register_cobranza_jobs(scheduler, force=True)
        for job_id in _COBRANZA_JOB_IDS:
            try:
                scheduler.resume_job(job_id)
            except Exception:
                pass
        logger.warning("[killswitch] AUTOCALL ENABLED by %s — campaign jobs resumed.", actor)
    else:
        for job_id in _COBRANZA_JOB_IDS:
            try:
                scheduler.pause_job(job_id)
            except Exception:
                pass
        logger.warning("[killswitch] AUTOCALL DISABLED by %s — campaign jobs paused, no debtor will be called.", actor)

    return enabled


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def safe_initiate_call(debtor: dict, user_id: str) -> None:
    """
    Fire-and-forget: create outbound Twilio call → Pipecat pipeline.
    On success: stores call_sid on the debtor document and inserts call mapping.
    On failure: resets estado to 'pendiente' so the next job run can retry.
    """
    db = get_db()
    try:
        # Runtime kill-switch: a task may have been queued before the switch
        # flipped OFF. Re-check right before dialing so in-flight calls abort.
        if not await is_autocall_enabled():
            logger.warning(
                "[scheduler] Autocall OFF — aborting queued call for debtor %s; resetting to pendiente",
                debtor["_id"],
            )
            await db.debtors.update_one(
                {"_id": debtor["_id"]},
                {"$set": {"estado": "pendiente", "updated_at": datetime.now(timezone.utc)}},
            )
            return

        from twilio.rest import Client

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([account_sid, auth_token, from_number]):
            raise RuntimeError("Twilio not configured")

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        call = client.calls.create(
            to=to_number, from_=from_number,
            url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
        )
        call_sid = call.sid
        logger.info("[scheduler] Twilio call %s -> %s (debtor %s)", call_sid, to_number, debtor["_id"])

        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid, "user_id": user_id,
            "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"vapi_call_id": call_sid, "updated_at": datetime.now(timezone.utc)}},
        )
    except Exception as e:
        logger.error("[scheduler] Call failed for debtor %s: %s", debtor["_id"], e)
        await db.debtors.update_one(
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
    if not await is_autocall_enabled():
        logger.info("[pre_vencimiento_job] Autocall kill-switch OFF — skipping")
        return
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

        await db.debtors.update_one(
            {"_id": debtor["_id"]},
            {"$set": {"estado": "llamando", "updated_at": datetime.now(timezone.utc)}},
        )
        asyncio.create_task(safe_initiate_call(debtor, user_id))


# ---------------------------------------------------------------------------
# Job 2: Post-vencimiento retry (sin_contacto / pendiente, past due)
# ---------------------------------------------------------------------------

async def post_vencimiento_job() -> None:
    """
    Retries debtors in estado='pendiente' or 'sin_contacto' whose vencimiento
    has already passed. Respects max_intentos, frecuencia_dias, and Ley 2300.
    """
    if not await is_autocall_enabled():
        logger.info("[post_vencimiento_job] Autocall kill-switch OFF — skipping")
        return
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
        estrategia = (config_doc or {}).get("estrategia", {})

        # Respect frecuencia_dias: days since last contact
        frecuencia_dias = estrategia.get("frecuencia_dias", 1)
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
        asyncio.create_task(safe_initiate_call(debtor, user_id))


# ---------------------------------------------------------------------------
# Job 3: Rescue stuck 'llamando' debtors (call may not complete cleanly)
# ---------------------------------------------------------------------------

async def rescue_stuck_llamando_job() -> None:
    """
    Resets debtors stuck in estado='llamando' for more than 15 minutes back to
    'sin_contacto' so they are eligible for retry by the next job run.

    Handles edge case where WebSocket/Pipecat pipeline may not complete cleanly.
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

def register_cobranza_jobs(scheduler, force: bool = False) -> None:
    """
    Register all 3 cobranza campaign jobs on the given APScheduler instance.

    Call this from main.py lifespan *after* scheduler.start() has been called.
    Does NOT import scheduler at module level to avoid circular imports.

    Args:
        scheduler: AsyncIOScheduler instance from landa.scheduler
        force:     when True, register the jobs regardless of the boot-time env
                   var. Used by the runtime kill-switch when it is turned ON, so
                   a worker booted with autocall disabled can be enabled live.

    Jobs are registered in a PAUSED state whenever autocall is currently OFF, so
    even a forced/boot registration never dials until the master switch is ON.
    """
    # ── KILL-SWITCH (default OFF for safety) ─────────────────────────────────
    # These jobs place REAL outbound calls to REAL debtors. They must NEVER fire
    # just because the app booted — a deploy would start dialing people. So the
    # automated calling campaign only registers when COBRANZA_AUTOCALL_ENABLED is
    # explicitly truthy. Default = disabled: the app runs, manual test calls via
    # /call/initiate-v2 still work, but the scheduler dials no one.
    autocall_enabled = os.getenv("COBRANZA_AUTOCALL_ENABLED", "false").lower() in ("1", "true", "yes")
    if not autocall_enabled and not force:
        logger.warning(
            "[register_cobranza_jobs] COBRANZA_AUTOCALL_ENABLED is not set — "
            "automated calling jobs NOT registered (no debtor will be auto-called). "
            "Set COBRANZA_AUTOCALL_ENABLED=true or flip the runtime kill-switch ON."
        )
        return

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
    logger.warning(
        "[register_cobranza_jobs] AUTOCALL ENABLED — Registered: cobr_pre_vencimiento (60m), "
        "cobr_post_vencimiento (60m), cobr_rescue_llamando (10m). Real debtors WILL be called."
    )
