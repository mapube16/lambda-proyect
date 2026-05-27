from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, WebSocketException, Query, status
from jose import JWTError, jwt

from auth import SECRET_KEY, ALGORITHM, get_current_user
from database import get_client_profile
from models import AgentRole
from pipeline_helpers import _build_runtime_agents
from services.connection_manager import manager
import state

router = APIRouter()


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if not user_id:
            raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)
    except JWTError:
        raise WebSocketException(code=status.WS_1008_POLICY_VIOLATION)

    await manager.connect(websocket, user_id=user_id)

    orch_agents = state.orchestrator.get_all_agents()
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
    await websocket.send_json({"type": "initial_state", "agents": agents_payload})

    try:
        while True:
            data = await websocket.receive_json()

            if data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})

            elif data.get("type") == "create_agent":
                try:
                    agent = await state.orchestrator.create_agent(name=data.get("name", "Agent"), role=AgentRole(data.get("role", "coder")))
                    agent_data = agent.model_dump()
                    if agent_data.get("created_at"):
                        agent_data["created_at"] = agent_data["created_at"].isoformat()
                    await manager.broadcast({"type": "agent_created", "agent": agent_data})
                except Exception as e:
                    print(f"Error creating agent: {e}")

            elif data.get("type") == "run_task":
                agent_id = data.get("agent_id")
                task = data.get("task")
                if agent_id and task:
                    import asyncio
                    asyncio.create_task(state.orchestrator.run_agent(agent_id, task))

            elif data.get("type") == "agent_state":
                agent_id = data.get("agent_id") or data.get("agent")
                if agent_id:
                    state.update_agent_state_cache(user_id, agent_id, {"state": data.get("state"), "current_tool": data.get("current_tool"), "tool_status": data.get("tool_status")})

    except WebSocketDisconnect:
        manager.disconnect(user_id)
