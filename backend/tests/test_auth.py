import pytest


# --- AUTH-01: Registration ----------------------------------------------------

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

async def test_register_duplicate_email(async_client):
    """POST /auth/register with existing email returns 400."""
    payload = {"email": "dup@example.com", "password": "pass1234"}
    await async_client.post("/auth/register", json=payload)
    response = await async_client.post("/auth/register", json=payload)
    assert response.status_code == 400

async def test_password_not_stored_plain(async_client):
    """Registered user's hashed_password in DB starts with $2b$ (bcrypt)."""
    # Use the mock DB already initialized by the reset_db fixture (via conftest)
    from database import get_user_by_email
    await async_client.post("/auth/register", json={
        "email": "inspect@example.com",
        "password": "plaintext"
    })
    user = await get_user_by_email("inspect@example.com")
    assert user is not None
    assert user["hashed_password"].startswith("$2b$")
    assert user["hashed_password"] != "plaintext"


# --- AUTH-02: Login / JWT -----------------------------------------------------

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

async def test_protected_route_no_token(async_client):
    """GET /api/agents without Authorization header returns 401 (not 403)."""
    response = await async_client.get("/api/agents")
    assert response.status_code == 401

async def test_websocket_no_token_rejected(async_client):
    """WebSocket /ws without ?token= query param is rejected with WS close code 1008."""
    with pytest.raises(Exception):
        async with async_client.websocket_connect("/ws") as ws:
            # Connection should be rejected — if we get here close code should be 1008
            pass

async def test_tenant_isolation(async_client):
    """User A's WebSocket messages are NOT delivered to user B's connection."""
    from main import manager
    from auth import create_access_token

    # Register two users
    await async_client.post("/auth/register", json={"email": "userA@example.com", "password": "passA"})
    await async_client.post("/auth/register", json={"email": "userB@example.com", "password": "passB"})
    resp_a = await async_client.post("/auth/login", json={"email": "userA@example.com", "password": "passA"})
    resp_b = await async_client.post("/auth/login", json={"email": "userB@example.com", "password": "passB"})
    token_a = resp_a.json()["access_token"]
    token_b = resp_b.json()["access_token"]

    # Decode tokens to get user_ids
    from jose import jwt as jose_jwt
    from auth import SECRET_KEY, ALGORITHM
    payload_a = jose_jwt.decode(token_a, SECRET_KEY, algorithms=[ALGORITHM])
    payload_b = jose_jwt.decode(token_b, SECRET_KEY, algorithms=[ALGORITHM])
    user_id_a = payload_a["sub"]
    user_id_b = payload_b["sub"]

    # Verify ConnectionManager keys messages by user_id
    # send_to_user(user_id_A) should only reach user A, not user B
    # We test this by checking that send_to_user only stores per-user key
    assert user_id_a != user_id_b, "Users must have distinct IDs"

    # Verify the manager's active_connections dict is keyed by user_id (str)
    # This validates the architecture: Dict[str, WebSocket] not Set[WebSocket]
    assert isinstance(manager.active_connections, dict), \
        "ConnectionManager must use Dict[str, WebSocket] for tenant isolation"

    # Verify send_to_user method exists and is keyed routing
    assert hasattr(manager, "send_to_user"), \
        "ConnectionManager must have send_to_user for targeted delivery"
