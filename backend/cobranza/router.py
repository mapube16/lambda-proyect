"""
router.py — REST endpoints for cobranza debtor management.
All endpoints require authentication and enforce tenant isolation via user_id.
Prefix: /api/cobranza
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, Field

from auth import get_current_user, require_staff
from database import get_db, get_client_profile
from cobranza.debtor_crud import (
    bulk_create_debtors,
    bulk_upsert_debtors,
    create_debtor,
    delete_debtor,
    get_debtor_by_id,
    get_debtors,
    update_debtor,
)
from cobranza.csv_parser import normalize_phone, parse_debtor_csv
from cobranza.cobranza_queen import generate_cobranza_proposal
from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today


# ── Cobranza-enabled guard ─────────────────────────────────────────────────────

async def _require_cobranza_enabled(current_user: dict) -> None:
    """
    Raise 403 if the current user does not have cobranza_enabled=True in
    their company_voice document.  Purely read-only CRUD routes (list, get)
    are NOT protected by this guard — only call-initiating routes are.
    """
    user_id = str(current_user["user_id"])
    db = get_db()
    doc = await db.company_voice.find_one({"user_id": user_id})
    if not doc or not doc.get("cobranza_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cobranza no habilitado para esta cuenta. Contacte al staff para activarlo.",
        )

logger = logging.getLogger("cobranza.router")

router = APIRouter(prefix="/api/cobranza", tags=["cobranza"])


# ── Request / Response Models ─────────────────────────────────────────────────

class DebtorCreate(BaseModel):
    nombre: str
    telefono: str
    monto: float
    vencimiento: str  # "YYYY-MM-DD"
    notas: Optional[str] = None
    max_intentos: int = 5


class DebtorPatch(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    monto: Optional[float] = None
    vencimiento: Optional[str] = None  # "YYYY-MM-DD"
    notas: Optional[str] = None
    # Override humano de la exclusión (informe §2): liberar un falso positivo
    # del clasificador de entidades estatales, o excluir manualmente a alguien.
    no_llamar: Optional[bool] = None


# ── Status ───────────────────────────────────────────────────────────────────

@router.get("/status")
async def cobranza_status(current_user: dict = Depends(get_current_user)):
    """Returns whether cobranza is enabled for the current user and if strategy is configured."""
    user_id = str(current_user["user_id"])
    db = get_db()
    doc = await db.company_voice.find_one({"user_id": user_id})
    enabled = bool((doc or {}).get("cobranza_enabled", False))
    config_doc = await db.cobranza_config.find_one({"user_id": user_id})
    configured = bool((config_doc or {}).get("estrategia"))
    
    # DEBUG: Log what we found
    import logging
    logger = logging.getLogger("cobranza")
    logger.info(f"[cobranza_status] user_id={user_id}, doc found: {doc is not None}, enabled: {enabled}, config found: {config_doc is not None}, configured: {configured}")
    
    return {"enabled": enabled, "configured": configured, "_debug_user_id": user_id, "_debug_doc_exists": doc is not None}


# ── Cobranza config (multi-tenant, editable desde UI) ─────────────────────────
# Todos los parámetros del tenant viven en tenant_config.cobranza y se editan desde
# aquí. CERO hardcode: sede/estados/ramos/mora/horarios/timings por tenant.

class SoftsegurosCarteraBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sede: int
    estadopolizas_selected: list[int] = Field(default_factory=list)
    ramos_selected: list[int] = Field(default_factory=list)
    tipo: str = "cartera_por_pagar_compania"
    fecha_desde: Optional[str] = None   # "YYYY-MM-DD" — ventana de compromiso (deuda viva)
    fecha_hasta: Optional[str] = None   # techo FIJO (solo arranque) …
    # … o techo RODANTE: hoy + N días hábiles, recalculado en cada sync (régimen).
    # Si se define, tiene prioridad sobre fecha_hasta.
    fecha_hasta_rodante_dias: Optional[int] = Field(None, ge=0, le=30)
    ventana_proximos_dias: int = Field(30, ge=0, le=365)
    solo_no_recaudadas: bool = True
    alias_aseguradoras: dict[str, str] = Field(default_factory=dict)
    max_concurrency: int = Field(5, ge=1, le=20)
    base_url: Optional[str] = None


class TimingsBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offsets_intentos_dias_habiles: list[int] = Field(default_factory=lambda: [-1, 0, 2])
    frecuencia_dias: int = Field(1, ge=1, le=30)
    max_intentos: int = Field(3, ge=1, le=10)
    pre_vencimiento_dias: int = Field(1, ge=0, le=30)
    agendar_por: str = "fecha_compromiso"  # o "fecha_pago"


class HorariosBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str = "America/Bogota"
    dias_habiles: list[int] = Field(default_factory=lambda: [1, 2, 3, 4, 5])
    franjas: list[list[str]] = Field(default_factory=list)         # [["09:00","12:00"],["14:00","16:00"]]
    franjas_sabado: list[list[str]] = Field(default_factory=list)
    festivos: list[str] = Field(default_factory=list)              # ["YYYY-MM-DD"]
    max_contactos_dia: int = Field(1, ge=1, le=10)


class VolumenBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    llamadas_por_dia: int = Field(30, ge=1, le=5000)
    distribucion: str = "uniforme"
    # Gate DURO por fecha: antes de esta fecha, el dispatcher no marca a NADIE
    # de este tenant — sin importar el kill-switch manual (defensa en
    # profundidad: no depende de que alguien se acuerde de prender el switch
    # el día correcto). None = sin gate (el kill-switch manual manda solo).
    fecha_activacion: Optional[str] = None  # "YYYY-MM-DD"


class EstrategiaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tono: Optional[str] = None
    guion: dict[str, str] = Field(default_factory=dict)


class CobranzaConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    softseguros_cartera: Optional[SoftsegurosCarteraBlock] = None
    timings: Optional[TimingsBlock] = None
    horarios: Optional[HorariosBlock] = None
    volumen: Optional[VolumenBlock] = None
    estrategia: Optional[EstrategiaBlock] = None


class SincronizarBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    # Carga manual con ventana custom (fecha_desde/fecha_hasta/ventana_proximos_dias…).
    # Si viene, corre en modo "manual" y PINEA los deudores (el sweep diario no los toca).
    override_filters: Optional[dict] = None


# Ley 2300 (Colombia) = techo legal duro. La UI nunca puede exceder esto.
_LEY2300_LV = (7 * 60, 19 * 60)    # L-V 07:00–19:00
_LEY2300_SAB = (8 * 60, 15 * 60)   # Sáb 08:00–15:00


def _hhmm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def _validate_franjas(franjas: list, legal: tuple, label: str) -> None:
    lo, hi = legal
    for fr in franjas or []:
        if not isinstance(fr, (list, tuple)) or len(fr) != 2:
            raise HTTPException(status_code=400, detail=f"{label}: cada franja debe ser [inicio, fin] HH:MM")
        try:
            a, b = _hhmm(fr[0]), _hhmm(fr[1])
        except Exception:
            raise HTTPException(status_code=400, detail=f"{label}: hora inválida (usa HH:MM)")
        if a >= b:
            raise HTTPException(status_code=400, detail=f"{label}: {fr[0]} debe ser antes de {fr[1]}")
        if a < lo or b > hi:
            raise HTTPException(
                status_code=400,
                detail=f"{label}: {fr[0]}-{fr[1]} excede el límite legal (Ley 2300: {lo//60:02d}:00-{hi//60:02d}:00)",
            )


@router.get("/config")
async def get_cobranza_config(current_user: dict = Depends(get_current_user)):
    """Devuelve el bloque `cobranza` de tenant_config para pre-cargar la UI. {} si no está configurado."""
    from cobranza.config_cache import get_tenant_config
    user_id = str(current_user["user_id"])
    cfg = await get_tenant_config(user_id)
    return cfg.get("cobranza") or {}


@router.patch("/config")
async def patch_cobranza_config(
    body: CobranzaConfigPatch,
    current_user: dict = Depends(get_current_user),
):
    """Actualiza (parcial) la config de cobranza del tenant. Clampa horarios contra Ley 2300."""
    from cobranza.tenant_config import set_cobranza_config
    from cobranza.config_cache import get_tenant_config
    user_id = str(current_user["user_id"])
    if body.horarios is not None:
        _validate_franjas(body.horarios.franjas, _LEY2300_LV, "franjas (L-V)")
        _validate_franjas(body.horarios.franjas_sabado, _LEY2300_SAB, "franjas (Sáb)")
    block = body.model_dump(exclude_none=True)
    if not block:
        raise HTTPException(status_code=400, detail="No hay bloques de config para actualizar.")
    await set_cobranza_config(user_id, block)
    cfg = await get_tenant_config(user_id)
    return {"saved": True, "cobranza": cfg.get("cobranza") or {}}


@router.post("/sincronizar")
async def cobranza_sincronizar(
    body: Optional[SincronizarBody],
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Dispara un sync de la cartera Softseguros en background. Sin `override_filters`
    = refresh con la config estándar. Con `override_filters` = carga manual (pinned)."""
    user_id = str(current_user["user_id"])
    override = body.override_filters if body else None
    mode = "manual" if override else "cron_daily"

    async def _run():
        try:
            from softseguros.sync import run_cartera_sync
            await run_cartera_sync(get_db(), user_id, mode=mode, override_filters=override)
        except Exception:  # noqa: BLE001
            logger.exception("cobranza sincronizar failed user_id=%s mode=%s", user_id, mode)

    background_tasks.add_task(_run)
    return {"sync_started": True, "mode": mode, "pinned": override is not None}


