"""
routes/debtors.py — REST API for SOFTSEGUROS-backed debtors (Phase 18, Plan 04).

Prefix: /api/debtors. All endpoints require JWT (Depends(require_softseguros_enabled)) except
GET /api/debtors/health. Every query on the `debtors` collection is tenant-scoped
by user_id.

Endpoints:
  POST /configure-softseguros   — validate creds against SOFTSEGUROS, save, kick off onboarding sync (background)
  GET  /configure-softseguros   — {configured, configured_at}; never returns the password
  GET  /                        — paginated list, optional ?status=proximos_a_vencer|ya_vencidos
  GET  /sync-status             — last sync log + next cron time + is_syncing_now
  GET  /sync-logs               — recent sync logs
  POST /sync-now                — manual delta sync (rate-limited 1/5min per user → 429 + Retry-After)
  GET  /{id}                    — single debtor (404 if not owned)
  GET  /{id}/verify-fresh       — pre-call freshness check (fail-open)
  GET  /health                  — liveness, no auth
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel

from auth import get_current_user
from database import get_db

logger = logging.getLogger("routes.debtors")

router = APIRouter(prefix="/api/debtors", tags=["debtors"])


# ── Service authorization gate ────────────────────────────────────────────────
# No service is enabled by default. Landa staff must explicitly authorize the
# SOFTSEGUROS integration per client (sets company_voice.softseguros_enabled=True).
# Mirrors the cobranza_enabled pattern in main.py.

async def require_softseguros_enabled(current_user: dict = Depends(get_current_user)) -> dict:
    """Reject with 403 unless this user's company_voice has softseguros_enabled=True."""
    user_id = str(current_user["user_id"])
    db = get_db()
    cv = await db.company_voice.find_one({"user_id": user_id}, {"softseguros_enabled": 1, "_id": 0})
    if not cv or not cv.get("softseguros_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="La integración SOFTSEGUROS no está habilitada para esta cuenta. Contacta a Landa.",
        )
    return current_user


_RATE_LIMIT_SECONDS = 5 * 60
_SYNCING_WINDOW = timedelta(minutes=45)
_VALID_STATUSES = {"proximos_a_vencer", "ya_vencidos"}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ── Models ────────────────────────────────────────────────────────────────────

class ConfigureSoftsegurosBody(BaseModel):
    username: str
    password: str


# ── Background-safe sync runner ───────────────────────────────────────────────

async def _safe_run_sync(user_id: str, mode: str) -> None:
    """Run run_sync, swallowing & logging all exceptions (BackgroundTasks doesn't surface them)."""
    try:
        from softseguros.sync import run_sync
        db = get_db()
        await run_sync(db, user_id, mode=mode)
    except Exception:  # noqa: BLE001
        logger.exception("background softseguros sync failed user_id=%s mode=%s", user_id, mode)


# ── Health ────────────────────────────────────────────────────────────────────

@router.get("/health")
async def debtors_health():
    """Liveness probe — no auth required."""
    return {"status": "ok"}


# ── Configure SOFTSEGUROS credentials ─────────────────────────────────────────

@router.post("/configure-softseguros")
async def configure_softseguros(
    body: ConfigureSoftsegurosBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_softseguros_enabled),
):
    """Validate SOFTSEGUROS credentials, store them encrypted, and kick off an onboarding sync."""
    user_id = str(current_user["user_id"])
    db = get_db()

    from softseguros.adapter import SoftSegurosAdapter, SoftSegurosAuthError, SoftSegurosAPIError
    from softseguros.credentials import save_credentials

    adapter = SoftSegurosAdapter(body.username, body.password)
    try:
        await adapter.authenticate()
    except (SoftSegurosAuthError, SoftSegurosAPIError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="credenciales inválidas")
    except Exception:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="No se pudo contactar a SOFTSEGUROS, intente más tarde",
        )
    finally:
        try:
            await adapter.close()
        except Exception:  # pragma: no cover
            pass

    await save_credentials(db, user_id, body.username, body.password)
    background_tasks.add_task(_safe_run_sync, user_id, "onboarding")
    return {"sync_started": True}


@router.get("/configure-softseguros")
async def get_configure_softseguros(current_user: dict = Depends(require_softseguros_enabled)):
    """Return whether SOFTSEGUROS is configured. NEVER returns the password."""
    user_id = str(current_user["user_id"])
    db = get_db()
    doc = await db.softseguros_credentials.find_one(
        {"user_id": user_id}, {"configured_at": 1, "_id": 0}
    )
    if not doc:
        return {"configured": False, "configured_at": None}
    return {"configured": True, "configured_at": doc.get("configured_at")}


# ── List debtors ──────────────────────────────────────────────────────────────

