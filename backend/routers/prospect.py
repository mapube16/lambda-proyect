import os
import json
import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field

from auth import get_current_user
from database import (
    get_db, get_active_campaign, save_campaign, get_runs_by_user, get_leads_by_run,
    create_run, update_run_status, get_ideal_leads, get_rejected_leads,
    get_client_profile, get_prospecting_excluded_domains, save_lead,
    upsert_prospecting_knowledge, get_prospecting_knowledge, get_or_create_prospecting_knowledge,
)
from onboarding import chat_turn, extract_campaign_from_nl
from pipeline_helpers import _build_runtime_agents, _normalize_agent_configs
import state

logger = logging.getLogger(__name__)

router = APIRouter()


class ProspectRequest(BaseModel):
    campaign: dict = {}
    max_results: int = 20
    source_priority: str = "serper"


class ChatRequest(BaseModel):
    messages: list[dict]


class LeadsChatRequest(BaseModel):
    messages: list[dict]


class ApplyIntentRequest(BaseModel):
    intent_type: str
    payload: dict


class NLProspectRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class KnowledgeUpsertRequest(BaseModel):
    product_description: Optional[str] = None
    icp_summary: Optional[str] = None


# ── Prospecting ───────────────────────────────────────────────────────────────

@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    campaign = request.campaign
    active = None
    if not campaign:
        active = await get_active_campaign(user_id)
        if active:
            campaign = {k: v for k, v in active.items() if k not in ("_id", "user_id", "is_active", "created_at")}
    profile = await get_client_profile(user_id)
    personality_prompt = (profile or {}).get("personality_prompt", "")
    orch_agents = state.orchestrator.get_all_agents() if state.orchestrator else []
    if orch_agents:
        runtime_agents = [{"id": a.id, "name": a.name, "role": a.role.value, "state": "idle", "palette": a.palette, "current_tool": None} for a in orch_agents]
    else:
        runtime_agents = _build_runtime_agents(profile)
    exclusions = await get_prospecting_excluded_domains(user_id)
    campaign_id = active["_id"] if (not request.campaign and active) else ""

    import uuid
    run_id = str(uuid.uuid4())   # API owns run_id — UUID4 (NOT ObjectId; ObjectId breaks msgpack — RESEARCH Pitfall 7)
    await create_run(user_id=user_id, campaign_id=campaign_id,
                     max_results=min(request.max_results, 50), run_id=run_id)

    # Strip any ObjectId / _id from campaign before enqueue (msgpack cannot serialize ObjectId)
    safe_campaign = {k: v for k, v in (campaign or {}).items() if k != "_id"}

    await state.arq_pool.enqueue_job(
        "run_prospecting_job",
        run_id=run_id,
        user_id=user_id,
        campaign=safe_campaign,
        max_results=min(request.max_results, 50),
        personality_prompt=personality_prompt,
        runtime_agents=runtime_agents,
        excluded_domains=exclusions.get("excluded_domains", []),
        source_priority=request.source_priority,
        _job_id=run_id,   # dedupe — run_id as job id (RESEARCH Pattern 3)
    )
    return {
        "status": "queued",
        "run_id": run_id,
        "message": "Campaña encolada — los agentes comenzarán pronto",
        "exclusion_stats": exclusions.get("stats", {}),
    }


# ── Campaign Chat ─────────────────────────────────────────────────────────────

async def _build_campaign_chat_context(user_id: str) -> str:
    active_campaign, profile, ideal_leads, rejected_leads = await asyncio.gather(
        get_active_campaign(user_id), get_client_profile(user_id), get_ideal_leads(user_id), get_rejected_leads(user_id),
    )
    rag_context = ""
    try:
        from rag import query_rag
        rag_context = await query_rag(user_id, "contexto de negocio, propuesta de valor, cliente ideal, restricciones y tono comercial", top_k=4)
    except Exception:
        pass
    campaign_lines = [f"- {k}: {str(active_campaign.get(k) or '').strip()}" for k in ("industria_objetivo", "ciudad_objetivo", "dolor_operativo", "solucion_ofrecida", "software_clave", "jerarquia_decisores") if active_campaign and str(active_campaign.get(k) or "").strip()]
    profile_lines = []
    if profile:
        if profile.get("business_summary"):
            profile_lines.append(f"- resumen_negocio: {str(profile['business_summary'])[:900]}")
        if profile.get("personality_prompt"):
            profile_lines.append(f"- personalidad_guardada: {str(profile['personality_prompt'])[:900]}")
        if profile.get("agents"):
            roles = [str(a.get("role") or "") for a in profile["agents"]]
            profile_lines.append(f"- agentes_configurados: {', '.join(r for r in roles if r)}")
    learning_lines = [f"- leads_aprobados_historicos: {len(ideal_leads)}", f"- leads_rechazados_historicos: {len(rejected_leads)}"]
    if rejected_leads:
        recent_reasons = [str((r or {}).get("reason") or "").strip() for r in rejected_leads[:5]]
        recent_reasons = [r for r in recent_reasons if r]
        if recent_reasons:
            learning_lines.append(f"- razones_rechazo_recurrentes: {' | '.join(recent_reasons[:3])}")
    sections = []
    if campaign_lines:
        sections.append("=== CAMPAÑA ACTIVA ===\n" + "\n".join(campaign_lines))
    if profile_lines:
        sections.append("=== PERFIL DEL NEGOCIO ===\n" + "\n".join(profile_lines))
    if learning_lines:
        sections.append("=== HISTORIAL DE APRENDIZAJE ===\n" + "\n".join(learning_lines))
    if rag_context:
        sections.append(f"=== DOCUMENTOS DEL NEGOCIO ===\n{rag_context[:2000]}")
    return "\n\n".join(sections)


