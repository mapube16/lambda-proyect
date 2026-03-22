"""
Isomorph Office - Backend Server
FastAPI server with WebSocket support for real-time agent visualization
"""
import os
import json
import asyncio
from typing import Dict, Optional
from contextlib import asynccontextmanager
from dotenv import load_dotenv

load_dotenv()  # Must be before any module that reads env vars at import time

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Show Hive framework + our adapter logs
for _logger in ("hive_adapter", "hive_llm", "hive_tools", "hive_graph",
                 "framework.graph.event_loop_node", "framework.graph.executor"):
    logging.getLogger(_logger).setLevel(logging.INFO)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, HTTPException, Depends, Query, status, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import DuplicateKeyError
from jose import JWTError, jwt
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, require_staff, SECRET_KEY, ALGORITHM
)
from database import (
    init_db, get_db, get_user_by_email, create_user,
    save_campaign, get_active_campaign, get_campaigns_by_user,
    create_run, update_run_status, get_runs_by_user,
    save_lead, get_leads_by_run, get_leads_by_user, update_lead_hitl,
    seed_users, get_all_users, get_user_by_id, get_client_summary,
    get_knowledge_sources, delete_knowledge_source, delete_knowledge_by_user,
    get_ideal_leads, get_rejected_leads,
    upsert_client_profile, get_client_profile,
    discard_onboarding_draft,
    sync_user_root_onboarding_from_profile,
    get_user_root_onboarding,
    get_prospecting_excluded_domains,
    upsert_whatsapp_agent, get_whatsapp_agent, list_whatsapp_agents, delete_whatsapp_agent,
)
from models import (
    Agent, AgentState, AgentRole,
    CreateAgentRequest, TaskRequest, AgentResponse,
    UserCreate, Token
)
from orchestrator import HiveOrchestrator
from onboarding import chat_turn
from landa.scheduler import start_scheduler, shutdown_scheduler

# WebSocket connection manager — keyed by user_id for tenant isolation
class ConnectionManager:
    def __init__(self):
        # Keyed by user_id (str). Phase 1: last-connection-wins for same user.
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket

    def disconnect(self, user_id: str):
        self.active_connections.pop(user_id, None)

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to a specific user only — core tenant isolation method."""
        ws = self.active_connections.get(user_id)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(user_id)

    async def broadcast(self, message: dict):
        """Legacy broadcast — sends to ALL users. Keep for orchestrator compatibility (Phase 2 will remove)."""
        disconnected = []
        for uid, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(uid)
        for uid in disconnected:
            self.disconnect(uid)


manager = ConnectionManager()
orchestrator: HiveOrchestrator = None
hive_adapter = None


def _build_runtime_agents(profile: Optional[dict]) -> list[dict]:
    from hive_graph import PIPELINE_AGENTS as DEFAULT_PIPELINE_AGENTS

    agents = (profile or {}).get("agents") or []
    if not agents:
        return DEFAULT_PIPELINE_AGENTS

    allowed_roles = {"coder", "researcher", "writer", "reviewer", "planner"}
    role_alias = {
        "whatsapp_sender": "writer",
    }

    runtime_agents: list[dict] = []
    for idx, agent in enumerate(agents):
        raw_role = str(agent.get("role") or "").strip().lower()
        normalized_role = role_alias.get(raw_role, raw_role)
        if normalized_role not in allowed_roles:
            normalized_role = "reviewer"

        runtime_agents.append({
            "id": str(agent.get("id") or f"agent-{idx + 1:03d}"),
            "name": str(agent.get("name") or f"Agente {idx + 1}"),
            "role": normalized_role,
            "state": "idle",
            "palette": idx % 6,
            "current_tool": None,
            "tool_status": None,
            "seat_id": None,
            "is_subagent": False,
            "parent_agent_id": None,
        })

    return runtime_agents or DEFAULT_PIPELINE_AGENTS


def _resolve_agent_model(role: str, campaign: dict) -> str:
    if role == "reviewer":
        return str(campaign.get("llm_analista") or "openai/gpt-4.1-nano")
    if role == "writer":
        return str(campaign.get("llm_redactor") or "openai/gpt-4.1-nano")
    return "tooling-only"


def _normalize_agent_configs(agents: list, campaign: dict, personality_prompt: str) -> list[dict]:
    role_to_responsibility = {
        "researcher": "Descubrir empresas objetivo por industria y ciudad",
        "planner": "Extraer señales clave del sitio web y preparar contexto",
        "reviewer": "Calificar fit B2B y decidir aprobación/rechazo",
        "writer": "Redactar outreach personalizado según hallazgos",
        "whatsapp_sender": "Enviar y gestionar outreach por WhatsApp",
    }

    normalized: list[dict] = []
    for agent in agents or []:
        role = str(agent.get("role") or "")
        persona = str(agent.get("persona") or "")

        if role == "reviewer":
            prompt_text = personality_prompt or persona
            prompt_source = "onboarding.system_prompt_analista"
        elif role == "writer":
            prompt_text = "backend/prospector.py::_motor_scoring_prompt"
            prompt_source = "backend.prospector"
        else:
            prompt_text = persona
            prompt_source = "onboarding.agent.persona"

        normalized.append({
            "id": str(agent.get("id") or ""),
            "name": str(agent.get("name") or ""),
            "role": role,
            "channel": str(agent.get("channel") or "email"),
            "model": _resolve_agent_model(role, campaign),
            "responsibility": role_to_responsibility.get(role, "Responsabilidad definida por onboarding"),
            "persona": persona,
            "prompt": prompt_text,
            "prompt_source": prompt_source,
        })
    return normalized


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, orchestrator, and HiveAdapter on startup"""
    global orchestrator, hive_adapter
    await init_db()
    from auth import hash_password as _hash
    await seed_users([
        {"email": "staff@isomorph.com",   "hashed_password": _hash("isomorph2026"), "role": "staff"},
        {"email": "dpg.seguros@gmail.com", "hashed_password": _hash("seguros2026"),  "role": "client"},
    ])

    # Legacy orchestrator (kept for non-prospect agent ops)
    api_key = os.getenv("OPENAI_API_KEY", "demo-key")
    orchestrator = HiveOrchestrator(api_key)
    orchestrator.set_broadcast_callback(manager.broadcast)

    # HiveAdapter: real multi-agent engine for prospecting
    from hive_adapter import HiveAdapter
    hive_adapter = HiveAdapter(send_to_user_callback=manager.send_to_user)

    await start_scheduler()
    print("Isomorph Office started!")
    yield
    shutdown_scheduler()
    print("Shutting down...")


