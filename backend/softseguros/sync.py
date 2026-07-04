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

# Default import filters: import both kinds of debtor, only real debt, last 12 months.
# - include_vencidos / include_proximos: which buckets are persisted as is_active.
# - cartera_states: which estado_cartera values count as "cobrable" at all.
# - max_age_months: discard pólizas whose fecha_fin is older than (today - N months).
#                   None = no age limit.
_DEFAULT_IMPORT_FILTERS = {
    "include_vencidos": True,
    "include_proximos": True,
    "cartera_states": ["Pendiente por pagar"],
    "max_age_months": 12,
    # When False (default) only Vigente/Devengada pólizas count; cancelled or
    # not-renewed pólizas are excluded even if they have outstanding debt.
    "include_cancelled": False,
}
_VALID_CARTERA_STATES = {"Pendiente por pagar", "Sin pagos Asignados"}
# Póliza estados considered "active" (still in force). Anything else
# (Cancelada, No renovada, …) is only imported when include_cancelled=True.
_ACTIVE_POLIZA_STATES = {"vigente", "devengada"}


def _normalize_import_filters(f: Optional[dict]) -> dict:
    """Coerce a raw filters dict. Falls back to defaults. Guarantees:
    - at least one of include_vencidos / include_proximos is True
    - cartera_states is a non-empty subset of _VALID_CARTERA_STATES
    - max_age_months is None or a positive int."""
    if not isinstance(f, dict):
        return dict(_DEFAULT_IMPORT_FILTERS)
    iv = bool(f.get("include_vencidos", True))
    ip = bool(f.get("include_proximos", True))
    if not iv and not ip:
        iv, ip = True, True
    raw_states = f.get("cartera_states")
    if isinstance(raw_states, list) and raw_states:
        cartera_states = [s for s in raw_states if s in _VALID_CARTERA_STATES]
        if not cartera_states:
            cartera_states = list(_DEFAULT_IMPORT_FILTERS["cartera_states"])
    else:
        cartera_states = list(_DEFAULT_IMPORT_FILTERS["cartera_states"])
    max_age = f.get("max_age_months", _DEFAULT_IMPORT_FILTERS["max_age_months"])
    if max_age is None:
        max_age_months = None
    else:
        try:
            mm = int(max_age)
            max_age_months = mm if mm > 0 else None
        except (TypeError, ValueError):
            max_age_months = _DEFAULT_IMPORT_FILTERS["max_age_months"]
    return {
        "include_vencidos": iv,
        "include_proximos": ip,
        "cartera_states": cartera_states,
        "max_age_months": max_age_months,
        "include_cancelled": bool(f.get("include_cancelled", False)),
    }


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


class SyncCancelledError(Exception):
    """Raised when the user requested cancellation of a running sync."""


def _humanize_error(exc: Exception) -> str:
    """Convert a backend exception into a short user-readable message.
    Strips PyMongo / httpx noise; preserves the human signal."""
    cls = type(exc).__name__
    msg = str(exc)
    low = msg.lower()
    if "e11000 duplicate key" in low:
        return "Conflicto de datos en la base de datos al guardar deudores. Reintentá; si persiste, contacta a Landa."
    if "timeout" in low or "timed out" in low:
        return "SOFTSEGUROS tardó demasiado en responder. La importación se reintentará automáticamente en el próximo sync."
    if "connection" in low and ("refused" in low or "reset" in low):
        return "No se pudo conectar a SOFTSEGUROS. Verificá tu conexión e intentá más tarde."
    if cls in ("SoftSegurosAuthError",) or "401" in msg or "unauthorized" in low:
        return "Credenciales SOFTSEGUROS inválidas o token expirado. Reconectá tu cuenta."
    if "504" in msg or "502" in msg or "503" in msg:
        return "SOFTSEGUROS no está disponible en este momento. Reintentá más tarde."
    if "429" in msg:
        return "SOFTSEGUROS está limitando peticiones (rate limit). La importación se reintentará."
    # Fallback: first line only, capped.
    first = msg.split("\n")[0].strip()[:240]
    return f"{cls}: {first}" if first else cls


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _today() -> date:
    return _utcnow().date()


# ── póliza → debtor doc mapping ───────────────────────────────────────────────

