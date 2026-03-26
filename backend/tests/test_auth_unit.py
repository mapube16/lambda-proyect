"""
Unit tests for auth.py — password hashing, JWT creation, and get_current_user dependency.
TDD: these tests are written before implementation (Plan 01-02).
These test the auth module functions directly (not via HTTP endpoints).
"""
import pytest
import os
from jose import jwt
from datetime import timedelta, datetime, timezone

# Use a test secret key
TEST_SECRET = "test-secret-key-for-testing-plan-01-02"
TEST_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def set_secret_env(monkeypatch):
    """Ensure SECRET_KEY env var is set for all auth tests."""
    monkeypatch.setenv("SECRET_KEY", TEST_SECRET)


# --- hash_password ---

def test_hash_password_returns_bcrypt_hash():
    """hash_password('secret') returns a string starting with $2b$."""
    from auth import hash_password
    h = hash_password("secret")
    assert isinstance(h, str)
    assert h.startswith("$2b$"), f"Expected bcrypt hash, got: {h[:10]}"


def test_hash_password_different_hashes_for_same_input():
    """Two hashes of the same password differ (bcrypt salting)."""
    from auth import hash_password
    h1 = hash_password("secret")
    h2 = hash_password("secret")
    assert h1 != h2, "Bcrypt should produce unique salted hashes"


# --- verify_password ---

def test_verify_password_returns_true_for_correct_password():
    """verify_password('secret', hash_password('secret')) returns True."""
    from auth import hash_password, verify_password
    h = hash_password("secret")
    assert verify_password("secret", h) is True


def test_verify_password_returns_false_for_wrong_password():
    """verify_password('wrong', hash_password('secret')) returns False."""
    from auth import hash_password, verify_password
    h = hash_password("secret")
    assert verify_password("wrong", h) is False


# --- create_access_token ---

def test_create_access_token_returns_jwt_string():
    """create_access_token returns a 3-part JWT string."""
    from auth import create_access_token
    token = create_access_token({"sub": "42"})
    assert isinstance(token, str)
    parts = token.split(".")
    assert len(parts) == 3, f"Expected JWT with 3 parts, got {len(parts)}"


def test_create_access_token_decodable_with_secret():
    """JWT is decodable with SECRET_KEY and contains sub claim."""
    from auth import create_access_token, SECRET_KEY, ALGORITHM
    token = create_access_token({"sub": "42"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert payload["sub"] == "42"


def test_create_access_token_contains_exp_claim():
    """JWT contains expiry claim."""
    from auth import create_access_token, SECRET_KEY, ALGORITHM
    token = create_access_token({"sub": "1"})
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    assert "exp" in payload


# --- get_current_user ---

@pytest.mark.asyncio
async def test_get_current_user_returns_user_id_for_valid_token():
    """get_current_user returns {'user_id': str, 'role': str} for a valid token."""
    from auth import create_access_token, get_current_user
    token = create_access_token({"sub": "42"})
    result = await get_current_user(token=token)
    assert result["user_id"] == "42"
    assert isinstance(result["user_id"], str)
    assert "role" in result


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_missing_token():
    """get_current_user raises HTTPException 401 when token is None."""
    from fastapi import HTTPException
    from auth import get_current_user
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=None)
    assert exc_info.value.status_code == 401, (
        f"Expected 401, got {exc_info.value.status_code}"
    )


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_tampered_token():
    """get_current_user raises HTTPException 401 for a tampered token."""
    from fastapi import HTTPException
    from auth import get_current_user
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token="tampered.jwt.token")
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_raises_401_for_expired_token():
    """get_current_user raises HTTPException 401 for expired token."""
    from fastapi import HTTPException
    from auth import get_current_user
    # Create token with negative expiry (already expired)
    expired_token = jwt.encode(
        {"sub": "42", "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        TEST_SECRET,
        algorithm=TEST_ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=expired_token)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_never_raises_403():
    """get_current_user raises 401, NEVER 403, even with missing token."""
    from fastapi import HTTPException
    from auth import get_current_user
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(token=None)
    assert exc_info.value.status_code != 403


def test_oauth2_scheme_has_auto_error_false():
    """oauth2_scheme is configured with auto_error=False to suppress automatic 403."""
    import auth
    assert auth.oauth2_scheme.auto_error is False
