from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel

from auth import get_current_user
from database import get_roadmap_state, set_roadmap_state
from models import RoadmapState

router = APIRouter()


@router.get("/api/health")
async def health():
    return {"ok": True, "message": "Lambda Office API", "status": "running"}


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