def _parse_forma_pago(raw) -> Optional[str]:
    """SOFTSEGUROS forma_pago_texto comes as a JSON blob like
    {"banco":"","pagare":"","cheque":"","contado":"1"} — turn it into a human
    label ("Contado", "Financiado", "Cheque", "Pagaré") for speech. Returns None
    when nothing is set, so the agent simply omits the modality."""
    if not raw:
        return None
    # Already a clean label?
    if isinstance(raw, str) and not raw.strip().startswith("{"):
        return raw.strip() or None
    import json as _json
    try:
        d = _json.loads(raw) if isinstance(raw, str) else (raw if isinstance(raw, dict) else {})
    except (ValueError, TypeError):
        return None
    labels = {"contado": "Contado", "banco": "Financiado", "pagare": "Pagaré", "cheque": "Cheque"}
    for key, label in labels.items():
        v = str(d.get(key, "")).strip()
        if v and v not in ("0", "", "false", "None"):
            return label
    return None


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
        # Insurer NAME (e.g. "PREVISORA") — the agent needs this to answer
        # "¿con qué compañía es mi póliza?". The API exposes it as
        # ramo_aseguradora_nombre; only the NIT was being stored before.
        "aseguradora_nombre": p.get("ramo_aseguradora_nombre"),
        "ramo_nombre": p.get("ramo_nombre"),
        "ramo_global_nombre": p.get("ramo_global_nombre"),
        # Payment modality: the CLEAN field is `forma_pago` ("Contado",
        # "Fraccionado", "Financiado", "Acuerdo de pago"). `forma_pago_texto` is a
        # JSON blob ({}) — NOT human text; we keep its parsed form only as fallback.
        "forma_pago": (p.get("forma_pago") or "").strip() or None,
        "forma_pago_texto": _parse_forma_pago(p.get("forma_pago_texto")),
        # Payment MEAN ("Debito", "PSE", "Efectivo"...) — used to skip clients on
        # automatic debit. Comes empty on most policies.
        "medio_pago": (p.get("medio_pago") or "").strip() or None,
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


# ── cartera real (cuota) → debtor doc mapping ─────────────────────────────────
# The REAL endpoint (list_pagospolizas_filtro_paginados) returns one row per CUOTA
# with its own fecha_pago / fecha_realizara_pago (compromiso) / edad_cartera (mora).
# Everything below is driven by tenant_config — zero DPG hardcoding. See
# CARTERA_ENDPOINT.md for the field contract.

def _build_cartera_query(c: dict) -> list:
    """Build the querystring (list of (key, value) tuples) for
    list_pagospolizas_filtro_paginados from the tenant's `softseguros_cartera`
    config. NOTHING is hardcoded: sede/estados/ramos/tipo/order all come from
    config. `sede` is REQUIRED — without it the endpoint returns 504.
    List filters (estados, ramos) become repeated tuples so httpx repeats the key.
    """
    if not c.get("sede"):
        raise ValueError(
            "softseguros_cartera.sede es obligatorio (sin sede el endpoint da 504)"
        )
    # tipo=cartera_por_pagar_compania es la vista de DEUDA VIVA (recaudado=False).
    # consultar_nominas_pasadas es la vista de pagos YA cobrados — NO usar para la cola.
    tipo = c.get("tipo", "cartera_por_pagar_compania")
    q = [
        ("sede", str(c["sede"])),
        ("tipo", tipo),
        ("fecha_a_buscar", c.get("fecha_a_buscar", tipo)),
        ("order_by", c.get("order_by", "fecha_pago")),
        ("sort_by", c.get("sort_by", "asc")),
        ("dias_vencidos", str(c.get("dias_vencidos", -1))),
        ("fecha_busqueda_pagos", str(c.get("fecha_busqueda_pagos", -1))),
        ("search_in", c.get("search_in", "poliza_numero_poliza")),
    ]
    # Date window on fecha_pago (the ONLY server-side date filter). API names them
    # fecha_inicio/fecha_fin; config exposes them as fecha_desde/fecha_hasta.
    # Compromiso has NO server filter — filter it locally after fetch.
    if c.get("fecha_desde"):
        q.append(("fecha_inicio", str(c["fecha_desde"])))
    if c.get("fecha_hasta"):
        q.append(("fecha_fin", str(c["fecha_hasta"])))
    for eid in c.get("estadopolizas_selected", []) or []:
        q.append(("estadopolizas_selected[]", str(eid)))
    for rid in c.get("ramos_selected", []) or []:
        q.append(("ramos_selected[]", str(rid)))
    for k, v in (c.get("extra_filtros") or {}).items():
        q.append((k, str(v)))
    return q


