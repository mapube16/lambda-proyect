"""
test_prospect_chat.py — Phase 23: Intelligent Prospecting Chat with NL Input and Company Knowledge Base.

Requirement areas:
  NL-01: extract_campaign_from_nl() returns CAMPAIGN_READY with all required fields for a complete NL description
  NL-02: POST /api/chat/prospect returns {"status":"extracted", "campaign":{...}} for a well-formed NL message
  KB-01: upsert_prospecting_knowledge() creates document with user_id; second call updates without duplicate
  KB-02: append_lead_signal() appends to approved/rejected lists without duplicates ($addToSet)
  KB-03: Knowledge base context is injected into NL extraction prompt (context param non-empty when knowledge exists)

All stubs use strict=False so CI never blocks on unimplemented features.
Heavy imports are placed INSIDE test bodies (lazy) so collection succeeds before modules are extended.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


# ── KB-01: upsert_prospecting_knowledge — create then update ─────────────────

@pytest.mark.xfail(reason="KB-01: upsert_prospecting_knowledge not implemented yet", strict=False)
async def test_upsert_prospecting_knowledge_creates_then_updates():
    from database import upsert_prospecting_knowledge, get_prospecting_knowledge
    # First call creates
    await upsert_prospecting_knowledge("u1", {"product_description": "A"})
    doc = await get_prospecting_knowledge("u1")
    assert doc.get("product_description") == "A"
    assert doc.get("user_id") == "u1"
    # Second call updates without duplication
    await upsert_prospecting_knowledge("u1", {"product_description": "B"})
    doc2 = await get_prospecting_knowledge("u1")
    assert doc2.get("product_description") == "B"
    # Only one document should exist
    from database import get_db
    db = get_db()
    count = await db.prospecting_knowledge.count_documents({"user_id": "u1"})
    assert count == 1


@pytest.mark.xfail(reason="KB-01: get_or_create_prospecting_knowledge auto-seed not implemented yet", strict=False)
async def test_get_or_create_prospecting_knowledge_seeds_from_profile():
    import database
    from database import get_or_create_prospecting_knowledge, upsert_client_profile
    # Setup client profile with business_summary
    await upsert_client_profile("u2", {"business_summary": "Software de nomina para PYMEs", "personality_prompt": "", "campaign": {}, "agents": []})
    # get_or_create should seed product_description from business_summary
    doc = await get_or_create_prospecting_knowledge("u2")
    assert "product_description" in doc
    assert "Software de nomina" in doc.get("product_description", "")


# ── KB-02: append_lead_signal — dedup via $addToSet ──────────────────────────

@pytest.mark.xfail(reason="KB-02: append_lead_signal not implemented yet", strict=False)
async def test_append_lead_signal_addtoset_dedup():
    from database import append_lead_signal, get_prospecting_knowledge
    # Append same signal twice
    await append_lead_signal("u3", "X", "approved")
    await append_lead_signal("u3", "X", "approved")
    doc = await get_prospecting_knowledge("u3")
    signals = doc.get("approved_lead_signals", [])
    assert signals.count("X") == 1, f"Expected exactly 1 occurrence of X, got {signals.count('X')}"


@pytest.mark.xfail(reason="KB-02: append_lead_signal rejected type not implemented yet", strict=False)
async def test_append_lead_signal_rejected_goes_to_correct_list():
    from database import append_lead_signal, get_prospecting_knowledge
    await append_lead_signal("u4", "Y", "rejected")
    doc = await get_prospecting_knowledge("u4")
    assert "Y" in doc.get("rejected_lead_signals", [])
    assert "Y" not in doc.get("approved_lead_signals", [])


# ── NL-01: extract_campaign_from_nl — returns CAMPAIGN_READY string ──────────

@pytest.mark.xfail(reason="NL-01: extract_campaign_from_nl not implemented yet", strict=False)
async def test_extract_campaign_from_nl_complete_description():
    """extract_campaign_from_nl returns a string containing CAMPAIGN_READY: (mocked OpenAI)."""
    mock_reply = 'CAMPAIGN_READY:\n{"nombre_remitente": "Test", "empresa_remitente": "Acme", "industria_objetivo": "logistica", "ciudad_objetivo": "Bogota", "dolor_operativo": "procesos manuales", "solucion_ofrecida": "software ERP", "software_clave": "Excel", "jerarquia_decisores": "Gerente", "signal_sources": ["serper"], "max_results": 20}'

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = mock_reply

    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        from onboarding import extract_campaign_from_nl
        result = await extract_campaign_from_nl(
            "busca propietarios en Bogota",
            "sk-test",
            "",
        )
    assert "CAMPAIGN_READY:" in result


@pytest.mark.xfail(reason="NL-01: extract_campaign_from_nl context injection not implemented yet", strict=False)
async def test_extract_campaign_from_nl_uses_context():
    """extract_campaign_from_nl includes context in the system prompt sent to OpenAI."""
    captured_messages = []

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "CAMPAIGN_READY:\n{}"

    async def mock_create(**kwargs):
        captured_messages.extend(kwargs.get("messages", []))
        return mock_response

    mock_client = AsyncMock()
    mock_client.chat.completions.create = mock_create

    with patch("openai.AsyncOpenAI", return_value=mock_client):
        from onboarding import extract_campaign_from_nl
        await extract_campaign_from_nl(
            "busca logistica",
            "sk-test",
            context="Producto: software ERP para transporte",
        )

    full_system = " ".join(m["content"] for m in captured_messages if m["role"] == "system")
    assert "software ERP para transporte" in full_system


# ── NL-02: POST /api/chat/prospect endpoint ──────────────────────────────────

@pytest.mark.xfail(reason="NL-02: /api/chat/prospect endpoint not implemented yet", strict=False)
async def test_nl_prospect_endpoint_requires_auth(async_client):
    """POST /api/chat/prospect without JWT returns 401."""
    resp = await async_client.post("/api/chat/prospect", json={"message": "busca empresas"})
    assert resp.status_code == 401


@pytest.mark.xfail(reason="NL-02: /api/chat/prospect extracted response not implemented yet", strict=False)
async def test_nl_prospect_endpoint_returns_extracted(async_client):
    """POST /api/chat/prospect with valid JWT + extractable message returns status=extracted."""
    import database, state
    from auth import create_access_token
    from unittest.mock import AsyncMock, MagicMock, patch

    user = await database.create_user("nl_prospect@test.com", "hashed", role="client")
    uid = user["id"]
    token = create_access_token({"sub": str(uid)})

    state.arq_pool = AsyncMock()
    state.arq_pool.enqueue_job = AsyncMock(return_value=None)

    mock_reply = 'CAMPAIGN_READY:\n{"nombre_remitente": "Ana", "empresa_remitente": "TechCo", "industria_objetivo": "logistica", "ciudad_objetivo": "Bogota", "dolor_operativo": "lento", "solucion_ofrecida": "ERP", "software_clave": "Excel", "jerarquia_decisores": "Gerente", "signal_sources": ["serper"], "max_results": 20}'
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = mock_reply
    mock_client = AsyncMock()
    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    with patch("openai.AsyncOpenAI", return_value=mock_client), \
         patch("os.getenv", side_effect=lambda k, d=None: "sk-test" if k == "OPENAI_API_KEY" else d):
        resp = await async_client.post(
            "/api/chat/prospect",
            json={"message": "busca empresas de logistica en Bogota"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body.get("status") == "extracted"
    assert "campaign" in body
    assert body["campaign"].get("industria_objetivo") == "logistica"


# ── KB-03: knowledge base context injection ──────────────────────────────────

@pytest.mark.xfail(reason="KB-03: knowledge base context injection not implemented yet", strict=False)
async def test_nl_context_injection_uses_knowledge_base(async_client):
    """If prospecting_knowledge.product_description exists, it appears in context passed to extract_campaign_from_nl."""
    import database, state
    from auth import create_access_token
    from unittest.mock import AsyncMock, MagicMock, patch

    user = await database.create_user("kb_ctx@test.com", "hashed", role="client")
    uid = user["id"]
    token = create_access_token({"sub": str(uid)})

    # Pre-seed knowledge base
    await database.upsert_prospecting_knowledge(
        str(uid),
        {"product_description": "CRM para constructoras colombianas"},
    )

    state.arq_pool = AsyncMock()
    state.arq_pool.enqueue_job = AsyncMock(return_value=None)

    captured_contexts = []

    async def fake_extract(message, api_key, context=""):
        captured_contexts.append(context)
        return "CAMPAIGN_READY:\n{}"

    with patch("routers.prospect.extract_campaign_from_nl", side_effect=fake_extract), \
         patch("os.getenv", side_effect=lambda k, d=None: "sk-test" if k == "OPENAI_API_KEY" else d):
        await async_client.post(
            "/api/chat/prospect",
            json={"message": "busca constructoras en Medellin"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert len(captured_contexts) >= 1
    assert "CRM para constructoras colombianas" in captured_contexts[0]
