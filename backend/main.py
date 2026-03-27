"""
Lambda Office - Backend Server
FastAPI server with WebSocket support for real-time agent visualization
"""
import os
import sys
# Add backend/ to sys.path so bare imports (from auth, from database, etc.) work
# when running from project root as: python -m uvicorn backend.main:app
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
                 "framework.graph.event_loop_node", "framework.graph.executor",
                 "wa_handler"):
    logging.getLogger(_logger).setLevel(logging.INFO)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, HTTPException, Depends, Query, status, Request, Body
from fastapi.responses import Response, FileResponse
from fastapi.staticfiles import StaticFiles
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
    save_lead, get_leads_by_run, get_leads_by_user, get_lead_by_id, update_lead_hitl,
    seed_users, get_all_users, get_user_by_id, get_client_summary,
    get_knowledge_sources, delete_knowledge_source, delete_knowledge_by_user,
    get_ideal_leads, get_rejected_leads,
    upsert_client_profile, get_client_profile,
    discard_onboarding_draft,
    sync_user_root_onboarding_from_profile,
    get_user_root_onboarding,
    get_prospecting_excluded_domains,
    upsert_whatsapp_agent, get_whatsapp_agent, list_whatsapp_agents, delete_whatsapp_agent,
    create_registration_request, get_all_registration_requests, update_registration_request_status,
    add_phone_to_user
)
from fastapi import APIRouter

from pydantic import BaseModel

from fastapi import FastAPI


