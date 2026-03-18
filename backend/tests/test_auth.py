import pytest


# --- AUTH-01: Registration ----------------------------------------------------

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_register_success(async_client):
    """POST /auth/register with new email returns 201, no password in body."""
    response = await async_client.post("/auth/register", json={
        "email": "test@example.com",
        "password": "securepass123"
    })
    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert "email" in body
    assert "password" not in body
    assert "hashed_password" not in body

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_register_duplicate_email(async_client):
    """POST /auth/register with existing email returns 400."""
    payload = {"email": "dup@example.com", "password": "pass1234"}
    await async_client.post("/auth/register", json=payload)
    response = await async_client.post("/auth/register", json=payload)
    assert response.status_code == 400

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_password_not_stored_plain(async_client):
    """Registered user's hashed_password in DB starts with $2b$ (bcrypt)."""
    # This test imports database directly to inspect storage
    from database import get_user_by_email, init_db
    await init_db()
    await async_client.post("/auth/register", json={
        "email": "inspect@example.com",
        "password": "plaintext"
    })
    user = await get_user_by_email("inspect@example.com")
    assert user is not None
    assert user["hashed_password"].startswith("$2b$")
    assert user["hashed_password"] != "plaintext"


# --- AUTH-02: Login / JWT -----------------------------------------------------

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_login_returns_jwt(async_client):
    """POST /auth/login with valid credentials returns access_token."""
    await async_client.post("/auth/register", json={
        "email": "login@example.com", "password": "pass5678"
    })
    response = await async_client.post("/auth/login", json={
        "email": "login@example.com", "password": "pass5678"
    })
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_login_wrong_password(async_client):
    """POST /auth/login with wrong password returns 401."""
    await async_client.post("/auth/register", json={
        "email": "wrong@example.com", "password": "correct"
    })
    response = await async_client.post("/auth/login", json={
        "email": "wrong@example.com", "password": "wrong"
    })
    assert response.status_code == 401


# --- AUTH-03: Route / WebSocket Protection ------------------------------------

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_protected_route_no_token(async_client):
    """GET /api/agents without Authorization header returns 401 (not 403)."""
    response = await async_client.get("/api/agents")
    assert response.status_code == 401

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_websocket_no_token_rejected(async_client):
    """WebSocket /ws without ?token= query param is rejected with WS close code 1008."""
    assert False, "websocket token guard: not implemented yet"

@pytest.mark.xfail(reason="not implemented yet", strict=True)
async def test_tenant_isolation(async_client):
    """User A's WebSocket messages are NOT delivered to user B's connection."""
    # Register two users
    await async_client.post("/auth/register", json={"email": "userA@example.com", "password": "passA"})
    await async_client.post("/auth/register", json={"email": "userB@example.com", "password": "passB"})
    resp_a = await async_client.post("/auth/login", json={"email": "userA@example.com", "password": "passA"})
    resp_b = await async_client.post("/auth/login", json={"email": "userB@example.com", "password": "passB"})
    token_a = resp_a.json()["access_token"]
    token_b = resp_b.json()["access_token"]
    # Connecting both; trigger a user-A-specific event and confirm B does not receive it
    # Full implementation after ConnectionManager is keyed — stub asserts False
    assert False, "tenant isolation: verify send_to_user delivers only to correct user"
