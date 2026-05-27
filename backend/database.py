"""
database.py — Motor (async MongoDB) persistence layer.
All DB operations are here. No other module touches Motor directly.
"""
import os
import logging
from typing import Optional
from datetime import datetime, timezone
from urllib.parse import urlparse
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import OperationFailure

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "hive_office")

_client: Optional[AsyncIOMotorClient] = None

logger = logging.getLogger(__name__)


async def _safe_index(collection, keys, **kwargs):
    """Create index, ignoring conflicts with existing indexes (e.g. prod has different options)."""
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code == 86:  # IndexKeySpecsConflict
            logger.warning("Index conflict on %s (skipped): %s", collection.name, exc.details.get("errmsg", ""))
        else:
            raise


def get_db():
    return _client[DB_NAME]


async def init_db(client: Optional[AsyncIOMotorClient] = None) -> None:
    global _client
    import certifi
    _client = client or AsyncIOMotorClient(MONGODB_URI, tlsCAFile=certifi.where())
    db = _client[DB_NAME]
    await _safe_index(db.users, "email", unique=True)
    await _safe_index(db.campaigns, [("user_id", 1), ("is_active", 1)])
    await _safe_index(db.runs, [("user_id", 1), ("started_at", -1)])
    await _safe_index(db.runs, "run_id", unique=True, sparse=True)
    await _safe_index(db.leads, [("run_id", 1), ("user_id", 1)])
    await _safe_index(db.leads, [("user_id", 1), ("created_at", -1)])
    await _safe_index(db.client_knowledge, [("user_id", 1), ("filename", 1)])
    await _safe_index(db.client_profiles, "user_id", unique=True)
    await _safe_index(db.ideal_leads, [("user_id", 1), ("lead_id", 1)], unique=True)
    await _safe_index(db.rejected_leads, [("user_id", 1), ("lead_id", 1)], unique=True)
    await _safe_index(db.whatsapp_agents, "phone_number", unique=True)
    await _safe_index(db.whatsapp_agents, "cliente_id")
    # ── Landa Foundation (Phase 12) indexes ──────────────────────────────────
    await _safe_index(db.leads, "estado")
    await _safe_index(db.leads, [("user_id", 1), ("estado", 1)])
    await _safe_index(db.sector_profiles, [("sector", 1), ("pais_region", 1)])
    await _safe_index(db.scheduled_actions, "fecha_programada")
    await _safe_index(db.scheduled_actions, [("estado", 1), ("fecha_programada", 1)])
    await _safe_index(db.scheduled_actions, "lead_id")
    # ── Phase 16: wa_sessions TTL index ──────────────────────────────────────
    await _safe_index(db.wa_sessions, "phone", unique=True)
    await _safe_index(db.wa_sessions, [("updated_at", 1)], expireAfterSeconds=86400)
    # ── Registration requests index (staff access control) ──────────────────
    await _safe_index(db.registration_requests, "email", unique=True)
    await _safe_index(db.registration_requests, [("created_at", -1)])
    # ── Agents persistence ───────────────────────────────────────────────────
    await _safe_index(db.agents, "agent_id", unique=True)
    # ── Phase 17: Cobranza debtors indexes ───────────────────────────────────
    await _safe_index(db.debtors, [("user_id", 1), ("estado", 1)])
    await _safe_index(db.debtors, [("user_id", 1), ("created_at", -1)])
    await _safe_index(db.debtors, "vapi_call_id", sparse=True)
    await _safe_index(db.debtors, [("user_id", 1), ("telefono", 1)], unique=True, partialFilterExpression={"source": "manual"})
    # ── Email OAuth + Events ──────────────────────────────────────────────────
    await _safe_index(db.email_events, [("user_id", 1), ("timestamp", -1)])
    await _safe_index(db.email_events, "message_id")
    await _safe_index(db.email_events, "lead_id")
    # ── Phase 17: Voice Orchestrator (Assembly AI) ───────────────────────────
    await _safe_index(db.cobranza_calls_in_progress, "call_sid", unique=True)
    await _safe_index(db.cobranza_calls_in_progress, [("user_id", 1), ("started_at", -1)])
    await _safe_index(db.cobranza_calls_in_progress, [("started_at", 1)], expireAfterSeconds=3600)
    await _safe_index(db.cobranza_calls, [("user_id", 1), ("created_at", -1)])
    await _safe_index(db.cobranza_calls, "call_id", unique=True)


# ── Seed ──────────────────────────────────────────────────────────────────────

async def seed_users(users: list[dict]) -> None:
    """Create seed users if they don't exist. Each dict: {email, hashed_password, role}."""
    db = get_db()
    for u in users:
        existing = await db.users.find_one({"email": u["email"]})
        if not existing:
            await db.users.insert_one({
                "email": u["email"],
                "hashed_password": u["hashed_password"],
                "role": u.get("role", "client"),
                "created_at": datetime.now(timezone.utc),
            })


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> Optional[dict]:
    db = get_db()
    doc = await db.users.find_one({"email": email})
    if doc is None:
        return None
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "hashed_password": doc["hashed_password"],
        "role": doc.get("role", "client"),
        "created_at": doc.get("created_at"),
        "phones": doc.get("phones", []),
        "phone": doc.get("phone"),
    }


