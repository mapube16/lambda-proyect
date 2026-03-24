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

@pytest.mark.xfail(reason="WA-01: notify_user() not yet implemented", strict=False)
async def test_notify_user_routing_web():
    """notify_user() sends WS event when notification_channel='web'."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-01: notify_user() not yet implemented", strict=False)
async def test_notify_user_routing_whatsapp():
    """notify_user() sends WA message (no WS) when notification_channel='whatsapp'."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-01: notify_user() not yet implemented", strict=False)
async def test_notify_user_routing_both():
    """notify_user() sends WS + WA when notification_channel='both'."""
    pytest.fail("not implemented")


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

@pytest.mark.xfail(reason="WA-02: wa_sessions CRUD not yet implemented", strict=False)
async def test_session_created_on_first_message():
    """get_or_create_wa_session() creates doc if phone not in wa_sessions."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-02: wa_sessions CRUD not yet implemented", strict=False)
async def test_session_sliding_window_max_10_turns():
    """update_wa_session() keeps only last 10 turns in history."""
    pytest.fail("not implemented")


# ── WA-02: webhook end-to-end ─────────────────────────────────────────────────

@pytest.mark.xfail(reason="WA-02: wa_handler.process_inbound() not yet implemented", strict=False)
async def test_webhook_returns_empty_twiml(async_client):
    """POST /api/whatsapp/incoming returns <Response/> immediately."""
    pytest.fail("not implemented")


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
