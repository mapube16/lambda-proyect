"""
Test suite for 4 critical endpoints before Phase 16 UI rollout:
- GET /api/leads/{lead_id}
- GET /api/leads/{lead_id}/draft
- GET /api/staff/stats
- GET /api/staff/agents/active
"""
import pytest
from httpx import AsyncClient
import database
import auth
from datetime import datetime, timezone


async def _make_test_user(email: str, role: str = "client") -> str:
    """Insert user directly and return JWT token."""
    db = database.get_db()
    result = await db.users.insert_one({
        "email": email,
        "hashed_password": auth.hash_password("test123"),
        "role": role,
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    return auth.create_access_token({"sub": user_id, "role": role})


@pytest.fixture
async def client_token():
    """Create a client user and return JWT token."""
    return await _make_test_user("client@test.com", "client")


@pytest.fixture
async def staff_token():
    """Create a staff user and return JWT token."""
    return await _make_test_user("staff@test.com", "staff")


@pytest.fixture
async def lead_doc(client_token: str):
    """Create a sample lead and return its ID."""
    db = database.get_db()

    # Decode token to get client user_id
    from auth import SECRET_KEY, ALGORITHM
    from jose import jwt as _jwt
    payload = _jwt.decode(client_token, SECRET_KEY, algorithms=[ALGORITHM])
    client_id = payload["sub"]
    
    lead = {
        "user_id": client_id,
        "run_id": "run_001",
        "company_name": "Acme Corp",
        "url": "https://acme.com",
        "score": 85,
        "hitl_status": "pending",
        "estado": "checkpoint",
        "expediente_json": {
            "decisor": {
                "nombre": "John Doe",
                "cargo": "CEO",
                "email": "john@acme.com"
            },
            "borradores": {
                "email_asuntos": ["Re: Oportunidad de negocio"],
                "email_cuerpo": "Hola John,\n\nTe escribo para ofrecerte nuestros servicios..."
            }
        }
    }
    
    result = await db.leads.insert_one(lead)
    return str(result.inserted_id)


class TestGetLeadDetail:
    """Test GET /api/leads/{lead_id}"""
    
    async def test_get_lead_success(self, async_client: AsyncClient, client_token: str, lead_doc: str):
        """Client can retrieve their own lead."""
        resp = await async_client.get(
            f"/api/leads/{lead_doc}",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["company_name"] == "Acme Corp"
        assert data["score"] == 85
        assert data["estado"] == "checkpoint"
    
    async def test_get_lead_not_found(self, async_client: AsyncClient, client_token: str):
        """Return 404 for non-existent lead."""
        resp = await async_client.get(
            "/api/leads/invalid_id_12345",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()
    
    async def test_get_lead_unauthorized(self, async_client: AsyncClient, lead_doc: str):
        """Reject request without token."""
        resp = await async_client.get(f"/api/leads/{lead_doc}")
        assert resp.status_code in [401, 403]  # No token = 401 or 403
    
    async def test_get_lead_cross_tenant_blocked(self, async_client: AsyncClient, lead_doc: str):
        """Another client cannot see this lead."""
        other_token = await _make_test_user("other@test.com", "client")

        resp = await async_client.get(
            f"/api/leads/{lead_doc}",
            headers={"Authorization": f"Bearer {other_token}"}
        )
        assert resp.status_code == 404


class TestGetLeadDraft:
    """Test GET /api/leads/{lead_id}/draft"""
    
    async def test_get_draft_with_email(self, async_client: AsyncClient, client_token: str, lead_doc: str):
        """Draft endpoint returns email preview with expediente data."""
        resp = await async_client.get(
            f"/api/leads/{lead_doc}/draft",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify lead fields present
        assert data["company_name"] == "Acme Corp"
        
        # Verify email_draft object
        assert "email_draft" in data
        assert data["email_draft"]["decisor"]["nombre"] == "John Doe"
        assert data["email_draft"]["decisor"]["email"] == "john@acme.com"
        assert len(data["email_draft"]["asuntos"]) > 0
        assert "servicios" in data["email_draft"]["cuerpo"].lower()
    
    async def test_get_draft_no_expediente(self, async_client: AsyncClient, client_token: str):
        """Draft endpoint handles missing expediente gracefully."""
        db = database.get_db()
        from auth import SECRET_KEY, ALGORITHM
        from jose import jwt as _jwt
        payload = _jwt.decode(client_token, SECRET_KEY, algorithms=[ALGORITHM])
        client_id = payload["sub"]
        
        lead = {
            "user_id": client_id,
            "run_id": "run_002",
            "company_name": "Simple Lead",
            "url": "https://simple.com",
            "score": 60,
            "hitl_status": "pending",
        }
        
        result = await db.leads.insert_one(lead)
        lead_id = str(result.inserted_id)
        
        resp = await async_client.get(
            f"/api/leads/{lead_id}/draft",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "email_draft" in data
        assert data["email_draft"]["cuerpo"] == ""
    
    async def test_get_draft_not_found(self, async_client: AsyncClient, client_token: str):
        """Return 404 if lead doesn't exist."""
        resp = await async_client.get(
            "/api/leads/fake_id_9999/draft",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 404


class TestGetStaffStats:
    """Test GET /api/staff/stats"""
    
    async def test_get_stats_staff_only(self, async_client: AsyncClient, client_token: str):
        """Non-staff users cannot access stats."""
        resp = await async_client.get(
            "/api/staff/stats",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 403  # Forbidden for non-staff
    
    async def test_get_stats_global_totals(self, async_client: AsyncClient, staff_token: str, lead_doc: str):
        """Staff can see global stats across all clients."""
        resp = await async_client.get(
            "/api/staff/stats",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "global" in data
        assert "per_client" in data
        
        # Verify global fields
        assert "total_leads" in data["global"]
        assert "total_runs" in data["global"]
        assert "total_approved" in data["global"]
        assert "total_checkpoint" in data["global"]
        assert "active_runs" in data["global"]
        
        # Should count at least 1 lead (from lead_doc fixture)
        assert data["global"]["total_leads"] >= 1
    
    async def test_get_stats_per_client_breakdown(self, async_client: AsyncClient, staff_token: str, lead_doc: str):
        """Stats include per-client breakdown."""
        resp = await async_client.get(
            "/api/staff/stats",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify per-client structure
        assert isinstance(data["per_client"], list)
        assert len(data["per_client"]) >= 1
        
        client = data["per_client"][0]
        assert "client_id" in client
        assert "client_email" in client
        assert "total_leads" in client
        assert "total_runs" in client
        assert "approved_leads" in client
        assert "active_runs" in client
    
    async def test_get_stats_no_token(self, async_client: AsyncClient):
        """Reject request without token."""
        resp = await async_client.get("/api/staff/stats")
        assert resp.status_code in [401, 403]  # Unauthorized or Forbidden


class TestGetStaffAgentsActive:
    """Test GET /api/staff/agents/active"""
    
    async def test_get_agents_staff_only(self, async_client: AsyncClient, client_token: str):
        """Non-staff users cannot access agent activity."""
        resp = await async_client.get(
            "/api/staff/agents/active",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 403
    
    async def test_get_agents_structure(self, async_client: AsyncClient, staff_token: str):
        """Response has correct structure even with no active agents."""
        resp = await async_client.get(
            "/api/staff/agents/active",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # Verify structure
        assert "pipeline_registry" in data
        assert "per_client_active" in data
        
        # pipeline_registry should be a dict or list with agent definitions
        assert isinstance(data["pipeline_registry"], (dict, list))
        
        # per_client_active should be a list
        assert isinstance(data["per_client_active"], list)
    
    async def test_get_agents_no_token(self, async_client: AsyncClient):
        """Reject request without token."""
        resp = await async_client.get("/api/staff/agents/active")
        assert resp.status_code in [401, 403]  # Unauthorized or Forbidden


class TestEndpointIntegration:
    """Integration tests for all 4 endpoints together."""
    
    async def test_client_workflow(self, async_client: AsyncClient, client_token: str, lead_doc: str):
        """Typical client workflow: list leads → view detail → get draft → (in UI: copy & send)."""
        
        # 1. Client gets their leads
        resp = await async_client.get(
            "/api/leads",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        leads = resp.json()
        assert len(leads) >= 1
        
        # 2. Client views lead detail
        resp = await async_client.get(
            f"/api/leads/{lead_doc}",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        lead_detail = resp.json()
        assert lead_detail["company_name"] == "Acme Corp"
        
        # 3. Client gets email draft preview
        resp = await async_client.get(
            f"/api/leads/{lead_doc}/draft",
            headers={"Authorization": f"Bearer {client_token}"}
        )
        assert resp.status_code == 200
        draft = resp.json()
        assert "email_draft" in draft
        assert len(draft["email_draft"]["asuntos"]) > 0
    
    async def test_staff_monitoring_workflow(self, async_client: AsyncClient, staff_token: str, lead_doc: str):
        """Typical staff workflow: check stats → monitor active agents."""
        
        # 1. Staff checks global stats
        resp = await async_client.get(
            "/api/staff/stats",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["global"]["total_leads"] >= 1
        
        # 2. Staff monitors active agents
        resp = await async_client.get(
            "/api/staff/agents/active",
            headers={"Authorization": f"Bearer {staff_token}"}
        )
        assert resp.status_code == 200
        agents = resp.json()
        assert "pipeline_registry" in agents
        assert "per_client_active" in agents
