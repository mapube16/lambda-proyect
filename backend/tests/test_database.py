"""
Tests for database.py — aiosqlite user persistence.
TDD: these tests are written before implementation.
"""
import pytest
import asyncio
import os
import tempfile
import aiosqlite

# We must monkeypatch DATABASE_URL to use a temp file for isolation


@pytest.fixture
async def db_path(tmp_path):
    """Return a fresh DB path for each test."""
    return str(tmp_path / "test_hive_office.db")


@pytest.fixture
async def initialized_db(db_path, monkeypatch):
    """Import database module with DATABASE_URL patched to temp file, run init_db."""
    import database
    monkeypatch.setattr(database, "DATABASE_URL", db_path)
    await database.init_db()
    return database, db_path


@pytest.mark.asyncio
async def test_init_db_creates_users_table(db_path, monkeypatch):
    """init_db() creates the users table without error."""
    import database
    monkeypatch.setattr(database, "DATABASE_URL", db_path)
    await database.init_db()

    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ) as cursor:
            row = await cursor.fetchone()
    assert row is not None, "users table was not created"


@pytest.mark.asyncio
async def test_init_db_is_idempotent(db_path, monkeypatch):
    """Calling init_db() twice does not raise an error."""
    import database
    monkeypatch.setattr(database, "DATABASE_URL", db_path)
    await database.init_db()
    await database.init_db()  # second call must not raise


@pytest.mark.asyncio
async def test_get_user_by_email_returns_none_for_unknown(initialized_db):
    """get_user_by_email returns None for an email not in the DB."""
    database, db_path = initialized_db
    result = await database.get_user_by_email("unknown@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_create_user_returns_id_and_email(initialized_db):
    """create_user returns dict with id and email only — no hashed_password."""
    database, db_path = initialized_db
    result = await database.create_user("a@b.com", "$2b$hash_placeholder")
    assert "id" in result
    assert result["email"] == "a@b.com"
    assert "hashed_password" not in result, "hashed_password must not be in return value"


@pytest.mark.asyncio
async def test_create_user_id_is_positive_integer(initialized_db):
    """create_user returns an integer id >= 1."""
    database, db_path = initialized_db
    result = await database.create_user("b@c.com", "$2b$hash_placeholder")
    assert isinstance(result["id"], int)
    assert result["id"] >= 1


@pytest.mark.asyncio
async def test_get_user_by_email_returns_correct_row(initialized_db):
    """get_user_by_email returns dict with all required keys after insert."""
    database, db_path = initialized_db
    await database.create_user("found@example.com", "$2b$real_hash")
    user = await database.get_user_by_email("found@example.com")
    assert user is not None
    assert user["email"] == "found@example.com"
    assert user["hashed_password"] == "$2b$real_hash"
    assert "id" in user
    assert "created_at" in user


@pytest.mark.asyncio
async def test_duplicate_email_raises_integrity_error(initialized_db):
    """Inserting duplicate email raises aiosqlite.IntegrityError."""
    database, db_path = initialized_db
    await database.create_user("dup@example.com", "$2b$hash1")
    with pytest.raises(aiosqlite.IntegrityError):
        await database.create_user("dup@example.com", "$2b$hash2")
