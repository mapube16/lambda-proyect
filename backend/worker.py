"""
ARQ Worker — executes the Hive prospecting pipeline out-of-process.

Runs as a separate Railway service: `arq worker.WorkerSettings`.
The FastAPI lifespan does NOT run here — this module initializes its OWN
MongoDB and Redis clients in on_startup (RESEARCH Pitfall 2 + Pitfall 6).
Never import or reference state.* / manager from this file.
"""
import asyncio
import json
import logging
import os

import redis.asyncio as aioredis

import database
from arq_pool import redis_settings_from_url, redis_url
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
    """ARQ job: run the Hive pipeline, publish events to ws:{user_id}:{run_id}."""
    redis_client: aioredis.Redis = ctx["redis"]
    channel = f"ws:{user_id}:{run_id}"

    async def publish_event(uid: str, message: dict) -> None:
        await redis_client.publish(f"ws:{uid}:{run_id}", json.dumps(message))

    adapter = HiveAdapter(send_to_user_callback=publish_event)
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
        # HiveAdapter.start_run launches an asyncio.Task and returns immediately;
        # await the in-flight task so the ARQ job stays alive until the pipeline finishes.
        task = adapter._runs.get(user_id)
        if isinstance(task, asyncio.Task):
            await task
        try:
            await database.update_run_status(run_id, status="complete")
        except Exception as db_exc:  # noqa: BLE001
            logger.warning("[worker] could not update run status to complete: %s", db_exc)
        return {"status": "complete", "run_id": run_id}
    except Exception as exc:  # noqa: BLE001
        logger.error("[worker] job failed run=%s: %s", run_id, exc)
        await redis_client.publish(channel, json.dumps({"type": "error", "message": str(exc)}))
        try:
            await database.update_run_status(run_id, status="error")
        except Exception:
            pass
        raise


async def on_startup(ctx: dict) -> None:
    """Init Worker-owned resources. Runs once when the worker process boots."""
    ctx["redis"] = await aioredis.from_url(redis_url(), decode_responses=False)
    await database.init_db()  # uses MONGODB_URI/MONGO_URL env var — must be set on Worker service
    logger.info("[worker] started — redis + mongo initialized")


async def on_shutdown(ctx: dict) -> None:
    redis_client = ctx.get("redis")
    if redis_client is not None:
        await redis_client.aclose()


class WorkerSettings:
    functions = [run_prospecting_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = redis_settings_from_url()
    max_jobs = 5
    job_timeout = 600       # 10m max per prospecting run
    keep_result = 86400     # keep result 24h for status checks
    max_tries = 1           # do NOT auto-retry — prospecting costs LLM/scraping calls (RESEARCH anti-pattern)