@router.get("")
@router.get("/")
async def list_debtors(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(require_softseguros_enabled),
):
    """Paginated list of this user's active SOFTSEGUROS debtors, optionally filtered by status."""
    user_id = str(current_user["user_id"])
    db = get_db()

    query: dict = {"user_id": user_id, "source": "softseguros", "is_active": True}
    if status_filter is not None:
        if status_filter not in _VALID_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"status inválido '{status_filter}' (esperado uno de {sorted(_VALID_STATUSES)})",
            )
        query["status_softseguros"] = status_filter

    total = await db.debtors.count_documents(query)
    cursor = (
        db.debtors.find(query)
        .sort("vencimiento", 1)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(length=page_size)
    return {"items": [_serialize(d) for d in docs], "page": page, "page_size": page_size, "total": total}


# ── Sync status & logs ────────────────────────────────────────────────────────

@router.get("/sync-status")
async def sync_status(current_user: dict = Depends(require_softseguros_enabled)):
    """Report the most recent sync, the next scheduled cron run, and whether a sync is running now."""
    user_id = str(current_user["user_id"])
    db = get_db()

    last = await db.softseguros_sync_logs.find_one(
        {"user_id": user_id}, sort=[("started_at", -1)]
    )

    # Is a (non-pre-call) sync running right now?
    cutoff = _utcnow() - _SYNCING_WINDOW
    in_progress = await db.softseguros_sync_logs.find_one({
        "user_id": user_id,
        "status": "in_progress",
        "started_at": {"$gte": cutoff},
        "mode": {"$ne": "pre_call_check"},
    })

    # Next cron timestamp from the APScheduler instance, if available.
    next_sync_at = None
    try:
        from main import app as _app
        sched = getattr(_app.state, "softseguros_scheduler", None)
        if sched is not None:
            for job in sched.get_jobs():
                nrt = getattr(job, "next_run_time", None)
                if nrt is not None:
                    next_sync_at = nrt
                    break
    except Exception:  # pragma: no cover
        next_sync_at = None

    if not last:
        return {
            "last_sync_at": None,
            "last_sync_mode": None,
            "last_sync_status": None,
            "debtors_created": 0,
            "debtors_updated": 0,
            "next_sync_at": next_sync_at,
            "is_syncing_now": in_progress is not None,
        }

    return {
        "last_sync_at": last.get("completed_at") or last.get("started_at"),
        "last_sync_mode": last.get("mode"),
        "last_sync_status": last.get("status"),
        "debtors_created": last.get("debtors_created", 0),
        "debtors_updated": last.get("debtors_updated", 0),
        "debtors_marked_paid": last.get("debtors_marked_paid", 0),
        "debtors_marked_deleted": last.get("debtors_marked_deleted", 0),
        "next_sync_at": next_sync_at,
        "is_syncing_now": in_progress is not None,
    }


@router.get("/sync-logs")
async def sync_logs(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_softseguros_enabled),
):
    """Most recent SOFTSEGUROS sync logs for the current user."""
    user_id = str(current_user["user_id"])
    db = get_db()
    cursor = db.softseguros_sync_logs.find({"user_id": user_id}).sort("started_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    return {"items": [_serialize(d) for d in docs]}


# ── Manual sync (rate-limited) ────────────────────────────────────────────────

@router.post("/sync-now")
async def sync_now(
    background_tasks: BackgroundTasks,
    response: Response,
    current_user: dict = Depends(require_softseguros_enabled),
):
    """Trigger a manual delta sync. Rate-limited to 1 per 5 minutes per user (429 + Retry-After)."""
    user_id = str(current_user["user_id"])
    db = get_db()

    last_manual = await db.softseguros_sync_logs.find_one(
        {"user_id": user_id, "mode": "manual"}, sort=[("started_at", -1)]
    )
    if last_manual:
        started_at = last_manual.get("started_at")
        if started_at is not None:
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = (_utcnow() - started_at).total_seconds()
            if elapsed < _RATE_LIMIT_SECONDS:
                retry_after = int(_RATE_LIMIT_SECONDS - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Sincronización manual demasiado frecuente, intente más tarde",
                    headers={"Retry-After": str(retry_after)},
                )

    background_tasks.add_task(_safe_run_sync, user_id, "manual")
    return {"sync_started": True}


# ── Single debtor ─────────────────────────────────────────────────────────────

@router.get("/{debtor_id}")
async def get_debtor(debtor_id: str, current_user: dict = Depends(require_softseguros_enabled)):
    """Return a single debtor doc. 404 if it doesn't exist or belongs to another user."""
    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Debtor not found")
    doc = await db.debtors.find_one({"_id": oid, "user_id": user_id})
    if doc is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": _serialize(doc)}


# ── Pre-call freshness check ──────────────────────────────────────────────────

@router.get("/{debtor_id}/verify-fresh")
async def verify_fresh(debtor_id: str, current_user: dict = Depends(require_softseguros_enabled)):
    """Pre-call freshness check for a SOFTSEGUROS debtor. Fail-open on provider errors."""
    user_id = str(current_user["user_id"])
    db = get_db()

    from softseguros.verify import (
        verify_poliza_fresh,
        VerifyNotFoundError,
        VerifyNoCredentialsError,
    )

    try:
        return await verify_poliza_fresh(db, user_id, debtor_id)
    except VerifyNotFoundError:
        raise HTTPException(status_code=404, detail="Debtor not found")
    except VerifyNoCredentialsError:
        raise HTTPException(status_code=400, detail="SOFTSEGUROS no configurado para esta cuenta")
