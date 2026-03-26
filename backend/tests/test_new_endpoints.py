"""
test_new_endpoints.py — Tests for:
  GET /api/leads/{lead_id}
  GET /api/leads/{lead_id}/draft
  GET /api/staff/stats
  GET /api/staff/agents/active

Nota: el helper _make_user crea usuarios directamente en la DB mock
(evita pasar por /auth/register que es interceptado por el mount de StaticFiles en tests).
"""
from datetime import datetime, timezone


async def _make_user(db, email: str, role: str = "client") -> tuple[str, str]:
    """Insert user directly and return (user_id, jwt_token)."""
    import auth
    result = await db.users.insert_one({
        "email": email,
        "hashed_password": auth.hash_password("secret"),
        "role": role,
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = auth.create_access_token({"sub": user_id, "role": role})
    return user_id, token


# ── GET /api/leads/{lead_id} ──────────────────────────────────────────────────

async def test_get_lead_returns_full_doc(async_client):
    """GET /api/leads/{lead_id} returns full lead with expediente_json."""
    import database
    db = database.get_db()
    user_id, token = await _make_user(db, "lead1@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    lead_id = await database.save_lead(
        run_id="run-123",
        user_id=user_id,
        lead_data={
            "company_name": "Test Corp",
            "score": 85,
            "expediente_json": {
                "decisor": {"nombre": "John", "email": "john@test.com"},
                "borradores": {"email_cuerpo": "Hello", "email_asuntos": ["Subject 1"]},
            },
        },
    )

    resp = await async_client.get(f"/api/leads/{lead_id}", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["company_name"] == "Test Corp"
    assert data["expediente_json"]["decisor"]["nombre"] == "John"
    assert data["_id"] == lead_id


async def test_get_lead_404_not_found(async_client):
    """GET /api/leads/{lead_id} returns 404 for invalid/missing lead."""
    import database
    db = database.get_db()
    _, token = await _make_user(db, "lead2@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    # Valid-format ObjectId that doesn't exist
    from bson import ObjectId as _ObjId
    fake_id = str(_ObjId())
    resp = await async_client.get(f"/api/leads/{fake_id}", headers=headers)
    assert resp.status_code == 404


async def test_get_lead_cross_tenant_returns_404(async_client):
    """GET /api/leads/{lead_id} must not return another user's lead."""
    import database
    db = database.get_db()
    user1_id, _      = await _make_user(db, "owner@test.com")
    _,        token2 = await _make_user(db, "other@test.com")

    lead_id = await database.save_lead(
        run_id="run-x",
        user_id=user1_id,
        lead_data={"company_name": "Secret Corp"},
    )

    resp = await async_client.get(
        f"/api/leads/{lead_id}",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert resp.status_code == 404


# ── GET /api/leads/{lead_id}/draft ───────────────────────────────────────────

async def test_get_lead_draft_returns_email_preview(async_client):
    """GET /api/leads/{lead_id}/draft returns email_draft block."""
    import database
    db = database.get_db()
    user_id, token = await _make_user(db, "draft1@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    lead_id = await database.save_lead(
        run_id="run-456",
        user_id=user_id,
        lead_data={
            "company_name": "Draft Corp",
            "expediente_json": {
                "decisor": {"nombre": "Jane", "email": "jane@test.com"},
                "borradores": {
                    "email_cuerpo": "Test body",
                    "email_asuntos": ["Subj1", "Subj2"],
                },
            },
        },
    )

    resp = await async_client.get(f"/api/leads/{lead_id}/draft", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "email_draft" in data
    assert data["email_draft"]["cuerpo"] == "Test body"
    assert data["email_draft"]["asuntos"] == ["Subj1", "Subj2"]
    assert data["email_draft"]["decisor"]["email"] == "jane@test.com"


async def test_get_lead_draft_empty_expediente(async_client):
    """GET /api/leads/{lead_id}/draft returns empty fields when no expediente_json."""
    import database
    db = database.get_db()
    user_id, token = await _make_user(db, "draft2@test.com")
    headers = {"Authorization": f"Bearer {token}"}

    lead_id = await database.save_lead(
        run_id="run-empty",
        user_id=user_id,
        lead_data={"company_name": "Empty Corp", "expediente_json": {}},
    )

    resp = await async_client.get(f"/api/leads/{lead_id}/draft", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["email_draft"]["asuntos"] == []
    assert data["email_draft"]["cuerpo"] == ""
    assert data["email_draft"]["decisor"] == {}


# ── GET /api/staff/stats ─────────────────────────────────────────────────────

async def test_get_staff_stats_returns_global_and_per_client(async_client):
    """GET /api/staff/stats returns global totals + per-client list."""
    import database
    db = database.get_db()
    _, staff_token = await _make_user(db, "stats_staff@test.com", role="staff")
    headers = {"Authorization": f"Bearer {staff_token}"}

    # Create 2 clients with 3 leads each
    for i in range(2):
        client_id, _ = await _make_user(db, f"stats_client{i}@test.com", role="client")
        for j in range(3):
            await db.leads.insert_one({
                "user_id": client_id,
                "company_name": f"Corp{i}{j}",
                "hitl_status": "pending",
                "created_at": datetime.now(timezone.utc),
            })

    resp = await async_client.get("/api/staff/stats", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "global" in data
    assert "per_client" in data
    assert data["global"]["total_leads"] == 6
    assert data["global"]["total_clients"] == 2
    assert len(data["per_client"]) == 2
    assert data["per_client"][0]["total_leads"] == 3


async def test_staff_stats_requires_staff_role(async_client):
    """GET /api/staff/stats returns 403 for non-staff."""
    import database
    db = database.get_db()
    _, client_token = await _make_user(db, "nonstaf@test.com", role="client")
    headers = {"Authorization": f"Bearer {client_token}"}

    resp = await async_client.get("/api/staff/stats", headers=headers)
    assert resp.status_code == 403


# ── GET /api/staff/agents/active ─────────────────────────────────────────────

async def test_get_staff_agents_active_returns_registry(async_client):
    """GET /api/staff/agents/active returns pipeline_registry with 4 agents."""
    import database
    db = database.get_db()
    _, staff_token = await _make_user(db, "agents_staff@test.com", role="staff")
    headers = {"Authorization": f"Bearer {staff_token}"}

    resp = await async_client.get("/api/staff/agents/active", headers=headers)
    assert resp.status_code == 200
    data = resp.json()

    assert "pipeline_registry" in data
    assert "per_client_active" in data
    assert len(data["pipeline_registry"]) == 4
    assert data["pipeline_registry"][0]["name"] == "Buscador"


async def test_staff_agents_requires_staff_role(async_client):
    """GET /api/staff/agents/active returns 403 for non-staff."""
    import database
    db = database.get_db()
    _, client_token = await _make_user(db, "nonstaf2@test.com", role="client")
    headers = {"Authorization": f"Bearer {client_token}"}

    resp = await async_client.get("/api/staff/agents/active", headers=headers)
    assert resp.status_code == 403
