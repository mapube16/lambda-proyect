"""
database.py — Motor (async MongoDB) persistence layer.
All DB operations are here. No other module touches Motor directly.
"""
import os
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGODB_DB", "hive_office")

# Module-level client — initialized in init_db(), overridable in tests
_client: Optional[AsyncIOMotorClient] = None


def get_db():
    """Return the database handle. Requires init_db() to have been called."""
    return _client[DB_NAME]


async def init_db(client: Optional[AsyncIOMotorClient] = None) -> None:
    """Connect to MongoDB and create indexes.
    Pass a custom client for testing (e.g. mongomock_motor).
    Call from lifespan on startup.
    """
    global _client
    _client = client or AsyncIOMotorClient(MONGODB_URI)
    db = _client[DB_NAME]
    # Unique index on email — enforces deduplication at the DB level
    await db.users.create_index("email", unique=True)
    # Campaigns indexes
    await db.campaigns.create_index([("user_id", 1), ("is_active", 1)])
    # Runs indexes
    await db.runs.create_index([("user_id", 1), ("started_at", -1)])
    # Leads indexes
    await db.leads.create_index([("run_id", 1), ("user_id", 1)])
    await db.leads.create_index([("user_id", 1), ("created_at", -1)])


# ── Users ─────────────────────────────────────────────────────────────────────

async def get_user_by_email(email: str) -> Optional[dict]:
    """Return user document as dict or None if not found."""
    db = get_db()
    doc = await db.users.find_one({"email": email})
    if doc is None:
        return None
    return {
        "id": str(doc["_id"]),
        "email": doc["email"],
        "hashed_password": doc["hashed_password"],
        "created_at": doc.get("created_at"),
    }


async def create_user(email: str, hashed_password: str) -> dict:
    """Insert user. Returns {id, email}.
    Raises pymongo.errors.DuplicateKeyError on duplicate email.
    """
    db = get_db()
    result = await db.users.insert_one({
        "email": email,
        "hashed_password": hashed_password,
        "created_at": datetime.now(timezone.utc),
    })
    return {"id": str(result.inserted_id), "email": email}


# ── Campaigns ─────────────────────────────────────────────────────────────────

async def save_campaign(user_id: str, campaign: dict) -> str:
    """Upsert active campaign for a user. Returns campaign_id as str.

    Deactivates all existing active campaigns for the user, then inserts a
    new document with is_active=True.
    """
    db = get_db()
    # Deactivate old active campaigns for this user
    await db.campaigns.update_many(
        {"user_id": user_id, "is_active": True},
        {"$set": {"is_active": False}},
    )
    doc = {
        "user_id": user_id,
        # 8 campaign vars (plus optional extras like llm_analista / llm_redactor)
        **{k: v for k, v in campaign.items()},
        "created_at": datetime.now(timezone.utc),
        "is_active": True,
    }
    result = await db.campaigns.insert_one(doc)
    return str(result.inserted_id)


async def get_active_campaign(user_id: str) -> Optional[dict]:
    """Get the active campaign for a user. Returns dict with str _id or None."""
    db = get_db()
    doc = await db.campaigns.find_one({"user_id": user_id, "is_active": True})
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


# ── Runs ──────────────────────────────────────────────────────────────────────

async def create_run(user_id: str, campaign_id: str, max_results: int) -> str:
    """Create a run document. Returns run_id as str."""
    db = get_db()
    result = await db.runs.insert_one({
        "user_id": user_id,
        "campaign_id": campaign_id,
        "status": "running",
        "max_results": max_results,
        "total_found": 0,
        "total_approved": 0,
        "started_at": datetime.now(timezone.utc),
        "completed_at": None,
    })
    return str(result.inserted_id)


async def update_run_status(
    run_id: str,
    status: str,
    total_found: int = None,
    total_approved: int = None,
) -> None:
    """Update run status and optionally counts."""
    db = get_db()
    update: dict = {"status": status}
    if total_found is not None:
        update["total_found"] = total_found
    if total_approved is not None:
        update["total_approved"] = total_approved
    if status in ("complete", "error"):
        update["completed_at"] = datetime.now(timezone.utc)
    await db.runs.update_one(
        {"_id": ObjectId(run_id)},
        {"$set": update},
    )


async def get_runs_by_user(user_id: str) -> list:
    """Return all runs for a user, most recent first."""
    db = get_db()
    cursor = db.runs.find({"user_id": user_id}).sort("started_at", -1)
    docs = await cursor.to_list(length=200)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


# ── Leads ─────────────────────────────────────────────────────────────────────

async def save_lead(run_id: str, user_id: str, lead_data: dict) -> str:
    """Insert a lead result. Returns lead_id as str."""
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
    })
    return str(result.inserted_id)


async def get_leads_by_run(run_id: str, user_id: str) -> list:
    """Get all leads for a run (tenant-safe: requires user_id match)."""
    db = get_db()
    cursor = db.leads.find({"run_id": run_id, "user_id": user_id})
    docs = await cursor.to_list(length=1000)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def get_leads_by_user(user_id: str, limit: int = 100) -> list:
    """Get recent leads for a user across all runs."""
    db = get_db()
    cursor = db.leads.find({"user_id": user_id}).sort("created_at", -1).limit(limit)
    docs = await cursor.to_list(length=limit)
    for doc in docs:
        doc["_id"] = str(doc["_id"])
    return docs


async def update_lead_hitl(lead_id: str, user_id: str, decision: str) -> bool:
    """Set hitl_status to 'approved' or 'rejected'. Returns True if updated.

    Tenant-safe: only updates if user_id matches.
    """
    db = get_db()
    result = await db.leads.update_one(
        {"_id": ObjectId(lead_id), "user_id": user_id},
        {"$set": {"hitl_status": decision, "hitl_at": datetime.now(timezone.utc)}},
    )
    return result.modified_count == 1
