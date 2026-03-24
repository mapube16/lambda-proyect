"""
test_whatsapp.py — Phase 16: WhatsApp Conversational Advisor Bot.
Tests cover WA-01 (webhook + routing), WA-02 (sessions + wa_handler),
WA-03 (tool calling + voice notes), WA-04 (asesor_interno tools).

All tests start as xfail stubs. Each plan removes xfail as it implements the feature.
"""
import pytest
import pytest_asyncio
import database
from mongomock_motor import AsyncMongoMockClient
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Fresh in-memory MongoDB per test — mirrors conftest.py pattern."""
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    await database.get_db().users.drop()


@pytest_asyncio.fixture
async def async_client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── WA-01: notify_user() routing ──────────────────────────────────────────────

async def test_notify_user_routing_web():
    """notify_user() with channel='web' sends WS only, no WA."""
    from unittest.mock import AsyncMock, patch, MagicMock
    import main as main_module

    mock_cv = {"notification_channel": "web", "wa_phone_number": None}
    mock_send_to_user = AsyncMock()
    mock_send_whatsapp = AsyncMock()

    with patch.object(main_module.manager, "send_to_user", mock_send_to_user), \
         patch("main.get_or_create_company_voice", AsyncMock(return_value=mock_cv)), \
         patch("main.send_whatsapp_text", mock_send_whatsapp, create=True):
        await main_module.notify_user("user123", {"type": "lead_checkpoint"})

    mock_send_to_user.assert_awaited_once()
    mock_send_whatsapp.assert_not_awaited()


async def test_notify_user_routing_whatsapp():
    """notify_user() with channel='whatsapp' sends WA only, no WS."""
    from unittest.mock import AsyncMock, patch
    import main as main_module

    mock_cv = {"notification_channel": "whatsapp", "wa_phone_number": "+573001234567"}
    mock_send_to_user = AsyncMock()
    mock_send_whatsapp = AsyncMock()

    with patch.object(main_module.manager, "send_to_user", mock_send_to_user), \
         patch("main.get_or_create_company_voice", AsyncMock(return_value=mock_cv)), \
         patch("main.send_whatsapp_text", mock_send_whatsapp, create=True):
        await main_module.notify_user("user123", {"type": "lead_checkpoint"})

    mock_send_to_user.assert_not_awaited()
    mock_send_whatsapp.assert_awaited_once()


async def test_notify_user_routing_both():
    """notify_user() with channel='both' sends WS + WA."""
    from unittest.mock import AsyncMock, patch
    import main as main_module

    mock_cv = {"notification_channel": "both", "wa_phone_number": "+573001234567"}
    mock_send_to_user = AsyncMock()
    mock_send_whatsapp = AsyncMock()

    with patch.object(main_module.manager, "send_to_user", mock_send_to_user), \
         patch("main.get_or_create_company_voice", AsyncMock(return_value=mock_cv)), \
         patch("main.send_whatsapp_text", mock_send_whatsapp, create=True):
        await main_module.notify_user("user123", {"type": "lead_checkpoint"})

    mock_send_to_user.assert_awaited_once()
    mock_send_whatsapp.assert_awaited_once()


# ── WA-01: Webhook routing ────────────────────────────────────────────────────

@pytest.mark.xfail(reason="WA-01: /api/whatsapp/incoming not yet implemented", strict=False)
async def test_routing_strips_whatsapp_prefix(async_client):
    """Webhook strips 'whatsapp:' prefix from From before DB lookup."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-01: /api/whatsapp/incoming not yet implemented", strict=False)
async def test_routing_unknown_number_returns_twiml(async_client):
    """Unknown From number returns empty TwiML <Response/> without error."""
    pytest.fail("not implemented")


# ── WA-02: wa_sessions CRUD ───────────────────────────────────────────────────

