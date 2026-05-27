"""Routes for the legacy HiveOrchestrator agent management (not LANDA agents)."""
import asyncio

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import JSONResponse

from auth import get_current_user
from models import Agent, AgentRole, AgentState, CreateAgentRequest, TaskRequest, AgentResponse
import state

router = APIRouter()


@router.get("/api/agents")
async def get_agents(current_user: dict = Depends(get_current_user)):
    agents = state.orchestrator.get_all_agents()
    result = []
    for a in agents:
        d = a.model_dump()
        if d.get("created_at"):
            d["created_at"] = d["created_at"].isoformat()
        result.append(d)
    return result


@router.post("/api/agents", response_model=Agent)
async def create_agent(request: CreateAgentRequest, current_user: dict = Depends(get_current_user)):
    agent = await state.orchestrator.create_agent(name=request.name, role=request.role)
    d = agent.model_dump()
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    return d


@router.get("/api/agents/{agent_id}", response_model=Agent)
async def get_agent(agent_id: str, current_user: dict = Depends(get_current_user)):
    agent = state.orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    d = agent.model_dump()
    if d.get("created_at"):
        d["created_at"] = d["created_at"].isoformat()
    return d


@router.delete("/api/agents")
async def delete_all_agents(current_user: dict = Depends(get_current_user)):
    await state.orchestrator.delete_all_agents()
    return {"status": "deleted_all"}


@router.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: str, current_user: dict = Depends(get_current_user)):
    success = await state.orchestrator.delete_agent(agent_id)
    if not success:
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": agent_id}


@router.post("/api/agents/{agent_id}/task", response_model=AgentResponse)
async def run_agent_task(agent_id: str, request: TaskRequest, current_user: dict = Depends(get_current_user)):
    agent = state.orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    result = await state.orchestrator.run_agent(agent_id, request.task)
    return result


@router.post("/api/demo/simulate")
async def simulate_agent_activity(agent_id: str, current_user: dict = Depends(get_current_user)):
    agent = state.orchestrator.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    async def simulate():
        states = [
            (AgentState.THINKING, None, "Processing..."),
            (AgentState.TOOL_USE, "read_file", "Reading config.py"),
            (AgentState.TOOL_USE, "write_file", "Writing output.py"),
            (AgentState.THINKING, None, "Analyzing..."),
            (AgentState.TOOL_USE, "run_code", "Executing tests"),
            (AgentState.WAITING, None, "Done!"),
        ]
        for s, tool, status in states:
            await state.orchestrator.update_agent_state(agent_id, s, tool, status)
            await asyncio.sleep(2)

    asyncio.create_task(simulate())
    return {"status": "simulation_started", "agent_id": agent_id}
