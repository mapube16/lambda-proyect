"""
softseguros/verify.py — Pre-call freshness check (Phase 18, Mode 4).

verify_poliza_fresh(db, user_id, debtor_id) is the single source of truth for the
"should the voice agent call this debtor right now?" decision. It performs one
GET /api/poliza/{softseguros_poliza_id} against SOFTSEGUROS and centralizes the
mutation logic so Phase 17 only has to consume the returned dict.

Decision branches:
  - already_paid  → estado_cartera in {Pagada,Comisionada} OR recaudado=True OR the
                    póliza now classifies as pagado/futuro → mark local pagado+inactive.
  - not_found     → 404 from SOFTSEGUROS → mark local eliminado+inactive.
  - outdated      → fecha_fin / total / estado_poliza_nombre differs → upsert local (re-classify).
  - ok            → no relevant change → bump last_verified only.

Fail-open: on httpx.TimeoutException, exhausted 5xx retries, or any unexpected
error → return {should_call: True, reason: "ok", warning: "verification_unavailable"}
WITHOUT mutating the local doc.

Every non-error path appends a softseguros_sync_logs entry with mode='pre_call_check'.
"""
import logging
from datetime import date, datetime, timezone
from typing import Optional

from bson import ObjectId

import httpx

from . import credentials as _credentials
from .adapter import (
    SoftSegurosAdapter,
    SoftSegurosAPIError,
    SoftSegurosNotFoundError,
    SoftSegurosRateLimitError,
    SoftSegurosServerError,
)
from .classifier import classify_poliza
from cobranza import debtor_crud

logger = logging.getLogger(__name__)

_PAID_CARTERA = {"pagada", "comisionada"}
_ACTIVE_BUCKETS = {"ya_vencidos", "proximos_a_vencer"}


class VerifyNotFoundError(Exception):
    """Raised when the debtor doc doesn't exist / isn't a softseguros debtor (route → 404)."""


class VerifyNoCredentialsError(Exception):
    """Raised when the user has no SOFTSEGUROS credentials (route → 400)."""


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


def _is_paid(p: dict) -> bool:
    ec = (p.get("estado_cartera") or "").strip().lower()
    return bool(p.get("recaudado")) or ec in _PAID_CARTERA


def _fresh_data(p: dict) -> dict:
    return {
        "estado_cartera": p.get("estado_cartera"),
        "estado_poliza_nombre": p.get("estado_poliza_nombre"),
        "fecha_fin": p.get("fecha_fin"),
        "fecha_limite_pago": p.get("fecha_limite_pago"),
        "total": p.get("total"),
        "recaudado": bool(p.get("recaudado")),
    }


async def _log_pre_call_check(db, user_id: str, status: str) -> None:
    now = _utcnow()
    try:
        await db.softseguros_sync_logs.insert_one({
            "user_id": user_id,
            "mode": "pre_call_check",
            "started_at": now,
            "completed_at": now,
            "status": status,
            "error_message": None,
            "polizas_scanned": 1,
            "total_count": 0,
            "max_poliza_id_seen": None,
            "debtors_created": 0,
            "debtors_updated": 0,
            "debtors_marked_paid": 0,
            "debtors_marked_deleted": 0,
            "total_requests": 1,
            "duration_seconds": 0.0,
        })
    except Exception:  # pragma: no cover — logging must never break the call decision
        logger.warning("verify_poliza_fresh: failed to write pre_call_check sync log", exc_info=True)


def _poliza_to_debtor_doc(p: dict, bucket: str) -> dict:
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
        "aseguradora_nombre": p.get("ramo_aseguradora_nombre"),
        "ramo_nombre": p.get("ramo_nombre"),
        "ramo_global_nombre": p.get("ramo_global_nombre"),
        "forma_pago_texto": p.get("forma_pago_texto"),
        "objeto_asegurado": p.get("codio_objeto_asegurado") or p.get("datos_objeto_asegurado"),
        "valor_asegurado_riesgo": p.get("valor_asegurado_riesgo"),
        "numero_de_cuotas": p.get("numero_de_cuotas"),
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


