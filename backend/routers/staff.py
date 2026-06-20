import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field

from auth import get_current_user, require_staff
from database import (
    get_db, get_all_users, get_client_summary, get_runs_by_user, get_leads_by_user,
    save_campaign, get_campaigns_by_user, get_client_profile, upsert_client_profile,
    sync_user_root_onboarding_from_profile, get_user_root_onboarding,
    get_ideal_leads, get_rejected_leads, get_user_by_id,
)
from pipeline_helpers import _normalize_agent_configs, _build_runtime_agents
from services.notifications import send_whatsapp_text
import state

logger = logging.getLogger(__name__)

router = APIRouter()

_PIPELINE_REGISTRY = [
    {"name": "Buscador",  "description": "Descubre empresas por web search"},
    {"name": "Scraper",   "description": "Extrae datos del sitio web"},
    {"name": "Analista",  "description": "Califica y genera expediente"},
    {"name": "Redactor",  "description": "Genera borrador de email personalizado"},
]

VALID_SOURCES = {"google_maps", "secop_adjudicados", "secop_licitaciones"}


class SaveClientProfileRequest(BaseModel):
    business_summary: str = ""
    personality_prompt: str = ""
    campaign: dict = Field(default_factory=dict)
    agents: list = Field(default_factory=list)


class WelcomeEmailRequest(BaseModel):
    password: str
    agents: list
    campaign: dict
    business_summary: str = ""
    login_url: str = "http://localhost:5173"


class ClientSourcesRequest(BaseModel):
    fuentes_habilitadas: list[str]
    notification_channel: str = "web"
    wa_phone_number: Optional[str] = None
    wa_phone_id: Optional[str] = None
    wa_token: Optional[str] = None


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/api/staff/stats")
async def staff_get_stats(_staff: dict = Depends(require_staff)):
    from database import get_all_client_summaries
    db = get_db()
    users = await get_all_users()
    clients = [u for u in users if u["role"] == "client"]
    client_ids = [u["id"] for u in clients]
    total_leads_count, total_approved_count, total_runs_count, total_checkpoint_count = await asyncio.gather(
        db.leads.count_documents({}),
        db.leads.count_documents({"hitl_status": "approved"}),
        db.runs.count_documents({}),
        db.leads.count_documents({"estado": "checkpoint"}),
    )
    running_tasks = state.hive_adapter._runs if state.hive_adapter else {}
    active_run_ids = {uid for uid, task in running_tasks.items() if not task.done()}
    active_runs = len(active_run_ids)
    summaries = await get_all_client_summaries(client_ids) if client_ids else {}
    per_client = []
    for u in clients:
        uid = u["id"]
        s = summaries.get(uid, {})
        per_client.append({
            "client_id": uid,
            "client_email": u.get("email", ""),
            "total_leads": s.get("total_leads", 0),
            "approved_leads": s.get("approved_leads", 0),
            "total_runs": s.get("total_runs", 0),
            "active_runs": 1 if uid in active_run_ids else 0,
            "last_run_at": s.get("last_run_at"),
            "last_run_status": s.get("last_run_status"),
        })
    return {
        "global": {
            "total_clients": len(clients),
            "total_leads": total_leads_count,
            "total_approved": total_approved_count,
            "total_checkpoint": total_checkpoint_count,
            "total_runs": total_runs_count,
            "active_runs": active_runs,
        },
        "per_client": per_client,
    }


@router.get("/api/staff/agents/active")
async def staff_get_active_agents(_staff: dict = Depends(require_staff)):
    running_ids = {uid for uid, task in state.hive_adapter._runs.items() if not task.done()} if state.hive_adapter else set()
    per_client_active = [{"client_id": uid, "status": "running", "agents": _PIPELINE_REGISTRY} for uid in running_ids]
    return {"pipeline_registry": _PIPELINE_REGISTRY, "per_client_active": per_client_active}


# ── Clients ───────────────────────────────────────────────────────────────────

@router.get("/api/staff/clients")
async def staff_get_clients(_staff: dict = Depends(require_staff)):
    users = await get_all_users()
    return [u for u in users if u["role"] == "client"]