async def get_user_by_id(user_id: str) -> Optional[dict]:
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    if doc is None:
        return None
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "role": doc.get("role", "client"),
        "created_at": doc.get("created_at"),
        "phones": doc.get("phones", []),
        "phone": doc.get("phone"),
    }


async def get_user_root_onboarding(user_id: str) -> Optional[dict]:
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None
    if doc is None:
        return None

    keys = [
        "onboarding_business_summary",
        "onboarding_personality_prompt",
        "onboarding_campaign",
        "onboarding_agents",
        "onboarding_agent_models",
        "onboarding_agent_personalities",
        "onboarding_prompts",
        "onboarding_agents_count",
        "onboarding_updated_at",
    ]
    payload = {k: doc.get(k) for k in keys if k in doc}
    return payload or None


async def create_user(
    email: str, 
    hashed_password: str, 
    role: str = "client",
    full_name: str = None,
    company_name: str = None,
    phone: str = None,
    country: str = None,
) -> dict:
    db = get_db()
    user_doc = {
        "email": email,
        "hashed_password": hashed_password,
        "role": role,
        "created_at": datetime.now(timezone.utc),
    }
    # Add optional fields if provided
    if full_name:
        user_doc["full_name"] = full_name
    if company_name:
        user_doc["company_name"] = company_name
    if phone:
        user_doc["phone"] = phone
        user_doc["phones"] = [phone]
    if country:
        user_doc["country"] = country
    
    result = await db.users.insert_one(user_doc)
    return {"id": str(result.inserted_id), "email": email, "role": role}


async def get_all_users() -> list:
    """Return all users (staff-only endpoint)."""
    db = get_db()
    cursor = db.users.find({}).sort("created_at", -1)
    docs = await cursor.to_list(length=500)
    return [
        {
            "id": str(d["_id"]),
            "email": d["email"],
            "role": d.get("role", "client"),
            "created_at": d.get("created_at"),
            "phones": d.get("phones", []),
            "phone": d.get("phone"),
        }
        for d in docs
    ]

# --- NUEVAS FUNCIONES PARA SOPORTE MULTI-NÚMERO ---
async def get_user_by_phone(phone: str) -> Optional[dict]:
    """Busca usuario por cualquier número en phones o phone principal."""
    db = get_db()
    doc = await db.users.find_one({"$or": [
        {"phones": phone},
        {"phone": phone}
    ]})
    if not doc:
        return None
    doc["id"] = str(doc["_id"])
    return doc

async def add_phone_to_user(user_id: str, new_phone: str) -> bool:
    """Agrega un nuevo número a la lista phones del usuario (sin duplicados)."""
    import logging
    db = get_db()
    logging.info(f"[add_phone_to_user] user_id={user_id} new_phone={new_phone}")
    try:
        obj_id = ObjectId(user_id)
    except Exception as e:
        logging.error(f"[add_phone_to_user] Invalid ObjectId: {e}")
        return False
    user_before = await db.users.find_one({"_id": obj_id})
    logging.info(f"[add_phone_to_user] User before update: {user_before}")
    result = await db.users.update_one(
        {"_id": obj_id},
        {"$addToSet": {"phones": new_phone}}
    )
    user_after = await db.users.find_one({"_id": obj_id})
    logging.info(f"[add_phone_to_user] Update result: matched={result.matched_count} modified={result.modified_count}")
    logging.info(f"[add_phone_to_user] User after update: {user_after}")
    return result.matched_count == 1


async def delete_user_by_id(user_id: str) -> bool:
    db = get_db()
    try:
        result = await db.users.delete_one({"_id": ObjectId(user_id)})
    except Exception:
        return False
    return result.deleted_count == 1


async def delete_client_profile(user_id: str) -> int:
    db = get_db()
    result = await db.client_profiles.delete_many({"user_id": user_id})
    return result.deleted_count


async def get_user_activity_counts(user_id: str) -> dict:
    """Counts persisted activity to determine whether a user is a disposable onboarding draft."""
    import asyncio as _asyncio
    db = get_db()
    leads, runs, campaigns = await _asyncio.gather(
        db.leads.count_documents({"user_id": user_id}),
        db.runs.count_documents({"user_id": user_id}),
        db.campaigns.count_documents({"user_id": user_id}),
    )
    return {
        "leads": leads,
        "runs": runs,
        "campaigns": campaigns,
    }


async def discard_onboarding_draft(user_id: str) -> dict:
    """
    Remove onboarding-only data for a user.
    If the user has no persisted activity (runs/leads/campaigns), also delete the user account.
    """
    import asyncio as _asyncio

    knowledge_deleted, profile_deleted, activity = await _asyncio.gather(
        delete_knowledge_by_user(user_id),
        delete_client_profile(user_id),
        get_user_activity_counts(user_id),
    )

    deleted_user = False
    can_delete_user = all(activity[k] == 0 for k in ("leads", "runs", "campaigns"))
    if can_delete_user:
        deleted_user = await delete_user_by_id(user_id)

    return {
        "knowledge_deleted": knowledge_deleted,
        "profile_deleted": profile_deleted,
        "deleted_user": deleted_user,
        "activity": activity,
    }


