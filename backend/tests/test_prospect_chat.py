"""Phase 23 — Wave 0 Nyquist scaffold for NL prospecting chat + knowledge base.

All stubs use strict=False so CI never blocks on unimplemented features.
Subsequent plans (23-02, 23-03) flip these to green by implementing the modules.
"""
import pytest

# ===== NL-01: extract_campaign_from_nl() =====

@pytest.mark.xfail(strict=False, reason="NL-01: extract_campaign_from_nl not implemented yet")
async def test_extract_campaign_from_nl_complete_description():
    """Complete NL description yields CAMPAIGN_READY: with all required fields."""
    from onboarding import extract_campaign_from_nl  # lazy import
    reply = await extract_campaign_from_nl(
        "busca propietarios arrendando en Bogota industria inmobiliaria",
        openai_api_key="sk-test",
        context="",
    )
    assert "CAMPAIGN_READY:" in reply

@pytest.mark.xfail(strict=False, reason="NL-01: extract_campaign_from_nl not implemented yet")
async def test_extract_campaign_from_nl_uses_context():
    """When context is non-empty, it is appended to the system prompt."""
    from onboarding import extract_campaign_from_nl
    reply = await extract_campaign_from_nl(
        "busca empresas similares",
        openai_api_key="sk-test",
        context="=== CONTEXTO DEL NEGOCIO ===\nProducto: seguros empresariales",
    )
    assert reply  # contract: returns str, not None

# ===== NL-02: POST /api/chat/prospect =====

@pytest.mark.xfail(strict=False, reason="NL-02: /api/chat/prospect endpoint not implemented yet")
async def test_nl_prospect_endpoint_returns_extracted(async_client):
    """POST /api/chat/prospect with well-formed message returns status=extracted."""
    # Setup user directly in DB (codebase pattern)
    import auth as _auth
    import database as _db
    from datetime import datetime, timezone
    result = await _db.get_db().users.insert_one({
        "email": "p23a@test.com",
        "hashed_password": _auth.hash_password("x12345678"),
        "role": "client",
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = _auth.create_access_token({"sub": user_id, "role": "client"})
    r = await async_client.post(
        "/api/chat/prospect",
        json={"message": "busca propietarios en Bogota"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("extracted", "needs_clarification")

@pytest.mark.xfail(strict=False, reason="NL-02: /api/chat/prospect endpoint requires auth")
async def test_nl_prospect_endpoint_requires_auth(async_client):
    """POST /api/chat/prospect without JWT returns 401."""
    r = await async_client.post("/api/chat/prospect", json={"message": "hola"})
    assert r.status_code == 401

# ===== KB-01: upsert_prospecting_knowledge() =====

@pytest.mark.xfail(strict=False, reason="KB-01: prospecting_knowledge CRUD not implemented yet")
async def test_upsert_prospecting_knowledge_creates_then_updates():
    """First call inserts; second call with same user_id updates without duplicate."""
    from database import upsert_prospecting_knowledge, get_prospecting_knowledge
    await upsert_prospecting_knowledge("user_kb_1", {"product_description": "seguros A"})
    await upsert_prospecting_knowledge("user_kb_1", {"product_description": "seguros B"})
    doc = await get_prospecting_knowledge("user_kb_1")
    assert doc["product_description"] == "seguros B"

# ===== KB-02: append_lead_signal() =====

@pytest.mark.xfail(strict=False, reason="KB-02: append_lead_signal not implemented yet")
async def test_append_lead_signal_addtoset_dedup():
    """$addToSet ensures duplicate signals are not added twice."""
    from database import append_lead_signal, get_prospecting_knowledge
    await append_lead_signal("user_kb_2", "industria=logistica ciudad=Bogota", "approved")
    await append_lead_signal("user_kb_2", "industria=logistica ciudad=Bogota", "approved")
    doc = await get_prospecting_knowledge("user_kb_2")
    assert doc["approved_lead_signals"].count("industria=logistica ciudad=Bogota") == 1

# ===== KB-03: knowledge base context injection =====

@pytest.mark.xfail(strict=False, reason="KB-03: NL endpoint must inject knowledge base context")
async def test_nl_context_injection_uses_knowledge_base(async_client, monkeypatch):
    """When prospecting_knowledge has product_description, it is passed as context to extractor."""
    captured = {}
    async def fake_extract(message, openai_api_key, context=""):
        captured["context"] = context
        return 'CAMPAIGN_READY:\n{"industria_objetivo": "inmobiliaria", "ciudad_objetivo": "Bogota"}'
    monkeypatch.setattr("onboarding.extract_campaign_from_nl", fake_extract)
    # Setup user directly in DB (codebase pattern)
    import auth as _auth
    import database as _db
    from datetime import datetime, timezone
    result = await _db.get_db().users.insert_one({
        "email": "p23kb@test.com",
        "hashed_password": _auth.hash_password("x12345678"),
        "role": "client",
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = _auth.create_access_token({"sub": user_id, "role": "client"})
    from database import upsert_prospecting_knowledge
    await upsert_prospecting_knowledge(user_id, {"product_description": "seguros empresariales"})
    await async_client.post(
        "/api/chat/prospect",
        json={"message": "busca empresas similares"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert "seguros empresariales" in captured.get("context", "")

# ===== SIGNAL-FB-01: lead decision fires signal feedback =====

@pytest.mark.xfail(strict=False, reason="SIGNAL-FB-01: lead decision must fire append_lead_signal")
async def test_lead_decision_fires_signal_feedback(async_client, monkeypatch):
    """POST /api/leads/{id}/decision with decision=aprobar triggers asyncio.create_task on append_lead_signal."""
    calls = []
    async def fake_append(user_id, signal, signal_type):
        calls.append((user_id, signal, signal_type))
    monkeypatch.setattr("database.append_lead_signal", fake_append)
    # Setup user directly in DB (codebase pattern: create_access_token, not REST register)
    import auth as _auth
    import database as _db
    from datetime import datetime, timezone
    result = await _db.get_db().users.insert_one({
        "email": "p23sig@test.com",
        "hashed_password": _auth.hash_password("x12345678"),
        "role": "client",
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = _auth.create_access_token({"sub": user_id, "role": "client"})
    from database import get_db
    db = get_db()
    res = await db.leads.insert_one({
        "user_id": user_id,
        "estado": "checkpoint",
        "empresa": "ACME",
        "expediente_json": {"industria": "logistica", "ciudad": "Bogota"},
    })
    lead_id = str(res.inserted_id)
    r = await async_client.post(
        f"/api/leads/{lead_id}/decision",
        json={"decision": "aprobar", "canal_elegido": "email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200
    import asyncio
    await asyncio.sleep(0.1)  # let fire-and-forget task run
    assert len(calls) >= 1
    assert calls[0][2] == "approved"
