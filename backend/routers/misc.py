from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel

from auth import get_current_user
from database import get_db, get_roadmap_state, set_roadmap_state
from models import RoadmapState

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"ok": True, "message": "Lambda Office API", "status": "running"}


# Sections always available unless a client has an explicit `modules_enabled`
# override — keeps today's behavior for every existing client (full platform,
# cobranza gated only by its own `cobranza_enabled` flag as before).
_DEFAULT_NON_COBRANZA_MODULES = ["leads", "email", "canales"]


@router.get("/api/client/modules")
async def get_enabled_modules(current_user=Depends(get_current_user)):
    """
    Which ClientDashboard sections this tenant is authorized to use — drives the
    feature-locked modal in the sidebar for anything not in the returned list.

    No `modules_enabled` override on the tenant's company_voice doc → every
    client keeps today's behavior (leads/email/canales always on, cobranza
    gated by the existing cobranza_enabled flag). An explicit override (set by
    staff via POST /api/staff/clients/{id}/modules) replaces the list wholesale
    — used for single-purpose tenants like DPG (cobranza-only).
    """
    db = get_db()
    doc = await db.company_voice.find_one({"user_id": str(current_user["user_id"])})
    override = (doc or {}).get("modules_enabled")
    if override is not None:
        return {"modules_enabled": override}

    modules = list(_DEFAULT_NON_COBRANZA_MODULES)
    if bool((doc or {}).get("cobranza_enabled", False)):
        modules.append("cobranza")
    return {"modules_enabled": modules}


@router.get("/api/roadmap-state", response_model=RoadmapState)
async def api_get_roadmap_state(current_user=Depends(get_current_user)):
    from fastapi import HTTPException
    if current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff only")
    user_id = current_user["user_id"]
    state = await get_roadmap_state(user_id)
    if not state:
        return {"user_id": user_id, "state": {}, "updated_at": None}
    return state


@router.post("/api/roadmap-state", response_model=dict)
async def api_set_roadmap_state(body: dict = Body(...), current_user=Depends(get_current_user)):
    from fastapi import HTTPException
    if current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff only")
    return await set_roadmap_state(current_user["user_id"], body.get("state", {}))