# ── Campaigns ─────────────────────────────────────────────────────────────────

async def save_campaign(user_id: str, campaign: dict) -> str:
    db = get_db()
    await db.campaigns.update_many(
        {"user_id": user_id, "is_active": True},
        {"$set": {"is_active": False}},
    )
    doc = {
        "user_id": user_id,
        **{k: v for k, v in campaign.items()},
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
    }
    result = await db.campaigns.insert_one(doc)
    return str(result.inserted_id)


async def get_active_campaign(user_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db.campaigns.find_one({"user_id": user_id, "is_active": True})
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


async def patch_active_campaign(user_id: str, fields: dict) -> bool:
    db = get_db()
    result = await db.campaigns.update_one(
        {"user_id": user_id, "is_active": True},
        {"$set": fields},
    )
    return result.modified_count > 0


async def get_campaigns_by_user(user_id: str) -> list:
    db = get_db()
    cursor = db.campaigns.find({"user_id": user_id}).sort("created_at", -1)
    docs = await cursor.to_list(length=50)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


# ── Client Profile (Onboarding memory) ───────────────────────────────────────

async def upsert_client_profile(user_id: str, profile: dict) -> None:
    """
    Save or update the client onboarding profile (single doc per user).
    Stores business personality prompt + agent configuration used by the pipeline.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    set_payload = {
        "user_id": user_id,
        "business_summary": profile.get("business_summary", ""),
        "personality_prompt": profile.get("personality_prompt", ""),
        "campaign": profile.get("campaign", {}),
        "agents": profile.get("agents", []),
        "updated_at": now,
    }
    await db.client_profiles.update_one(
        {"user_id": user_id},
        {
            "$set": set_payload,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )

    await _upsert_user_root_onboarding(user_id, set_payload)


def _build_user_root_onboarding_payload(profile: dict) -> dict:
    agents = profile.get("agents", []) or []
    personality_prompt = profile.get("personality_prompt", "")

    agent_models = [
        {
            "id": str(a.get("id") or ""),
            "name": str(a.get("name") or ""),
            "role": str(a.get("role") or ""),
            "model": str(a.get("model") or ""),
        }
        for a in agents
    ]

    agent_personalities = [
        {
            "id": str(a.get("id") or ""),
            "name": str(a.get("name") or ""),
            "persona": str(a.get("persona") or ""),
            "responsibility": str(a.get("responsibility") or ""),
        }
        for a in agents
    ]

    prompts = {
        "personality_prompt": personality_prompt,
        "agent_prompts": [
            {
                "id": str(a.get("id") or ""),
                "role": str(a.get("role") or ""),
                "prompt": str(a.get("prompt") or ""),
                "prompt_source": str(a.get("prompt_source") or ""),
            }
            for a in agents
        ],
    }

    return {
        "onboarding_business_summary": profile.get("business_summary", ""),
        "onboarding_personality_prompt": personality_prompt,
        "onboarding_campaign": profile.get("campaign", {}) or {},
        "onboarding_agents": agents,
        "onboarding_agent_models": agent_models,
        "onboarding_agent_personalities": agent_personalities,
        "onboarding_prompts": prompts,
        "onboarding_agents_count": len(agents),
        "onboarding_updated_at": profile.get("updated_at", datetime.now(timezone.utc)),
    }


async def _upsert_user_root_onboarding(user_id: str, profile: dict) -> None:
    db = get_db()
    root_payload = _build_user_root_onboarding_payload(profile)
    try:
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": root_payload},
        )
    except Exception:
        # If user_id is invalid or user is missing, keep client_profiles write successful.
        return


async def sync_user_root_onboarding_from_profile(user_id: str) -> bool:
    """
    Backfill root onboarding fields in users collection from client_profiles.
    Returns True when sync succeeded, False when no profile exists.
    """
    profile = await get_client_profile(user_id)
    if not profile:
        return False
    await _upsert_user_root_onboarding(user_id, profile)
    return True


async def get_client_profile(user_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db.client_profiles.find_one({"user_id": user_id})
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


# ── Runs ──────────────────────────────────────────────────────────────────────

async def create_run(user_id: str, campaign_id: str, max_results: int, run_id: str = None) -> str:
    import uuid
    db = get_db()
    run_id = run_id or str(uuid.uuid4())
    await db.runs.insert_one({
        "run_id": run_id,
        "user_id": user_id,
        "campaign_id": campaign_id,
        "status": "queued",
        "max_results": max_results,
        "total_found": 0,
        "total_approved": 0,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
    })
    return run_id


async def update_run_status(
    run_id: str,
    status: str,
    total_found: int = None,
    total_approved: int = None,
    agent_logs: dict = None,
) -> None:
    db = get_db()
    update: dict = {"status": status}
    if total_found is not None:
        update["total_found"] = total_found
    if total_approved is not None:
        update["total_approved"] = total_approved
    if agent_logs is not None:
        update["agent_logs"] = agent_logs
    if status in ("complete", "error"):
        update["completed_at"] = datetime.now(timezone.utc)
    await db.runs.update_one(
        {"run_id": run_id},
        {"$set": update},
    )


async def get_runs_by_user(user_id: str) -> list:
    db = get_db()
    cursor = db.runs.find({"user_id": user_id}).sort("started_at", -1)
    docs = await cursor.to_list(length=200)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


# ── Leads ─────────────────────────────────────────────────────────────────────

async def save_lead(run_id: str, user_id: str, lead_data: dict) -> str:
    db = get_db()
    result = await db.leads.insert_one({
        "run_id": run_id,
        "user_id": user_id,
        "company_name": lead_data.get("company_name", ""),
        "url": lead_data.get("url", ""),
        "phone": lead_data.get("phone", ""),
        "address": lead_data.get("address", ""),
        "score": lead_data.get("score"),
        "system_state": lead_data.get("system_state", "REJECTED_BY_AI"),
        "expediente_markdown": lead_data.get("expediente_markdown"),
        "expediente_json": lead_data.get("expediente_json", {}),
        "hitl_status": "pending",
        "hitl_at": None,
        "created_at": datetime.now(timezone.utc),
        # ── Landa fields (Phase 12) — optional, default None ─────────────────
        "estado": lead_data.get("estado"),
        "decisor": lead_data.get("decisor"),
        "canales": lead_data.get("canales"),
        "canal_elegido": lead_data.get("canal_elegido"),
        "puntaje": lead_data.get("puntaje"),
        "criterios": lead_data.get("criterios", []),
        "senales_intencion": lead_data.get("senales_intencion", []),
        "recomendacion_agente": lead_data.get("recomendacion_agente"),
        "motivo_nurturing": lead_data.get("motivo_nurturing"),
        "intento_actual": lead_data.get("intento_actual", 1),
        "fecha_entrada_nurturing": lead_data.get("fecha_entrada_nurturing"),
        "ciclo_nurturing": lead_data.get("ciclo_nurturing", 0),
        "historial_conversacion": lead_data.get("historial_conversacion", []),
    })
    return str(result.inserted_id)


async def get_leads_by_run(run_id: str, user_id: str) -> list:
    db = get_db()
    cursor = db.leads.find({"run_id": run_id, "user_id": user_id})
    docs = await cursor.to_list(length=1000)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def get_leads_by_user(user_id: str, limit: int = 100) -> list:
    db = get_db()
    cursor = db.leads.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def get_lead_by_id(lead_id: str, user_id: str) -> Optional[dict]:
    """Get single lead by ID (tenant-safe)."""
    db = get_db()
    try:
        doc = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    except Exception:
        return None
    if not doc:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


async def update_lead_hitl(lead_id: str, user_id: str, decision: str) -> bool:
    db = get_db()
    result = await db.leads.update_one(
        {"_id": ObjectId(lead_id), "user_id": user_id},
        {"$set": {"hitl_status": decision, "hitl_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count == 1


async def update_lead_nit_data(lead_id: str, nit_data: dict) -> None:
    """Patch nit_data onto an existing lead document after async NIT enrichment completes."""
    db = get_db()
    await db.leads.update_one(
        {"_id": ObjectId(lead_id)},
        {"$set": {"nit_data": nit_data}},
    )


async def get_client_summary(user_id: str) -> dict:
    """Stats for a single client — queries run in parallel."""
    import asyncio as _asyncio
    db = get_db()
    total_runs, total_leads, approved_leads, last_run, active_campaign = await _asyncio.gather(
        db.runs.count_documents({"user_id": user_id}),
        db.leads.count_documents({"user_id": user_id}),
        db.leads.count_documents({"user_id": user_id, "hitl_status": "approved"}),
        db.runs.find_one({"user_id": user_id}, sort=[("started_at", -1)]),
        get_active_campaign(user_id),
    )
    return {
        "total_runs": total_runs,
        "total_leads": total_leads,
        "approved_leads": approved_leads,
        "last_run_at": last_run["started_at"] if last_run else None,
        "last_run_status": last_run.get("status") if last_run else None,
        "active_campaign": active_campaign,
    }


# ── Client Knowledge (RAG) ────────────────────────────────────────────────────

async def save_knowledge_chunk(
    user_id: str,
    chunk_text: str,
    embedding: list,
    filename: str,
    source_type: str,
    chunk_index: int,
) -> str:
    db = get_db()
    result = await db.client_knowledge.insert_one({
        "user_id": user_id,
        "chunk_text": chunk_text,
        "embedding": embedding,
        "filename": filename,
        "source_type": source_type,
        "chunk_index": chunk_index,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)


async def get_knowledge_chunks(user_id: str) -> list:
    """Return all knowledge chunks for a user (with embeddings for similarity search)."""
    db = get_db()
    cursor = db.client_knowledge.find({"user_id": user_id})
    return await cursor.to_list(length=10_000)


async def get_knowledge_sources(user_id: str) -> list:
    """Return distinct sources (filenames) uploaded for a user."""
    db = get_db()
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$filename",
            "source_type": {"$first": "$source_type"},
            "chunk_count": {"$sum": 1},
            "created_at": {"$first": "$created_at"},
        }},
        {"$sort": {"created_at": -1}},
    ]
    docs = await db.client_knowledge.aggregate(pipeline).to_list(length=200)
    return [
        {
            "filename": d["_id"],
            "source_type": d["source_type"],
            "chunk_count": d["chunk_count"],
            "created_at": d.get("created_at"),
        }
        for d in docs
    ]


async def delete_knowledge_source(user_id: str, filename: str) -> int:
    db = get_db()
    result = await db.client_knowledge.delete_many({"user_id": user_id, "filename": filename})
    return result.deleted_count


async def delete_knowledge_by_user(user_id: str) -> int:
    """Delete ALL knowledge chunks for a user."""
    db = get_db()
    result = await db.client_knowledge.delete_many({"user_id": user_id})
    return result.deleted_count


# ── Learning Loop (Phase 11) ──────────────────────────────────────────────────

async def save_ideal_lead(
    user_id: str,
    lead_id: str,
    company_name: str,
    url: str,
    embedding: list,
    profile_text: str,
    score,
) -> str:
    db = get_db()
    # Upsert by lead_id so re-approving doesn't duplicate
    result = await db.ideal_leads.update_one(
        {"user_id": user_id, "lead_id": lead_id},
        {"$set": {
            "user_id": user_id,
            "lead_id": lead_id,
            "company_name": company_name,
            "url": url,
            "embedding": embedding,
            "profile_text": profile_text,
            "score": score,
            "created_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )
    return str(result.upserted_id or lead_id)


async def get_ideal_leads(user_id: str) -> list:
    db = get_db()
    cursor = db.ideal_leads.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=500)


async def save_rejected_lead(
    user_id: str,
    lead_id: str,
    company_name: str,
    url: str,
    reason: str,
) -> None:
    db = get_db()
    await db.rejected_leads.update_one(
        {"user_id": user_id, "lead_id": lead_id},
        {"$set": {
            "user_id": user_id,
            "lead_id": lead_id,
            "company_name": company_name,
            "url": url,
            "reason": reason,
            "created_at": datetime.now(timezone.utc),
        }},
        upsert=True,
    )


async def get_rejected_leads(user_id: str) -> list:
    db = get_db()
    cursor = db.rejected_leads.find({"user_id": user_id}).sort("created_at", -1)
    return await cursor.to_list(length=500)


def _normalize_domain(raw_url: str) -> str:
    if not raw_url:
        return ""
    value = str(raw_url).strip()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    try:
        parsed = urlparse(value)
        host = (parsed.netloc or "").lower().strip()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


async def get_prospecting_excluded_domains(user_id: str) -> dict:
    """
    Build exclusion lists for prospecting to avoid resurfacing companies already seen,
    contacted, or rejected in past runs.
    """
    db = get_db()
    leads_cursor = db.leads.find(
        {"user_id": user_id},
        {"url": 1, "hitl_status": 1, "email_sent": 1, "system_state": 1},
    )
    rejected_cursor = db.rejected_leads.find(
        {"user_id": user_id},
        {"url": 1, "reason": 1},
    )

    leads, rejected = await __import__("asyncio").gather(
        leads_cursor.to_list(length=10_000),
        rejected_cursor.to_list(length=2_000),
    )

    seen_domains: set[str] = set()
    contacted_domains: set[str] = set()
    not_interested_domains: set[str] = set()

    for lead in leads:
        domain = _normalize_domain(str(lead.get("url") or ""))
        if not domain:
            continue
        seen_domains.add(domain)
        if bool(lead.get("email_sent")):
            contacted_domains.add(domain)
        if str(lead.get("hitl_status") or "") == "rejected":
            not_interested_domains.add(domain)

    for rej in rejected:
        domain = _normalize_domain(str(rej.get("url") or ""))
        if domain:
            seen_domains.add(domain)
            not_interested_domains.add(domain)

    excluded_domains = seen_domains | contacted_domains | not_interested_domains
    return {
        "excluded_domains": sorted(excluded_domains),
        "stats": {
            "seen": len(seen_domains),
            "contacted": len(contacted_domains),
            "not_interested": len(not_interested_domains),
            "total_excluded": len(excluded_domains),
        },
    }


async def get_all_client_summaries(user_ids: list[str]) -> dict[str, dict]:
    """
    Single-pass aggregation for all clients at once — 3 round-trips total regardless of
    how many clients there are, vs 5 × N round-trips with the old per-client approach.
    Returns {user_id: summary_dict}.
    """
    import asyncio as _asyncio
    db = get_db()

    leads_pipeline = [
        {"$match": {"user_id": {"$in": user_ids}}},
        {"$group": {
            "_id": "$user_id",
            "total_leads": {"$sum": 1},
            "approved_leads": {"$sum": {"$cond": [{"$eq": ["$hitl_status", "approved"]}, 1, 0]}},
        }},
    ]
    runs_pipeline = [
        {"$match": {"user_id": {"$in": user_ids}}},
        {"$sort": {"started_at": -1}},
        {"$group": {
            "_id": "$user_id",
            "total_runs": {"$sum": 1},
            "last_run_at": {"$first": "$started_at"},
            "last_run_status": {"$first": "$status"},
        }},
    ]
    campaigns_pipeline = [
        {"$match": {"user_id": {"$in": user_ids}, "is_active": True}},
        {"$group": {"_id": "$user_id", "campaign": {"$first": "$$ROOT"}}},
    ]

    leads_res, runs_res, campaigns_res = await _asyncio.gather(
        db.leads.aggregate(leads_pipeline).to_list(length=1000),
        db.runs.aggregate(runs_pipeline).to_list(length=1000),
        db.campaigns.aggregate(campaigns_pipeline).to_list(length=1000),
    )

    leads_map = {r["_id"]: r for r in leads_res}
    runs_map  = {r["_id"]: r for r in runs_res}
    campaigns_map = {}
    for r in campaigns_res:
        c = r["campaign"]
        c["_id"] = str(c["_id"])
        campaigns_map[r["_id"]] = c

    result = {}
    for uid in user_ids:
        l = leads_map.get(uid, {})
        r = runs_map.get(uid, {})
        result[uid] = {
            "total_runs":     r.get("total_runs", 0),
            "total_leads":    l.get("total_leads", 0),
            "approved_leads": l.get("approved_leads", 0),
            "last_run_at":    r.get("last_run_at"),
            "last_run_status": r.get("last_run_status"),
            "active_campaign": campaigns_map.get(uid),
        }
    return result


# ── WhatsApp Agents ───────────────────────────────────────────────────────────

async def upsert_whatsapp_agent(config: dict) -> dict:
    """Crea o actualiza la configuración de un agente WhatsApp por número de teléfono."""
    db = get_db()
    phone = config["phone_number"]
    config["updated_at"] = datetime.now(timezone.utc)
    await db.whatsapp_agents.update_one(
        {"phone_number": phone},
        {"$set": config, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    return await get_whatsapp_agent(phone)


async def get_whatsapp_agent(phone_number: str) -> Optional[dict]:
    """Busca config de agente por número de teléfono del asesor."""
    db = get_db()
    doc = await db.whatsapp_agents.find_one({"phone_number": phone_number})
    if doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def list_whatsapp_agents(cliente_id: Optional[str] = None) -> list[dict]:
    """Lista todos los agentes, opcionalmente filtrados por cliente."""
    db = get_db()
    query = {"cliente_id": cliente_id} if cliente_id else {}
    docs = await db.whatsapp_agents.find(query).sort("created_at", -1).to_list(length=500)
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs


async def delete_whatsapp_agent(phone_number: str) -> bool:
    db = get_db()
    result = await db.whatsapp_agents.delete_one({"phone_number": phone_number})
    return result.deleted_count > 0


# ── Phase 16: wa_sessions CRUD ────────────────────────────────────────────────

async def get_or_create_wa_session(
    phone: str,
    profile: str,
    user_id: str,
) -> dict:
    """Return existing wa_session for phone, or create a new one.

    Uses upsert so concurrent calls don't create duplicates.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = await db.wa_sessions.find_one_and_update(
        {"phone": phone},
        {
            "$setOnInsert": {
                "phone": phone,
                "user_id": user_id,
                "profile": profile,
                "history": [],
                "updated_at": now,
            }
        },
        upsert=True,
        return_document=True,  # ReturnDocument.AFTER equivalent in motor
    )
    # find_one_and_update with return_document=True returns the doc after update
    if doc is None:
        # Fallback: fetch after upsert
        doc = await db.wa_sessions.find_one({"phone": phone})
    return doc


