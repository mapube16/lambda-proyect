"""
ARQ Worker — executes the Hive prospecting pipeline out-of-process.

Runs as a separate Railway service: `arq worker.WorkerSettings`.
Events are written to MongoDB; the frontend polls /api/runs/{run_id}/status.
"""
import asyncio
import logging
import os
import sys

# Windows: stdout por defecto es cp1252 y revienta con caracteres como '→'/'ñ'
# en prints de debug, tumbando el job entero. Forzamos UTF-8.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

from dotenv import load_dotenv
load_dotenv()

import database
from arq_pool import redis_settings_from_url
from hive_adapter import HiveAdapter

logger = logging.getLogger("worker")
logging.basicConfig(level=logging.INFO)


async def run_prospecting_job(
    ctx: dict,
    run_id: str,
    user_id: str,
    campaign_id: str,
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
        # Mark the run as running so the UI can distinguish "en cola" from "corriendo".
        try:
            await database.update_run_status(run_id, status="running")
        except Exception as db_exc:
            logger.warning("[worker] could not update run status to running: %s", db_exc)

        # ── Vertical AISLADO: empresas recién creadas (RUES) ──────────────────
        # No usa el grafo web (las empresas nuevas no tienen sitio). Descubre por
        # RUES y enriquece por NIT. Evita el cuelgue por resolución Bing.
        _kind = str(campaign.get("pipeline") or source_priority or "").lower()
        if _kind == "rues" or str(campaign.get("source_priority") or "").lower() == "rues":
            from rues_radar import build_recien_creadas_leads
            industria = (campaign.get("industria_objetivo")
                         or (campaign.get("sectors") or [""])[0]
                         or campaign.get("name", ""))
            ciudad = (campaign.get("ciudad_objetivo")
                      or (campaign.get("cities") or [""])[0] or "")
            dias = int(campaign.get("rues_dias_recientes", 180) or 180)
            logger.info("[worker] RUES vertical aislado — industria=%r ciudad=%r", industria, ciudad)
            leads = await build_recien_creadas_leads(industria, ciudad, max_results=max_results, dias_recientes=dias)
            for ld in leads:
                try:
                    await database.save_lead(run_id, user_id, ld, campaign_id)
                except Exception as e:
                    logger.warning("[worker] RUES save_lead failed: %s", e)
            qn = sum(1 for l in leads if l.get("system_state") == "SUCCESS_READY_FOR_REVIEW")
            await database.update_run_status(run_id, status="complete", total_found=len(leads), total_approved=qn)
            logger.info("[worker] RUES vertical done: %d leads (%d calificados)", len(leads), qn)
            return {"status": "complete", "run_id": run_id, "leads": len(leads)}

        # ── Vertical AISLADO: SECOP (pólizas de cumplimiento) ─────────────────
        # Licitaciones abiertas → proponentes probables → enriquecer NIT. Sin Bing.
        if _kind == "secop" or str(campaign.get("source_priority") or "").lower() == "secop":
            from secop_radar import build_secop_leads
            # Pólizas de cumplimiento: TODA empresa que se presente a un proceso es
            # prospecto, sin importar sector ni ciudad → sin filtro (keyword=None).
            logger.info("[worker] SECOP vertical aislado — todas las empresas presentándose (sin filtro de sector)")
            leads = await build_secop_leads(keyword=None, ciudad=None, max_results=max_results)
            for ld in leads:
                try:
                    await database.save_lead(run_id, user_id, ld, campaign_id)
                except Exception as e:
                    logger.warning("[worker] SECOP save_lead failed: %s", e)
            qn = sum(1 for l in leads if l.get("system_state") == "SUCCESS_READY_FOR_REVIEW")
            await database.update_run_status(run_id, status="complete", total_found=len(leads), total_approved=qn)
            logger.info("[worker] SECOP vertical done: %d leads (%d calificados)", len(leads), qn)
            return {"status": "complete", "run_id": run_id, "leads": len(leads)}

        # Wrap save_lead to include campaign_id from the job parameter
        async def save_lead_with_campaign(run_id: str, user_id: str, lead_data: dict) -> str:
            return await database.save_lead(run_id, user_id, lead_data, campaign_id)

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
            save_lead=save_lead_with_campaign,
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
