"""
database.py — aiosqlite user persistence for Phase 1 auth.
All DB operations are here. No other module touches aiosqlite directly.
"""
import aiosqlite
from typing import Optional

DATABASE_URL = "hive_office.db"


async def init_db() -> None:
    """Create users table if it does not exist. Call from lifespan on startup."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()


async def get_user_by_email(email: str) -> Optional[dict]:
    """Return user row as dict or None if not found."""
    async with aiosqlite.connect(DATABASE_URL) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, email, hashed_password, created_at FROM users WHERE email = ?",
            (email,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(email: str, hashed_password: str) -> dict:
    """Insert user, return {id, email}. Caller must pre-check for duplicates.
    Raises aiosqlite.IntegrityError on duplicate email.
    """
    async with aiosqlite.connect(DATABASE_URL) as db:
        cursor = await db.execute(
            "INSERT INTO users (email, hashed_password) VALUES (?, ?)",
            (email, hashed_password)
        )
        await db.commit()
        return {"id": cursor.lastrowid, "email": email}