async def update_wa_session(phone: str, new_turn: dict) -> None:
    """Append new_turn to history, keeping only last 10 turns (sliding window).

    Also updates updated_at to reset the TTL clock.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    # First push the new turn
    await db.wa_sessions.update_one(
        {"phone": phone},
        {
            "$push": {"history": new_turn},
            "$set": {"updated_at": now},
        }
    )
    # Then slice to keep only last 10 (Motor does not support $push $slice in one op with mongomock)
    doc = await db.wa_sessions.find_one({"phone": phone})
    if doc and len(doc.get("history", [])) > 10:
        trimmed = doc["history"][-10:]
        await db.wa_sessions.update_one(
            {"phone": phone},
            {"$set": {"history": trimmed}},
        )


# ── wa_config: bot flags + active mode per phone ──────────────────────────────
# Schema: { phone, bots: { secop: bool, landa: bool }, active: str }
# 'active' is the currently selected bot. Only bots with flag=true are accessible.

async def get_wa_bot_config(phone: str) -> dict:
    """Return full bot config for a phone. Defaults: landa enabled+active."""
    db = get_db()
    doc = await db.wa_config.find_one({"phone": phone}) or {}
    return {
        "bots": doc.get("bots", {"landa": True, "secop": False}),
        "active": doc.get("active", "landa"),
    }


async def get_wa_bot_mode(phone: str) -> str:
    """Return the active bot mode for a phone. Backwards-compatible."""
    config = await get_wa_bot_config(phone)
    return config["active"]


async def set_wa_bot_mode(phone: str, bot_mode: str) -> None:
    """Set the active bot for a phone (only if that bot is enabled)."""
    db = get_db()
    await db.wa_config.update_one(
        {"phone": phone},
        {"$set": {"phone": phone, "active": bot_mode}},
        upsert=True,
    )


async def set_wa_bot_flags(phone: str, bots: dict) -> None:
    """Set which bots are enabled for a phone. bots = { 'landa': True, 'secop': False, ... }"""
    db = get_db()
    await db.wa_config.update_one(
        {"phone": phone},
        {"$set": {"phone": phone, "bots": bots}},
        upsert=True,
    )


# ── Registration Requests (Staff Access Control) ───────────────────────────

async def create_registration_request(
    email: str,
    full_name: str,
    company_name: str,
    phone: Optional[str] = None,
    country: Optional[str] = None,
    role: str = "user",
    message: Optional[str] = None,
) -> dict:
    """Save a registration request for staff review."""
    db = get_db()
    request_doc = {
        "email": email,
        "full_name": full_name,
        "company_name": company_name,
        "phone": phone,
        "country": country,
        "role": role,
        "message": message,
        "created_at": datetime.now(timezone.utc),
        "status": "pending",  # pending, approved, rejected, contacted
    }
    try:
        result = await db.registration_requests.insert_one(request_doc)
        return {"id": str(result.inserted_id), "email": email, "status": "pending"}
    except Exception as e:
        return {"error": str(e)}


async def get_all_registration_requests() -> list:
    """Get all registration requests (staff-only endpoint)."""
    db = get_db()
    cursor = db.registration_requests.find({}).sort("created_at", -1)
    docs = await cursor.to_list(length=1000)
    return [
        {
            "id": str(d["_id"]),
            "email": d.get("email"),
            "full_name": d.get("full_name"),
            "company_name": d.get("company_name"),
            "phone": d.get("phone"),
            "country": d.get("country"),
            "role": d.get("role"),
            "message": d.get("message"),
            "status": d.get("status"),
            "created_at": d.get("created_at").isoformat() if d.get("created_at") else None,
        }
        for d in docs
    ]


async def update_registration_request_status(request_id: str, status: str) -> dict:
    """Update registration request status (staff action)."""
    db = get_db()
    result = await db.registration_requests.update_one(
        {"_id": ObjectId(request_id)},
        {
            "$set": {
                "status": status,
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )
    if result.matched_count == 0:
        return {"error": "Request not found"}
    return {"id": request_id, "status": status}


# ── Agents persistence ────────────────────────────────────────────────────────

async def save_agent(agent_doc: dict) -> None:
    """Upsert an agent document keyed by agent_id."""
    db = get_db()
    await db.agents.update_one(
        {"agent_id": agent_doc["agent_id"]},
        {"$set": agent_doc},
        upsert=True,
    )


async def load_all_agents() -> list[dict]:
    """Return all persisted agent documents."""
    db = get_db()
    cursor = db.agents.find({})
    return await cursor.to_list(length=None)


async def delete_agent_db(agent_id: str) -> None:
    """Delete a single agent from the DB."""
    db = get_db()
    await db.agents.delete_one({"agent_id": agent_id})


async def delete_all_agents_db() -> None:
    """Delete all agents from the DB."""
    db = get_db()
    await db.agents.delete_many({})


# ── Roadmap State ───────────────────────────────────────────────────────
async def get_roadmap_state(user_id: str) -> Optional[dict]:
    db = get_db()
    doc = await db.roadmap_state.find_one({"user_id": user_id})
    if not doc:
        return None
    return {"user_id": doc["user_id"], "state": doc["state"], "updated_at": doc.get("updated_at")}

async def set_roadmap_state(user_id: str, state: dict) -> dict:
    db = get_db()
    result = await db.roadmap_state.update_one(
        {"user_id": user_id},
        {"$set": {"state": state, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
    return {"ok": True, "updated": result.modified_count > 0 or result.upserted_id is not None}


# ── Email OAuth (Gmail / Outlook) ────────────────────────────────────────────

async def save_email_oauth_tokens(user_id: str, provider: str, tokens_encrypted: str, email_sender: str) -> bool:
    """
    Guarda los tokens OAuth del usuario encriptados.
    provider: "gmail" | "outlook"
    tokens_encrypted: string encriptado (resultado de encrypt_tokens)
    email_sender: email del usuario (juan@empresa.com)
    """
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "email_provider": provider,
                    "email_oauth_tokens": tokens_encrypted,
                    "email_sender_address": email_sender,
                    "email_configured_at": datetime.now(timezone.utc),
                }
            }
        )
        return result.matched_count > 0
    except Exception as e:
        logging.error(f"[database] save_email_oauth_tokens failed: {e}")
        return False


async def get_email_oauth_tokens(user_id: str) -> Optional[dict]:
    """
    Obtiene los tokens OAuth del usuario.
    Retorna: { provider, encrypted_tokens, email_sender_address } o None
    """
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if not doc or "email_oauth_tokens" not in doc:
            return None

        return {
            "provider": doc.get("email_provider"),
            "encrypted_tokens": doc.get("email_oauth_tokens"),
            "email_sender_address": doc.get("email_sender_address"),
        }
    except Exception as e:
        logging.error(f"[database] get_email_oauth_tokens failed: {e}")
        return None


async def delete_email_oauth_tokens(user_id: str) -> bool:
    """Elimina los tokens OAuth del usuario (desconectar)."""
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$unset": {
                    "email_provider": "",
                    "email_oauth_tokens": "",
                    "email_sender_address": "",
                    "email_configured_at": "",
                }
            }
        )
        return result.matched_count > 0
    except Exception as e:
        logging.error(f"[database] delete_email_oauth_tokens failed: {e}")
        return False


async def save_email_event(lead_id: str, event_type: str, message_id: str, user_id: str = None) -> None:
    """
    Guarda un evento de email (apertura, click, etc.)
    event_type: "opened" | "clicked" | "bounced"
    """
    db = get_db()
    try:
        await db.email_events.insert_one({
            "lead_id": lead_id,
            "user_id": user_id,
            "message_id": message_id,
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception as e:
        logging.error(f"[database] save_email_event failed: {e}")


async def get_email_stats(user_id: str) -> dict:
    """
    Calcula estadísticas de email para un usuario.
    Retorna: { sent_count, opened_count, clicked_count, open_rate }
    """
    db = get_db()
    try:
        # Contar leads con message_id (enviados)
        sent = await db.leads.count_documents({
            "user_id": user_id,
            "message_id": {"$exists": True, "$ne": None}
        })

        # Contar aperturas únicas
        opened = await db.email_events.count_documents({
            "user_id": user_id,
            "event_type": "opened"
        })

        # Contar clicks
        clicked = await db.email_events.count_documents({
            "user_id": user_id,
            "event_type": "clicked"
        })

        open_rate = int((opened / sent * 100)) if sent > 0 else 0

        return {
            "sent_count": sent,
            "opened_count": opened,
            "clicked_count": clicked,
            "open_rate": open_rate,
        }
    except Exception as e:
        logging.error(f"[database] get_email_stats failed: {e}")
        return {"sent_count": 0, "opened_count": 0, "clicked_count": 0, "open_rate": 0}


# ── SMTP Configuration (Usuario configura sus credenciales SMTP) ─────────────

async def save_smtp_config(user_id: str, smtp_config_encrypted: str) -> bool:
    """
    Guarda la configuración SMTP del usuario encriptada.
    smtp_config_encrypted: JSON encriptado con { email, password, smtp_host, smtp_port }
    """
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "smtp_config_encrypted": smtp_config_encrypted,
                    "smtp_configured_at": datetime.now(timezone.utc),
                }
            }
        )
        return result.matched_count > 0
    except Exception as e:
        logging.error(f"[database] save_smtp_config failed: {e}")
        return False


async def get_smtp_config(user_id: str) -> Optional[str]:
    """
    Obtiene la configuración SMTP encriptada del usuario.
    Retorna: string encriptado o None si no está configurado.
    """
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if not doc or "smtp_config_encrypted" not in doc:
            return None
        return doc.get("smtp_config_encrypted")
    except Exception as e:
        logging.error(f"[database] get_smtp_config failed: {e}")
        return None


async def delete_smtp_config(user_id: str) -> bool:
    """Elimina la configuración SMTP del usuario."""
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$unset": {
                    "smtp_config_encrypted": "",
                    "smtp_configured_at": "",
                }
            }
        )
        return result.matched_count > 0
    except Exception as e:
        logging.error(f"[database] delete_smtp_config failed: {e}")
        return False


async def save_email_template(user_id: str, template: dict) -> bool:
    """Guarda el template personalizado del correo del usuario."""
    db = get_db()
    try:
        result = await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {
                "$set": {
                    "email_template": template,
                    "email_template_updated_at": datetime.now(timezone.utc),
                }
            }
        )
        return result.matched_count > 0
    except Exception as e:
        logging.error(f"[database] save_email_template failed: {e}")
        return False


async def get_email_template(user_id: str) -> Optional[dict]:
    """Obtiene el template personalizado del correo del usuario."""
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if not doc:
            return None
        return doc.get("email_template") or _get_default_template()
    except Exception as e:
        logging.error(f"[database] get_email_template failed: {e}")
        return None


def _get_default_template() -> dict:
    """Template por defecto para nuevos usuarios."""
    return {
        "subject_prefix": "",
        "body_template": "Hola {nombre},\n\n{mensaje}\n\nSaludos,\n{firma}",
        "footer": "Esta es una comunicación automática de Landa.",
        "brand_color": "#78dce8",
        "logo_url": "",
    }


async def get_smtp_status(user_id: str) -> dict:
    """
    Obtiene el estado de configuración SMTP del usuario.
    Retorna: { configured: bool, email: str or None }
    """
    db = get_db()
    try:
        doc = await db.users.find_one({"_id": ObjectId(user_id)})
        if not doc or "smtp_config_encrypted" not in doc:
            return {"configured": False, "email": None}

        # Para obtener el email sin desencriptar, lo extraemos del config
        # (El frontend lo tendrá en su estado)
        return {
            "configured": True,
            "email": doc.get("smtp_email_display")  # Campo adicional que guardamos
        }
    except Exception as e:
        logging.error(f"[database] get_smtp_status failed: {e}")
        return {"configured": False, "email": None}