def _norm_phone_co(raw) -> str:
    """poliza_cliente_celular is 10 digits (CO mobile). Twilio needs E.164 (+57…)."""
    if not raw:
        return ""
    s = str(raw).strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    if not digits:
        return ""
    if s.startswith("+"):
        return "+" + digits
    if len(digits) == 10:
        return "+57" + digits
    if len(digits) == 12 and digits.startswith("57"):
        return "+" + digits
    return "+" + digits  # best effort — already has a country code


def _num(v) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _pago_to_debtor_doc(pago: dict, bucket: str, alias_aseguradoras: Optional[dict] = None) -> dict:
    """Map a SOFTSEGUROS cuota (list_pagospolizas_filtro_paginados row) + bucket →
    the $set payload for a debtor. ONE debtor == ONE cuota, keyed by
    `softseguros_pago_id` (the global cuota id). See CARTERA_ENDPOINT.md §mapeo."""
    aseg = pago.get("aseguradora_nombre") or None
    if aseg and alias_aseguradoras:
        aseg = alias_aseguradoras.get(aseg, aseg)
    nombre = " ".join(
        str(x) for x in (pago.get("poliza_cliente_nombres"), pago.get("poliza_cliente_apellidos")) if x
    ).strip()
    return {
        # ── idempotency keys ──
        "softseguros_pago_id": pago.get("id"),          # global cuota id (unique)
        "softseguros_poliza_id": pago.get("poliza_id"),  # groups cuotas of a policy
        # ── client ──
        "nombre": nombre,
        "telefono": _norm_phone_co(pago.get("poliza_cliente_celular")),
        "cliente_documento": pago.get("poliza_cliente_numero_documento"),
        "cliente_celular": pago.get("poliza_cliente_celular"),
        # ── the two dates that drive the ARIA sequence (informe §3) ──
        "vencimiento": pago.get("fecha_pago"),            # fecha de pago = vencimiento cuota
        "fecha_pago": pago.get("fecha_pago"),
        "fecha_compromiso": pago.get("fecha_realizara_pago"),  # fecha acordada con el cliente
        "fecha_realizo_pago": pago.get("fecha_realizo_pago"),
        "edad_cartera": pago.get("edad_cartera"),
        "dias_mora": pago.get("edad_cartera"),
        # ── money ──
        "monto": _num(pago.get("valor_a_pagar")) or _num(pago.get("valor_neto_a_pagar")) or 0.0,
        "valor_cuota": _num(pago.get("valor_a_pagar")),
        "saldo_pendiente": _num(pago.get("saldo_pendiente")),
        "numero_cuota": pago.get("numero_pago") or pago.get("pago_poliza_consecutivo"),
        # ── policy ──
        "numero_poliza": pago.get("poliza_numero_poliza"),
        "ramo_nombre": pago.get("ramo_nombre"),
        "ramo_id": pago.get("ramo_id"),
        "aseguradora_nombre": aseg,
        "forma_pago": (pago.get("poliza_forma_pago") or "").strip() or None,
        "objeto_asegurado": pago.get("poliza_codio_objeto_asegurado"),
        "recaudado": bool(pago.get("recaudado")),
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

    # Pre-compute filter cut-offs.
    allowed_cartera_states = {s.strip().lower() for s in active_filters.get("cartera_states", [])}
    max_age_months = active_filters.get("max_age_months")
    if max_age_months:
        # Approx: 30 days per month is fine here (filter is a heuristic).
        from datetime import timedelta as _td
        oldest_allowed = today - _td(days=int(max_age_months) * 30)
    else:
        oldest_allowed = None

    include_cancelled = bool(active_filters.get("include_cancelled", False))

    def _passes_user_filters(p: dict) -> bool:
        """Return False if the póliza fails the user's cartera_states / max_age /
        estado_poliza (cancelled) filter."""
        # cartera_states filter
        ec = (p.get("estado_cartera") or "").strip().lower()
        if allowed_cartera_states and ec not in allowed_cartera_states:
            return False
        # estado_poliza filter: unless include_cancelled, keep only active pólizas.
        if not include_cancelled:
            ep = (p.get("estado_poliza_nombre") or "").strip().lower()
            if ep not in _ACTIVE_POLIZA_STATES:
                return False
        # max_age_months filter (fecha de referencia)
        if oldest_allowed is not None:
            from .classifier import _to_date as _to_date_fn  # noqa: PLC0415
            fref = _to_date_fn(p.get("fecha_limite_pago")) or _to_date_fn(p.get("fecha_fin"))
            if fref is not None and fref < oldest_allowed:
                return False
        return True

    # Write buffer — pólizas are turned into pymongo UpdateOne ops and flushed
    # to Mongo in one bulk_write per chunk (instead of one round-trip per póliza,
    # which dominated the sync wall-clock on Atlas).
    write_buffer: list = []
    # pids that need a "pagado" soft-mark (separate op shape).
    paid_pids: list = []

    def _persist_poliza(p: dict):
        """Classify + filter a póliza and queue its write op (no I/O here)."""
        pid = p.get("id")
        if pid is None:
            return
        counters["polizas_scanned"] += 1
        if counters["max_poliza_id_seen"] is None or pid > counters["max_poliza_id_seen"]:
            counters["max_poliza_id_seen"] = pid
        bucket = _classify(p, today)

        if bucket in _COBRABLE_BUCKETS and not _passes_user_filters(p):
            doc = _poliza_to_debtor_doc(p, bucket)
            doc["is_active"] = False
            write_buffer.append(debtor_crud.build_softseguros_upsert_op(user_id, pid, doc))
            counters["debtors_excluded_by_filter"] += 1
            return
        if bucket in _COBRABLE_BUCKETS:
            if bucket in allowed_buckets:
                doc = _poliza_to_debtor_doc(p, bucket)  # is_active=True
            else:
                # Cobrable but the user didn't import this kind: keep the doc
                # (preserving Phase-17 call history) but inactive.
                doc = _poliza_to_debtor_doc(p, bucket)
                doc["is_active"] = False
                counters["debtors_excluded_by_filter"] += 1
            write_buffer.append(debtor_crud.build_softseguros_upsert_op(user_id, pid, doc))
        elif bucket == "pagado":
            paid_pids.append(pid)
        # "futuro" → not persisted in v1.

    async def _flush_writes():
        """Execute buffered upserts in one bulk_write, then the paid soft-marks."""
        if write_buffer:
            ops = list(write_buffer)
            write_buffer.clear()
            res = await debtor_crud.bulk_write_debtor_ops(db, ops)
            counters["debtors_created"] += res["created"]
            counters["debtors_updated"] += res["updated"]
        if paid_pids:
            pids = list(paid_pids)
            paid_pids.clear()
            for pid in pids:
                await debtor_crud.mark_debtor_paid_by_softseguros_poliza_id(db, user_id, pid)

    async def _fetch_page(page: int) -> dict:
        return await call(lambda: adapter.list_polizas(page=page))

    def _page_max_fecha(payload: dict):
        """Latest fecha_fin/fecha_limite_pago on a page, as a date (or None)."""
        from .classifier import _to_date as _to_date_fn  # noqa: PLC0415
        best = None
        for p in payload.get("results", []):
            d = _to_date_fn(p.get("fecha_limite_pago")) or _to_date_fn(p.get("fecha_fin"))
            if d is not None and (best is None or d > best):
                best = d
        return best

    async def _probe_start_page(last_pg: int, oldest_allowed_date) -> int:
        """
        Binary-search for the first page whose pólizas fall inside the age window.

        SAFE ONLY because we verified that for this account fecha_fin grows
        ~monotonically with the page number (id ascending). We bias the result
        a few pages earlier as a safety margin against minor non-monotonicity,
        and cap the probe at ~12 requests. Returns 1 if anything is uncertain
        (i.e. degrade to a full scan rather than risk skipping real debt).
        """
        if oldest_allowed_date is None or last_pg <= 40:
            return 1
        lo, hi = 1, last_pg
        probes = 0
        candidate = 1
        while lo <= hi and probes < 12:
            mid = (lo + hi) // 2
            probes += 1
            try:
                payload = await _fetch_page(mid)
            except Exception:  # noqa: BLE001 — any probe failure → full scan
                return 1
            page_max = _page_max_fecha(payload)
            if page_max is None:
                # Can't tell — search lower half to stay safe.
                hi = mid - 1
                continue
            if page_max < oldest_allowed_date:
                # This page is entirely too old → recent data is further ahead.
                lo = mid + 1
            else:
                # This page reaches into the window → start at/below here.
                candidate = mid
                hi = mid - 1
        # Safety margin: back off ~20 pages (≈200 pólizas) so a slightly
        # out-of-order old póliza near the boundary is still caught.
        start = max(1, candidate - 20)
        return start

    # Flush counters to the sync_log doc so the UI can poll live progress.
    async def _flush_progress():
        await db.softseguros_sync_logs.update_one(
            {"_id": log_id},
            {"$set": {
                "polizas_scanned": counters["polizas_scanned"],
                "total_count": counters["total_count"],
                "debtors_created": counters["debtors_created"],
                "debtors_updated": counters["debtors_updated"],
                "debtors_excluded_by_filter": counters["debtors_excluded_by_filter"],
                "debtors_marked_paid": counters["debtors_marked_paid"],
                "debtors_marked_deleted": counters["debtors_marked_deleted"],
                "total_requests": call.total_requests,
            }}
        )

    async def _check_cancelled():
        st = await db.softseguros_sync_state.find_one({"user_id": user_id}, {"cancel_requested": 1})
        if st and st.get("cancel_requested"):
            # Clear the flag so a subsequent sync doesn't get instantly cancelled.
            await db.softseguros_sync_state.update_one(
                {"user_id": user_id}, {"$set": {"cancel_requested": False}}
            )
            raise SyncCancelledError("sync cancelled by user")

    try:
        await call(lambda: adapter.authenticate())

        # ── Phase A: determine the page range to fetch ───────────────────────
        first = await _fetch_page(1)
        total_count = int(first.get("count") or 0)
        counters["total_count"] = total_count
        last_page = max(1, math.ceil(total_count / PAGE_SIZE)) if total_count else 1

        state = await db.softseguros_sync_state.find_one({"user_id": user_id})

        early_cutoff_used = False
        if is_full_scan or not state:
            # Early-cutoff: when the user asked for a short age window
            # (max_age_months <= 12) and the listing is large, binary-probe for
            # the first in-window page and skip the (verified-older) prefix.
            # Falls back to a full scan if the probe is uncertain.
            start_page = 1
            if (
                is_full_scan
                and oldest_allowed is not None
                and max_age_months is not None
                and max_age_months <= 12
                and last_page > 200
            ):
                start_page = await _probe_start_page(last_page, oldest_allowed)
                early_cutoff_used = start_page > 1
            pages_to_fetch = list(range(start_page, last_page + 1))
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

        def _handle_page_payload(payload: dict):
            # Pure CPU: classify + queue write ops into the buffer. No I/O —
            # the actual Mongo write happens once per chunk in _flush_writes().
            for p in payload.get("results", []):
                if p.get("id") is not None:
                    seen_ids.add(p["id"])
                _persist_poliza(p)

        # Page 1
        if 1 in pages_to_fetch:
            _handle_page_payload(first)
            remaining = [pg for pg in pages_to_fetch if pg != 1]
        else:
            remaining = list(pages_to_fetch)

        # Fetch the rest concurrently in chunks. After each chunk: flush the
        # write buffer (one bulk_write), flush progress, check cancellation.
        CHUNK_SIZE = 20

        async def _fetch_and_handle(pg: int):
            payload = await _fetch_page(pg)
            _handle_page_payload(payload)

        await _flush_writes()     # persist page 1
        await _flush_progress()   # initial flush right after page 1

        if remaining:
            for i in range(0, len(remaining), CHUNK_SIZE):
                await _check_cancelled()
                chunk = remaining[i : i + CHUNK_SIZE]
                await asyncio.gather(*(_fetch_and_handle(pg) for pg in chunk))
                await _flush_writes()
                await _flush_progress()

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
    except SyncCancelledError:
        status = "cancelled"
        error_message = None
        logger.info("softseguros run_sync cancelled by user user_id=%s mode=%s", user_id, mode)
    except Exception as exc:  # noqa: BLE001 — record & re-raise
        status = "failed"
        error_message = _humanize_error(exc)
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
        "early_cutoff_used": locals().get("early_cutoff_used", False),
        "duration_seconds": (completed_at - started_at).total_seconds(),
    }
    await db.softseguros_sync_logs.update_one({"_id": log_id}, {"$set": final})

    if status == "failed":
        raise SoftSegurosAPIError(f"sync failed: {error_message}")

    out = dict(log_doc)
    out.update(final)
    out["_id"] = str(log_id)
    return out
