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

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

JOB_ID = "softseguros_daily_sync"


def _daily_hour() -> int:
    try:
        return int(os.getenv("SOFTSEGUROS_SYNC_DAILY_HOUR_UTC", "3"))
    except ValueError:
        return 3


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


async def setup_scheduler(app) -> AsyncIOScheduler:
    """Create, register the daily cron job on, start, and stash an AsyncIOScheduler on app.state."""
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        run_daily_sync_for_all_users,
        trigger=CronTrigger(hour=_daily_hour(), minute=0, timezone="UTC"),
        id=JOB_ID,
        replace_existing=True,
        misfire_grace_time=3600,
    )
    scheduler.start()
    app.state.softseguros_scheduler = scheduler
    logger.info("softseguros scheduler started — daily sync at %02d:00 UTC", _daily_hour())
    return scheduler


def shutdown_scheduler(app) -> None:
    """Shut down the SOFTSEGUROS scheduler if one is attached to app.state."""
    sched = getattr(app.state, "softseguros_scheduler", None)
    if sched is not None:
        try:
            sched.shutdown(wait=False)
        except Exception:  # pragma: no cover
            logger.warning("softseguros scheduler shutdown raised", exc_info=True)
