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
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel

from auth import get_current_user
from database import get_db

logger = logging.getLogger("routes.debtors")

router = APIRouter(prefix="/api/debtors", tags=["debtors"])


# ── Service authorization gate ────────────────────────────────────────────────
# No service is enabled by default. Landa staff must explicitly authorize the
# SOFTSEGUROS integration per client (sets company_voice.softseguros_enabled=True).
# Mirrors the cobranza_enabled pattern in main.py.

async def require_softseguros_enabled(request: Request, current_user: dict = Depends(get_current_user)) -> dict:
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

class ImportFilters(BaseModel):
    """Onboarding/reimport filters chosen by the user.
    - include_vencidos / include_proximos: which buckets are persisted active.
    - cartera_states: which estado_cartera values count as "cobrable" at all.
      Allowed: "Pendiente por pagar", "Sin pagos Asignados".
    - max_age_months: discard pólizas whose fecha_fin is older than this many months.
      None = no age limit.
    - include_cancelled: when False (default) only Vigente/Devengada pólizas are
      imported; cancelled / not-renewed ones are skipped even with open debt."""
    include_vencidos: bool = True
    include_proximos: bool = True
    cartera_states: Optional[list[str]] = None
    max_age_months: Optional[int] = 12
    include_cancelled: bool = False


class ConfigureSoftsegurosBody(BaseModel):
    username: str
    password: str
    import_filters: Optional[ImportFilters] = None


class ReimportBody(BaseModel):
    import_filters: ImportFilters


class DisconnectBody(BaseModel):
    """User must type 'BORRAR' to confirm. Anything else is rejected."""
    confirm: str


# ── Background-safe sync runner ───────────────────────────────────────────────

async def _safe_run_sync(user_id: str, mode: str, import_filters: Optional[dict] = None) -> None:
    """Run run_sync, swallowing & logging all exceptions (BackgroundTasks doesn't surface them)."""
    try:
        from softseguros.sync import run_sync
        db = get_db()
        await run_sync(db, user_id, mode=mode, import_filters=import_filters)
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
    filters = body.import_filters.model_dump() if body.import_filters is not None else None
    background_tasks.add_task(_safe_run_sync, user_id, "onboarding", filters)
    return {"sync_started": True}


_DEFAULT_FILTERS = {"include_vencidos": True, "include_proximos": True}


@router.get("/configure-softseguros")
async def get_configure_softseguros(current_user: dict = Depends(require_softseguros_enabled)):
    """Return whether SOFTSEGUROS is configured + the active import filters. NEVER returns the password."""
    user_id = str(current_user["user_id"])
    db = get_db()
    doc = await db.softseguros_credentials.find_one(
        {"user_id": user_id}, {"configured_at": 1, "_id": 0}
    )
    state = await db.softseguros_sync_state.find_one(
        {"user_id": user_id}, {"import_filters": 1, "_id": 0}
    )
    import_filters = (state or {}).get("import_filters") or dict(_DEFAULT_FILTERS)
    if not doc:
        return {"configured": False, "configured_at": None, "import_filters": import_filters}
    return {
        "configured": True,
        "configured_at": doc.get("configured_at"),
        "import_filters": import_filters,
    }


# ── List debtors ──────────────────────────────────────────────────────────────

# Valid sort fields → Mongo field + default direction.
_SORT_MAP = {
    "vencimiento": ("vencimiento", 1),   # earliest first
    "monto":       ("monto", -1),         # largest first
    "nombre":      ("nombre", 1),
    "dias_vencidos": ("vencimiento", 1),  # earliest = most-days-overdue
}


def _build_aging_filter(bucket: Optional[str]) -> dict:
    """Translate a UI bucket (1-30 / 31-60 / 61-90 / 90+) into a Mongo $expr range on
    days-since-vencimiento. `vencimiento` is an ISO date string (we store SOFTSEGUROS's
    fecha_limite_pago or fecha_fin verbatim). We compute days via $dateDiff over
    $dateFromString.

    Returns an empty dict if bucket is None or invalid."""
    if not bucket:
        return {}
    ranges = {
        "1-30":  (1, 30),
        "31-60": (31, 60),
        "61-90": (61, 90),
        "90+":   (91, 100_000),
    }
    if bucket not in ranges:
        return {}
    lo, hi = ranges[bucket]
    # days_overdue = days between vencimiento and today (positive when overdue)
    return {
        "$expr": {
            "$let": {
                "vars": {
                    "v": {"$dateFromString": {"dateString": "$vencimiento", "onError": None, "onNull": None}},
                },
                "in": {
                    "$and": [
                        {"$ne": ["$$v", None]},
                        {"$gte": [{"$dateDiff": {"startDate": "$$v", "endDate": "$$NOW", "unit": "day"}}, lo]},
                        {"$lte": [{"$dateDiff": {"startDate": "$$v", "endDate": "$$NOW", "unit": "day"}}, hi]},
                    ]
                }
            }
        }
    }


