import os
import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

from auth import get_current_user, require_staff, hash_password
from database import (
    get_db, get_user_by_email, create_user, save_campaign,
    upsert_client_profile, get_knowledge_sources, discard_onboarding_draft,
)
from onboarding import chat_turn
from pipeline_helpers import _normalize_agent_configs

logger = logging.getLogger(__name__)

router = APIRouter()


class OnboardClientRequest(BaseModel):
    email: str
    password: str
    campaign: dict
    agents: list
    system_prompt_analista: str = ""
    business_summary: str = ""
    wa_phone_number: Optional[str] = None
    wa_name: Optional[str] = None
    wa_company: Optional[str] = None


class OnboardChatRequest(BaseModel):
    messages: list


class SaveConversationRequest(BaseModel):
    messages: list = []
    text: str = ""


@router.post("/api/staff/onboard/discard/{client_id}")
async def discard_onboarding_data(client_id: str, _staff: dict = Depends(require_staff)):
    result = await discard_onboarding_draft(client_id)
    return {"ok": True, **result}


@router.post("/api/staff/onboard/chat/{client_id}")
async def onboard_chat_turn(client_id: str, request: OnboardChatRequest, _staff: dict = Depends(require_staff)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    reply = await chat_turn(request.messages, api_key)
    return {"reply": reply}


@router.post("/api/staff/onboard/save-conversation/{client_id}")
async def save_onboarding_conversation(client_id: str, request: SaveConversationRequest, _staff: dict = Depends(require_staff)):
    from rag import ingest_document
    if request.text.strip():
        transcript = request.text.strip()
    else:
        lines = []
        for msg in request.messages:
            role = "Staff" if msg.get("role") == "user" else "Reina"
            lines.append(f"{role}: {msg.get('content', '')}")
        transcript = "\n\n".join(lines)
    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcripcion vacia")
    await ingest_document(client_id, transcript, "reunion_inicial.txt", "conversation")
    return {"ok": True, "chars": len(transcript)}


@router.post("/api/staff/onboard/propose/{client_id}")
async def propose_client_config(client_id: str, _staff: dict = Depends(require_staff)):
    from queen_proposal import generate_proposal
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    try:
        return await generate_proposal(client_id, api_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail="Invalid request data")


@router.get("/api/staff/onboard/debug-knowledge/{client_id}")
async def debug_onboard_knowledge(client_id: str, _staff: dict = Depends(require_staff)):
    from rag import get_all_knowledge_text
    knowledge_text = await get_all_knowledge_text(client_id)
    sources = await get_knowledge_sources(client_id)
    source_counts: dict[str, int] = {}
    chunk_counts: dict[str, int] = {}
    for s in sources:
        st = str(s.get("source_type", "desconocido"))
        source_counts[st] = source_counts.get(st, 0) + 1
        chunk_counts[st] = chunk_counts.get(st, 0) + int(s.get("chunk_count", 0) or 0)
    return {"client_id": client_id, "source_counts": source_counts, "chunk_counts": chunk_counts, "sources": sources, "knowledge_text": knowledge_text}


@router.post("/api/staff/onboard/ensure-client")
async def ensure_onboard_client(body: dict = Body(...), _staff: dict = Depends(require_staff)):
    email = (body.get("email") or "").strip()
    password = (body.get("password") or "").strip()
    if not email or not password:
        raise HTTPException(status_code=422, detail="Email y contrasena requeridos")
    existing = await get_user_by_email(email)
    if existing:
        if existing.get("role") != "client":
            raise HTTPException(status_code=409, detail="Ese email ya existe pero no es de tipo cliente.")
        return {"id": existing["id"], "email": existing["email"], "role": existing.get("role", "client"), "created": False}
    from pymongo.errors import DuplicateKeyError
    hashed = hash_password(password)
    try:
        created = await create_user(email, hashed, role="client")
    except DuplicateKeyError:
        existing = await get_user_by_email(email)
        return {"id": existing["id"], "email": existing["email"], "role": existing.get("role", "client"), "created": False}
    return {"id": created["id"], "email": created["email"], "role": "client", "created": True}


@router.post("/api/staff/onboard/create-client", status_code=201)
async def create_onboarded_client(request: OnboardClientRequest, _staff: dict = Depends(require_staff)):
    from pymongo.errors import DuplicateKeyError
    from datetime import datetime, timezone
    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Este email ya esta registrado")
    hashed = hash_password(request.password)
    try:
        user = await create_user(request.email, hashed, role="client")
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Este email ya esta registrado")
    campaign_id = await save_campaign(user["id"], request.campaign)
    normalized_agents = _normalize_agent_configs(request.agents, request.campaign or {}, request.system_prompt_analista)
    await upsert_client_profile(user["id"], {"business_summary": request.business_summary, "personality_prompt": request.system_prompt_analista, "campaign": request.campaign or {}, "agents": normalized_agents})
    db = get_db()
    await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"has_bot_secop": False, "bot_mode": None}})
    response = {"user_id": user["id"], "email": user["email"], "campaign_id": campaign_id, "message": "Cliente creado y campana configurada"}
    if request.wa_phone_number and request.wa_name and request.wa_company:
        try:
            from database import upsert_whatsapp_agent
            twilio_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
            await upsert_whatsapp_agent({"phone_number": request.wa_phone_number, "nombre_asesor": request.wa_name, "empresa": request.wa_company, "twilio_from": twilio_from, "cliente_id": user["id"], "activo": False, "bot_mode": "legacy"})
            await db.users.update_one({"_id": ObjectId(user["id"])}, {"$set": {"wa_phone_number": request.wa_phone_number}})
            response["wa_phone_number"] = request.wa_phone_number
            response["message"] += " + Agente WhatsApp configurado (activacion pendiente)"
        except Exception as e:
            response["wa_warning"] = str(e)
    return response
