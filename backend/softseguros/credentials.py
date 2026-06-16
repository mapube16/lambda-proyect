"""
softseguros/credentials.py — Fernet encryption + Mongo CRUD for per-user SOFTSEGUROS credentials.

All async functions accept `db` (Motor database) as first argument, consistent with
backend/cobranza/debtor_crud.py style. Plaintext passwords are NEVER logged — only
usernames may be referenced for diagnostics.
"""
import os
import logging
from datetime import datetime, timezone
from typing import Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

# ── Fail-fast on missing key at module import ─────────────────────────────────
_ENCRYPTION_KEY = os.getenv("SOFTSEGUROS_ENCRYPTION_KEY", "").strip()
if not _ENCRYPTION_KEY:
    raise RuntimeError(
        "SOFTSEGUROS_ENCRYPTION_KEY is missing or empty. Generate one with "
        '`python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` '
        "and set it in your environment before importing softseguros.credentials."
    )

try:
    _fernet = Fernet(_ENCRYPTION_KEY.encode())
except Exception as exc:  # invalid base64 / wrong length
    raise RuntimeError(
        f"SOFTSEGUROS_ENCRYPTION_KEY is not a valid Fernet key: {exc}"
    ) from exc


COLLECTION = "softseguros_credentials"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _encrypt(plaintext: str) -> str:
    """Encrypt plaintext; return base64 ciphertext string."""
    return _fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def _decrypt(ciphertext: str) -> str:
    """Decrypt base64 ciphertext; return plaintext. Raises InvalidToken on tamper."""
    return _fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")


async def save_credentials(db, user_id: str, username: str, password: str) -> None:
    """
    Encrypt password with Fernet and upsert credentials doc keyed by user_id.
    Never logs plaintext password.
    """
    now = _utcnow()
    encrypted = _encrypt(password)
    await db[COLLECTION].update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": username,
                "password_encrypted": encrypted,
                "updated_at": now,
            },
            "$setOnInsert": {
                "user_id": user_id,
                "configured_at": now,
            },
        },
        upsert=True,
    )
    logger.info("softseguros.save_credentials user_id=%s username=%r", user_id, username)


async def get_credentials(db, user_id: str) -> Optional[Tuple[str, str]]:
    """
    Read credentials doc, decrypt password, return (username, plaintext_password).
    Returns None if no doc exists or decryption fails.
    Plaintext password is NEVER logged.
    """
    doc = await db[COLLECTION].find_one({"user_id": user_id})
    if not doc:
        return None
    try:
        plaintext = _decrypt(doc["password_encrypted"])
    except (InvalidToken, KeyError) as exc:
        logger.error(
            "softseguros.get_credentials decryption failed user_id=%s err=%s",
            user_id, type(exc).__name__,
        )
        return None
    return doc["username"], plaintext


async def delete_credentials(db, user_id: str) -> bool:
    """Remove the credentials doc for a user. Returns True if deleted."""
    result = await db[COLLECTION].delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def is_configured(db, user_id: str) -> bool:
    """True if a credentials doc exists for this user."""
    doc = await db[COLLECTION].find_one({"user_id": user_id}, {"_id": 1})
    return doc is not None


async def get_configured_at(db, user_id: str) -> Optional[datetime]:
    """Return configured_at datetime or None."""
    doc = await db[COLLECTION].find_one({"user_id": user_id}, {"configured_at": 1})
    if not doc:
        return None
    return doc.get("configured_at")