@router.get("/api/staff/clients/{client_id}")
async def staff_get_client_detail(client_id: str, _staff: dict = Depends(require_staff)):
    summary = await get_client_summary(client_id)
    runs = await get_runs_by_user(client_id)
    user_root_onboarding = await get_user_root_onboarding(client_id)
    profile = await get_client_profile(client_id)
    runtime_agents = _build_runtime_agents(profile)
    db = get_db()
    voice_doc = await db.company_voice.find_one({"user_id": client_id}, {"cobranza_enabled": 1})
    cobranza_enabled = bool((voice_doc or {}).get("cobranza_enabled", False))
    return {**summary, "runs": runs, "user_root_onboarding": user_root_onboarding, "runtime_pipeline_agents": len(runtime_agents), "cobranza_enabled": cobranza_enabled}


@router.get("/api/staff/clients/{client_id}/leads")
async def staff_get_client_leads(client_id: str, _staff: dict = Depends(require_staff)):
    return await get_leads_by_user(client_id, limit=200)


@router.post("/api/staff/clients/{client_id}/campaigns")
async def staff_save_client_campaign(client_id: str, campaign: dict, _staff: dict = Depends(require_staff)):
    campaign.setdefault("llm_analista", "openrouter/anthropic/claude-haiku-3")
    campaign.setdefault("llm_redactor", "openrouter/openai/gpt-5.4-2026-03-05")
    return {"campaign_id": await save_campaign(client_id, campaign)}


@router.get("/api/staff/clients/{client_id}/campaigns")
async def staff_get_client_campaigns(client_id: str, _staff: dict = Depends(require_staff)):
    return await get_campaigns_by_user(client_id)


@router.get("/api/staff/clients/{client_id}/runs")
async def staff_get_client_runs(client_id: str, _staff: dict = Depends(require_staff)):
    return await get_runs_by_user(client_id)


@router.post("/api/staff/clients/{client_id}/profile")
async def staff_save_client_profile(client_id: str, request: SaveClientProfileRequest, _staff: dict = Depends(require_staff)):
    normalized_agents = _normalize_agent_configs(request.agents, request.campaign or {}, request.personality_prompt)
    await upsert_client_profile(client_id, {"business_summary": request.business_summary, "personality_prompt": request.personality_prompt, "campaign": request.campaign or {}, "agents": normalized_agents})
    return {"ok": True, "agents_stored": len(normalized_agents)}