@router.get("")
@router.get("/")
async def list_debtors(
    status_filter: Optional[str] = Query(None, alias="status"),
    bucket: Optional[str] = Query(None, description="1-30 | 31-60 | 61-90 | 90+"),
    min_monto: Optional[float] = Query(None, ge=0, alias="min_monto"),
    max_monto: Optional[float] = Query(None, ge=0, alias="max_monto"),
    ramo: Optional[list[str]] = Query(None, description="Multi-select ramo_nombre"),
    sort: str = Query("vencimiento", description="vencimiento | monto | nombre | dias_vencidos"),
    direction: str = Query("asc", description="asc | desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
    current_user: dict = Depends(require_softseguros_enabled),
):
    """Paginated, filtered, sorted list of this user's active SOFTSEGUROS debtors.

    Filters are server-side (Mongo). Text search (nombre / póliza / documento) lives
    on the client and runs over the current page — keeps the API surface small.
    """
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

    if ramo:
        # Accept comma-joined OR repeated query params.
        flat: list[str] = []
        for r in ramo:
            flat.extend([x.strip() for x in r.split(",") if x.strip()])
        if flat:
            query["ramo_nombre"] = {"$in": flat}

    if min_monto is not None or max_monto is not None:
        monto_range: dict = {}
        if min_monto is not None:
            monto_range["$gte"] = float(min_monto)
        if max_monto is not None:
            monto_range["$lte"] = float(max_monto)
        query["monto"] = monto_range

    aging_clause = _build_aging_filter(bucket)
    if aging_clause:
        # Merge with the existing query (both are top-level conditions).
        query = {"$and": [query, aging_clause]}

    # Sort
    sort_field, default_dir = _SORT_MAP.get(sort, _SORT_MAP["vencimiento"])
    sort_dir = -1 if direction.lower() == "desc" else (1 if direction.lower() == "asc" else default_dir)

    total = await db.debtors.count_documents(query)
    cursor = (
        db.debtors.find(query)
        .sort(sort_field, sort_dir)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )
    docs = await cursor.to_list(length=page_size)
    return {
        "items": [_serialize(d) for d in docs],
        "page": page,
        "page_size": page_size,
        "total": total,
        "sort": sort,
        "direction": "desc" if sort_dir == -1 else "asc",
    }


# Aging summary: counts + total monto per overdue bucket. Used by the dashboard
# KPIs strip. Same filters apply (so the KPIs reflect any active ramo/monto filter
# — but NOT the bucket filter itself, because the KPIs *are* the bucket selectors).
@router.get("/aging-summary")
async def aging_summary(
    status_filter: Optional[str] = Query(None, alias="status"),
    min_monto: Optional[float] = Query(None, ge=0),
    max_monto: Optional[float] = Query(None, ge=0),
    ramo: Optional[list[str]] = Query(None),
    current_user: dict = Depends(require_softseguros_enabled),
):
    user_id = str(current_user["user_id"])
    db = get_db()

    match: dict = {"user_id": user_id, "source": "softseguros", "is_active": True}
    if status_filter and status_filter in _VALID_STATUSES:
        match["status_softseguros"] = status_filter
    if ramo:
        flat: list[str] = []
        for r in ramo:
            flat.extend([x.strip() for x in r.split(",") if x.strip()])
        if flat:
            match["ramo_nombre"] = {"$in": flat}
    if min_monto is not None or max_monto is not None:
        rng: dict = {}
        if min_monto is not None:
            rng["$gte"] = float(min_monto)
        if max_monto is not None:
            rng["$lte"] = float(max_monto)
        match["monto"] = rng

    pipeline = [
        {"$match": match},
        {"$addFields": {
            "_v": {"$dateFromString": {"dateString": "$vencimiento", "onError": None, "onNull": None}},
        }},
        {"$addFields": {
            "_days": {"$cond": [
                {"$eq": ["$_v", None]},
                None,
                {"$dateDiff": {"startDate": "$_v", "endDate": "$$NOW", "unit": "day"}},
            ]}
        }},
        {"$addFields": {
            "_bucket": {"$switch": {
                "branches": [
                    {"case": {"$eq": ["$_days", None]}, "then": "unknown"},
                    {"case": {"$lt": ["$_days", 1]},   "then": "future"},
                    {"case": {"$lte": ["$_days", 30]}, "then": "1-30"},
                    {"case": {"$lte": ["$_days", 60]}, "then": "31-60"},
                    {"case": {"$lte": ["$_days", 90]}, "then": "61-90"},
                ],
                "default": "90+",
            }}
        }},
        {"$group": {
            "_id": "$_bucket",
            "count": {"$sum": 1},
            "total_monto": {"$sum": {"$ifNull": ["$monto", 0]}},
        }},
    ]
    buckets = {b: {"count": 0, "total_monto": 0.0} for b in ("1-30", "31-60", "61-90", "90+", "future", "unknown")}
    async for row in db.debtors.aggregate(pipeline):
        b = row["_id"]
        if b in buckets:
            buckets[b] = {"count": int(row["count"]), "total_monto": float(row["total_monto"] or 0)}

    # Collect distinct ramos for the ramo multi-select (for the same user).
    ramos_raw = await db.debtors.distinct(
        "ramo_nombre",
        {"user_id": user_id, "source": "softseguros", "is_active": True},
    )
    ramos = [r for r in ramos_raw if r]

    total_count = sum(b["count"] for b in buckets.values())
    total_monto = sum(b["total_monto"] for b in buckets.values())
    return {
        "buckets": buckets,
        "total": {"count": total_count, "total_monto": total_monto},
        "ramos": sorted(ramos),
    }


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

    # If a sync is in progress right now, report on THAT one's live counters
    # (in_progress doc), not on the last completed sync.
    live = in_progress if in_progress is not None else last
    if not last and not in_progress:
        return {
            "last_sync_at": None,
            "last_sync_mode": None,
            "last_sync_status": None,
            "started_at": None,
            "polizas_scanned": 0,
            "total_count": 0,
            "debtors_created": 0,
            "debtors_updated": 0,
            "debtors_excluded_by_filter": 0,
            "error_message": None,
            "next_sync_at": next_sync_at,
            "is_syncing_now": False,
        }

    return {
        "last_sync_at": (last or {}).get("completed_at") or (last or {}).get("started_at"),
        "last_sync_mode": live.get("mode"),
        "last_sync_status": live.get("status"),
        "started_at": live.get("started_at"),
        "polizas_scanned": live.get("polizas_scanned", 0),
        "total_count": live.get("total_count", 0),
        "debtors_created": live.get("debtors_created", 0),
        "debtors_updated": live.get("debtors_updated", 0),
        "debtors_marked_paid": live.get("debtors_marked_paid", 0),
        "debtors_marked_deleted": live.get("debtors_marked_deleted", 0),
        "debtors_excluded_by_filter": live.get("debtors_excluded_by_filter", 0),
        "error_message": (last or {}).get("error_message") if not in_progress else None,
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


# ── Cancel a running sync ─────────────────────────────────────────────────────

@router.post("/sync-cancel")
async def sync_cancel(current_user: dict = Depends(require_softseguros_enabled)):
    """Signal a running sync to stop at the next chunk boundary. Idempotent."""
    user_id = str(current_user["user_id"])
    db = get_db()
    await db.softseguros_sync_state.update_one(
        {"user_id": user_id},
        {"$set": {"cancel_requested": True}, "$setOnInsert": {"user_id": user_id}},
        upsert=True,
    )
    return {"cancel_requested": True}


# ── Re-import with new filters ────────────────────────────────────────────────

@router.post("/reimport")
async def reimport(
    body: ReimportBody,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(require_softseguros_enabled),
):
    """
    Re-import the SOFTSEGUROS cartera with new filters. Full re-scan, but it does
    NOT delete anything: existing debtor docs (and their Phase-17 call history) are
    upserted; pólizas that no longer match the new filters keep their doc but get
    is_active=False. Rate-limited like a manual sync (1 per 5 min).
    """
    user_id = str(current_user["user_id"])
    db = get_db()

    # Must have credentials configured.
    creds_doc = await db.softseguros_credentials.find_one({"user_id": user_id}, {"_id": 1})
    if not creds_doc:
        raise HTTPException(status_code=400, detail="SOFTSEGUROS no configurado para esta cuenta")

    # Rate-limit (share the manual-sync window — both are heavy).
    last_heavy = await db.softseguros_sync_logs.find_one(
        {"user_id": user_id, "mode": {"$in": ["manual", "reimport"]}}, sort=[("started_at", -1)]
    )
    if last_heavy:
        started_at = last_heavy.get("started_at")
        if started_at is not None:
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            elapsed = (_utcnow() - started_at).total_seconds()
            if elapsed < _RATE_LIMIT_SECONDS:
                retry_after = int(_RATE_LIMIT_SECONDS - elapsed) + 1
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Re-importación demasiado frecuente, intente más tarde",
                    headers={"Retry-After": str(retry_after)},
                )

    filters = body.import_filters.model_dump()
    background_tasks.add_task(_safe_run_sync, user_id, "reimport", filters)
    return {"sync_started": True, "import_filters": filters}


# ── Disconnect SOFTSEGUROS (delete credentials + all imported debtors) ────────

# Lightweight count endpoint so the modal can show impact before confirming.
@router.get("/disconnect-softseguros/impact")
async def disconnect_impact(current_user: dict = Depends(require_softseguros_enabled)):
    """How many docs will be removed by a disconnect. Used by the confirm modal."""
    user_id = str(current_user["user_id"])
    db = get_db()
    debtors_total = await db.debtors.count_documents({"user_id": user_id, "source": "softseguros"})
    # Count total call-history entries across all softseguros debtors (approx via $size).
    pipeline = [
        {"$match": {"user_id": user_id, "source": "softseguros"}},
        {"$project": {"n": {"$size": {"$ifNull": ["$historial_llamadas", []]}}}},
        {"$group": {"_id": None, "total": {"$sum": "$n"}}},
    ]
    agg = await db.debtors.aggregate(pipeline).to_list(length=1)
    calls_total = agg[0]["total"] if agg else 0
    return {
        "debtors_to_delete": debtors_total,
        "call_history_to_delete": calls_total,
        "credentials_will_be_deleted": True,
        "sync_logs_preserved": True,
    }


@router.post("/disconnect-softseguros")
async def disconnect_softseguros(
    body: DisconnectBody,
    current_user: dict = Depends(require_softseguros_enabled),
):
    """
    Disconnect SOFTSEGUROS for this user. Deletes:
      - softseguros_credentials doc for user_id
      - all debtors with source="softseguros" for user_id (including their
        Phase-17 call history, which lives inside each debtor doc)
      - softseguros_sync_state doc (resets the high-water mark)
    Preserves:
      - softseguros_sync_logs (audit trail — kept for Landa's records)

    Requires confirm == "BORRAR" exactly (case-sensitive) to prevent accidental
    triggers.
    """
    if body.confirm != "BORRAR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Para desconectar, escribí exactamente 'BORRAR' en el campo de confirmación.",
        )

    user_id = str(current_user["user_id"])
    db = get_db()

    # If a sync is running, refuse — the user must cancel it first to avoid races.
    cutoff = _utcnow() - _SYNCING_WINDOW
    running = await db.softseguros_sync_logs.find_one({
        "user_id": user_id,
        "status": "in_progress",
        "started_at": {"$gte": cutoff},
        "mode": {"$ne": "pre_call_check"},
    })
    if running is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Hay una sincronización en curso. Cancelala primero desde 'Cancelar importación'.",
        )

    # Delete in this order: credentials (stop future syncs) → debtors → sync_state
    cred_deleted = await db.softseguros_credentials.delete_one({"user_id": user_id})
    debtors_deleted = await db.debtors.delete_many({"user_id": user_id, "source": "softseguros"})
    state_deleted = await db.softseguros_sync_state.delete_one({"user_id": user_id})

    logger.info(
        "softseguros disconnect user_id=%s credentials=%d debtors=%d state=%d",
        user_id, cred_deleted.deleted_count, debtors_deleted.deleted_count, state_deleted.deleted_count,
    )

    return {
        "disconnected": True,
        "credentials_deleted": cred_deleted.deleted_count,
        "debtors_deleted": debtors_deleted.deleted_count,
        "sync_state_deleted": state_deleted.deleted_count,
    }


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
