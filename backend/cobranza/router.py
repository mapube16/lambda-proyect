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

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from auth import get_current_user
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
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(get_current_user),
):
    """Paginated debtors for the authenticated user, filterable by estado or group."""
    user_id = str(current_user["user_id"])
    db = get_db()
    return await get_debtors(db, user_id, estado=estado, group=group, page=page, page_size=page_size)


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

    base = {"user_id": user_id}

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
        {"$match": {"user_id": user_id}},
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


# ── Campaign Pause / Resume ────────────────────────────────────────────────────

@router.post("/campaign/pause")
async def pause_campaign(current_user: dict = Depends(get_current_user)):
    """Pause the automated call campaign for this tenant."""
    user_id = str(current_user["user_id"])
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.cobranza_config.update_one(
        {"user_id": user_id},
        {"$set": {"campaign_paused": True, "campaign_paused_at": now, "updated_at": now}},
        upsert=True,
    )
    logger.info("[campaign] Paused for user %s", user_id)
    return {"ok": True, "campaign_paused": True}


@router.post("/campaign/resume")
async def resume_campaign(current_user: dict = Depends(get_current_user)):
    """Resume the automated call campaign for this tenant."""
    user_id = str(current_user["user_id"])
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.cobranza_config.update_one(
        {"user_id": user_id},
        {"$set": {"campaign_paused": False, "campaign_resumed_at": now, "updated_at": now}},
        upsert=True,
    )
    logger.info("[campaign] Resumed for user %s", user_id)
    return {"ok": True, "campaign_paused": False}


@router.get("/campaign/status")
async def campaign_status(current_user: dict = Depends(get_current_user)):
    """Return whether the automated campaign is currently paused."""
    user_id = str(current_user["user_id"])
    db = get_db()
    doc = await db.cobranza_config.find_one({"user_id": user_id}, {"campaign_paused": 1})
    paused = bool((doc or {}).get("campaign_paused", False))
    return {"campaign_paused": paused}


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

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        call = client.calls.create(
            to=to_number, from_=from_number,
            url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
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

    twilio_client = TwilioClient(account_sid, auth_token)
    to_number = debtor.get("telefono")
    call = twilio_client.calls.create(
        to=to_number, from_=from_number,
        url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
        record=True,
        recording_status_callback=f"{webhook_url}/api/cobranza/voice/recording-callback",
        recording_status_callback_method="POST",
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