# ── EMERGENCY KILL-SWITCH (master ON/OFF for automated dialing) ────────────────
#
# Hot switch with immediate effect — no redeploy, no worker restart. Flips the
# runtime flag in Mongo and pauses/resumes the live APScheduler campaign jobs.
# OFF  → the whole automated-calling circuit stops; nobody gets auto-dialed, and
#        calls queued just before the flip are aborted before they dial. The API,
#        inbound handling and manual test calls stay alive.
# ON   → dialing resumes.
# Staff-only: this is a system-wide control, not per-tenant.

class KillSwitchPayload(BaseModel):
    enabled: bool


# ── Jornada de hoy (informe §2.1: revisión previa del colaborador) ─────────────

@router.get("/jornada-hoy")
async def jornada_hoy(current_user: dict = Depends(get_current_user)):
    """
    Llamadas PROGRAMADAS para hoy, en el orden real de marcación (prioridad del
    informe: vencen hoy → preventivas → mayor mora). Es la lista que el
    colaborador de cartera revisa ANTES de la jornada para excluir clientes
    (botón pausar). Se calcula en vivo con la misma lógica del dispatcher, así
    que refleja exactamente lo que el bot va a hacer.
    """
    from cobranza.sequence_engine import (
        CALLABLE_ESTADOS, _parse_festivos, _tz,
        compute_proximo_intento, prioridad_informe,
    )
    user_id = str(current_user["user_id"])
    db = get_db()

    from cobranza.config_cache import get_tenant_config
    cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
    timings, horarios = cfg.get("timings") or {}, cfg.get("horarios") or {}
    volumen = cfg.get("volumen") or {}
    tz = _tz(horarios)
    today_local = datetime.now(timezone.utc).astimezone(tz).date()
    extra_fest = _parse_festivos(horarios)

    cursor = db.debtors.find(
        {
            "user_id": user_id,
            "is_active": {"$ne": False},
            "no_llamar": {"$ne": True},  # entidades estatales / opt-out (informe §2)
            "estado": {"$in": list(CALLABLE_ESTADOS)},
        },
        {
            "nombre": 1, "telefono": 1, "numero_poliza": 1, "ramo_nombre": 1,
            "dias_mora": 1, "edad_cartera": 1, "vencimiento": 1, "fecha_pago": 1,
            "fecha_compromiso": 1, "fecha_reagendada": 1, "estado": 1, "monto": 1,
            "intentos": 1, "proximo_intento_at": 1, "ultimo_contacto_fecha": 1,
        },
    )
    programados = []
    async for d in cursor:
        at = d.get("proximo_intento_at")
        if at is None:
            # sin cita persistida (p.ej. planner aún no corre) → misma cuenta pura
            verdict, at = compute_proximo_intento(d, timings, horarios, today=today_local)
            if verdict != "cita":
                continue
        if at.tzinfo is None:
            from datetime import timezone as _tzu
            at = at.replace(tzinfo=_tzu.utc)
        at_local = at.astimezone(tz)
        if at_local.date() > today_local:
            continue  # cita futura — no es de hoy
        grupo, _ = prioridad_informe(d, today_local, extra_fest)
        programados.append({
            "_id": str(d["_id"]),
            "nombre": d.get("nombre"),
            "telefono": d.get("telefono"),
            "numero_poliza": d.get("numero_poliza"),
            "ramo_nombre": d.get("ramo_nombre"),
            "estado": d.get("estado"),
            "monto": d.get("monto"),
            "dias_mora": d.get("dias_mora") or d.get("edad_cartera") or 0,
            "intento": int(d.get("intentos") or 0) + 1,
            "hora": at_local.strftime("%H:%M"),
            "grupo": ["vence_hoy", "preventiva", "backlog"][grupo],
            "_orden": prioridad_informe(d, today_local, extra_fest),
        })

    programados.sort(key=lambda x: x["_orden"])
    cupo = int(volumen.get("llamadas_por_dia") or 30)
    for i, p in enumerate(programados):
        p.pop("_orden", None)
        p["dentro_cupo"] = i < cupo
    return {
        "fecha": today_local.isoformat(),
        "total": len(programados),
        "cupo_diario": cupo,
        "items": programados,
    }