app = FastAPI(
    title="Isomorph Office",
    description="Real-time AI agent visualization backend",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:5176", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ REST API Endpoints ============

@app.get("/")
async def root():
    return {"message": "Isomorph Office API", "status": "running"}


@app.post("/auth/register", status_code=201)
async def register(user: UserCreate):
    """Register a new user. Returns {id, email} — never returns password."""
    existing = await get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    try:
        created = await create_user(user.email, hashed)
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    return {"id": created["id"], "email": created["email"]}


@app.post("/auth/login")
async def login(user: UserCreate):
    """Authenticate user, return signed JWT. Returns 401 on bad credentials."""
    db_user = await get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": str(db_user["id"]), "role": db_user.get("role", "client")})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": str(db_user["id"]),
        "role": db_user.get("role", "client"),
        "email": db_user["email"],
    }


@app.get("/api/diagnostics/maps")
async def diagnostics_maps(current_user: dict = Depends(get_current_user)):
    """Runtime diagnostics for Google Maps usage in discovery flow."""
    raw_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
    key = raw_key.strip()
    configured = bool(key)

    providers = ["google_maps", "bing", "duckduckgo"] if configured else ["bing", "duckduckgo"]
    fallback = ["bing", "duckduckgo"]
    key_preview = f"***{key[-4:]}" if configured and len(key) >= 4 else ("***" if configured else None)

    return {
        "google_maps_configured": configured,
        "google_maps_key_preview": key_preview,
        "discovery_providers": providers,
        "fallback_if_maps_fails": fallback,
        "user_role": current_user.get("role", "client"),
    }


@app.get("/api/agents")
async def get_agents(current_user: dict = Depends(get_current_user)):
    """Get all agents"""
    return orchestrator.get_all_agents()


@app.post("/api/agents", response_model=Agent)
async def create_agent(request: CreateAgentRequest, current_user: dict = Depends(get_current_user)):
    """Create a new agent"""
    agent = await orchestrator.create_agent(
        name=request.name,
        role=request.role,
        instructions=request.instructions
    )
    return agent


@app.get("/api/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, current_user: dict = Depends(get_current_user)):
    """Get a specific agent"""
    agent = orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@app.delete("/api/agents")
async def delete_all_agents(current_user: dict = Depends(get_current_user)):
    """Delete all agents"""
    agent_ids = list(orchestrator.agents.keys())
    for agent_id in agent_ids:
        await orchestrator.remove_agent(agent_id)
    await manager.broadcast({"type": "initial_state", "agents": []})
    return {"status": "cleared", "count": len(agent_ids)}


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, current_user: dict = Depends(get_current_user)):
    """Delete an agent"""
    agent = orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    await orchestrator.remove_agent(agent_id)

    # Broadcast removal
    await manager.broadcast({
        "type": "agent_removed",
        "agent_id": agent_id
    })

    return {"status": "deleted", "agent_id": agent_id}


