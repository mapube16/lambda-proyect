"""
softseguros/scheduler.py — APScheduler wiring for the daily SOFTSEGUROS sync.

A single AsyncIOScheduler with one cron job that, once a day at
SOFTSEGUROS_SYNC_DAILY_HOUR_UTC:00 UTC, iterates every user with SOFTSEGUROS
credentials configured and runs a delta sync (mode="cron_daily") for each,
sequentially, to avoid hammering the SOFTSEGUROS API.

setup_scheduler(app) is called from the FastAPI lifespan startup AFTER init_db,
and stores the scheduler on app.state.softseguros_scheduler. On shutdown, call
app.state.softseguros_scheduler.shutdown() if present.
"""
import os
import logging
from datetime import datetime, timezone, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_ID = "softseguros_daily_sync"


def _sync_hours_utc() -> str:
    """
    Horas UTC (lista separada por comas, formato cron) a las que corre el sync.
    Default "13,18" = 08:00 y 13:00 Colombia — UNA HORA ANTES de cada franja de
    llamadas del informe (9-12 / 14-16): así nadie que ya pagó recibe llamada
    (informe §3: verificar el estado actual antes de cada contacto; el sweep
    marca pagados → is_active=False y el dispatcher los salta).
    Compat: si solo existe el viejo SOFTSEGUROS_SYNC_DAILY_HOUR_UTC, se usa.
    """
    hours = os.getenv("SOFTSEGUROS_SYNC_HOURS_UTC")
    if hours:
        return hours
    return os.getenv("SOFTSEGUROS_SYNC_DAILY_HOUR_UTC") or "13,18"


async def run_daily_sync_for_all_users() -> None:
    """Iterate every user with SOFTSEGUROS credentials and run a delta sync sequentially."""
    # Lazy imports — keep module import cheap and avoid circulars.
    from database import get_db
    from softseguros.sync import run_cartera_sync, NoCredentialsError

    db = get_db()
    cursor = db.softseguros_credentials.find({}, {"user_id": 1})
    user_ids = [doc["user_id"] for doc in await cursor.to_list(length=None) if doc.get("user_id")]
    logger.info("softseguros daily sync: %d user(s) with credentials", len(user_ids))
    for user_id in user_ids:
        try:
            # CUOTA model (the real cartera). Uses the tenant's standing config and
            # runs the soft-delete sweep, never touching pinned/manual loads.
            await run_cartera_sync(db, user_id, mode="cron_daily")
        except NoCredentialsError:
            continue
        except Exception:  # noqa: BLE001 — one bad tenant must not abort the rest
            logger.exception("softseguros daily sync failed for user_id=%s", user_id)


async def run_catchup_if_stale(max_age_hours: float = None) -> None:
    """
    Al arrancar: si el último sync de cartera de un tenant es más viejo que
    SOFTSEGUROS_CATCHUP_STALE_HOURS (default 6h), corre un sync cron_daily de una
    vez. El jobstore de APScheduler es EN MEMORIA y el servicio redespliega
    seguido, así que el cron fijo (13,18 UTC) se pierde entre reinicios y la data
    se congela (se detectó cartera de 11 días vieja). Este catch-up garantiza
    data fresca en cada boot cuando ya está vencida, sin re-sincronizar en
    redeploys seguidos (el chequeo de frescura lo evita). Best-effort — nunca
    tumba el arranque.
    """
    from database import get_db
    from softseguros.sync import run_cartera_sync, NoCredentialsError

    max_age = max_age_hours or float(os.getenv("SOFTSEGUROS_CATCHUP_STALE_HOURS", "6"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=max_age)
    db = get_db()
    docs = await db.softseguros_credentials.find({}, {"user_id": 1}).to_list(length=None)
    for doc in docs:
        uid = doc.get("user_id")
        if not uid:
            continue
        st = await db.softseguros_sync_state.find_one({"user_id": uid}, {"last_cartera_sync_at": 1})
        last = (st or {}).get("last_cartera_sync_at")
        if last is not None:
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            if last >= cutoff:
                continue  # fresca — no re-sincronizar en redeploys seguidos
        try:
            logger.warning("softseguros catch-up: cartera stale for user_id=%s (last=%s) — syncing now", uid, last)
            res = await run_cartera_sync(db, uid, mode="cron_daily")
            logger.info("softseguros catch-up done user_id=%s: %s", uid,
                        {k: res.get(k) for k in ("debtors_updated", "debtors_created", "debtors_marked_paid")})
        except NoCredentialsError:
            continue
        except Exception:  # noqa: BLE001 — one bad tenant must not abort the rest
            logger.exception("softseguros catch-up sync failed user_id=%s", uid)


async def setup_scheduler(app) -> AsyncIOScheduler:
    """Create, register the daily cron job on, start, and stash an AsyncIOScheduler on app.state."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_daily_sync_for_all_users,
        trigger=CronTrigger(hour=_sync_hours_utc(), minute=0, timezone="UTC"),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.state.softseguros_scheduler = scheduler
    logger.info("softseguros scheduler started — sync at %s:00 UTC (pre-franja)", _sync_hours_utc())
    return scheduler


def shutdown_scheduler(app) -> None:
    """Shut down the SOFTSEGUROS scheduler if one is attached to app.state."""
    sched = getattr(app.state, "softseguros_scheduler", None)
    if sched is not None:
        try:
            sched.shutdown(wait=False)
        except Exception:  # pragma: no cover
            logger.warning("softseguros scheduler shutdown raised", exc_info=True)
