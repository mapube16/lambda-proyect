"""
database.py — Motor (async MongoDB) user persistence for Phase 1 auth.
All DB operations are here. No other module touches Motor directly.
"""
import os
from typing import Optional
from datetime import datetime, timezone
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