@router.get("/api/staff/clients/{client_id}/profile")
async def staff_get_client_profile(client_id: str, _staff: dict = Depends(require_staff)):
    profile = await get_client_profile(client_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return profile


@router.post("/api/staff/clients/{client_id}/profile/sync-user-root")
async def staff_sync_profile_to_user_root(client_id: str, _staff: dict = Depends(require_staff)):
    synced = await sync_user_root_onboarding_from_profile(client_id)
    if not synced:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return {"ok": True, "synced_user_id": client_id}


@router.post("/api/staff/clients/{client_id}/send-welcome")
async def send_welcome_to_client(client_id: str, request: WelcomeEmailRequest, _staff: dict = Depends(require_staff)):
    from mailer import send_welcome_email, send_staff_summary
    if not os.getenv("MAILERSEND_API_KEY"):
        raise HTTPException(status_code=503, detail="MAILERSEND_API_KEY not configured")
    user = await get_user_by_id(client_id)
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")
    client_email = user["email"]
    try:
        await send_welcome_email(client_email=client_email, client_password=request.password, agents=request.agents, campaign=request.campaign, business_summary=request.business_summary, login_url=request.login_url)
    except Exception as e:
        logger.warning("[send-welcome] error for %s: %s", client_email, e)
        return {"ok": False, "sent_to": client_email, "warning": str(e)}
    staff_email = os.getenv("MAILERSEND_STAFF_EMAIL")
    if staff_email:
        asyncio.create_task(send_staff_summary(staff_email=staff_email, client_email=client_email, business_summary=request.business_summary, agents=request.agents, campaign=request.campaign))
    return {"ok": True, "sent_to": client_email}


@router.get("/api/staff/clients/{client_id}/learning")
async def staff_client_learning(client_id: str, _staff: dict = Depends(require_staff)):
    api_key = os.getenv("OPENAI_API_KEY")
    ideal, rejected = await asyncio.gather(get_ideal_leads(client_id), get_rejected_leads(client_id))
    patterns = []
    if len(ideal) >= 3 and api_key:
        from learning import detect_patterns
        patterns = await detect_patterns(client_id, api_key)
    return {"ideal_count": len(ideal), "rejected_count": len(rejected), "patterns": patterns}


@router.post("/api/staff/clients/{target_user_id}/sources")
async def update_client_sources(target_user_id: str, request: ClientSourcesRequest, _staff: dict = Depends(require_staff)):
    invalid = [s for s in request.fuentes_habilitadas if s not in VALID_SOURCES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid sources: {invalid}. Valid values: {sorted(VALID_SOURCES)}")
    update_fields = {"fuentes_habilitadas": request.fuentes_habilitadas, "notification_channel": request.notification_channel}
    if request.wa_phone_number is not None:
        update_fields["wa_phone_number"] = request.wa_phone_number
    if request.wa_phone_id is not None:
        update_fields["wa_phone_id"] = request.wa_phone_id
    if request.wa_token is not None:
        update_fields["wa_token"] = request.wa_token
    db = get_db()
    prev = await db.company_voice.find_one({"user_id": target_user_id}) or {}
    prev_phone = prev.get("wa_phone_number", "")
    await db.company_voice.update_one({"user_id": target_user_id}, {"$set": update_fields}, upsert=True)
    new_phone = request.wa_phone_number
    if new_phone and new_phone != prev_phone and request.notification_channel in ("whatsapp", "both"):
        asyncio.create_task(send_whatsapp_text(new_phone, "Hola! Soy el asistente de Landa. A partir de ahora recibiras notificaciones de tus leads por aqui."))
    return {"status": "ok", "user_id": target_user_id, "fuentes_habilitadas": request.fuentes_habilitadas, "notification_channel": request.notification_channel}


# ── WA Config ─────────────────────────────────────────────────────────────────

@router.get("/api/staff/wa-config/{phone}")
async def get_wa_config(phone: str, _staff=Depends(require_staff)):
    from database import get_wa_bot_config
    return await get_wa_bot_config(phone)


@router.post("/api/staff/wa-config/{phone}")
async def save_wa_config(phone: str, body: dict = Body(...), _staff=Depends(require_staff)):
    from database import set_wa_bot_flags
    await set_wa_bot_flags(phone, body.get("bots", {}))
    return {"ok": True}


# ── Activate Bot ──────────────────────────────────────────────────────────────

@router.post("/api/staff/activate-bot/{user_id}", dependencies=[Depends(require_staff)])
async def activate_bot_secop(user_id: str):
    db = get_db()
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe")
    if not user.get("wa_phone_number"):
        raise HTTPException(status_code=400, detail="Usuario no tiene telefono WhatsApp asignado.")
    now = datetime.now(timezone.utc)
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": {"has_bot_secop": True, "bot_mode": "legacy", "bot_enabled_at": now.isoformat() + "Z"}})
    await db.whatsapp_agents.update_one({"phone_number": user["wa_phone_number"]}, {"$set": {"activo": True}}, upsert=False)
    return {"ok": True, "user_id": user_id, "email": user["email"], "wa_phone_number": user["wa_phone_number"], "has_bot_secop": True, "message": "Bot SECOP activado correctamente"}


# ── Cobranza toggle ───────────────────────────────────────────────────────────

@router.post("/api/staff/clients/{client_id}/cobranza/enable", status_code=200)
async def staff_enable_cobranza(client_id: str, _staff=Depends(require_staff)):
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.company_voice.update_one({"user_id": client_id}, {"$set": {"cobranza_enabled": True, "cobranza_enabled_at": now, "updated_at": now}, "$setOnInsert": {"user_id": client_id, "created_at": now}}, upsert=True)
    return {"ok": True, "client_id": client_id, "cobranza_enabled": True}


@router.post("/api/staff/clients/{client_id}/cobranza/disable", status_code=200)
async def staff_disable_cobranza(client_id: str, _staff=Depends(require_staff)):
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.company_voice.update_one({"user_id": client_id}, {"$set": {"cobranza_enabled": False, "updated_at": now}})
    return {"ok": True, "client_id": client_id, "cobranza_enabled": False}


# ── Tenant provisioning (one POST = one fully-configured client) ────────────────

class VoicePersonaModel(BaseModel):
    """Layer 2 of the 3-layer voice prompt. All free-text, NO 2000-char cap."""
    agent_name: Optional[str] = None
    company_name: Optional[str] = None
    company_brand: Optional[str] = None
    tono: Optional[str] = None
    greeting_template: Optional[str] = None
    greeting_template_no_name: Optional[str] = None
    pitch_template: Optional[str] = None
    business_rules: Optional[str] = None
    objection_handling: Optional[str] = None
    forbidden: Optional[str] = None


class ProvisionTenantRequest(BaseModel):
    # Account
    email: str
    password: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = "CO"
    # Voice agent identity (Layer 2)
    voice_persona: VoicePersonaModel = Field(default_factory=VoicePersonaModel)
    # Feature flags
    enable_cobranza: bool = True
    enable_voice: bool = True
    # Optional SoftSeguros credentials (encrypted at rest)
    softseguros_username: Optional[str] = None
    softseguros_password: Optional[str] = None


@router.post("/api/staff/tenants/provision", status_code=201)
async def staff_provision_tenant(
    request: ProvisionTenantRequest,
    _staff=Depends(require_staff),
):
    """
    Provision a complete client in a SINGLE request: creates the user account,
    sets its voice persona (Layer 2 of the voice prompt), enables modules, and
    optionally stores SoftSeguros credentials. Staff-only.

    Idempotent on email: if the user already exists, it is reused (persona/flags
    are still applied), so re-running the same curl updates config rather than
    erroring.
    """
    from auth import hash_password
    from database import get_user_by_email, create_user
    from cobranza.tenant_config import set_voice_persona, toggle_module

    db = get_db()
    now = datetime.now(timezone.utc)
    email = request.email.strip().lower()

    # ── Account: reuse if present, else create ───────────────────────────────
    existing = await get_user_by_email(email)
    if existing:
        user_id = str(existing["id"])
        created = False
    else:
        user = await create_user(
            email=email,
            hashed_password=hash_password(request.password),
            role="client",
            full_name=request.full_name,
            company_name=request.company_name,
            phone=request.phone,
            country=request.country,
        )
        user_id = str(user["id"])
        created = True

    # ── Layer 2 persona ──────────────────────────────────────────────────────
    persona = request.voice_persona.model_dump(exclude_none=True)
    if persona:
        await set_voice_persona(user_id, persona)

    # ── Module flags ─────────────────────────────────────────────────────────
    await toggle_module(user_id, "voice", request.enable_voice)
    if request.enable_cobranza:
        await db.company_voice.update_one(
            {"user_id": user_id},
            {"$set": {"cobranza_enabled": True, "cobranza_enabled_at": now, "updated_at": now},
             "$setOnInsert": {"user_id": user_id, "created_at": now}},
            upsert=True,
        )

    # ── Optional SoftSeguros credentials ─────────────────────────────────────
    softseguros_configured = False
    if request.softseguros_username and request.softseguros_password:
        try:
            from softseguros import credentials as _ss_credentials
            await _ss_credentials.save_credentials(
                db, user_id, request.softseguros_username, request.softseguros_password,
            )
            softseguros_configured = True
        except Exception as exc:
            logger.error("[provision] softseguros creds failed for %s: %s", user_id, exc)

    logger.info("[provision] tenant %s (created=%s) email=%s persona=%s cobranza=%s",
                user_id, created, email, persona.get("agent_name"), request.enable_cobranza)

    return {
        "ok": True,
        "created": created,
        "user_id": user_id,
        "email": email,
        "cobranza_enabled": request.enable_cobranza,
        "voice_enabled": request.enable_voice,
        "persona_set": bool(persona),
        "softseguros_configured": softseguros_configured,
    }