async def test_session_created_on_first_message():
    """get_or_create_wa_session() creates doc if phone not in wa_sessions."""
    from database import get_or_create_wa_session, get_db

    session = await get_or_create_wa_session(
        phone="+573001234567",
        profile="cliente",
        user_id="user123",
    )
    assert session["phone"] == "+573001234567"
    assert session["profile"] == "cliente"
    assert session["user_id"] == "user123"
    assert session["history"] == []

    # Calling again returns same session, no duplicate
    session2 = await get_or_create_wa_session(
        phone="+573001234567",
        profile="cliente",
        user_id="user123",
    )
    assert session2["phone"] == session["phone"]

    # Only one doc in collection
    count = await get_db().wa_sessions.count_documents({})
    assert count == 1


async def test_session_sliding_window_max_10_turns():
    """update_wa_session() keeps only last 10 turns in history."""
    from database import get_or_create_wa_session, update_wa_session

    await get_or_create_wa_session(
        phone="+573001234567",
        profile="cliente",
        user_id="user123",
    )

    # Add 11 turns
    for i in range(11):
        await update_wa_session("+573001234567", {"role": "user", "content": f"msg {i}"})

    from database import get_db
    doc = await get_db().wa_sessions.find_one({"phone": "+573001234567"})
    assert len(doc["history"]) == 10
    # Last turn should be msg 10 (the 11th added)
    assert doc["history"][-1]["content"] == "msg 10"


# ── WA-02: webhook end-to-end ─────────────────────────────────────────────────

async def test_webhook_returns_empty_twiml(async_client):
    """POST /api/whatsapp/incoming returns <Response/> immediately (wa_handler stub in place)."""
    from unittest.mock import AsyncMock, patch

    with patch("wa_handler.validate_twilio_signature", return_value=True), \
         patch("wa_handler.get_profile", AsyncMock(return_value=None)):
        resp = await async_client.post(
            "/api/whatsapp/incoming",
            data={
                "From": "whatsapp:+573001234567",
                "To": "whatsapp:+14155238886",
                "Body": "Hola",
                "NumMedia": "0",
            },
        )
    assert resp.status_code == 200
    assert "<Response/>" in resp.text
    assert resp.headers["content-type"].startswith("text/xml")


# ── WA-03: LLM tool calling (cliente profile) ─────────────────────────────────

@pytest.mark.xfail(reason="WA-03: dispatch_tool_cliente() not yet implemented", strict=False)
async def test_tool_call_ver_leads_checkpoint():
    """dispatch_tool_cliente('ver_leads_checkpoint', {}, user_id) returns list."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-03: dispatch_tool_cliente() not yet implemented", strict=False)
async def test_tool_call_aprobar_lead():
    """dispatch_tool_cliente('aprobar_lead', {lead_id, canal}, user_id) returns ok."""
    pytest.fail("not implemented")


# ── WA-03: Voice note transcription ──────────────────────────────────────────

@pytest.mark.xfail(reason="WA-03: voice note transcription not yet implemented", strict=False)
async def test_voice_note_transcription_success():
    """MediaUrl0 present → httpx download → Whisper → text returned."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-03: voice note transcription not yet implemented", strict=False)
async def test_voice_note_transcription_failure_returns_fallback():
    """Whisper failure → returns fallback message (not exception)."""
    pytest.fail("not implemented")


# ── WA-04: asesor_interno tools ───────────────────────────────────────────────

@pytest.mark.xfail(reason="WA-04: dispatch_tool_asesor() not yet implemented", strict=False)
async def test_asesor_tool_buscar_licitaciones():
    """dispatch_tool_asesor('buscar_licitaciones', {sector, ciudad}, user_id) calls secop_radar."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-04: dispatch_tool_asesor() not yet implemented", strict=False)
async def test_asesor_tool_enriquecer_empresa():
    """dispatch_tool_asesor('enriquecer_empresa', {nit}, user_id) calls nit_enricher."""
    pytest.fail("not implemented")