@app.post("/api/agents/{agent_id}/task", response_model=AgentResponse)
async def run_task(agent_id: str, request: TaskRequest, current_user: dict = Depends(get_current_user)):
    """Send a task to an agent"""
    agent = orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = await orchestrator.run_agent(agent_id, request.task)
        return AgentResponse(agent_id=agent_id, message=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ WebSocket Endpoint ============

@app.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket endpoint for real-time updates.
    Requires valid JWT as ?token= query param. Validated before accept.
    Reject with WS_1008_POLICY_VIOLATION if token is missing or invalid.
    """
    # Validate BEFORE accept — reject before handshake if invalid
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect(websocket, user_id=user_id)

    # Send runtime agents from onboarding profile (fallback to default 4)
    profile = await get_client_profile(user_id)
    runtime_agents = _build_runtime_agents(profile)
    await websocket.send_json({
        "type":   "initial_state",
        "agents": runtime_agents,
    })

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "create_agent":
                try:
                    agent = await orchestrator.create_agent(
                        name=data.get("name", "Agent"),
                        role=AgentRole(data.get("role", "coder"))
                    )
                    agent_data = agent.model_dump()
                    if 'created_at' in agent_data and agent_data['created_at']:
                        agent_data['created_at'] = agent_data['created_at'].isoformat()
                    await manager.broadcast({
                        "type": "agent_created",
                        "agent": agent_data
                    })
                except Exception as e:
                    print(f"Error creating agent: {e}")
                    import traceback
                    traceback.print_exc()

            elif data.get("type") == "run_task":
                agent_id = data.get("agent_id")
                task = data.get("task")
                if agent_id and task:
                    asyncio.create_task(
                        orchestrator.run_agent(agent_id, task)
                    )

    except WebSocketDisconnect:
        manager.disconnect(user_id)


# ============ Prospecting ============

from pydantic import BaseModel as _BaseModel, Field as _Field

class ProspectRequest(_BaseModel):
    campaign: dict = {}
    max_results: int = 20


@app.post("/api/prospect")
async def prospect(
    request: ProspectRequest,
    current_user: dict = Depends(get_current_user)
):
    """
    Run B2B prospecting pipeline.
    Agents discover companies via web search, scrape and analyze each one.
    Results are broadcast via WebSocket as they arrive and persisted to MongoDB.
    """
    user_id = str(current_user["user_id"])
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    # Use active campaign from DB if none provided in request
    campaign = request.campaign
    active = None
    if not campaign:
        active = await get_active_campaign(user_id)
        if active:
            # Strip internal DB fields before passing to pipeline
            campaign = {k: v for k, v in active.items()
                        if k not in ("_id", "user_id", "is_active", "created_at")}

    # Load client-specific personality prompt (set by Queen during onboarding)
    profile = await get_client_profile(user_id)
    personality_prompt = (profile or {}).get("personality_prompt", "")
    runtime_agents = _build_runtime_agents(profile)
    exclusions = await get_prospecting_excluded_domains(user_id)

    # Create a run document before launching the pipeline
    campaign_id = active["_id"] if (not request.campaign and active) else ""
    run_id = await create_run(
        user_id=user_id,
        campaign_id=campaign_id,
        max_results=min(request.max_results, 50),
    )

    async def _finalize_on_complete():
        """Wait for HiveAdapter task to finish, then update run status."""
        task = hive_adapter._runs.get(user_id)
        if task:
            try:
                await task
                await update_run_status(run_id, status="complete")
            except Exception as exc:
                print(f"[prospect] finalize error: {exc}")
                await update_run_status(run_id, status="error")

    await hive_adapter.start_run(
        user_id=user_id,
        inputs={
            "campaign": campaign,
            "max_results": min(request.max_results, 50),
            "personality_prompt": personality_prompt,
            "runtime_agents": runtime_agents,
            "excluded_domains": exclusions.get("excluded_domains", []),
        },
        run_id=run_id,
        save_lead=save_lead,
    )
    asyncio.create_task(_finalize_on_complete())

    return {
        "status": "running",
        "run_id": run_id,
        "message": "Campaña iniciada — los agentes están buscando empresas",
        "exclusion_stats": exclusions.get("stats", {}),
    }


# ============ Onboarding Chat ============

class ChatRequest(_BaseModel):
    messages: list[dict]  # [{role: "user"|"assistant", content: "..."}]


async def _build_campaign_chat_context(user_id: str) -> str:
    active_campaign, profile, ideal_leads, rejected_leads = await asyncio.gather(
        get_active_campaign(user_id),
        get_client_profile(user_id),
        get_ideal_leads(user_id),
        get_rejected_leads(user_id),
    )

    rag_context = ""
    try:
        from rag import query_rag
        rag_context = await query_rag(
            user_id,
            "contexto de negocio, propuesta de valor, cliente ideal, restricciones y tono comercial",
            top_k=4,
        )
    except Exception:
        rag_context = ""

    campaign_lines: list[str] = []
    if active_campaign:
        for key in (
            "industria_objetivo",
            "ciudad_objetivo",
            "dolor_operativo",
            "solucion_ofrecida",
            "software_clave",
            "jerarquia_decisores",
        ):
            value = str(active_campaign.get(key) or "").strip()
            if value:
                campaign_lines.append(f"- {key}: {value}")

    profile_lines: list[str] = []
    if profile:
        summary = str(profile.get("business_summary") or "").strip()
        if summary:
            profile_lines.append(f"- resumen_negocio: {summary[:900]}")
        personality = str(profile.get("personality_prompt") or "").strip()
        if personality:
            profile_lines.append(f"- personalidad_guardada: {personality[:900]}")
        agents = profile.get("agents") or []
        if agents:
            roles = [str(a.get("role") or "") for a in agents]
            profile_lines.append(f"- agentes_configurados: {', '.join([r for r in roles if r])}")

    learning_lines: list[str] = [
        f"- leads_aprobados_historicos: {len(ideal_leads)}",
        f"- leads_rechazados_historicos: {len(rejected_leads)}",
    ]
    if rejected_leads:
        recent_reasons = [str((r or {}).get("reason") or "").strip() for r in rejected_leads[:5]]
        recent_reasons = [r for r in recent_reasons if r]
        if recent_reasons:
            learning_lines.append(f"- razones_rechazo_recurrentes: {' | '.join(recent_reasons[:3])}")

    sections: list[str] = []
    if campaign_lines:
        sections.append("CAMPAÑA_ACTIVA\n" + "\n".join(campaign_lines))
    if profile_lines:
        sections.append("PERFIL_ONBOARDING\n" + "\n".join(profile_lines))
    if learning_lines:
        sections.append("SEÑALES_DE_FEEDBACK\n" + "\n".join(learning_lines))
    if rag_context.strip():
        sections.append("MEMORIA_RAG_RELEVANTE\n" + rag_context[:2500])

    return "\n\n".join(sections)[:7000]


@app.post("/api/chat")
async def chat(
    request: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Conversational campaign configurator.
    Streams one assistant turn. When all 8 variables are collected,
    the reply contains CAMPAIGN_READY: {json}.
    Auto-saves the campaign to MongoDB when CAMPAIGN_READY is detected.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    user_id = str(current_user["user_id"])
    context = await _build_campaign_chat_context(user_id)
    reply = await chat_turn(request.messages, api_key, context=context)

    # Auto-save campaign when CAMPAIGN_READY is detected in the reply
    if "CAMPAIGN_READY:" in reply:
        try:
            marker = "CAMPAIGN_READY:"
            idx = reply.index(marker) + len(marker)
            # Extract the JSON blob that follows the marker
            raw_json = reply[idx:].strip()
            # Handle potential trailing text after the JSON object
            brace_start = raw_json.index("{")
            brace_end = raw_json.rindex("}") + 1
            campaign_data = json.loads(raw_json[brace_start:brace_end])
            await save_campaign(user_id, campaign_data)
        except Exception as e:
            # Non-fatal: log and continue
            print(f"[chat] Failed to auto-save campaign: {e}")

    return {"reply": reply}


# ============ Campaigns ============

@app.post("/api/campaigns")
async def save_campaign_endpoint(
    campaign: dict,
    current_user: dict = Depends(get_current_user),
):
    """Save/update the active campaign for the current user.
    Accepts the 8 campaign vars plus optional llm_analista and llm_redactor.
    Defaults: llm_analista='openrouter/anthropic/claude-haiku-3',
              llm_redactor='openrouter/openai/gpt-4o-mini'.
    """
    user_id = str(current_user["user_id"])
    campaign.setdefault("llm_analista", "openrouter/anthropic/claude-haiku-3")
    campaign.setdefault("llm_redactor", "openrouter/openai/gpt-4o-mini")
    campaign_id = await save_campaign(user_id, campaign)
    return {"campaign_id": campaign_id}


@app.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    """Get active campaign for current user. Returns null (not 404) when none exists."""
    user_id = str(current_user["user_id"])
    campaign = await get_active_campaign(user_id)
    return campaign  # None serializes as JSON null — frontend checks for null


# ============ Runs ============

@app.get("/api/runs")
async def get_runs(current_user: dict = Depends(get_current_user)):
    """Get run history for current user."""
    user_id = str(current_user["user_id"])
    runs = await get_runs_by_user(user_id)
    return runs


@app.get("/api/runs/{run_id}/leads")
async def get_run_leads(run_id: str, current_user: dict = Depends(get_current_user)):
    """Get leads for a specific run (tenant-safe)."""
    user_id = str(current_user["user_id"])
    leads = await get_leads_by_run(run_id, user_id)
    return leads


# ============ Leads HITL ============

@app.patch("/api/leads/{lead_id}/approve")
async def approve_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Approve a lead (HITL decision). Also embeds lead into ideal_leads corpus and fires outreach."""
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "approved")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    # Fetch leads once — shared by learning embed and outreach tasks
    leads = await get_leads_by_user(user_id, limit=200)
    lead_data = next((l for l in leads if l["_id"] == lead_id), None)
    # Fire-and-forget: embed approved lead for learning (non-blocking)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and lead_data:
        from learning import embed_and_store_approved_lead
        asyncio.create_task(embed_and_store_approved_lead(user_id, lead_id, lead_data))
    # Phase 13: Fire-and-forget outreach on approval
    if lead_data:
        canal = lead_data.get("canal_elegido", "email")
        from outreach_agent import run_outreach
        asyncio.create_task(run_outreach(lead_id, user_id, canal, intento=1))
    return {"status": "approved", "lead_id": lead_id}


