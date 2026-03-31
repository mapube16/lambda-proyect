# ─── Roadmap State Model ────────────────────────────────────────────────
class RoadmapState(BaseModel):
    user_id: str
    state: dict  # {check_id: bool, ...}
    updated_at: Optional[datetime] = None
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from datetime import datetime


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    TOOL_USE = "tool_use"
    WAITING = "waiting"
    ERROR = "error"


class AgentRole(str, Enum):
    CODER = "coder"
    RESEARCHER = "researcher"
    WRITER = "writer"
    REVIEWER = "reviewer"
    PLANNER = "planner"


class ToolActivity(BaseModel):
    tool_name: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime] = None


class Agent(BaseModel):
    id: str
    name: str
    role: AgentRole
    state: AgentState = AgentState.IDLE
    current_tool: Optional[str] = None
    tool_status: Optional[str] = None
    palette: int = 0  # 0-5 for different character sprites
    seat_id: Optional[str] = None
    is_subagent: bool = False
    parent_agent_id: Optional[str] = None
    created_at: datetime = datetime.now()
    

class AgentUpdate(BaseModel):
    """WebSocket message for agent state updates"""
    type: str = "agent_update"
    agent_id: str
    state: AgentState
    current_tool: Optional[str] = None
    tool_status: Optional[str] = None


class CreateAgentRequest(BaseModel):
    name: str
    role: AgentRole
    instructions: Optional[str] = None


class TaskRequest(BaseModel):
    agent_id: str
    task: str


class ChatMessage(BaseModel):
    role: str
    content: str


class AgentResponse(BaseModel):
    agent_id: str
    message: str
    tool_calls: Optional[List[Dict[str, Any]]] = None


# ─── Auth models (Phase 1) ────────────────────────────────────────────────

class UserCreate(BaseModel):
    """Request body for POST /auth/register and POST /auth/login."""
    email: str
    password: str
    full_name: Optional[str] = None
    company_name: Optional[str] = None
    phone: Optional[str] = None
    phones: Optional[List[str]] = None  # Soporte para múltiples números
    country: Optional[str] = None
    role: Optional[str] = None


class Token(BaseModel):
    """Response body for POST /auth/login."""
    access_token: str
    token_type: str = "bearer"
    email: str
    role: str


class RegistrationRequest(BaseModel):
    """Request body for POST /auth/register-request - creates signup request for staff review."""
    email: str
    full_name: str
    company_name: str
    phone: Optional[str] = None
    country: Optional[str] = None
    role: Optional[str] = "user"
    message: Optional[str] = None  # Why they're interested
    token_type: str = "bearer"
