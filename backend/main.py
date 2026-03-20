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

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, WebSocketException, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pymongo.errors import DuplicateKeyError
from jose import JWTError, jwt
from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, SECRET_KEY, ALGORITHM
)
from database import (
    init_db, get_user_by_email, create_user,
    save_campaign, get_active_campaign,
    create_run, update_run_status, get_runs_by_user,
    save_lead, get_leads_by_run, get_leads_by_user, update_lead_hitl,
)
from models import (
    Agent, AgentState, AgentRole,
    CreateAgentRequest, TaskRequest, AgentResponse,
    UserCreate, Token
)
from orchestrator import HiveOrchestrator
from prospector import run_prospect
from onboarding import chat_turn

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and orchestrator on startup"""
    global orchestrator
    await init_db()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("Warning: OPENAI_API_KEY not set. Using demo mode.")
        api_key = "demo-key"

    orchestrator = HiveOrchestrator(api_key)
    orchestrator.set_broadcast_callback(manager.broadcast)

    print("Isomorph Office started!")
    yield
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


@app.post("/auth/login", response_model=Token)
async def login(user: UserCreate):
    """Authenticate user, return signed JWT. Returns 401 on bad credentials."""
    db_user = await get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=401,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token(data={"sub": str(db_user["id"])})
    return {"access_token": token, "token_type": "bearer"}


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

    # Send current state on connect
    agents = orchestrator.get_all_agents()
    agents_data = []
    for a in agents:
        d = a.model_dump()
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        agents_data.append(d)
    await websocket.send_json({
        "type": "initial_state",
        "agents": agents_data
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

from pydantic import BaseModel as _BaseModel

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
    if not campaign:
        active = await get_active_campaign(user_id)
        if active:
            # Strip internal DB fields before passing to pipeline
            campaign = {k: v for k, v in active.items()
                        if k not in ("_id", "user_id", "is_active", "created_at")}

    # Create a run document before launching the pipeline
    campaign_id = active["_id"] if (not request.campaign and active) else ""
    run_id = await create_run(
        user_id=user_id,
        campaign_id=campaign_id,
        max_results=min(request.max_results, 50),
    )

    async def _run_and_finalize():
        try:
            result = await run_prospect(
                campaign=campaign,
                openai_api_key=api_key,
                max_results=min(request.max_results, 50),
                orchestrator=orchestrator,
                send_to_user=manager.send_to_user,
                user_id=user_id,
                run_id=run_id,
                save_lead=save_lead,
            )
            total_found = result.get("total_analyzed", 0)
            total_approved = result.get("total_approved", 0)
            await update_run_status(
                run_id,
                status="complete",
                total_found=total_found,
                total_approved=total_approved,
            )
        except Exception as exc:
            print(f"[prospect] pipeline error: {exc}")
            await update_run_status(run_id, status="error")

    asyncio.create_task(_run_and_finalize())

    return {"status": "running", "run_id": run_id, "message": "Campaña iniciada — los agentes están buscando empresas"}


# ============ Onboarding Chat ============

class ChatRequest(_BaseModel):
    messages: list[dict]  # [{role: "user"|"assistant", content: "..."}]


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
    reply = await chat_turn(request.messages, api_key)

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
    """Get active campaign for current user."""
    user_id = str(current_user["user_id"])
    campaign = await get_active_campaign(user_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="No active campaign")
    return campaign


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
    """Approve a lead (HITL decision)."""
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "approved")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    return {"status": "approved", "lead_id": lead_id}


@app.patch("/api/leads/{lead_id}/reject")
async def reject_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Reject a lead (HITL decision)."""
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "rejected")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    return {"status": "rejected", "lead_id": lead_id}


@app.get("/api/leads")
async def get_user_leads(current_user: dict = Depends(get_current_user)):
    """Get all leads for current user (recent first)."""
    user_id = str(current_user["user_id"])
    leads = await get_leads_by_user(user_id)
    return leads


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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
