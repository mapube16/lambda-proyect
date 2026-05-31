"""
ARQ Worker — executes the Hive prospecting pipeline out-of-process.

Runs as a separate Railway service: `arq worker.WorkerSettings`.
Events are written to MongoDB; the frontend polls /api/runs/{run_id}/status.
"""
import asyncio
import logging
import os

import database
from arq_pool import redis_settings_from_url
from hive_adapter import HiveAdapter

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)


async def run_prospecting_job(
    ctx: dict,
    run_id: str,
    user_id: str,
    campaign: dict,
    max_results: int,
    personality_prompt: str,
    runtime_agents: list,
    excluded_domains: list,
    source_priority: str,
) -> dict:
    """ARQ job: run the Hive pipeline. Results are persisted to MongoDB for polling."""

    async def noop_event(uid: str, message: dict) -> None:
        """No-op — frontend polls MongoDB instead of receiving WS events."""
        pass

    adapter = HiveAdapter(send_to_user_callback=noop_event)
    try:
        await adapter.start_run(
            user_id=user_id,
            inputs={
                "campaign": campaign,
                "max_results": max_results,
                "personality_prompt": personality_prompt,
                "runtime_agents": runtime_agents,
                "excluded_domains": excluded_domains,
                "source_priority": source_priority,
            },
            run_id=run_id,
            save_lead=database.save_lead,
        )
        task = adapter._runs.get(user_id)
        if isinstance(task, asyncio.Task):
            await task
        try:
            await database.update_run_status(run_id, status="complete")
        except Exception as db_exc:
            logger.warning("[worker] could not update run status to complete: %s", db_exc)
        return {"status": "complete", "run_id": run_id}
    except Exception as exc:
        logger.error("[worker] job failed run=%s: %s", run_id, exc)
        try:
            await database.update_run_status(run_id, status="error")
        except Exception:
            pass
        raise


async def on_startup(ctx: dict) -> None:
    await database.init_db()
    logger.info("[worker] started — mongo initialized")


async def on_shutdown(ctx: dict) -> None:
    pass


class WorkerSettings:
    functions = [run_prospecting_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings_from_url()
    max_jobs = 5
    job_timeout = 600
    keep_result = 86400
    max_tries = 1