# --- Lifespan context manager (debe ir antes de la app) ---
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB, orchestrator, and HiveAdapter on startup"""
    global orchestrator, hive_adapter
    await init_db()
    from auth import hash_password as _hash
    await seed_users([
        {"email": "staff@lambda.com",   "hashed_password": _hash("lambda2026"), "role": "staff"},
        {"email": "dpg.seguros@gmail.com", "hashed_password": _hash("seguros2026"),  "role": "client"},
    ])

    # Legacy orchestrator (kept for non-prospect agent ops)
    api_key = os.getenv("OPENAI_API_KEY", "demo-key")
    print("Isomorph Office started!")
    yield
    shutdown_scheduler()
    print("Shutting down...")

# --- Configuración de logging global para FastAPI/Uvicorn ---
import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger().setLevel(logging.INFO)

# --- Modelo para request de agregar teléfono ---
class AddPhoneRequest(BaseModel):
    phone: str
from models import (
    Agent, AgentState, AgentRole,
    CreateAgentRequest, TaskRequest, AgentResponse,
    UserCreate, Token, RegistrationRequest
)
from orchestrator import HiveOrchestrator
from onboarding import chat_turn
from landa.scheduler import start_scheduler, shutdown_scheduler
from landa.company_voice import get_or_create_company_voice

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


# ============ WhatsApp notification helpers (Phase 16 — WA-01) ============

async def send_whatsapp_text(phone: str, message: str) -> None:
    """Send a WhatsApp text message via Twilio REST API.

    Uses whatsapp_agent._send_whatsapp() pattern. Non-fatal — logs on failure.
    """
    import base64, httpx
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "")
    if not sid or not token or not from_number:
        logging.warning("[WA] Twilio creds not configured — skipping WA send")
        return
    wa_to = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"
    auth = "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={"Authorization": auth},
                data={"To": wa_to, "From": from_number, "Body": message},
            )
            if resp.status_code not in (200, 201):
                logging.error("[WA] Twilio send error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logging.error("[WA] send_whatsapp_text error: %s", e)


def _format_wa_notification(event: dict) -> str:
    """Format a WS event dict into a WhatsApp-friendly text message.

    Max 1600 chars. Plain text + emojis. No rich markdown.
    """
    event_type = event.get("type", "")
    empresa = event.get("empresa", "")
    if event_type == "lead_checkpoint":
        puntaje = event.get("puntaje", 0)
        return f"✅ Lead listo para revisión: {empresa} (puntaje: {puntaje}). Escribe 'ver leads' para revisarlos."
    elif event_type == "lead_handover":
        canal = event.get("canal", "email")
        return f"🤝 {empresa} respondió. Escribe 'ver oportunidad' para tomar el control. Canal: {canal}."
    elif event_type == "lead_archived":
        return f"📁 {empresa} fue archivado."
    else:
        return f"Actualización de Landa: {event_type}"


async def notify_user(user_id: str, event: dict) -> None:
    """Unified notification router — replaces direct send_to_user() calls.

    Reads notification_channel from company_voice and routes:
    - 'web' → WebSocket only
    - 'whatsapp' → WhatsApp only
    - 'both' → WebSocket + WhatsApp
    - missing → defaults to 'web' (Phase 15 fallback)
    """
    cv = await get_or_create_company_voice(user_id)
    channel = cv.get("notification_channel", "web")

    if channel in ("web", "both"):
        await manager.send_to_user(user_id, event)

    if channel in ("whatsapp", "both"):
        wa_number = cv.get("wa_phone_number")
        if wa_number:
            message = _format_wa_notification(event)
            await send_whatsapp_text(wa_number, message)


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
        {"email": "staff@lambda.com",   "hashed_password": _hash("lambda2026"), "role": "staff"},
        {"email": "dpg.seguros@gmail.com", "hashed_password": _hash("seguros2026"),  "role": "client"},
    ])

    # Legacy orchestrator (kept for non-prospect agent ops)
    api_key = os.getenv("OPENAI_API_KEY", "demo-key")
    orchestrator = HiveOrchestrator(api_key)
    orchestrator.set_broadcast_callback(manager.broadcast)
    await orchestrator.load_agents_from_db()

    # Seed default agents if office is empty
    if not orchestrator.get_all_agents():
        from models import AgentRole
        defaults = [
            ("Investigadora", AgentRole.RESEARCHER),
            ("Prospector",    AgentRole.PLANNER),
            ("Redactora",     AgentRole.WRITER),
            ("Analista",      AgentRole.REVIEWER),
        ]
        for name, role in defaults:
            await orchestrator.create_agent(name=name, role=role)
        print(f"Seeded {len(defaults)} default agent(s)")

    # HiveAdapter: real multi-agent engine for prospecting
    from hive_adapter import HiveAdapter
    hive_adapter = HiveAdapter(send_to_user_callback=manager.send_to_user)

    await start_scheduler()
    from landa.scheduler import scheduler as _cobr_scheduler
    from cobranza.campaign_scheduler import register_cobranza_jobs
    register_cobranza_jobs(_cobr_scheduler)
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
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============ REST API Endpoints ============

@app.get("/api/staff/wa-config/{phone}")
async def get_wa_config(phone: str, _staff=Depends(require_staff)):
    from database import get_wa_bot_config
    return await get_wa_bot_config(phone)

@app.post("/api/staff/wa-config/{phone}")
async def save_wa_config(phone: str, body: dict = Body(...), _staff=Depends(require_staff)):
    from database import set_wa_bot_flags
    await set_wa_bot_flags(phone, body.get("bots", {}))
    return {"ok": True}

@app.patch("/api/users/{user_id}/phones", status_code=200)
async def api_add_phone_to_user(user_id: str, req: AddPhoneRequest, current_user=Depends(get_current_user)):
    """Agrega un número a la lista de phones del usuario (sin duplicados)."""
    logging.info(f"[api_add_phone_to_user] PATCH /api/users/{user_id}/phones body={req.dict()} current_user={current_user}")
    if current_user["user_id"] != user_id and current_user.get("role") != "staff":
        logging.warning(f"[api_add_phone_to_user] No autorizado: current_user={current_user} user_id={user_id}")
        raise HTTPException(status_code=403, detail="No autorizado")
    ok = await add_phone_to_user(user_id, req.phone)
    if not ok:
        logging.error(f"[api_add_phone_to_user] Fallo al agregar teléfono: user_id={user_id} phone={req.phone}")
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    logging.info(f"[api_add_phone_to_user] Teléfono agregado: user_id={user_id} phone={req.phone}")
    return {"success": True, "added": req.phone}

@app.get("/api/health")
async def root():
    return {"message": "Lambda Office API", "status": "running"}


@app.post("/auth/register", status_code=201)
async def register(user: UserCreate):
    """Register a new user. Returns {id, email} — never returns password."""
    existing = await get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    try:
        created = await create_user(
            user.email, 
            hashed,
            role=user.role or "client",
            full_name=user.full_name,
            company_name=user.company_name,
            phone=user.phone,
            country=user.country,
        )
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


@app.post("/auth/google-login")
async def google_login(data: dict):
    """
    Authenticate user with Google OAuth token.
    Expects: { "token": "<google-jwt-token>" }
    """
    import urllib.request
    
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token requerido")
    
    try:
        # Verify Google token by making request to Google's tokeninfo endpoint
        # This validates the token is legitimate and gets user info
        url = f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={token}"
        with urllib.request.urlopen(url) as response:
            user_info = json.loads(response.read().decode())
        
        email = user_info.get("email")
        name = user_info.get("name", "")
        
        if not email:
            raise HTTPException(status_code=400, detail="Email no disponible en token de Google")
        
        # Check if user exists
        db_user = await get_user_by_email(email)
        
        if not db_user:
            # Create user if doesn't exist
            hashed_pw = hash_password("google_oauth_no_password_needed")
            try:
                db_user = await create_user(
                    email,
                    hashed_pw,
                    role="client",
                    full_name=name
                )
            except DuplicateKeyError:
                # User was just created by concurrent request, fetch it
                db_user = await get_user_by_email(email)
        
        # Create JWT token for our app
        token = create_access_token(data={"sub": str(db_user["id"]), "role": db_user.get("role", "client")})
        return {
            "access_token": token,
            "token_type": "bearer",
            "user_id": str(db_user["id"]),
            "role": db_user.get("role", "client"),
            "email": db_user["email"],
        }
    
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Error al validar token de Google: {str(e)}")


@app.post("/auth/register-request", status_code=202)
async def register_request(req: RegistrationRequest):
    """
    Submit a registration request for staff review.
    Staff will contact the user to approve/deny access.
    Returns 202 Accepted (not 201 Created, as the account isn't created yet).
    """
    result = await create_registration_request(
        email=req.email,
        full_name=req.full_name,
        company_name=req.company_name,
        phone=req.phone,
        country=req.country,
        role=req.role or "user",
        message=req.message,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {
        "message": "Registration request submitted successfully. Our team will contact you soon.",
        "status": "pending",
    }


@app.get("/admin/registration-requests")
async def get_registration_requests(current_user: dict = Depends(get_current_user)):
    """Get all registration requests (staff-only endpoint)."""
    # Check if user is admin/staff
    if current_user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Staff only")
    
    requests = await get_all_registration_requests()
    return {"requests": requests}


@app.patch("/admin/registration-requests/{request_id}/status")
async def update_request_status(
    request_id: str,
    status_update: dict,
    current_user: dict = Depends(get_current_user),
):
    """Update registration request status: pending, approved, rejected, contacted."""
    # Check if user is admin/staff
    if current_user.get("role") not in ["admin", "staff"]:
        raise HTTPException(status_code=403, detail="Staff only")
    
    new_status = status_update.get("status")
    if new_status not in ["pending", "approved", "rejected", "contacted"]:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    result = await update_registration_request_status(request_id, new_status)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


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
    print(f"[WS] connection attempt, token={'present' if token else 'MISSING'}")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            print("[WS] rejected: no user_id in token")
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError as e:
        print(f"[WS] rejected: JWTError {e}")
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect(websocket, user_id=user_id)
    print(f"[WS] user {user_id} connected. orchestrator has {len(orchestrator.agents)} agents")

    # Send agents from orchestrator (DB-persisted), fallback to profile/default
    orch_agents = orchestrator.get_all_agents()
    if orch_agents:
        agents_payload = []
        for a in orch_agents:
            d = a.model_dump()
            if d.get("created_at"):
                d["created_at"] = d["created_at"].isoformat()
            agents_payload.append(d)
    else:
        profile = await get_client_profile(user_id)
        agents_payload = _build_runtime_agents(profile)
    await websocket.send_json({
        "type":   "initial_state",
        "agents": agents_payload,
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

            elif data.get("type") == "agent_state":
                # Cache agent state for staff view
                agent_id = data.get("agent_id") or data.get("agent")
                state = data.get("state")
                current_tool = data.get("current_tool")
                tool_status = data.get("tool_status")
                
                if agent_id:
                    _update_agent_state_cache(user_id, agent_id, {
                        "state": state,
                        "current_tool": current_tool,
                        "tool_status": tool_status,
                    })

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
    # Use DB orchestrator agents so agent_update WS messages animate the canvas
    orch_agents = orchestrator.get_all_agents()
    if orch_agents:
        runtime_agents = [
            {"id": a.id, "name": a.name, "role": a.role.value,
             "state": "idle", "palette": a.palette, "current_tool": None}
            for a in orch_agents
        ]
    else:
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
        """Wait for HiveAdapter task to finish, then update run status and save agent logs."""
        task = hive_adapter._runs.get(user_id)
        if task:
            try:
                result = await task
                agent_logs = None
                if isinstance(result, dict):
                    agent_logs = result.get("agent_logs")
                await update_run_status(run_id, status="complete", agent_logs=agent_logs)
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
              llm_redactor='openrouter/openai/gpt-5.4-2026-03-05'.
    """
    user_id = str(current_user["user_id"])
    campaign.setdefault("llm_analista", "openrouter/anthropic/claude-haiku-3")
    campaign.setdefault("llm_redactor", "openrouter/openai/gpt-5.4-2026-03-05")
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


@app.get("/api/runs/{run_id}/report")
async def get_run_report(run_id: str, current_user: dict = Depends(get_current_user)):
    """Get agent decision logs for a specific run (shown when user clicks an agent card)."""
    from database import get_db
    from bson import ObjectId
    user_id = str(current_user["user_id"])
    db = get_db()
    run = await db.runs.find_one({"_id": ObjectId(run_id), "user_id": user_id})
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return {
        "run_id": run_id,
        "status": run.get("status"),
        "total_found":    run.get("total_found", 0),
        "total_approved": run.get("total_approved", 0),
        "agent_logs":     run.get("agent_logs", {}),
    }


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


@app.get("/api/leads/checkpoint")
async def get_checkpoint_leads(current_user: dict = Depends(get_current_user)):
    """Return all leads in estado='checkpoint' for the authenticated user."""
    user_id = str(current_user["user_id"])
    db = get_db()
    leads = await db.leads.find(
        {"user_id": user_id, "estado": "checkpoint"}
    ).sort("estado_updated_at", -1).to_list(length=100)
    result = []
    for l in leads:
        l["_id"] = str(l["_id"])
        result.append({
            "id": l["_id"],
            "empresa": l.get("company_name") or l.get("empresa", ""),
            "decisor": l.get("decisor"),
            "puntaje": l.get("puntaje", 0),
            "criterios": l.get("criterios", []),
            "senales": l.get("señales", l.get("senales", [])),
            "canales": l.get("canales", []),
            "canal_elegido": l.get("canal_elegido"),
            "estado": l.get("estado"),
        })
    return result


# ============ Lead Detail & Draft Preview (NEW) ============

@app.get("/api/leads/{lead_id}")
async def get_lead_detail(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Get full lead document with all fields (dossier modal)."""
    user_id = str(current_user["user_id"])
    lead = await get_lead_by_id(lead_id, user_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    return lead


@app.get("/api/leads/{lead_id}/draft")
async def get_lead_draft(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Get lead + email draft preview (no send)."""
    user_id = str(current_user["user_id"])
    lead = await get_lead_by_id(lead_id, user_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    
    exp = lead.get("expediente_json") or {}
    borradores = exp.get("borradores") or {}
    
    return {
        **lead,
        "email_draft": {
            "asuntos": borradores.get("email_asuntos", []),
            "cuerpo": borradores.get("email_cuerpo", ""),
            "decisor": exp.get("decisor", {}),
        }
    }


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

@app.get("/api/staff/stats")
async def get_staff_stats(_staff: dict = Depends(require_staff)):
    """Global stats across all clients + per-client breakdown."""
    db = get_db()
    users = await get_all_users()
    clients = [u for u in users if u["role"] == "client"]
    
    # Global totals
    total_leads = await db.leads.count_documents({})
    total_runs = await db.runs.count_documents({})
    total_approved = await db.leads.count_documents({"hitl_status": "approved"})
    total_checkpoint = await db.leads.count_documents({"estado": "checkpoint"})
    active_runs = await db.runs.count_documents({"status": "running"})
    
    # Per-client breakdown
    per_client = []
    for client in clients:
        client_id = client["id"]
        client_leads = await db.leads.count_documents({"user_id": client_id})
        client_runs = await db.runs.count_documents({"user_id": client_id})
        client_approved = await db.leads.count_documents({"user_id": client_id, "hitl_status": "approved"})
        client_active_runs = await db.runs.count_documents({"user_id": client_id, "status": "running"})
        
        per_client.append({
            "client_id": client_id,
            "client_email": client["email"],
            "total_leads": client_leads,
            "total_runs": client_runs,
            "approved_leads": client_approved,
            "active_runs": client_active_runs,
        })
    
    return {
        "global": {
            "total_leads": total_leads,
            "total_runs": total_runs,
            "total_approved": total_approved,
            "total_checkpoint": total_checkpoint,
            "active_runs": active_runs,
        },
        "per_client": per_client,
    }


# ============ Global Agent State Cache (for staff view) ============
_agent_state_cache: Dict[str, Dict[str, dict]] = {}


def _update_agent_state_cache(user_id: str, agent_id: str, state_data: dict):
    """Update agent state for a client in the cache."""
    if user_id not in _agent_state_cache:
        _agent_state_cache[user_id] = {}
    _agent_state_cache[user_id][agent_id] = {
        **state_data,
        "updated_at": datetime.now(timezone.utc),
    }


@app.get("/api/staff/agents/active")
async def get_staff_agents_active(_staff: dict = Depends(require_staff)):
    """Get pipeline registry + per-client agent activity."""
    from hive_graph import PIPELINE_AGENTS
    
    # Pipeline registry (static)
    pipeline = PIPELINE_AGENTS
    
    # Per-client active state (dynamic from cache)
    per_client_agents = []
    for user_id, agents_dict in _agent_state_cache.items():
        for agent_id, state_data in agents_dict.items():
            # Only include recent updates (< 60 seconds old)
            updated_at = state_data.get("updated_at")
            if updated_at and (datetime.now(timezone.utc) - updated_at).total_seconds() < 60:
                per_client_agents.append({
                    "user_id": user_id,
                    "agent_id": agent_id,
                    "state": state_data.get("state", "idle"),
                    "current_tool": state_data.get("current_tool"),
                    "tool_status": state_data.get("tool_status"),
                })
    
    return {
        "pipeline_registry": pipeline,
        "per_client_active": per_client_agents,
    }


@app.get("/api/staff/stats")
async def staff_get_stats(_staff: dict = Depends(require_staff)):
    """
    Aggregated platform stats across all clients.
    Returns: { global: {...}, per_client: [...] }
    Used by StaffDashboard header cards.
    """
    from database import get_all_client_summaries
    db = get_db()

    # Global aggregation
    users = await get_all_users()
    clients = [u for u in users if u["role"] == "client"]
    client_ids = [u["user_id"] for u in clients]

    total_leads_count, total_approved_count, total_runs_count = await asyncio.gather(
        db.leads.count_documents({}),
        db.leads.count_documents({"hitl_status": "approved"}),
        db.runs.count_documents({}),
    )
    active_runs = len([t for t in hive_adapter._runs.values() if not t.done()])

    # Per-client summaries (single-pass aggregation)
    summaries = await get_all_client_summaries(client_ids) if client_ids else {}
    per_client = []
    for u in clients:
        uid = u["user_id"]
        s = summaries.get(uid, {})
        per_client.append({
            "user_id":       uid,
            "email":         u.get("email", ""),
            "total_leads":   s.get("total_leads", 0),
            "approved_leads": s.get("approved_leads", 0),
            "total_runs":    s.get("total_runs", 0),
            "last_run_at":   s.get("last_run_at"),
            "last_run_status": s.get("last_run_status"),
        })

    return {
        "global": {
            "total_clients":  len(clients),
            "total_leads":    total_leads_count,
            "total_approved": total_approved_count,
            "total_runs":     total_runs_count,
            "active_runs":    active_runs,
        },
        "per_client": per_client,
    }


# Fixed pipeline registry — matches hive_graph agent roles
_PIPELINE_REGISTRY = [
    {"name": "Buscador",     "description": "Descubre empresas por web search"},
    {"name": "Scraper",      "description": "Extrae datos del sitio web"},
    {"name": "Analista",     "description": "Califica y genera expediente"},
    {"name": "Redactor",     "description": "Genera borrador de email personalizado"},
]


@app.get("/api/staff/agents/active")
async def staff_get_active_agents(_staff: dict = Depends(require_staff)):
    """
    Returns pipeline registry + per-client active run status.
    { pipeline_registry: [...], per_client_active: {user_id: {status, agents}} }
    """
    running_ids = {uid for uid, task in hive_adapter._runs.items() if not task.done()}

    # Build per-client active dict
    per_client_active: dict = {}
    for uid in running_ids:
        per_client_active[uid] = {"status": "running", "agents": _PIPELINE_REGISTRY}

    return {
        "pipeline_registry": _PIPELINE_REGISTRY,
        "per_client_active": per_client_active,
    }


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


# ============ Apply Chat Intent ============

class ApplyIntentRequest(_BaseModel):
    intent_type: str
    payload: dict


@app.post("/api/campaign/apply-intent")
async def apply_campaign_intent(
    request: ApplyIntentRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Apply a structured intent from the leads chat to the active campaign.
    Supported: refine_target, adjust_tone, blacklist_company.
    Returns the updated campaign.
    """
    from database import patch_active_campaign, get_active_campaign

    user_id = str(current_user["user_id"])
    t = request.intent_type
    p = request.payload

    if t == "refine_target":
        field = p.get("field", "").strip()
        value = p.get("value", "").strip()
        allowed = {
            "industria_objetivo", "ciudad_objetivo", "dolor_operativo",
            "solucion_ofrecida", "software_clave", "jerarquia_decisores",
            "sector_propio_cliente",
        }
        if not field or field not in allowed:
            raise HTTPException(status_code=400, detail=f"Campo no permitido: {field}")
        await patch_active_campaign(user_id, {field: value})

    elif t == "adjust_tone":
        tone = p.get("tone") or p.get("value", "").strip()
        if tone:
            await patch_active_campaign(user_id, {"tono_correo": tone})

    elif t == "blacklist_company":
        # Append sector/company to the sector_propio_cliente exclusion list
        # or to a dedicated blacklisted_sectors field
        sector = p.get("sector") or p.get("company") or p.get("value", "")
        if sector:
            campaign = await get_active_campaign(user_id)
            existing = campaign.get("sectores_excluidos", "") if campaign else ""
            updated = f"{existing}, {sector}".strip(", ") if existing else sector
            await patch_active_campaign(user_id, {"sectores_excluidos": updated})

    elif t == "campaign_feedback":
        feedback = p.get("feedback") or p.get("value", "")
        if feedback:
            await patch_active_campaign(user_id, {"ultimo_feedback": feedback})

    else:
        raise HTTPException(status_code=400, detail=f"Intent no soportado: {t}")

    campaign = await get_active_campaign(user_id)
    return {"ok": True, "campaign": campaign}


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
    # Optional WhatsApp bot fields — if provided, creates agent but has_bot_secop stays false
    wa_phone_number: Optional[str] = None  # e.g. "+573123528153"
    wa_name: Optional[str] = None          # e.g. "Maximiliano Pulido Beltran"
    wa_company: Optional[str] = None       # e.g. "Seguros"


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
    
    If WhatsApp fields are provided (wa_phone_number, wa_name, wa_company),
    creates the WhatsApp agent but leaves has_bot_secop=false until explicitly activated.
    """
    from pymongo.errors import DuplicateKeyError as _DupKey
    from datetime import timezone

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

    # Initialize WhatsApp bot config (always false by default, activated on demand)
    db = get_db()
    await db.users.update_one(
        {"_id": ObjectId(user["id"])},
        {
            "$set": {
                "has_bot_secop": False,
                "bot_mode": None,
            }
        },
    )

    # If WhatsApp fields provided: create agent, assign phone, but keep bot inactive
    response = {
        "user_id": user["id"],
        "email": user["email"],
        "campaign_id": campaign_id,
        "message": "Cliente creado y campaña configurada",
    }

    if request.wa_phone_number and request.wa_name and request.wa_company:
        try:
            # Create WhatsApp agent
            from database import upsert_whatsapp_agent
            twilio_from = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
            agent_config = {
                "phone_number": request.wa_phone_number,
                "nombre_asesor": request.wa_name,
                "empresa": request.wa_company,
                "twilio_from": twilio_from,
                "cliente_id": user["id"],
                "activo": False,  # Agent created but not active
                "bot_mode": "legacy",  # Default SECOP bot mode
            }
            await upsert_whatsapp_agent(agent_config)

            # Assign phone to user
            await db.users.update_one(
                {"_id": ObjectId(user["id"])},
                {"$set": {"wa_phone_number": request.wa_phone_number}},
            )

            response["wa_phone_number"] = request.wa_phone_number
            response["message"] += " + Agente WhatsApp configurado (activación pendiente)"
        except Exception as e:
            logging.warning(f"[onboard] Failed to create WhatsApp agent: {e}")
            response["wa_warning"] = str(e)

    return response


@app.post("/api/staff/activate-bot/{user_id}", dependencies=[Depends(require_staff)])
async def activate_bot_secop(user_id: str):
    """
    Activate SECOP WhatsApp bot for a user.
    Changes has_bot_secop from false → true.
    Requires user to have wa_phone_number already assigned.
    """
    from bson import ObjectId
    
    db = get_db()
    
    # Verify user exists and has phone assigned
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no existe")
    
    if not user.get("wa_phone_number"):
        raise HTTPException(
            status_code=400,
            detail="Usuario no tiene teléfono WhatsApp asignado. Asígnaelo primero."
        )
    
    # Activate bot
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$set": {
                "has_bot_secop": True,
                "bot_mode": "legacy",
                "bot_enabled_at": datetime.now(timezone.utc).isoformat() + "Z",
            }
        },
    )
    
    # Verify agent exists in whatsapp_agents and set active=True
    await db.whatsapp_agents.update_one(
        {"phone_number": user["wa_phone_number"]},
        {"$set": {"activo": True}},
        upsert=False,
    )
    
    return {
        "ok": True,
        "user_id": user_id,
        "email": user["email"],
        "wa_phone_number": user["wa_phone_number"],
        "has_bot_secop": True,
        "message": "Bot SECOP activado correctamente",
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


VALID_SOURCES = {"google_maps", "secop_adjudicados", "secop_licitaciones"}


class ClientSourcesRequest(_BaseModel):
    fuentes_habilitadas: list[str]  # ["google_maps", "secop_adjudicados", "secop_licitaciones"]
    notification_channel: str = "web"          # "web" | "whatsapp" | "both"
    wa_phone_number: str | None = None         # client's WA number (receives notifications)
    wa_phone_id: str | None = None             # Meta phone_id for outreach FROM this client
    wa_token: str | None = None                # Meta API token (None = use Landa global)


@app.post("/api/staff/clients/{target_user_id}/sources")
async def update_client_sources(
    target_user_id: str,
    request: ClientSourcesRequest,
    _staff: dict = Depends(require_staff),
):
    """
    Set the enabled discovery sources for a client.
    Staff-only. Valid values: google_maps, secop_adjudicados, secop_licitaciones.
    """
    invalid = [s for s in request.fuentes_habilitadas if s not in VALID_SOURCES]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sources: {invalid}. Valid values: {sorted(VALID_SOURCES)}",
        )

    # Build update fields - always include fuentes and notification_channel
    update_fields = {
        "fuentes_habilitadas": request.fuentes_habilitadas,
        "notification_channel": request.notification_channel,
    }
    # Only set WhatsApp fields if they are not None
    if request.wa_phone_number is not None:
        update_fields["wa_phone_number"] = request.wa_phone_number
    if request.wa_phone_id is not None:
        update_fields["wa_phone_id"] = request.wa_phone_id
    if request.wa_token is not None:
        update_fields["wa_token"] = request.wa_token

    db = get_db()
    # Read previous state to detect new WA number (for welcome message)
    prev = await db.company_voice.find_one({"user_id": target_user_id}) or {}
    prev_phone = prev.get("wa_phone_number", "")

    await db.company_voice.update_one(
        {"user_id": target_user_id},
        {"$set": update_fields},
        upsert=True,
    )

    # Send welcome message when a new WA number is set and channel is WA-enabled
    new_phone = request.wa_phone_number
    channel_is_wa = request.notification_channel in ("whatsapp", "both")
    if new_phone and new_phone != prev_phone and channel_is_wa:
        asyncio.create_task(send_whatsapp_text(
            new_phone,
            "👋 Hola! Soy el asistente de Landa. A partir de ahora recibirás notificaciones de tus leads por aquí.\n\nPuedes escribirme en cualquier momento para revisar leads, aprobar prospectos o consultar el estado de tu campaña.",
        ))

    return {
        "status": "ok",
        "user_id": target_user_id,
        "fuentes_habilitadas": request.fuentes_habilitadas,
        "notification_channel": request.notification_channel,
    }


# ============ Lead Lifecycle API (Phase 14 — LANDA-09) ============

class LeadDecisionRequest(_BaseModel):
    decision: str                  # "aprobar" | "pausar" | "rechazar"
    canal_elegido: str | None = None
    motivo: str | None = None


DECISION_MAP = {"aprobar": "outreach", "pausar": "pausado", "rechazar": "nurturing"}


@app.post("/api/leads/{lead_id}/decision")
async def lead_decision(
    lead_id: str,
    request: LeadDecisionRequest,
    current_user: dict = Depends(get_current_user),
):
    """Process a human decision on a checkpoint lead: aprobar, pausar, or rechazar."""
    from landa.state_machine import update_lead_estado
    from landa.agents.outreach import run_outreach as _run_outreach

    user_id = str(current_user["user_id"])
    new_estado = DECISION_MAP.get(request.decision)
    if not new_estado:
        raise HTTPException(status_code=400, detail=f"Unknown decision: {request.decision}")

    db = get_db()
    # Set motivo_nurturing before transition if rechazar
    if request.decision == "rechazar":
        from bson import ObjectId as _ObjId
        motivo = request.motivo or "rechazado_humano"
        await db.leads.update_one(
            {"_id": _ObjId(lead_id)},
            {"$set": {"motivo_nurturing": motivo}},
        )

    try:
        updated = await update_lead_estado(lead_id, user_id, new_estado)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Fire-and-forget outreach
    if request.decision == "aprobar":
        canal = request.canal_elegido or updated.get("canal_elegido", "email")
        asyncio.create_task(_run_outreach(lead_id, user_id, canal, intento=1))
        await notify_user(user_id, {
            "type": "lead_checkpoint",
            "lead_id": lead_id,
            "empresa": updated.get("company_name") or updated.get("empresa", ""),
            "puntaje": updated.get("puntaje", 0),
            "accion": "aprobado",
        })
    elif request.decision == "rechazar":
        await notify_user(user_id, {
            "type": "lead_archived",
            "lead_id": lead_id,
            "empresa": updated.get("company_name") or updated.get("empresa", ""),
        })
    else:
        await manager.send_to_user(user_id, {
            "type": "agent_state",
            "agent": "investigador",
            "state": "idle",
            "message": f"Lead pausado: {updated.get('company_name', lead_id)}",
        })

    return {"status": "ok", "lead_id": lead_id, "nuevo_estado": new_estado}


# ============ Lead Lifecycle API (Phase 14 — LANDA-10, LANDA-11) ============

class CallReportRequest(_BaseModel):
    resultado: str          # "bien" | "mas_o_menos" | "mal" | "no_pude"
    detalle: str | None = None
    sub_tipo: str | None = None


@app.get("/api/leads/{lead_id}/handover")
async def get_handover(lead_id: str, current_user: dict = Depends(get_current_user)):
    """
    Return handover package: full lead doc, conversation thread,
    original qualification, and an AI-generated closing suggestion.
    sugerencia_cierre is non-fatal — returns "" if OPENAI_API_KEY not set.
    """
    from landa.core.context import call_agent as _call_agent
    from bson import ObjectId as _ObjId

    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        lead = await db.leads.find_one({"_id": _ObjId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead["_id"] = str(lead["_id"])

    hilo = lead.get("historial_conversacion", [])
    calificacion = {
        "puntaje": lead.get("puntaje", 0),
        "criterios": lead.get("criterios", []),
        "canales": lead.get("canales", []),
    }

    empresa = lead.get("company_name") or lead.get("empresa", "empresa desconocida")
    decisor = lead.get("decisor", "el decisor")
    system_prompt = "Eres un experto en ventas B2B colombianas."
    user_message = (
        f"Genera una sugerencia de cierre concisa (2-3 oraciones) para llamar a {decisor} "
        f"de {empresa}. Contexto del hilo: {str(hilo)[-500:]}"
    )
    try:
        sugerencia = await _call_agent(system_prompt, user_message)
    except Exception:
        sugerencia = ""

    return {
        "lead": lead,
        "hilo_conversacion": hilo,
        "calificacion_original": calificacion,
        "sugerencia_cierre": sugerencia,
    }


@app.post("/api/leads/{lead_id}/handover/tomar")
async def handover_tomar(lead_id: str, current_user: dict = Depends(get_current_user)):
    """
    Human takes over the lead:
    - Cancel all pending scheduler actions
    - Transition to 'handover' state
    - Schedule 48h no-report notification job
    - Emit lead_handover WebSocket event
    """
    from landa.state_machine import update_lead_estado
    from landa.scheduler import cancel_lead_actions, schedule_retry
    from bson import ObjectId as _ObjId

    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        lead = await db.leads.find_one({"_id": _ObjId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Cancel all pending scheduler jobs for this lead
    await cancel_lead_actions(lead_id)

    # Transition to handover state
    try:
        updated = await update_lead_estado(lead_id, user_id, "handover")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Schedule 48h no-report notification (RESEARCH pitfall 2)
    await schedule_retry(lead_id, canal="notificacion_48h", days=2)

    canal = lead.get("canal_elegido", "email")
    empresa = updated.get("company_name") or updated.get("empresa", "")
    await notify_user(user_id, {
        "type": "lead_handover",
        "lead_id": lead_id,
        "empresa": empresa,
        "canal": canal,
    })

    return {"status": "ok", "lead_id": lead_id, "estado": "handover"}


@app.post("/api/leads/{lead_id}/reporte-llamada")
async def reporte_llamada(
    lead_id: str,
    request: CallReportRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Log call outcome for a lead:
    - 'bien'/'mas_o_menos': fire-and-forget AI interpretation, return 200 immediately
    - 'mal': transition to nurturing, set motivo_nurturing
    - 'no_pude' sub_tipo='ocupado'/'apagado': schedule_retry(days=1)
    - 'no_pude' sub_tipo='incorrecto': set buscar_numero_alternativo=True (no state transition)
    - 'no_pude' sub_tipo='corto': schedule_retry(days=7)
    """
    from landa.state_machine import update_lead_estado
    from landa.scheduler import schedule_retry
    from landa.core.context import call_agent as _call_agent
    from bson import ObjectId as _ObjId

    user_id = str(current_user["user_id"])
    db = get_db()

    try:
        lead = await db.leads.find_one({"_id": _ObjId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    resultado = request.resultado
    detalle = request.detalle or ""
    sub_tipo = request.sub_tipo or ""

    if resultado == "mal":
        await db.leads.update_one(
            {"_id": _ObjId(lead_id)},
            {"$set": {"motivo_nurturing": detalle or "llamada_mal"}},
        )
        try:
            await update_lead_estado(lead_id, user_id, "nurturing")
        except ValueError:
            pass  # Already in nurturing or terminal state — non-fatal

    elif resultado == "no_pude":
        if sub_tipo in ("ocupado", "apagado"):
            canal = lead.get("canal_elegido", "telefono")
            await schedule_retry(lead_id, canal=canal, days=1)
        elif sub_tipo == "incorrecto":
            # Flag for alternative contact discovery — NOT a state transition (RESEARCH pitfall 4)
            await db.leads.update_one(
                {"_id": _ObjId(lead_id)},
                {"$set": {"buscar_numero_alternativo": True}},
            )
        elif sub_tipo == "corto":
            canal = lead.get("canal_elegido", "telefono")
            await schedule_retry(lead_id, canal=canal, days=7)

    elif resultado in ("bien", "mas_o_menos"):
        # Fire-and-forget AI interpretation — return 200 immediately
        async def _interpret_and_act():
            empresa_ia = lead.get("company_name") or lead.get("empresa", "empresa")
            sp = "Eres un coordinador de ventas B2B."
            um = (
                f"Resultado de llamada '{resultado}' con {empresa_ia}. "
                f"Detalle del vendedor: '{detalle}'. "
                f"Decide la siguiente acción: nurturing, reintento en 3 días, o handover completo. "
                f"Responde con solo una de: nurturing | reintento_3d | handover_completo"
            )
            try:
                decision_ia = await _call_agent(sp, um)
                decision_ia = decision_ia.strip().lower()
                if "nurturing" in decision_ia:
                    await update_lead_estado(lead_id, user_id, "nurturing")
                elif "reintento" in decision_ia:
                    canal_ret = lead.get("canal_elegido", "email")
                    await schedule_retry(lead_id, canal=canal_ret, days=3)
                # "handover_completo" — lead stays in current state, human acts
            except Exception:
                pass
        asyncio.create_task(_interpret_and_act())

    empresa = lead.get("company_name") or lead.get("empresa", "")
    await manager.send_to_user(user_id, {
        "type": "agent_state",
        "agent": "outreach",
        "state": "idle",
        "message": f"Reporte registrado para {empresa}",
    })

    return {"status": "ok", "lead_id": lead_id, "resultado": resultado}


# ============ WhatsApp Webhook (Phase 16 — WA-01) ============

async def _safe_task(coro, label: str):
    """Wrap a coroutine so exceptions from create_task are logged instead of silently dropped."""
    try:
        await coro
    except Exception as exc:
        logging.error("[WA] %s crashed: %s", label, exc, exc_info=True)


@app.post("/api/whatsapp/incoming")
async def whatsapp_incoming(request: Request):
    """
    Twilio webhook for inbound WhatsApp messages.

    Returns empty TwiML <Response/> immediately — all processing is async.
    Signature validation via X-Twilio-Signature header.
    Routing: strip 'whatsapp:' prefix from From, lookup in company_voice or users.
    """
    import wa_handler
    from debug_logger import get_payload_logger

    debug_log = get_payload_logger()
    
    form = await request.form()
    from_raw = str(form.get("From", ""))
    to_number = str(form.get("To", ""))
    body = str(form.get("Body", ""))
    num_media = int(form.get("NumMedia", "0"))
    media_url = str(form.get("MediaUrl0", "")) if num_media > 0 else ""

    from_phone = from_raw.replace("whatsapp:", "")
    print(f"[WA-WEBHOOK] from={from_phone} body={body!r:.60}", flush=True)

    # Log incoming webhook payload
    debug_log.log_event("webhook_received", {
        "from_phone": from_phone,
        "to_number": to_number,
        "body": body,
        "has_media": num_media > 0,
        "media_url": media_url if media_url else None,
        "body_length": len(body),
    }, level="DEBUG")

    # Validate Twilio signature (skip in test env if not configured)
    # Reconstruct the public URL using X-Forwarded headers (ngrok sets these)
    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    forwarded_host = request.headers.get("X-Forwarded-Host", "") or request.headers.get("Host", "")
    if forwarded_proto and forwarded_host:
        url = f"{forwarded_proto}://{forwarded_host}{request.url.path}"
    else:
        url = str(request.url)
    print(f"[WA-WEBHOOK] validation url={url}", flush=True)
    signature = request.headers.get("X-Twilio-Signature", "")
    post_data = dict(form)
    if not wa_handler.validate_twilio_signature(url, signature, post_data):
        logging.warning("[WA] Invalid Twilio signature from %s url=%s — ignoring", from_raw, url)
        debug_log.log_error(from_phone, "invalid_signature", "Twilio signature validation failed", {"url": url})
        return Response(content="<Response/>", media_type="text/xml")

    # Identify caller profile (non-blocking lookup, then async processing)
    profile = await wa_handler.get_profile(from_phone)
    print(f"[WA-WEBHOOK] profile={profile['profile'] if profile else 'NOT FOUND'}", flush=True)
    if profile is None:
        logging.warning("[WA] Unknown number %s — ignoring message", from_phone)
        debug_log.log_error(from_phone, "unknown_profile", "Profile not found in system", {})
        return Response(content="<Response/>", media_type="text/xml")

    # Handle bot-switch commands before routing
    from database import get_wa_bot_config, set_wa_bot_mode
    cmd = body.strip().lower()
    if cmd in ("/secop", "/landa"):
        config = await get_wa_bot_config(from_phone)
        target = "legacy" if cmd == "/secop" else "landa"
        flag_key = "secop" if cmd == "/secop" else "landa"
        if not config["bots"].get(flag_key):
            await send_whatsapp_text(from_phone, "❌ Ese bot no está habilitado para tu cuenta.")
        else:
            await set_wa_bot_mode(from_phone, target)
            label = "SECOP" if target == "legacy" else "Landa"
            await send_whatsapp_text(from_phone, f"✅ Modo {label} activado.")
        return Response(content="<Response/>", media_type="text/xml")

    # Route by active bot (from wa_config)
    config = await get_wa_bot_config(from_phone)
    bot_mode = config["active"]

    debug_log.log_event("router_decision", {
        "phone": from_phone,
        "bot_mode": bot_mode,
        "profile_name": profile.get("name") if profile else "unknown",
    }, level="DEBUG")

    if bot_mode == "legacy":
        # Original SECOP prospector bot
        from whatsapp_agent import handle_inbound_message
        agent_config = await get_whatsapp_agent(from_phone) or {}
        async def _legacy():
            try:
                await handle_inbound_message(from_phone, body, to_number, agent_config)
            except Exception as e:
                logging.error("[WA] legacy bot error: %s", e)
                debug_log.log_error(from_phone, "legacy_bot_error", str(e), {"body": body})
        asyncio.create_task(_legacy())

    elif bot_mode == "calendar":
        # Google Calendar agent (Phase 17)
        try:
            from calendar_agent import process_calendar_message
            asyncio.create_task(process_calendar_message(from_phone, body, media_url))
        except ImportError:
            asyncio.create_task(_safe_task(wa_handler.process_inbound(
                from_phone=from_phone, to_number=to_number,
                body="Agente de calendario no disponible aún.", media_url="", profile=profile,
            ), "process_inbound/calendar"))

    else:
        # Default: "landa" — LLM tool calling bot
        asyncio.create_task(_safe_task(
            wa_handler.process_inbound(
                from_phone=from_phone,
                to_number=to_number,
                body=body,
                media_url=media_url,
                profile=profile,
            ), "process_inbound"
        ))

    return Response(content="<Response/>", media_type="text/xml")


# ── Phase 17: Cobranza REST routes ───────────────────────────────────────────
from cobranza.router import router as cobranza_router
app.include_router(cobranza_router)

# ── Phase 17: Vapi webhook routes (cobranza voice agent) ─────────────────────
from cobranza.webhooks import vapi_router as _vapi_router
app.include_router(_vapi_router)


# ── Phase 17: Staff endpoint to enable cobranza for a client ─────────────────

@app.post("/api/staff/clients/{client_id}/cobranza/enable", status_code=200)
async def staff_enable_cobranza(
    client_id: str,
    _staff=Depends(require_staff),
):
    """
    POST /api/staff/clients/{client_id}/cobranza/enable
    Staff-only: sets cobranza_enabled=True on the client's company_voice document.
    Creates the document if it does not exist yet.
    """
    db = get_db()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    await db.company_voice.update_one(
        {"user_id": client_id},
        {
            "$set": {
                "cobranza_enabled": True,
                "cobranza_enabled_at": now,
                "updated_at": now,
            },
            "$setOnInsert": {"user_id": client_id, "created_at": now},
        },
        upsert=True,
    )
    return {"ok": True, "client_id": client_id, "cobranza_enabled": True}

# Servir archivos estáticos del frontend (build de Vite) — al final para no interceptar rutas API
import pathlib
frontend_dist = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
