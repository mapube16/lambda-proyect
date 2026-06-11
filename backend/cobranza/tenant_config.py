"""
tenant_config.py — Phase 25: Multi-tenant config CRUD.

Provides CRUD for three MongoDB collections:
  - tenant_configs   : per-tenant agent configuration (business_name, modules, etc.)
  - agent_instances  : per-tenant LLM agent settings (model, temperature, prompt_history)
  - rag_documents    : metadata for per-tenant RAG-ingested documents

All writes call invalidate_tenant_config(user_id) to uphold the CACHE-01 contract:
any config read via get_tenant_config() from config_cache.py reflects the latest
MongoDB values within the 300-second TTL window.

Tenant isolation is enforced by always filtering on {"user_id": user_id}.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId

from database import get_db


# ── Helpers ───────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    """Convert MongoDB document: _id ObjectId -> str, return None if None."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def _invalidate(user_id: str) -> None:
    """Fire-and-forget cache invalidation — import is lazy to avoid circular deps."""
    try:
        from cobranza.config_cache import invalidate_tenant_config
        await invalidate_tenant_config(user_id)
    except Exception:
        # If Redis is unavailable, the next cache read falls through to MongoDB.
        # Log but do not raise — CRUD must not fail because of cache.
        import logging
        logging.getLogger(__name__).warning(
            "invalidate_tenant_config failed for user_id=%s (non-fatal)", user_id
        )


# ── tenant_configs ─────────────────────────────────────────────────────────────

async def upsert_tenant_config(user_id: str, fields: dict) -> None:
    """
    Upsert tenant config document with the given fields.
    Always sets updated_at; sets created_at only on first insert.
    CACHE-01: calls invalidate_tenant_config on every successful write.
    """
    db = get_db()
    now = _utcnow()
    await db.tenant_configs.update_one(
        {"user_id": user_id},
        {
            "$set": {**fields, "user_id": user_id, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await _invalidate(user_id)


async def get_tenant_config_doc(user_id: str) -> Optional[dict]:
    """Return serialized tenant config dict (_id as str), or None if not found."""
    db = get_db()
    doc = await db.tenant_configs.find_one({"user_id": user_id})
    return _serialize(doc)


async def toggle_module(user_id: str, module: str, enabled: bool) -> None:
    """
    Upsert the modules.<module> flag on the tenant config document.
    CACHE-01: calls invalidate_tenant_config immediately after write so the
    next get_tenant_config() reflects the new value.
    """
    db = get_db()
    now = _utcnow()
    await db.tenant_configs.update_one(
        {"user_id": user_id},
        {
            "$set": {f"modules.{module}": enabled, "user_id": user_id, "updated_at": now},
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
    await _invalidate(user_id)


# ── agent_instances ────────────────────────────────────────────────────────────

async def upsert_agent_instance(user_id: str, fields: dict) -> None:
    """
    Upsert agent instance settings (model, temperature, tools_enabled, etc.).
    """
    db = get_db()
    now = _utcnow()
    await db.agent_instances.update_one(
        {"user_id": user_id},
        {
            "$set": {**fields, "user_id": user_id, "updated_at": now},
            "$setOnInsert": {"created_at": now, "prompt_history": []},
        },
        upsert=True,
    )


async def get_agent_instance(user_id: str) -> Optional[dict]:
    """Return serialized agent instance dict, or None if not found."""
    db = get_db()
    doc = await db.agent_instances.find_one({"user_id": user_id})
    return _serialize(doc)


async def append_prompt_version(user_id: str, agent_type: str, new_prompt: str) -> None:
    """
    Append a new prompt version entry to the agent instance's prompt_history,
    then trim to keep only the last 5 entries.

    Uses the two-op pattern (push then trim) per Phase 16/mongomock constraint:
    Motor + mongomock do NOT support $push + $slice in a single update_one, so
    we push first, then read + trim in a second update_one if needed.
    No $slice is used anywhere in this function.
    """
    db = get_db()
    now = _utcnow()
    entry = {"version": str(now.timestamp()), "prompt": new_prompt, "updated_at": now}

    # Op 1: push the new entry
    await db.agent_instances.update_one(
        {"user_id": user_id},
        {
            "$push": {"prompt_history": entry},
            "$set": {"updated_at": now},
        },
        upsert=True,
    )

    # Op 2: trim to last 5 if needed
    doc = await db.agent_instances.find_one({"user_id": user_id})
    if doc and len(doc.get("prompt_history", [])) > 5:
        trimmed = doc["prompt_history"][-5:]
        await db.agent_instances.update_one(
            {"user_id": user_id},
            {"$set": {"prompt_history": trimmed}},
        )


# ── rag_documents ──────────────────────────────────────────────────────────────

async def save_rag_document_metadata(
    user_id: str,
    filename: str,
    source_type: str,
    chunk_count: int,
) -> str:
    """
    Insert RAG document metadata into rag_documents collection.
    pinecone_namespace is set to user_id (per-tenant namespace isolation).
    Returns the inserted _id as str.
    """
    db = get_db()
    now = _utcnow()
    doc = {
        "user_id": user_id,
        "filename": filename,
        "source_type": source_type,
        "chunk_count": chunk_count,
        "pinecone_namespace": user_id,
        "created_at": now,
    }
    result = await db.rag_documents.insert_one(doc)
    return str(result.inserted_id)


async def get_rag_documents(user_id: str) -> list:
    """Return list of serialized RAG document metadata for the given user."""
    db = get_db()
    cursor = db.rag_documents.find({"user_id": user_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=None)
    return [_serialize(d) for d in docs]
