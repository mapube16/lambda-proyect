"""
tenant_admin.py — Phase 25: Multi-tenant self-service admin API.

Each authenticated tenant manages ONLY its own configuration:
  - tenant_configs   (modules, brand_name, language, voice_system_prompt)
  - agent_instances  (model, temperature, tools_enabled, prompt_history)
  - rag_documents    (upload, list — Pinecone namespace = user_id)

SECURITY (T-25-12..15): user_id is ALWAYS derived from the JWT via
Depends(get_current_user). It is NEVER read from the request body or path,
so a tenant can never touch another tenant's config, agents, or documents.
Prefix: /api/tenant
"""
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from auth import get_current_user
from cobranza.tenant_config import (
    append_prompt_version,
    get_rag_documents,
    toggle_module,
    upsert_agent_instance,
    upsert_tenant_config,
)
from cobranza.config_cache import get_tenant_config as get_cached_tenant_config

logger = logging.getLogger("tenant_admin")

router = APIRouter(prefix="/api/tenant", tags=["tenant-admin"])


# ── Request models (ASVS V5: max_length on free-text fields, T-25-13) ─────────

class TenantConfigUpdateRequest(BaseModel):
    modules: Optional[dict] = None
    voice_system_prompt: Optional[str] = Field(None, max_length=2000)
    brand_name: Optional[str] = Field(None, max_length=200)
    language: Optional[str] = None


class AgentInstanceUpdateRequest(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    tools_enabled: Optional[List[str]] = None
    new_prompt: Optional[str] = Field(None, max_length=2000)


class ModuleToggleRequest(BaseModel):
    enabled: bool


# ── tenant_configs ────────────────────────────────────────────────────────────

@router.get("/config")
async def get_my_config(current_user: dict = Depends(get_current_user)):
    """Return the authenticated tenant's config (read-through Redis cache)."""
    user_id = str(current_user["user_id"])
    config = await get_cached_tenant_config(user_id)
    return config or {}


@router.patch("/config")
async def update_my_config(
    request: TenantConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Patch tenant_configs. upsert_tenant_config invalidates Redis (CACHE-01)."""
    user_id = str(current_user["user_id"])
    update_data = {k: v for k, v in request.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(400, "No fields to update")
    try:
        await upsert_tenant_config(user_id, update_data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[tenant_admin] update_config failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to update config")
    return {"ok": True}


@router.post("/modules/{module}/toggle")
async def toggle_my_module(
    module: str,
    request: ModuleToggleRequest,
    current_user: dict = Depends(get_current_user),
):
    """Enable/disable a module. toggle_module invalidates Redis immediately."""
    user_id = str(current_user["user_id"])
    try:
        await toggle_module(user_id, module, request.enabled)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[tenant_admin] toggle_module failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to toggle module")
    return {"ok": True, "module": module, "enabled": request.enabled}


# ── agent_instances ───────────────────────────────────────────────────────────

@router.get("/agents")
async def list_my_agents(current_user: dict = Depends(get_current_user)):
    """List the tenant's agent_instances (filtered by user_id)."""
    user_id = str(current_user["user_id"])
    from database import get_db
    db = get_db()
    docs = []
    async for doc in db.agent_instances.find({"user_id": user_id}):
        doc["_id"] = str(doc["_id"])
        docs.append(doc)
    return docs


@router.patch("/agents/{agent_type}")
async def update_my_agent(
    agent_type: str,
    request: AgentInstanceUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Update agent_instances settings. When new_prompt is present, also append
    it to prompt_history (capped to last 5 versions by append_prompt_version).
    """
    user_id = str(current_user["user_id"])
    update_data = {
        k: v
        for k, v in request.model_dump(exclude={"new_prompt"}).items()
        if v is not None
    }
    # agent_type travels inside the document (one agent_instances doc per tenant)
    update_data["agent_type"] = agent_type
    try:
        await upsert_agent_instance(user_id, update_data)
        if request.new_prompt:
            await append_prompt_version(user_id, agent_type, request.new_prompt)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("[tenant_admin] update_agent failed: %s", exc, exc_info=True)
        raise HTTPException(500, "Failed to update agent")
    return {"ok": True}


# ── RAG documents (Pinecone namespace = user_id) ──────────────────────────────

@router.post("/rag/upload")
async def upload_rag_document(
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Ingest one or more documents into the tenant's Pinecone namespace."""
    user_id = str(current_user["user_id"])
    from cobranza.rag_service import ingest_document

    results = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            results.append({"filename": file.filename, "error": "empty file"})
            continue
        try:
            try:
                content = file_bytes.decode("utf-8")
            except UnicodeDecodeError:
                from rag import extract_text
                content = extract_text(
                    file_bytes, file.filename or "upload", file.content_type or ""
                )
            result = await ingest_document(
                user_id, content, title=file.filename or "upload", doc_type="file"
            )
            results.append({"filename": file.filename, **result})
        except Exception as e:
            logger.error("[tenant_admin] RAG upload failed for %s: %s", file.filename, e)
            results.append({"filename": file.filename, "error": str(e)[:100]})
    return results


@router.get("/rag/documents")
async def list_my_rag_documents(current_user: dict = Depends(get_current_user)):
    """List only the authenticated tenant's RAG documents (T-25-14)."""
    user_id = str(current_user["user_id"])
    return await get_rag_documents(user_id)
