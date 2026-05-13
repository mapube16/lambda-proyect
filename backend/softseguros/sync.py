"""
softseguros/sync.py — SOFTSEGUROS póliza sync engine (Phase 18, Plan 03).

Fetches pólizas from /api/poliza/ (the real model — /api/pagopoliza/ returns 504
upstream), filters the cobrable ones locally (SOFTSEGUROS ignores all server-side
filters), classifies each via classifier.classify_poliza, and upserts the
"ya_vencidos" / "proximos_a_vencer" ones into the Mongo `debtors` collection.

Sync modes (run_sync(db, user_id, mode)):
  - "onboarding"  → full scan of every page. Slow (~5,207 requests for DPG's 52K).
                    No soft-delete phase (no prior state).
  - "cron_daily"  → delta scan: re-fetch only the tail pages where new ids live,
  / "manual"        plus a soft-delete sweep (mark debtors now paid / 404 → is_active=false).

Concurrency: an asyncio.Semaphore(5) is created per run_sync call and wraps every
SOFTSEGUROS HTTP call.

run_sync persists one doc to softseguros_sync_logs per call and updates the
1-doc-per-user softseguros_sync_state checkpoint.
"""
import asyncio
import logging
import math
from datetime import date, datetime, timezone
from typing import Optional

from bson import ObjectId

from . import credentials as _credentials
from .adapter import (
    SoftSegurosAdapter,
    SoftSegurosAPIError,
    SoftSegurosNotFoundError,
)
from .classifier import classify_poliza
from cobranza import debtor_crud

logger = logging.getLogger(__name__)

PAGE_SIZE = 10  # SOFTSEGUROS /api/poliza/ — fixed, server-controlled.
MAX_CONCURRENCY = 5

# All cobrable buckets the classifier can produce (besides "pagado"/"futuro").
_COBRABLE_BUCKETS = {"ya_vencidos", "proximos_a_vencer"}
# Cartera states considered "paid" (mirrors classifier).
_PAID_CARTERA = {"pagada", "comisionada"}

# Default import filters: import both kinds of debtor.
_DEFAULT_IMPORT_FILTERS = {"include_vencidos": True, "include_proximos": True}


def _normalize_import_filters(f: Optional[dict]) -> dict:
    """Coerce a raw filters dict to {include_vencidos: bool, include_proximos: bool}.
    Falls back to the default (both True). Guarantees at least one is True."""
    if not isinstance(f, dict):
        return dict(_DEFAULT_IMPORT_FILTERS)
    iv = bool(f.get("include_vencidos", True))
    ip = bool(f.get("include_proximos", True))
    if not iv and not ip:
        # Refuse to import nothing — fall back to both.
        return dict(_DEFAULT_IMPORT_FILTERS)
    return {"include_vencidos": iv, "include_proximos": ip}


def _allowed_buckets(filters: dict) -> set:
    """The classifier buckets that should be persisted as ACTIVE debtors, given filters."""
    allowed = set()
    if filters.get("include_vencidos"):
        allowed.add("ya_vencidos")
    if filters.get("include_proximos"):
        allowed.add("proximos_a_vencer")
    return allowed