@router.post("/api/chat")
async def chat(request: ChatRequest, current_user: dict = Depends(get_current_user)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    user_id = str(current_user["user_id"])
    context = await _build_campaign_chat_context(user_id)
    reply = await chat_turn(request.messages, api_key, context=context)
    if "CAMPAIGN_READY:" in reply:
        try:
            marker = "CAMPAIGN_READY:"
            idx = reply.index(marker) + len(marker)
            raw_json = reply[idx:].strip()
            brace_start = raw_json.index("{")
            brace_end = raw_json.rindex("}") + 1
            campaign_data = json.loads(raw_json[brace_start:brace_end])
            await save_campaign(user_id, campaign_data)
        except Exception as e:
            logger.warning("[chat] Failed to auto-save campaign: %s", e)
    return {"reply": reply}


@router.post("/api/chat/leads")
async def leads_chat(request: LeadsChatRequest, current_user: dict = Depends(get_current_user)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    from chat_leads import leads_chat_turn
    return await leads_chat_turn(request.messages, str(current_user["user_id"]), api_key)


# ── Campaigns ─────────────────────────────────────────────────────────────────

@router.post("/api/campaigns")
async def save_campaign_endpoint(campaign: dict, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    campaign.setdefault("llm_analista", "openrouter/anthropic/claude-haiku-3")
    campaign.setdefault("llm_redactor", "openrouter/openai/gpt-5.4-2026-03-05")
    campaign_id = await save_campaign(user_id, campaign)
    return {"campaign_id": campaign_id}


@router.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    return await get_active_campaign(str(current_user["user_id"]))


# ── Runs ──────────────────────────────────────────────────────────────────────

@router.get("/api/runs")
async def get_runs(current_user: dict = Depends(get_current_user)):
    return await get_runs_by_user(str(current_user["user_id"]))


@router.get("/api/runs/{run_id}/report")
async def get_run_report(run_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    db = get_db()
    run = await db.runs.find_one({"run_id": run_id, "user_id": user_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {"run_id": run_id, "status": run.get("status"), "total_found": run.get("total_found", 0), "total_approved": run.get("total_approved", 0), "agent_logs": run.get("agent_logs", {})}


@router.get("/api/runs/{run_id}/leads")
async def get_run_leads(run_id: str, current_user: dict = Depends(get_current_user)):
    return await get_leads_by_run(run_id, str(current_user["user_id"]))


# ── Apply Chat Intent ─────────────────────────────────────────────────────────

@router.post("/api/campaign/apply-intent")
async def apply_campaign_intent(request: ApplyIntentRequest, current_user: dict = Depends(get_current_user)):
    from database import patch_active_campaign
    user_id = str(current_user["user_id"])
    t = request.intent_type
    p = request.payload
    if t == "refine_target":
        field = p.get("field", "").strip()
        value = p.get("value", "").strip()
        allowed = {"industria_objetivo", "ciudad_objetivo", "dolor_operativo", "solucion_ofrecida", "software_clave", "jerarquia_decisores", "sector_propio_cliente"}
        if not field or field not in allowed:
            raise HTTPException(status_code=400, detail=f"Campo no permitido: {field}")
        await patch_active_campaign(user_id, {field: value})
    elif t == "adjust_tone":
        tone = p.get("tone") or p.get("value", "").strip()
        if tone:
            await patch_active_campaign(user_id, {"tono_comercial": tone})
    elif t == "blacklist_company":
        company = p.get("company", "").strip()
        if company:
            from database import add_excluded_domain
            await add_excluded_domain(user_id, company)
    campaign = await get_active_campaign(user_id)
    return {"ok": True, "campaign": campaign}


# ── Client Profile ────────────────────────────────────────────────────────────

@router.get("/api/client/profile")
async def get_my_client_profile(current_user: dict = Depends(get_current_user)):
    return await get_client_profile(str(current_user["user_id"]))


# ── Learning ──────────────────────────────────────────────────────────────────

@router.get("/api/learning/stats")
async def learning_stats(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    ideal, rejected = await asyncio.gather(get_ideal_leads(user_id), get_rejected_leads(user_id))
    return {"ideal_count": len(ideal), "rejected_count": len(rejected), "ready_for_patterns": len(ideal) >= 3}


@router.get("/api/learning/patterns")
async def learning_patterns(current_user: dict = Depends(get_current_user)):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    from learning import detect_patterns
    patterns = await detect_patterns(str(current_user["user_id"]), api_key)
    return {"patterns": patterns}


# ── Diagnostics ───────────────────────────────────────────────────────────────

@router.get("/api/diagnostics/maps")
async def diagnostics_maps(current_user: dict = Depends(get_current_user)):
    key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    if not key:
        return {"status": "not_configured", "api_key_present": False}
    import httpx
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"https://maps.googleapis.com/maps/api/place/nearbysearch/json?location=4.711,-74.0721&radius=1000&type=restaurant&key={key}")
        data = resp.json()
        return {"status": data.get("status"), "api_key_present": True, "results_count": len(data.get("results", []))}
    except Exception as e:
        return {"status": "error", "api_key_present": True, "error": str(e)}


# ── NL Prospecting Chat (Phase 23) ────────────────────────────────────────────

def _build_nl_context(knowledge: dict) -> str:
    """Format prospecting_knowledge dict into a single context block for the system prompt.
    Caps signal lists at 20 items each and total context at 1500 chars (RESEARCH pitfall 3).
    """
    if not knowledge:
        return ""
    parts = []
    product = (knowledge.get("product_description") or "").strip()
    if product:
        parts.append(f"Producto: {product}")
    icp = (knowledge.get("icp_summary") or "").strip()
    if icp:
        parts.append(f"ICP: {icp}")
    approved = knowledge.get("approved_lead_signals") or []
    if approved:
        parts.append("Senales aprobadas:\n" + "\n".join(f"- {s}" for s in approved[:20]))
    rejected = knowledge.get("rejected_lead_signals") or []
    if rejected:
        parts.append("Senales rechazadas:\n" + "\n".join(f"- {s}" for s in rejected[:20]))
    blob = "\n\n".join(parts)
    return blob[:1500]


@router.post("/api/chat/prospect")
async def nl_prospect_chat(
    request: NLProspectRequest,
    current_user: dict = Depends(get_current_user),
):
    """Single-turn NL -> CAMPAIGN_READY extraction. Replaces multi-turn campaign form for v1."""
    user_id = str(current_user["user_id"])
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    knowledge = await get_or_create_prospecting_knowledge(user_id)
    context = _build_nl_context(knowledge)
    try:
        reply = await extract_campaign_from_nl(request.message, api_key, context=context)
    except Exception as e:
        logger.exception("[nl_prospect] extract failed: %s", e)
        raise HTTPException(status_code=502, detail="NL extraction failed")
    if "CAMPAIGN_READY:" in reply:
        try:
            marker = "CAMPAIGN_READY:"
            idx = reply.index(marker) + len(marker)
            raw_json = reply[idx:].strip()
            brace_start = raw_json.index("{")
            brace_end = raw_json.rindex("}") + 1
            campaign_data = json.loads(raw_json[brace_start:brace_end])
            # Strip _id if present (RESEARCH pitfall 1 — ObjectId msgpack guard)
            safe_campaign = {k: v for k, v in campaign_data.items() if k != "_id"}
            await save_campaign(user_id, safe_campaign)
            # Persist last_campaign_params for future context (fire-and-forget OK but sync is fine here)
            await upsert_prospecting_knowledge(user_id, {"last_campaign_params": safe_campaign})
            return {"status": "extracted", "campaign": safe_campaign}
        except Exception as e:
            logger.warning("[nl_prospect] parse failed: %s", e)
    return {"status": "needs_clarification", "reply": reply}


@router.get("/api/knowledge")
async def get_my_knowledge(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    doc = await get_or_create_prospecting_knowledge(user_id)
    # Return only the safe public fields
    return {
        "product_description": doc.get("product_description", ""),
        "icp_summary": doc.get("icp_summary", ""),
        "approved_lead_signals": doc.get("approved_lead_signals", []),
        "rejected_lead_signals": doc.get("rejected_lead_signals", []),
    }


@router.post("/api/knowledge")
async def upsert_my_knowledge(
    request: KnowledgeUpsertRequest,
    current_user: dict = Depends(get_current_user),
):
    user_id = str(current_user["user_id"])
    fields = {k: v for k, v in request.dict().items() if v is not None}
    if not fields:
        raise HTTPException(status_code=400, detail="No fields to update")
    await upsert_prospecting_knowledge(user_id, fields)
    return {"status": "ok"}