# ── Paquete de minutos ─────────────────────────────────────────────────────────

@router.get("/minutos")
async def get_minutos(current_user: dict = Depends(get_current_user)):
    """Saldo del paquete de minutos del tenant (solo lectura — recargas vía staff)."""
    from cobranza.minutes import get_saldo
    return await get_saldo(get_db(), str(current_user["user_id"]))


class MinutosRecarga(BaseModel):
    model_config = ConfigDict(extra="forbid")
    minutos: int
    nota: str = ""
    tipo: str = "compra"  # "compra" (>0) o "ajuste" (+/-)


@router.post("/minutos/{client_id}")
async def staff_recargar_minutos(
    client_id: str,
    body: MinutosRecarga,
    staff: dict = Depends(require_staff),
):
    """STAFF ONLY: registrar compra/ajuste de minutos para un tenant (ledger auditable)."""
    from cobranza.minutes import record_purchase
    try:
        saldo = await record_purchase(
            get_db(), client_id, body.minutos,
            nota=body.nota, actor=str(staff.get("email") or staff.get("user_id")),
            tipo=body.tipo,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return saldo


# ── Alertas tipadas (informe §7) ────────────────────────────────────────────

@router.get("/alertas")
async def get_alertas(
    solo_pendientes: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    """Cola de alertas del tenant — lo que el colaborador revisa a diario (informe §12)."""
    from cobranza.alerts import listar_alertas
    items = await listar_alertas(get_db(), str(current_user["user_id"]), solo_pendientes=solo_pendientes)
    return {"items": items, "total": len(items)}


@router.post("/alertas/{alerta_id}/atender")
async def atender_alerta(alerta_id: str, current_user: dict = Depends(get_current_user)):
    """Marca una alerta como atendida (el colaborador ya la gestionó)."""
    from cobranza.alerts import marcar_atendida
    ok = await marcar_atendida(
        get_db(), str(current_user["user_id"]), alerta_id,
        actor=str(current_user.get("email") or current_user["user_id"]),
    )
    if not ok:
        raise HTTPException(404, "Alerta no encontrada")
    return {"ok": True}


# ── Reportes diario/semanal (informe §12) ───────────────────────────────────

@router.get("/reportes/preview")
async def preview_reporte(
    tipo: str = Query("diario", pattern="^(diario|semanal)$"),
    current_user: dict = Depends(get_current_user),
):
    """Vista previa (sin enviar email) — métricas + síntesis reales del período."""
    from datetime import timedelta
    from cobranza import reports
    user_id = str(current_user["user_id"])
    db = get_db()
    if tipo == "diario":
        hoy = datetime.now(reports.COLOMBIA_TZ).date()
        start, end = reports._dia_utc_range(hoy)
        metrics = await reports.aggregate_metrics(db, user_id, start, end, hoy)
    else:
        hoy = datetime.now(reports.COLOMBIA_TZ).date()
        start, _ = reports._dia_utc_range(hoy - timedelta(days=6))
        _, end = reports._dia_utc_range(hoy)
        metrics = await reports.aggregate_metrics(db, user_id, start, end, hoy)
    muestras = await reports._muestras_del_dia(db, user_id, start, end)
    qualitative = await reports.synthesize_qualitative(muestras)
    return {"metrics": metrics, "qualitative": qualitative}


@router.post("/reportes/enviar-ahora")
async def enviar_reporte_ahora(
    tipo: str = Query("diario", pattern="^(diario|semanal)$"),
    staff: dict = Depends(require_staff),
):
    """STAFF ONLY: dispara el reporte fuera del cron (prueba/recuperación de un envío perdido)."""
    from cobranza import reports
    user_id = str(staff["user_id"])
    db = get_db()
    if tipo == "diario":
        return await reports.run_daily_report(db, user_id)
    return await reports.run_weekly_report(db, user_id)


@router.get("/killswitch")
async def get_killswitch(current_user: dict = Depends(require_staff)):
    """Return the current state of the automated-dialing master switch."""
    from cobranza.campaign_scheduler import is_autocall_enabled
    enabled = await is_autocall_enabled()
    return {"autocall_enabled": enabled}


@router.post("/killswitch")
async def set_killswitch(
    payload: KillSwitchPayload,
    current_user: dict = Depends(require_staff),
):
    """
    Master ON/OFF switch for the automated cobranza calling circuit.

    Body: {"enabled": false}  → STOP all automated calls immediately.
          {"enabled": true}   → resume automated calling.

    Effect is live (jobs paused/resumed in-process + Mongo flag persisted so it
    survives restarts). In-flight queued calls are aborted before dialing.
    """
    from cobranza.campaign_scheduler import set_autocall_enabled
    from landa.scheduler import scheduler

    actor = str(current_user.get("user_id", "staff"))
    new_state = await set_autocall_enabled(payload.enabled, scheduler=scheduler, actor=actor)
    logger.warning("[killswitch] autocall set to %s by %s", new_state, actor)
    return {
        "autocall_enabled": new_state,
        "message": (
            "Discado automático REANUDADO." if new_state
            else "Discado automático DETENIDO. Ninguna llamada saliente se realizará."
        ),
    }


# ── CSV Upload ────────────────────────────────────────────────────────────────

@router.post("/debtors/csv", status_code=status.HTTP_201_CREATED)
async def upload_debtors_csv(
    file: UploadFile = File(...),
    mode: str = Query("create", regex="^(create|update)$"),
    current_user: dict = Depends(get_current_user),
):
    """
    Upload a CSV file of debtors.
    mode=create (default): insert new debtors, skip duplicates by phone.
    mode=update: upsert by phone — updates nombre/monto/vencimiento/notas for
                 existing debtors, preserving estado/intentos/historial.
    Returns {created: N, updated: N, errors: [...]}
    """
    user_id = str(current_user["user_id"])
    db = get_db()

    file_bytes = await file.read()
    valid_rows, errors = parse_debtor_csv(file_bytes)

    if mode == "update":
        result = await bulk_upsert_debtors(db, user_id, valid_rows)
        return {"created": result["created"], "updated": result["updated"], "errors": errors}

    result = await bulk_create_debtors(db, user_id, valid_rows)
    return {"created": result["created"], "updated": 0, "errors": errors}


# ── Single Debtor Create ──────────────────────────────────────────────────────

@router.post("/debtors", status_code=status.HTTP_201_CREATED)
async def create_debtor_endpoint(
    body: DebtorCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a single debtor. Returns {debtor: {...}}."""
    user_id = str(current_user["user_id"])
    db = get_db()

    # Normalize phone
    normalized = normalize_phone(body.telefono)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"telefono inválido '{body.telefono}'",
        )

    # Parse vencimiento
    try:
        vencimiento = datetime.strptime(body.vencimiento.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"vencimiento inválido '{body.vencimiento}' (esperado YYYY-MM-DD)",
        )

    data = {
        "nombre": body.nombre,
        "telefono": normalized,
        "monto": body.monto,
        "vencimiento": vencimiento,
        "notas": body.notas,
        "max_intentos": body.max_intentos,
    }

    debtor = await create_debtor(db, user_id, data)
    return {"debtor": debtor}


# ── List Debtors ──────────────────────────────────────────────────────────────

@router.get("/debtors")
async def list_debtors(
    estado: Optional[str] = Query(None),
    group: Optional[str] = Query(None, description="atencion | pendientes | gestion | resueltos"),
    min_mora: Optional[int] = Query(None, ge=0, description="Solo deudores con dias_mora >= este valor"),
    sort: Optional[str] = Query(None, description="'mora' = mayor mora primero; por defecto, más reciente"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Paginated debtors for the authenticated user, filterable by estado, group or min_mora."""
    user_id = str(current_user["user_id"])
    db = get_db()
    return await get_debtors(
        db, user_id, estado=estado, group=group,
        min_mora=min_mora, sort=sort, page=page, page_size=page_size,
    )


# ── Today's activity summary (the 5 KPIs at the top of the cobranza panel) ──────
# IMPORTANT: declared BEFORE /debtors/{debtor_id} would never match these, but we
# use distinct paths (/today-summary, /funnel) so there's no ambiguity anyway.
@router.get("/today-summary")
async def today_summary(current_user: dict = Depends(get_current_user)):
    """Counts (and montos where relevant) of TODAY's bot activity, per the dashboard KPIs."""
    from datetime import datetime, timezone, timedelta
    user_id = str(current_user["user_id"])
    db = get_db()
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    # is_active != False: excluye deudores archivados por el sync (pagados upstream /
    # fuera de la ventana) para que no inflen los contadores de la cola activa.
    base = {"user_id": user_id, "is_active": {"$ne": False}}

    # Llamando ahora (live, not date-bound)
    llamando = await db.debtors.count_documents({**base, "estado": "llamando"})

    # Contactados hoy: last contact today AND currently a "contacted-ish" state
    contactados_hoy = await db.debtors.count_documents({
        **base,
        "ultimo_contacto_fecha": {"$gte": today_start},
        "estado": {"$in": ["contactado", "promesa_de_pago", "reagendado"]},
    })

    # Promesas hoy: moved to promesa_de_pago today (use updated_at). Sum monto_prometido.
    promesa_pipeline = [
        {"$match": {**base, "estado": "promesa_de_pago", "updated_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "monto": {"$sum": {"$ifNull": ["$monto_prometido", 0]}}}},
    ]
    pr = await db.debtors.aggregate(promesa_pipeline).to_list(length=1)
    promesas_hoy = {"count": pr[0]["n"], "monto": float(pr[0]["monto"] or 0)} if pr else {"count": 0, "monto": 0.0}

    # Pagado hoy: moved to pagado today. Sum monto.
    pagado_pipeline = [
        {"$match": {**base, "estado": "pagado", "updated_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "n": {"$sum": 1}, "monto": {"$sum": {"$ifNull": ["$monto", 0]}}}},
    ]
    pg = await db.debtors.aggregate(pagado_pipeline).to_list(length=1)
    pagado_hoy = {"count": pg[0]["n"], "monto": float(pg[0]["monto"] or 0)} if pg else {"count": 0, "monto": 0.0}

    # Sin contacto (accumulated — needs attention, not just today)
    sin_contacto = await db.debtors.count_documents({**base, "estado": "sin_contacto"})

    return {
        "llamando_ahora": llamando,
        "contactados_hoy": contactados_hoy,
        "promesas_hoy": promesas_hoy,
        "pagado_hoy": pagado_hoy,
        "sin_contacto": sin_contacto,
        "as_of": now,
    }


# ── Funnel: counts per estado across the WHOLE cartera ──────────────────────────
@router.get("/funnel")
async def funnel(current_user: dict = Depends(get_current_user)):
    """Count of debtors per estado (the pipeline bar). Whole cartera."""
    user_id = str(current_user["user_id"])
    db = get_db()
    pipeline = [
        {"$match": {"user_id": user_id, "is_active": {"$ne": False}}},
        {"$group": {"_id": "$estado", "n": {"$sum": 1}}},
    ]
    counts: dict[str, int] = {}
    async for row in db.debtors.aggregate(pipeline):
        counts[row["_id"] or "pendiente"] = int(row["n"])
    total = sum(counts.values())
    return {"counts": counts, "total": total}


# ── Get Single Debtor ─────────────────────────────────────────────────────────

@router.get("/debtors/{debtor_id}")
async def get_debtor_endpoint(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get full debtor document including historial_llamadas."""
    user_id = str(current_user["user_id"])
    db = get_db()
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if debtor is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": debtor}


# ── Patch Debtor ──────────────────────────────────────────────────────────────

@router.patch("/debtors/{debtor_id}")
async def patch_debtor_endpoint(
    debtor_id: str,
    body: DebtorPatch,
    current_user: dict = Depends(get_current_user),
):
    """Partially update nombre/telefono/monto/vencimiento/notas."""
    user_id = str(current_user["user_id"])
    db = get_db()

    patch: dict = {}
    if body.nombre is not None:
        patch["nombre"] = body.nombre
    if body.telefono is not None:
        normalized = normalize_phone(body.telefono)
        if normalized is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"telefono inválido '{body.telefono}'",
            )
        patch["telefono"] = normalized
    if body.monto is not None:
        patch["monto"] = body.monto
    if body.vencimiento is not None:
        try:
            patch["vencimiento"] = datetime.strptime(body.vencimiento.strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"vencimiento inválido '{body.vencimiento}' (esperado YYYY-MM-DD)",
            )
    if body.notas is not None:
        patch["notas"] = body.notas
    if body.no_llamar is not None:
        # Decisión humana: queda estampada como manual para que el clasificador
        # automático NUNCA la vuelva a tocar (run_clasificacion salta docs con
        # tipo_entidad ya definido).
        patch["no_llamar"] = body.no_llamar
        patch["no_llamar_motivo"] = "manual" if body.no_llamar else None
        patch["tipo_entidad"] = "estatal" if body.no_llamar else "privada"
        patch["clasificado_por"] = "manual"

    try:
        updated = await update_debtor(db, user_id, debtor_id, patch)
    except ValueError as e:
        if "telefono_duplicado" in str(e):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Ya existe un deudor con ese número de teléfono.",
            )
        raise
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


# ── Delete Debtor ─────────────────────────────────────────────────────────────

@router.delete("/debtors/{debtor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debtor_endpoint(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a debtor."""
    user_id = str(current_user["user_id"])
    db = get_db()
    deleted = await delete_debtor(db, user_id, debtor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Debtor not found")


# ── State Transition Endpoints ────────────────────────────────────────────────

@router.post("/debtors/{debtor_id}/pagar")
async def marcar_pagado(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark debtor as pagado."""
    user_id = str(current_user["user_id"])
    db = get_db()
    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pagado"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


@router.post("/debtors/{debtor_id}/pausar")
async def pausar_debtor(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Pause a debtor (sets estado=pausado)."""
    user_id = str(current_user["user_id"])
    db = get_db()
    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pausado"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


@router.post("/debtors/{debtor_id}/reactivar")
async def reactivar_debtor(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Reactivate a paused debtor (estado=pausado -> pendiente)."""
    user_id = str(current_user["user_id"])
    db = get_db()

    # Only reactivate if currently pausado
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if debtor is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    if debtor.get("estado") != "pausado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reactivate debtor with estado='{debtor.get('estado')}' (must be 'pausado')",
        )

    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pendiente"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


# ── Onboarding: Start (Queen proposal) ────────────────────────────────────────

class OnboardingStartBody(BaseModel):
    descripcion: str


@router.post("/onboarding/start")
async def onboarding_start(
    body: OnboardingStartBody,
    current_user: dict = Depends(get_current_user),
):
    """
    POST /api/cobranza/onboarding/start
    User describes their portfolio; Queen returns a cobranza strategy proposal.
    """
    user_id = str(current_user["user_id"])

    profile = await get_client_profile(user_id)
    empresa_nombre = (profile or {}).get("empresa_nombre", "la empresa")

    estrategia = await generate_cobranza_proposal(body.descripcion, empresa_nombre)
    return {"estrategia": estrategia}


# ── Onboarding: Approve (save campaign) ───────────────────────────────────────

class OnboardingApproveBody(BaseModel):
    estrategia: dict


@router.post("/onboarding/approve")
async def onboarding_approve(
    body: OnboardingApproveBody,
    current_user: dict = Depends(get_current_user),
):
    """
    POST /api/cobranza/onboarding/approve
    Persist approved (possibly user-edited) estrategia to cobranza_config collection.
    Automatically enables cobranza dashboard when strategy is approved.
    Returns campaign_id = user_id.
    """
    user_id = str(current_user["user_id"])
    db = get_db()
    now = datetime.now(timezone.utc)

    # Save cobranza strategy
    await db.cobranza_config.update_one(
        {"user_id": user_id},
        {"$set": {"estrategia": body.estrategia, "updated_at": now}},
        upsert=True,
    )

    # Auto-enable cobranza dashboard when strategy is approved
    await db.company_voice.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "cobranza_enabled": True,
                "cobranza_enabled_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {"user_id": user_id, "created_at": now},
        },
        upsert=True,
    )

    return {"campaign_id": user_id, "ok": True}


# ── Llamar Ahora (manual immediate call) ──────────────────────────────────────

async def _initiate_call_and_update(db, user_id: str, debtor: dict, config: dict) -> None:
    """Fire-and-forget: initiate Twilio/Pipecat call and update debtor state."""
    from datetime import datetime, timezone
    debtor_id = str(debtor["_id"])
    try:
        logger.info("[llamar-ahora] Starting Pipecat call for debtor %s", debtor_id)
        from twilio.rest import Client
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([account_sid, auth_token, from_number]):
            raise RuntimeError("Twilio not configured")

        from cobranza.minutes import require_saldo  # lanza si el paquete se agotó
        await require_saldo(db, user_id)

        from cobranza.minutes import call_status_kwargs
        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        call = client.calls.create(
            to=to_number, from_=from_number,
            url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
            **call_status_kwargs(),
        )
        call_sid = call.sid
        logger.info("[llamar-ahora] Twilio call %s -> %s", call_sid, to_number)

        # Store call mapping for WebSocket handler
        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid, "user_id": user_id,
            "debtor_id": debtor_id, "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await update_debtor(db, user_id, debtor_id, {"vapi_call_id": call_sid})
        logger.info("[llamar-ahora] Call initiated %s for debtor %s", call_sid, debtor_id)
    except (ValueError, RuntimeError) as e:
        logger.error("[llamar-ahora] Call failed for debtor %s: %s", debtor_id, e, exc_info=True)
        await update_debtor(db, user_id, debtor_id, {"estado": "pendiente"})
    except Exception as e:
        logger.error("[llamar-ahora] Unexpected error for debtor %s: %s", debtor_id, e, exc_info=True)
        await update_debtor(db, user_id, debtor_id, {"estado": "pendiente"})


@router.post("/debtors/{debtor_id}/llamar-ahora", status_code=status.HTTP_202_ACCEPTED)
async def llamar_ahora(
    debtor_id: str,
    test: bool = False,
    force: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """
    POST /api/cobranza/debtors/{debtor_id}/llamar-ahora
    Manually trigger an immediate call to a debtor.
    Requires cobranza_enabled flag set by staff.
    Ley 2300 compliance guards applied before initiating.
    Pass ?test=true to skip Ley 2300 guards (dev only).
    Pass ?force=true to override "already contacted today" (user accepted warning).
    """
    await _require_cobranza_enabled(current_user)
    user_id = str(current_user["user_id"])
    db = get_db()

    is_dev = os.getenv("ENV", "development") != "production"

    if not (test and is_dev):
        # Ley 2300: time window guard
        if not is_contact_allowed_now():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Fuera de horario permitido (Ley 2300)",
            )

    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if debtor is None:
        raise HTTPException(status_code=404, detail="Debtor not found")

    if debtor.get("no_llamar"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Este deudor no se gestiona por el bot ({debtor.get('no_llamar_motivo') or 'no_llamar'}).",
        )

    if not (test and is_dev) and not force:
        # Ley 2300: one contact per day — return 409 so frontend can show modal
        if has_been_contacted_today(debtor):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Ya fue contactado hoy (Ley 2300)",
            )

    # Fetch campaign config
    config_doc = await db.cobranza_config.find_one({"user_id": user_id}) or {}
    config = config_doc.get("estrategia", {})

    # Mark as calling
    await update_debtor(db, user_id, debtor_id, {"estado": "llamando", "vapi_call_id": None})

    # Initiate Twilio call (insert mapping first to avoid race condition with webhook)
    from twilio.rest import Client as TwilioClient
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
    webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

    if not all([account_sid, auth_token, from_number]):
        raise HTTPException(500, "Twilio not configured")

    # Paquete de minutos: sin saldo no se marca (402 = payment required).
    from cobranza.minutes import MinutesExhaustedError, require_saldo
    try:
        await require_saldo(db, user_id)
    except MinutesExhaustedError as e:
        await update_debtor(db, user_id, debtor_id, {"estado": debtor.get("estado", "pendiente")})
        raise HTTPException(402, str(e))

    from cobranza.minutes import call_status_kwargs
    twilio_client = TwilioClient(account_sid, auth_token)
    to_number = debtor.get("telefono")
    call = twilio_client.calls.create(
        to=to_number, from_=from_number,
        url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
        record=True,
        recording_status_callback=f"{webhook_url}/api/cobranza/voice/recording-callback",
        recording_status_callback_method="POST",
        **call_status_kwargs(),
    )
    call_sid = call.sid
    logger.info("[llamar-ahora] Twilio call %s -> %s", call_sid, to_number)

    # Insert mapping IMMEDIATELY so webhook/WS handler finds it
    await db.cobranza_calls_in_progress.insert_one({
        "call_sid": call_sid, "user_id": user_id,
        "debtor_id": debtor_id, "debtor_name": debtor.get("nombre"),
        "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
    })
    await update_debtor(db, user_id, debtor_id, {"vapi_call_id": call_sid})

    return {"ok": True, "call_sid": call_sid, "message": "Llamada iniciada (Pipecat)"}