class NoCredentialsError(Exception):
    """Raised when run_sync is called for a user with no SOFTSEGUROS credentials configured."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


# ── póliza → debtor doc mapping ───────────────────────────────────────────────

def _poliza_to_debtor_doc(p: dict, bucket: str) -> dict:
    """Map a SOFTSEGUROS póliza dict + classification bucket → the $set payload for a debtor."""
    return {
        "nombre": " ".join(
            str(x) for x in (p.get("cliente_nombres"), p.get("cliente_apellidos")) if x
        ).strip() or (p.get("cliente_nombres") or ""),
        "telefono": p.get("cliente_celular") or "",
        "monto": float(p["total"]) if p.get("total") is not None else 0.0,
        "vencimiento": p.get("fecha_limite_pago") or p.get("fecha_fin"),
        "numero_poliza": p.get("numero_poliza"),
        "softseguros_cliente_id": p.get("cliente"),
        "cliente_documento": p.get("cliente_numero_documento"),
        "cliente_email": p.get("cliente_email"),
        "cliente_celular": p.get("cliente_celular"),
        "aseguradora_nit": p.get("aseguradora_nit"),
        "ramo_nombre": p.get("ramo_nombre"),
        "ramo_global_nombre": p.get("ramo_global_nombre"),
        "vendedores_nombre": p.get("vendedores_nombre"),
        "estado_poliza_nombre": p.get("estado_poliza_nombre"),
        "estado_cartera": p.get("estado_cartera"),
        "prima": p.get("prima"),
        "total": p.get("total"),
        "total_pagado": p.get("total_pagado"),
        "recaudado": bool(p.get("recaudado")),
        "fecha_inicio": p.get("fecha_inicio"),
        "fecha_fin": p.get("fecha_fin"),
        "fecha_limite_pago": p.get("fecha_limite_pago"),
        "periodicidad": p.get("periodicidad"),
        "comicionada": bool(p.get("comicionada")),
        "status_softseguros": bucket,
        "is_active": True,
    }


def _classify(p: dict, today: date) -> str:
    return classify_poliza(
        estado_cartera=p.get("estado_cartera"),
        fecha_fin=p.get("fecha_fin"),
        fecha_limite_pago=p.get("fecha_limite_pago"),
        recaudado=bool(p.get("recaudado")),
        today=today,
    )


def _is_paid(p: dict) -> bool:
    ec = (p.get("estado_cartera") or "").strip().lower()
    return bool(p.get("recaudado")) or ec in _PAID_CARTERA


# ── concurrency-bounded request counter ───────────────────────────────────────

class _Caller:
    """Wraps adapter calls with a semaphore and counts total requests."""

    def __init__(self, sem: asyncio.Semaphore):
        self._sem = sem
        self.total_requests = 0

    async def __call__(self, coro_factory):
        async with self._sem:
            self.total_requests += 1
            return await coro_factory()


# ── main entry point ──────────────────────────────────────────────────────────

async def run_sync(db, user_id: str, mode: str, import_filters: Optional[dict] = None) -> dict:
    """
    Run a SOFTSEGUROS sync for `user_id` in the given `mode`
    ("onboarding" | "cron_daily" | "manual" | "reimport").

    `import_filters` ({include_vencidos: bool, include_proximos: bool}):
      - On "onboarding"/"reimport": if given, it's persisted to sync_state and used.
        If not given, defaults to both True.
      - On "cron_daily"/"manual": ignored as an argument — the filters stored in
        sync_state from the last onboarding/reimport are used (default both True).

    "reimport" behaves like "onboarding" (full scan) but, since prior debtor docs
    may carry Phase-17 call history, it does NOT delete anything: it upserts every
    cobrable póliza and flips is_active per the (possibly new) filters. Pólizas that
    no longer match the filters keep their doc + history but get is_active=False.

    Returns the sync_log dict (with str _id). Raises NoCredentialsError if the user
    has no credentials configured. Other exceptions are recorded in the sync_log
    (status="failed") and then re-raised.
    """
    if mode not in ("onboarding", "cron_daily", "manual", "reimport"):
        raise ValueError(f"unsupported sync mode: {mode!r}")

    creds = await _credentials.get_credentials(db, user_id)
    if not creds:
        raise NoCredentialsError(f"no SOFTSEGUROS credentials for user_id={user_id}")
    username, password = creds

    is_full_scan = mode in ("onboarding", "reimport")

    started_at = _utcnow()
    log_doc = {
        "user_id": user_id,
        "mode": mode,
        "started_at": started_at,
        "completed_at": None,
        "status": "in_progress",
        "error_message": None,
        "polizas_scanned": 0,
        "total_count": 0,
        "max_poliza_id_seen": None,
        "debtors_created": 0,
        "debtors_updated": 0,
        "debtors_marked_paid": 0,
        "debtors_marked_deleted": 0,
        "debtors_excluded_by_filter": 0,
        "total_requests": 0,
        "duration_seconds": None,
    }
    insert_res = await db.softseguros_sync_logs.insert_one(log_doc)
    log_id = insert_res.inserted_id

    sem = asyncio.Semaphore(MAX_CONCURRENCY)
    call = _Caller(sem)
    today = _today()
    adapter = SoftSegurosAdapter(username, password)

    # Resolve the import filters: on a full scan, the argument wins (or default);
    # on a delta, read whatever was persisted (or default).
    _state_for_filters = await db.softseguros_sync_state.find_one({"user_id": user_id}) or {}
    if is_full_scan:
        active_filters = _normalize_import_filters(
            import_filters if import_filters is not None else _state_for_filters.get("import_filters")
        )
    else:
        active_filters = _normalize_import_filters(_state_for_filters.get("import_filters"))
    allowed_buckets = _allowed_buckets(active_filters)

    counters = {
        "polizas_scanned": 0,
        "total_count": 0,
        "max_poliza_id_seen": None,
        "debtors_created": 0,
        "debtors_updated": 0,
        "debtors_marked_paid": 0,
        "debtors_marked_deleted": 0,
        "debtors_excluded_by_filter": 0,
    }

    async def _persist_poliza(p: dict):
        pid = p.get("id")
        if pid is None:
            return
        counters["polizas_scanned"] += 1
        if counters["max_poliza_id_seen"] is None or pid > counters["max_poliza_id_seen"]:
            counters["max_poliza_id_seen"] = pid
        bucket = _classify(p, today)
        if bucket in _COBRABLE_BUCKETS:
            if bucket in allowed_buckets:
                doc = _poliza_to_debtor_doc(p, bucket)  # is_active=True
                res = await debtor_crud.upsert_debtor_by_softseguros_poliza_id(db, user_id, pid, doc)
                if res["created"]:
                    counters["debtors_created"] += 1
                else:
                    counters["debtors_updated"] += 1
            else:
                # Cobrable, but the user didn't import this kind. Keep/refresh the doc
                # (preserving Phase-17 call history) but mark it inactive so it stays
                # out of the lists and the voice-agent queue.
                doc = _poliza_to_debtor_doc(p, bucket)
                doc["is_active"] = False
                await debtor_crud.upsert_debtor_by_softseguros_poliza_id(db, user_id, pid, doc)
                counters["debtors_excluded_by_filter"] += 1
        elif bucket == "pagado":
            # If we already track it locally, retire it.
            await debtor_crud.mark_debtor_paid_by_softseguros_poliza_id(db, user_id, pid)
        # "futuro" → not persisted in v1.

    async def _fetch_page(page: int) -> dict:
        return await call(lambda: adapter.list_polizas(page=page))

    try:
        await call(lambda: adapter.authenticate())

        # ── Phase A: determine the page range to fetch ───────────────────────
        first = await _fetch_page(1)
        total_count = int(first.get("count") or 0)
        counters["total_count"] = total_count
        last_page = max(1, math.ceil(total_count / PAGE_SIZE)) if total_count else 1

        state = await db.softseguros_sync_state.find_one({"user_id": user_id})

        if is_full_scan or not state:
            pages_to_fetch = list(range(1, last_page + 1))
        else:
            last_count = int(state.get("last_total_count") or 0)
            if total_count > last_count and last_count > 0:
                from_page = max(1, math.ceil(last_count / PAGE_SIZE))
            else:
                # Count didn't grow (or unknown) — re-scan a small tail to catch
                # estado_cartera changes on recent pólizas.
                from_page = max(1, last_page - 4)
            pages_to_fetch = list(range(from_page, last_page + 1))

        # ── Phase B: fetch + persist ─────────────────────────────────────────
        # Process page 1 results first (already fetched).
        seen_ids: set = set()

        async def _handle_page_payload(payload: dict):
            for p in payload.get("results", []):
                if p.get("id") is not None:
                    seen_ids.add(p["id"])
            # Persist sequentially within a page to keep upsert counters deterministic;
            # pages themselves are fetched concurrently under the semaphore.
            await asyncio.gather(*(_persist_poliza(p) for p in payload.get("results", [])))

        # Page 1
        if 1 in pages_to_fetch:
            await _handle_page_payload(first)
            remaining = [pg for pg in pages_to_fetch if pg != 1]
        else:
            remaining = list(pages_to_fetch)

        # Fetch the rest concurrently (semaphore caps in-flight at 5).
        async def _fetch_and_handle(pg: int):
            payload = await _fetch_page(pg)
            await _handle_page_payload(payload)

        if remaining:
            await asyncio.gather(*(_fetch_and_handle(pg) for pg in remaining))

        # ── Phase C: soft-delete sweep (skip on full scans — no prior state OR
        #    reimport preserves everything via upsert in Phase B) ──────────────
        if not is_full_scan and state:
            existing = await debtor_crud.list_active_softseguros_poliza_ids(db, user_id)
            missing = existing - seen_ids
            for pid in missing:
                try:
                    p = await call(lambda pid=pid: adapter.get_poliza(pid))
                except SoftSegurosNotFoundError:
                    if await debtor_crud.mark_debtor_deleted_by_softseguros_poliza_id(db, user_id, pid):
                        counters["debtors_marked_deleted"] += 1
                    continue
                except SoftSegurosAPIError as exc:
                    logger.warning("softseguros sync: get_poliza(%s) failed, leaving debtor untouched: %s", pid, exc)
                    continue
                if _is_paid(p):
                    if await debtor_crud.mark_debtor_paid_by_softseguros_poliza_id(db, user_id, pid):
                        counters["debtors_marked_paid"] += 1
                else:
                    # Still cobrable but fell off our page window — re-classify, then
                    # upsert respecting the active import filters.
                    bucket = _classify(p, today)
                    if bucket in _COBRABLE_BUCKETS:
                        doc = _poliza_to_debtor_doc(p, bucket)
                        if bucket not in allowed_buckets:
                            doc["is_active"] = False
                        await debtor_crud.upsert_debtor_by_softseguros_poliza_id(db, user_id, pid, doc)

        # ── Phase D: update checkpoint state ─────────────────────────────────
        now = _utcnow()
        state_set = {
            "user_id": user_id,
            "last_total_count": total_count,
            "updated_at": now,
        }
        if counters["max_poliza_id_seen"] is not None:
            # Never regress the high-water mark.
            prev_max = (state or {}).get("last_max_poliza_id") or 0
            state_set["last_max_poliza_id"] = max(prev_max, counters["max_poliza_id_seen"])
        if is_full_scan:
            state_set["last_full_scan_at"] = now
            state_set["import_filters"] = active_filters
        await db.softseguros_sync_state.update_one(
            {"user_id": user_id},
            {"$set": state_set, "$setOnInsert": {"last_weekly_rescan_at": None}},
            upsert=True,
        )

        status = "success"
        error_message = None

    except NoCredentialsError:
        raise
    except Exception as exc:  # noqa: BLE001 — record & re-raise
        status = "failed"
        error_message = str(exc)
        logger.exception("softseguros run_sync failed user_id=%s mode=%s", user_id, mode)
        # Fall through to finalize, then re-raise.
    finally:
        try:
            await adapter.close()
        except Exception:  # pragma: no cover
            pass

    completed_at = _utcnow()
    final = {
        "completed_at": completed_at,
        "status": status,
        "error_message": error_message,
        "polizas_scanned": counters["polizas_scanned"],
        "total_count": counters["total_count"],
        "max_poliza_id_seen": counters["max_poliza_id_seen"],
        "debtors_created": counters["debtors_created"],
        "debtors_updated": counters["debtors_updated"],
        "debtors_marked_paid": counters["debtors_marked_paid"],
        "debtors_marked_deleted": counters["debtors_marked_deleted"],
        "debtors_excluded_by_filter": counters["debtors_excluded_by_filter"],
        "total_requests": call.total_requests,
        "duration_seconds": (completed_at - started_at).total_seconds(),
    }
    await db.softseguros_sync_logs.update_one({"_id": log_id}, {"$set": final})

    if status == "failed":
        raise SoftSegurosAPIError(f"sync failed: {error_message}")

    out = dict(log_doc)
    out.update(final)
    out["_id"] = str(log_id)
    return out