async def verify_poliza_fresh(db, user_id: str, debtor_id: str) -> dict:
    """
    Perform a pre-call freshness check for a SOFTSEGUROS debtor.

    Returns a dict with at least:
        should_call: bool
        reason: "already_paid" | "not_found" | "outdated" | "ok"
        fresh_data: dict (optional)
        warning: "verification_unavailable" (only on fail-open)

    Raises VerifyNotFoundError if the debtor doesn't exist / isn't a softseguros debtor.
    Raises VerifyNoCredentialsError if the user has no SOFTSEGUROS credentials.
    """
    # ── Look up debtor (tenant-scoped) ───────────────────────────────────────
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        raise VerifyNotFoundError(f"invalid debtor_id {debtor_id!r}")

    debtor = await db.debtors.find_one({"_id": oid, "user_id": user_id})
    if not debtor or debtor.get("source") != "softseguros" or debtor.get("softseguros_poliza_id") is None:
        raise VerifyNotFoundError(f"debtor {debtor_id} not a softseguros debtor for user {user_id}")

    poliza_id = debtor["softseguros_poliza_id"]

    # ── Credentials ──────────────────────────────────────────────────────────
    creds = await _credentials.get_credentials(db, user_id)
    if not creds:
        raise VerifyNoCredentialsError(f"no SOFTSEGUROS credentials for user {user_id}")
    username, password = creds

    today = _today()
    adapter = SoftSegurosAdapter(username, password)
    try:
        try:
            p = await adapter.get_poliza(poliza_id)
        except SoftSegurosNotFoundError:
            await debtor_crud.mark_debtor_deleted_by_softseguros_poliza_id(db, user_id, poliza_id)
            await _log_pre_call_check(db, user_id, "success")
            return {"should_call": False, "reason": "not_found"}
        except (httpx.TimeoutException, SoftSegurosRateLimitError, SoftSegurosServerError) as exc:
            logger.warning("verify_poliza_fresh fail-open (provider unavailable): %s", exc)
            await _log_pre_call_check(db, user_id, "partial")
            return {"should_call": True, "reason": "ok", "warning": "verification_unavailable"}
        except (SoftSegurosAPIError, Exception) as exc:  # noqa: BLE001 — fail-open on anything else
            logger.warning("verify_poliza_fresh fail-open (unexpected error): %s", exc)
            await _log_pre_call_check(db, user_id, "partial")
            return {"should_call": True, "reason": "ok", "warning": "verification_unavailable"}

        # ── Got the póliza ───────────────────────────────────────────────────
        bucket = classify_poliza(
            estado_cartera=p.get("estado_cartera"),
            fecha_fin=p.get("fecha_fin"),
            fecha_limite_pago=p.get("fecha_limite_pago"),
            recaudado=bool(p.get("recaudado")),
            today=today,
        )

        if _is_paid(p) or bucket not in _ACTIVE_BUCKETS:
            # Paid, or no longer cobrable in the active window ("futuro"/"pagado").
            await debtor_crud.mark_debtor_paid_by_softseguros_poliza_id(db, user_id, poliza_id)
            await _log_pre_call_check(db, user_id, "success")
            return {"should_call": False, "reason": "already_paid", "fresh_data": _fresh_data(p)}

        # Still cobrable — check if local data is stale.
        changed = (
            p.get("fecha_fin") != debtor.get("fecha_fin")
            or p.get("total") != debtor.get("total")
            or p.get("estado_poliza_nombre") != debtor.get("estado_poliza_nombre")
        )
        if changed:
            await debtor_crud.upsert_debtor_by_softseguros_poliza_id(
                db, user_id, poliza_id, _poliza_to_debtor_doc(p, bucket)
            )
            await db.debtors.update_one(
                {"_id": oid, "user_id": user_id}, {"$set": {"last_verified": _utcnow()}}
            )
            await _log_pre_call_check(db, user_id, "success")
            return {"should_call": True, "reason": "outdated", "fresh_data": _fresh_data(p)}

        # No relevant change — just record the verification timestamp.
        await db.debtors.update_one(
            {"_id": oid, "user_id": user_id}, {"$set": {"last_verified": _utcnow()}}
        )
        await _log_pre_call_check(db, user_id, "success")
        return {"should_call": True, "reason": "ok"}
    finally:
        try:
            await adapter.close()
        except Exception:  # pragma: no cover
            pass


# Backwards-compat alias — the stale plan referenced verify_pagopoliza_fresh.
verify_pagopoliza_fresh = verify_poliza_fresh