@app.patch("/api/leads/{lead_id}/reject")
async def reject_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Reject a lead (HITL decision). Stores rejection in rejected_leads and transitions to nurturing."""
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "rejected")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    # Store rejection reason for learning
    leads = await get_leads_by_user(user_id, limit=200)
    lead_data = next((l for l in leads if l["_id"] == lead_id), None)
    if lead_data:
        from learning import store_rejected_lead
        asyncio.create_task(store_rejected_lead(user_id, lead_id, lead_data))
    # Phase 13: Transition rejected lead to nurturing lifecycle
    from bson import ObjectId as _ObjectId
    from landa.state_machine import update_lead_estado
    db = get_db()
    lead_doc = await db.leads.find_one({"_id": _ObjectId(lead_id)})
    if lead_doc and lead_doc.get("estado") == "checkpoint":
        await db.leads.update_one(
            {"_id": _ObjectId(lead_id)},
            {"$set": {"motivo_nurturing": "rechazado_humano"}},
        )
        try:
            await update_lead_estado(lead_id, user_id, "nurturing")
        except ValueError:
            pass  # Not in a valid state for this transition — skip gracefully
    return {"status": "rejected", "lead_id": lead_id}


@app.get("/api/leads")
async def get_user_leads(current_user: dict = Depends(get_current_user)):
    """Get all leads for current user (recent first)."""
    user_id = str(current_user["user_id"])
    leads = await get_leads_by_user(user_id)
    return leads


class SendEmailRequest(_BaseModel):
    subject_index: int = 0   # Which subject line from email_asuntos (0 or 1)


@app.post("/api/leads/{lead_id}/send-email")
async def send_lead_email(
    lead_id: str,
    request: SendEmailRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Send the AI-generated email draft to a lead's decisor via MailerSend.
    Requires MAILERSEND_API_KEY + MAILERSEND_FROM_EMAIL env vars.
    """
    from mailer import send_lead_outreach
    from database import db

    if not os.getenv("MAILERSEND_API_KEY"):
        raise HTTPException(status_code=503, detail="MAILERSEND_API_KEY not configured")

    user_id = str(current_user["user_id"])
    lead = await db.leads.find_one({"_id": lead_id, "user_id": user_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    exp       = lead.get("expediente_json") or {}
    borradores = exp.get("borradores") or {}
    decisor   = exp.get("decisor") or {}

    to_email = decisor.get("email") or ""
    if not to_email:
        raise HTTPException(status_code=422, detail="El lead no tiene email del decisor")

    body = borradores.get("email_cuerpo") or ""
    if not body:
        raise HTTPException(status_code=422, detail="El lead no tiene borrador de correo")

    subjects = borradores.get("email_asuntos") or []
    idx = min(request.subject_index, len(subjects) - 1) if subjects else 0
    subject = subjects[idx] if subjects else "Propuesta de colaboración"

    # Get campaign context for sender identity
    campaign = await db.campaigns.find_one({"user_id": user_id}, sort=[("created_at", -1)])
    camp = campaign or {}
    sender_name    = camp.get("nombre_remitente", "")
    sender_empresa = camp.get("empresa_remitente", "")
    reply_to       = camp.get("email_remitente", "")

    try:
        status = await send_lead_outreach(
            to_email=to_email,
            to_name=decisor.get("nombre") or "",
            subject=subject,
            body_text=body,
            sender_name=sender_name,
            sender_empresa=sender_empresa,
            reply_to_email=reply_to,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error de envío: {e}")

    await db.leads.update_one({"_id": lead_id}, {"$set": {"email_sent": True}})
    return {"ok": True, "to": to_email, "subject": subject, "status": status}


class WelcomeEmailRequest(_BaseModel):
    password: str            # Plain-text password to include in welcome email
    agents: list             # Agent list from the approved proposal
    campaign: dict           # Campaign vars
    business_summary: str = ""
    login_url: str = "http://localhost:5173"


@app.post("/api/staff/clients/{client_id}/send-welcome")
async def send_welcome_to_client(
    client_id: str,
    request: WelcomeEmailRequest,
    _staff: dict = Depends(require_staff),
):
    """
    Send the onboarding welcome email to a newly configured client.
    Includes their credentials, agent team, and campaign summary.
    Also sends a configuration summary to MAILERSEND_STAFF_EMAIL if set.
    """
    from mailer import send_welcome_email, send_staff_summary
    from database import get_user_by_id

    if not os.getenv("MAILERSEND_API_KEY"):
        raise HTTPException(status_code=503, detail="MAILERSEND_API_KEY not configured")

    user = await get_user_by_id(client_id)
    if not user:
        raise HTTPException(status_code=404, detail="Client not found")

    client_email = user["email"]

    try:
        await send_welcome_email(
            client_email=client_email,
            client_password=request.password,
            agents=request.agents,
            campaign=request.campaign,
            business_summary=request.business_summary,
            login_url=request.login_url,
        )
    except RuntimeError as e:
        logging.getLogger("main").warning("[send-welcome] runtime error for %s: %s", client_email, e)
        return {"ok": False, "sent_to": client_email, "warning": str(e)}
    except Exception as e:
        logging.getLogger("main").warning("[send-welcome] provider error for %s: %s", client_email, e)
        return {"ok": False, "sent_to": client_email, "warning": f"Error de envío: {e}"}

    # Non-blocking: also notify staff
    staff_email = os.getenv("MAILERSEND_STAFF_EMAIL")
    if staff_email:
        asyncio.create_task(send_staff_summary(
            staff_email=staff_email,
            client_email=client_email,
            business_summary=request.business_summary,
            agents=request.agents,
            campaign=request.campaign,
        ))

    return {"ok": True, "sent_to": client_email}


# ============ NIT Enricher / Radar Pólizas ============

class NitEnrichRequest(_BaseModel):
    nit: str


class RadarRequest(_BaseModel):
    sector: str
    ciudad: Optional[str] = None
    max_procesos: int = 10
    max_proponentes: int = 20


@app.post("/api/secop/enrich-nit")
async def enrich_nit_endpoint(
    request: NitEnrichRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Enriquece un NIT colombiano con datos de RUES, SECOP, Supersociedades y web.
    Retorna expediente completo listo para que una aseguradora ofrezca póliza de cumplimiento.
    """
    from nit_enricher import enrich_nit
    result = await enrich_nit(request.nit)
    return result


@app.post("/api/secop/radar-polizas")
async def radar_polizas_endpoint(
    request: RadarRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Radar de pólizas de cumplimiento:
    - Detecta licitaciones ABIERTAS en SECOP por sector
    - Identifica proponentes probables (por historial de contratos)
    - Enriquece cada proponente con NIT → expediente completo
    Retorna leads listos para que la aseguradora llame hoy mismo.
    """
    from secop_radar import build_poliza_leads
    result = await build_poliza_leads(
        keyword=request.sector,
        ciudad=request.ciudad,
        max_procesos=request.max_procesos,
        max_proponentes=request.max_proponentes,
    )
    return result


@app.get("/api/secop/procesos-abiertos")
async def procesos_abiertos_endpoint(
    sector: str,
    ciudad: Optional[str] = None,
    limit: int = 20,
    current_user: dict = Depends(get_current_user),
):
    """Lista licitaciones abiertas en SECOP para un sector dado."""
    from secop_radar import fetch_open_processes
    return await fetch_open_processes(sector, ciudad, limit)


# ============ Health check ============

@app.get("/api/health")
async def health():
    return {"ok": True}


# ============ WhatsApp Webhook (Twilio) ============

@app.post("/api/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    """
    Recibe mensajes entrantes de Twilio WhatsApp y los enruta al agente conversacional.
    Configurar en Twilio Console → Messaging → WhatsApp Sandbox → When a message comes in.
    URL: https://<tu-ngrok>.ngrok.io/api/whatsapp/webhook
    """
    form = await request.form()
    from_phone  = (form.get("From") or "").replace("whatsapp:", "")
    from_twilio = form.get("To") or os.getenv("TWILIO_FROM_NUMBER", "")
    body        = form.get("Body") or ""

    if not from_phone or not body:
        return {"ok": False, "error": "Missing From or Body"}

    _wa_log = logging.getLogger("whatsapp_webhook")
    _wa_log.info("[WA] from=%s body=%r twilio=%s", from_phone, body, from_twilio)

    # Cargar config del agente desde MongoDB (fallback a env vars si no existe)
    from whatsapp_agent import handle_inbound_message
    agent_config = await get_whatsapp_agent(from_phone) or {}

    async def _run():
        try:
            await handle_inbound_message(from_phone, body, from_twilio, agent_config)
        except Exception as e:
            _wa_log.error("[WA] handle error: %s", e, exc_info=True)

    asyncio.create_task(_run())

    # Twilio espera respuesta rápida — el agente responde de forma asíncrona vía API
    return Response(content="", media_type="text/xml")


# ============ WhatsApp Agents CRUD ============

class WhatsAppAgentConfig(_BaseModel):
    phone_number: str                        # número del asesor e.g. "+573123528153"
    twilio_from: str                         # número Twilio e.g. "whatsapp:+14155238886"
    nombre_asesor: str
    empresa: str
    telefono_asesor: Optional[str] = None
    sectores: list[str] = []
    ciudad_default: Optional[str] = None
    cliente_id: Optional[str] = None        # ObjectId del usuario en la plataforma
    activo: bool = True


@app.post("/api/whatsapp-agents", dependencies=[Depends(require_staff)])
async def create_whatsapp_agent(config: WhatsAppAgentConfig):
    """Crea o actualiza la configuración de un agente WhatsApp para un asesor."""
    doc = await upsert_whatsapp_agent(config.model_dump())
    return doc


@app.get("/api/whatsapp-agents", dependencies=[Depends(require_staff)])
async def list_agents(cliente_id: Optional[str] = None):
    """Lista todos los agentes WhatsApp configurados."""
    return await list_whatsapp_agents(cliente_id)


@app.get("/api/whatsapp-agents/{phone_number}", dependencies=[Depends(require_staff)])
async def get_agent(phone_number: str):
    doc = await get_whatsapp_agent(phone_number)
    if not doc:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return doc


@app.delete("/api/whatsapp-agents/{phone_number}", dependencies=[Depends(require_staff)])
async def remove_agent(phone_number: str):
    ok = await delete_whatsapp_agent(phone_number)
    if not ok:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return {"ok": True}


# ============ Demo Mode ============

@app.post("/api/demo/simulate")
async def simulate_agent_activity(agent_id: str, current_user: dict = Depends(get_current_user)):
    """Simulate agent activity for demo purposes"""
    agent = orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Simulate a work cycle
    async def simulate():
        states = [
            (AgentState.THINKING, None, "Processing..."),
            (AgentState.TOOL_USE, "read_file", "Reading config.py"),
            (AgentState.TOOL_USE, "write_file", "Writing output.py"),
            (AgentState.THINKING, None, "Analyzing..."),
            (AgentState.TOOL_USE, "run_code", "Executing tests"),
            (AgentState.WAITING, None, "Done!")
        ]

        for state, tool, status in states:
            await orchestrator.update_agent_state(agent_id, state, tool, status)
            await asyncio.sleep(2)

    asyncio.create_task(simulate())
    return {"status": "simulation_started", "agent_id": agent_id}


# ============ Staff Endpoints ============

@app.get("/api/staff/clients")
async def staff_get_clients(_staff: dict = Depends(require_staff)):
    """List all client users, including newly created accounts with no runs yet."""
    users = await get_all_users()
    clients = [u for u in users if u["role"] == "client"]
    return clients


@app.get("/api/staff/clients/{client_id}")
async def staff_get_client_detail(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """Full detail for one client: stats + campaign + runs."""
    summary = await get_client_summary(client_id)
    runs = await get_runs_by_user(client_id)
    user_root_onboarding = await get_user_root_onboarding(client_id)
    profile = await get_client_profile(client_id)
    runtime_agents = _build_runtime_agents(profile)
    return {
        **summary,
        "runs": runs,
        "user_root_onboarding": user_root_onboarding,
        "runtime_pipeline_agents": len(runtime_agents),
    }


@app.get("/api/staff/clients/{client_id}/leads")
async def staff_get_client_leads(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    leads = await get_leads_by_user(client_id, limit=200)
    return leads


@app.get("/api/staff/clients/{client_id}/campaigns")
async def staff_get_client_campaigns(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    campaigns = await get_campaigns_by_user(client_id)
    return campaigns


@app.get("/api/staff/clients/{client_id}/runs")
async def staff_get_client_runs(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    runs = await get_runs_by_user(client_id)
    return runs


class SaveClientProfileRequest(_BaseModel):
    business_summary: str = ""
    personality_prompt: str = ""
    campaign: dict = _Field(default_factory=dict)
    agents: list = _Field(default_factory=list)


@app.post("/api/staff/clients/{client_id}/profile")
async def staff_save_client_profile(
    client_id: str,
    request: SaveClientProfileRequest,
    _staff: dict = Depends(require_staff),
):
    normalized_agents = _normalize_agent_configs(
        request.agents,
        request.campaign or {},
        request.personality_prompt,
    )
    await upsert_client_profile(client_id, {
        "business_summary": request.business_summary,
        "personality_prompt": request.personality_prompt,
        "campaign": request.campaign or {},
        "agents": normalized_agents,
    })
    return {"ok": True, "agents_stored": len(normalized_agents)}


@app.get("/api/staff/clients/{client_id}/profile")
async def staff_get_client_profile(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    profile = await get_client_profile(client_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return profile


@app.post("/api/staff/clients/{client_id}/profile/sync-user-root")
async def staff_sync_profile_to_user_root(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """
    Backfill users.root onboarding fields from client_profiles for existing clients.
    Useful for users onboarded before root mirroring was introduced.
    """
    synced = await sync_user_root_onboarding_from_profile(client_id)
    if not synced:
        raise HTTPException(status_code=404, detail="Client profile not found")
    return {"ok": True, "synced_user_id": client_id}


@app.get("/api/client/profile")
async def get_my_client_profile(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    profile = await get_client_profile(user_id)
    return profile


# ============ Leads Chat (Phase 10) ============

class LeadsChatRequest(_BaseModel):
    messages: list[dict]


@app.post("/api/chat/leads")
async def leads_chat(
    request: LeadsChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Conversational lead feedback chat.
    Queen reads the user's recent leads + active campaign as context,
    answers questions in Spanish, and extracts structured intent per turn.
    Returns {reply: str, intent: {type, payload, proposal}}.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    user_id = str(current_user["user_id"])
    from chat_leads import leads_chat_turn
    result = await leads_chat_turn(request.messages, user_id, api_key)
    return result


# ============ RAG — Document Upload ============

from fastapi import UploadFile, File
from typing import List as _List

class UrlIngestRequest(_BaseModel):
    user_id: str | None = None
    url: str | None = None
    urls: list[str] = _Field(default_factory=list)
    source_type: str = "url_empresa"


@app.post("/api/staff/clients/{client_id}/knowledge/upload")
async def upload_knowledge_docs(
    client_id: str,
    files: _List[UploadFile] = File(...),
    _staff: dict = Depends(require_staff),
):
    """
    Upload one or more PDF, DOCX, or plain-text files for a client's knowledge base.
    Each file is chunked, embedded, and stored in MongoDB independently.
    """
    from rag import extract_text, ingest_document

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    results = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            results.append({"filename": file.filename, "error": "empty file"})
            continue
        try:
            text = extract_text(file_bytes, file.filename or "upload", file.content_type or "")
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
            continue
        if not text.strip():
            results.append({"filename": file.filename, "error": "no readable text"})
            continue
        chunk_count = await ingest_document(
            user_id=client_id,
            text=text,
            filename=file.filename or "upload",
            source_type="file",
        )
        results.append({"filename": file.filename, "chunks_stored": chunk_count})
    return results


@app.post("/api/staff/clients/{client_id}/knowledge/url")
async def ingest_knowledge_url(
    client_id: str,
    request: UrlIngestRequest,
    _staff: dict = Depends(require_staff),
):
    """Fetch one or many URLs and ingest their text content into the client's knowledge base."""
    from rag import fetch_url_text, ingest_document

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    source_type = (request.source_type or "url_empresa").strip().lower()
    if source_type not in {"url_empresa", "url_competencia", "url"}:
        raise HTTPException(status_code=422, detail="source_type inválido")

    urls: list[str] = []
    if request.url and request.url.strip():
        urls.append(request.url.strip())
    urls.extend([u.strip() for u in (request.urls or []) if isinstance(u, str) and u.strip()])

    # De-duplicate while preserving order
    deduped_urls: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u not in seen:
            seen.add(u)
            deduped_urls.append(u)

    if not deduped_urls:
        raise HTTPException(status_code=422, detail="Debes enviar al menos una URL")

    from urllib.parse import urlparse, urlunparse
    import hashlib

    def canonicalize_url(raw: str) -> str:
        parsed = urlparse(raw)
        # Keep scheme/netloc/path; drop tracking-heavy query/fragment for storage key stability
        clean = parsed._replace(query="", fragment="")
        return urlunparse(clean)

    def build_filename(raw_url: str) -> str:
        canonical = canonicalize_url(raw_url)
        parsed = urlparse(canonical)
        host = (parsed.netloc or "url").replace(":", "_")
        path = (parsed.path or "/").strip("/").replace("/", "_")
        base = f"{host}__{path}" if path else host
        digest = hashlib.sha1(raw_url.encode("utf-8")).hexdigest()[:10]
        # Keep filename compact and index-safe
        return f"{base[:140]}__{digest}"

    results = []
    for target_url in deduped_urls:
        try:
            text = await fetch_url_text(target_url)
        except Exception as e:
            results.append({"url": target_url, "error": f"Cannot fetch URL: {e}"})
            continue

        if not text.strip():
            results.append({"url": target_url, "error": "No readable text found at URL"})
            continue

        # Keep filename unique per URL while avoiding very long indexed values.
        filename = build_filename(target_url)
        chunk_count = await ingest_document(
            user_id=client_id,
            text=text,
            filename=filename,
            source_type=source_type,
        )
        results.append({
            "url": target_url,
            "url_canonical": canonicalize_url(target_url),
            "filename": filename,
            "source_type": source_type,
            "chunks_stored": chunk_count,
        })

    stored = [r for r in results if not r.get("error")]
    if not stored:
        first_error = results[0].get("error") if results else "No se pudo procesar ninguna URL"
        raise HTTPException(status_code=422, detail=first_error)

    return {
        "total_urls": len(deduped_urls),
        "stored_urls": len(stored),
        "results": results,
    }


@app.get("/api/staff/clients/{client_id}/knowledge")
async def get_knowledge_sources_endpoint(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """List all uploaded knowledge sources for a client."""
    sources = await get_knowledge_sources(client_id)
    return sources


@app.delete("/api/staff/clients/{client_id}/knowledge/{filename}")
async def delete_knowledge_source_endpoint(
    client_id: str,
    filename: str,
    _staff: dict = Depends(require_staff),
):
    """Remove a specific source from the client's knowledge base."""
    deleted = await delete_knowledge_source(client_id, filename)
    return {"deleted_chunks": deleted}


@app.delete("/api/staff/clients/{client_id}/knowledge")
async def clear_knowledge_endpoint(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """Clear ALL knowledge for a client (full reset)."""
    deleted = await delete_knowledge_by_user(client_id)
    return {"deleted_chunks": deleted}


@app.post("/api/staff/onboard/discard/{client_id}")
async def discard_onboarding_data(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """
    Discard onboarding draft data when the staff user closes onboarding without approval.
    Clears uploaded knowledge/profile and removes draft client account if it has no activity.
    """
    result = await discard_onboarding_draft(client_id)
    return {"ok": True, **result}


# ============ Queen Onboarding Proposal ============

class OnboardClientRequest(_BaseModel):
    email: str
    password: str
    campaign: dict  # The approved proposal's campaign vars
    agents: list    # The approved proposal's agent list
    system_prompt_analista: str = ""
    business_summary: str = ""


class OnboardChatRequest(_BaseModel):
    messages: list  # [{role, content}] — full conversation history


class SaveConversationRequest(_BaseModel):
    messages: list = []  # [{role, content}] — legacy chat format
    text: str = ""       # plain meeting transcript (preferred)


@app.post("/api/staff/onboard/chat/{client_id}")
async def onboard_chat_turn(
    client_id: str,
    request: OnboardChatRequest,
    _staff: dict = Depends(require_staff),
):
    """
    Run one turn of the business-discovery conversation for a new client.
    Uses onboarding.py SYSTEM_PROMPT (campaign configurator persona).
    The transcript is NOT saved here — call save-conversation when done.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    reply = await chat_turn(request.messages, api_key)
    return {"reply": reply}


@app.post("/api/staff/onboard/save-conversation/{client_id}")
async def save_onboarding_conversation(
    client_id: str,
    request: SaveConversationRequest,
    _staff: dict = Depends(require_staff),
):
    """
    Persist the meeting transcript into the client's RAG knowledge base.
    Stored as 'reunion_inicial.txt' so the Queen can read it during proposal generation.
    Accepts either plain text (preferred) or legacy messages[] format.
    """
    from rag import ingest_document

    if request.text.strip():
        transcript = request.text.strip()
    else:
        # Legacy: format chat messages as readable transcript
        lines = []
        for msg in request.messages:
            role = "Staff" if msg.get("role") == "user" else "Reina"
            lines.append(f"{role}: {msg.get('content', '')}")
        transcript = "\n\n".join(lines)

    if not transcript.strip():
        raise HTTPException(status_code=422, detail="Transcripción vacía")

    await ingest_document(client_id, transcript, "reunion_inicial.txt", "conversation")
    return {"ok": True, "chars": len(transcript)}


@app.post("/api/staff/onboard/propose/{client_id}")
async def propose_client_config(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """
    Queen analyses all uploaded docs for client_id and returns a full proposal:
    agents, system_prompt_analista, campaign variables, business summary.
    """
    from queen_proposal import generate_proposal

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")

    try:
        proposal = await generate_proposal(client_id, api_key)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return proposal


@app.get("/api/staff/onboard/debug-knowledge/{client_id}")
async def debug_onboard_knowledge(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """
    Debug endpoint: returns the exact hierarchical knowledge_text that will be sent
    to the Queen proposal step, plus source breakdown for verification.
    """
    from rag import get_all_knowledge_text

    knowledge_text = await get_all_knowledge_text(client_id)
    sources = await get_knowledge_sources(client_id)

    source_counts: dict[str, int] = {}
    chunk_counts: dict[str, int] = {}
    for s in sources:
        st = str(s.get("source_type", "desconocido"))
        source_counts[st] = source_counts.get(st, 0) + 1
        chunk_counts[st] = chunk_counts.get(st, 0) + int(s.get("chunk_count", 0) or 0)

    return {
        "client_id": client_id,
        "source_counts": source_counts,
        "chunk_counts": chunk_counts,
        "sources": sources,
        "knowledge_text": knowledge_text,
    }


@app.post("/api/staff/onboard/create-client", status_code=201)
async def create_onboarded_client(
    request: OnboardClientRequest,
    _staff: dict = Depends(require_staff),
):
    """
    Create a new client account and persist the approved campaign configuration.
    The account is ready to run prospecting immediately.
    """
    from pymongo.errors import DuplicateKeyError as _DupKey

    existing = await get_user_by_email(request.email)
    if existing:
        raise HTTPException(status_code=400, detail="Este email ya está registrado")

    hashed = hash_password(request.password)
    try:
        user = await create_user(request.email, hashed, role="client")
    except _DupKey:
        raise HTTPException(status_code=400, detail="Este email ya está registrado")

    # Save the approved campaign
    campaign_id = await save_campaign(user["id"], request.campaign)

    normalized_agents = _normalize_agent_configs(
        request.agents,
        request.campaign or {},
        request.system_prompt_analista,
    )
    await upsert_client_profile(user["id"], {
        "business_summary": request.business_summary,
        "personality_prompt": request.system_prompt_analista,
        "campaign": request.campaign or {},
        "agents": normalized_agents,
    })

    return {
        "user_id": user["id"],
        "email": user["email"],
        "campaign_id": campaign_id,
        "message": "Cliente creado y campaña configurada",
    }


# ============ Learning Loop (Phase 11) ============

@app.get("/api/learning/stats")
async def learning_stats(current_user: dict = Depends(get_current_user)):
    """Return counts of ideal + rejected leads stored for this user."""
    user_id = str(current_user["user_id"])
    ideal, rejected = await asyncio.gather(
        get_ideal_leads(user_id),
        get_rejected_leads(user_id),
    )
    return {
        "ideal_count": len(ideal),
        "rejected_count": len(rejected),
        "ready_for_patterns": len(ideal) >= 3,
    }


@app.get("/api/learning/patterns")
async def learning_patterns(current_user: dict = Depends(get_current_user)):
    """
    Analyse the ideal_leads corpus and return top-3 recurring patterns.
    Requires at least 3 approved leads. Returns [] otherwise.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    user_id = str(current_user["user_id"])
    from learning import detect_patterns
    patterns = await detect_patterns(user_id, api_key)
    return {"patterns": patterns}


@app.get("/api/staff/clients/{client_id}/learning")
async def staff_client_learning(
    client_id: str,
    _staff: dict = Depends(require_staff),
):
    """Return learning stats + patterns for a client (staff view)."""
    api_key = os.getenv("OPENAI_API_KEY")
    ideal, rejected = await asyncio.gather(
        get_ideal_leads(client_id),
        get_rejected_leads(client_id),
    )
    patterns = []
    if len(ideal) >= 3 and api_key:
        from learning import detect_patterns
        patterns = await detect_patterns(client_id, api_key)
    return {
        "ideal_count": len(ideal),
        "rejected_count": len(rejected),
        "patterns": patterns,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
