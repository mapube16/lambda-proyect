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

async def test_routing_strips_whatsapp_prefix(async_client):
    """Webhook strips 'whatsapp:' prefix from From before DB lookup.

    The wa_handler.get_profile() receives the clean phone number.
    We verify this by confirming the endpoint handles the prefixed From without error.
    """
    from unittest.mock import AsyncMock, patch

    with patch("wa_handler.get_profile", AsyncMock(return_value=None)) as mock_get_profile, \
         patch("wa_handler.validate_twilio_signature", return_value=True):
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
    # get_profile called with stripped number (no whatsapp: prefix)
    mock_get_profile.assert_awaited_once()
    call_args = mock_get_profile.call_args
    assert "whatsapp:" not in str(call_args)


async def test_routing_unknown_number_returns_twiml(async_client):
    """Unknown From returns empty TwiML, no error."""
    from unittest.mock import AsyncMock, patch

    with patch("wa_handler.get_profile", AsyncMock(return_value=None)), \
         patch("wa_handler.validate_twilio_signature", return_value=True):
        resp = await async_client.post(
            "/api/whatsapp/incoming",
            data={
                "From": "whatsapp:+999999999",
                "To": "whatsapp:+14155238886",
                "Body": "Hola",
                "NumMedia": "0",
            },
        )
    assert resp.status_code == 200
    assert "<Response/>" in resp.text


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

async def test_tool_call_ver_leads_checkpoint():
    """dispatch_tool_cliente('ver_leads_checkpoint', {}, user_id) returns result without raising."""
    from unittest.mock import patch, AsyncMock, MagicMock
    import wa_handler

    with patch("wa_handler.get_db") as mock_get_db:
        mock_db = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.to_list = AsyncMock(return_value=[])
        mock_db.leads.find.return_value = mock_cursor
        mock_get_db.return_value = mock_db

        result = await wa_handler.dispatch_tool_cliente(
            "ver_leads_checkpoint", {}, "user123"
        )
    # Result is a string (formatted list or "no leads" message)
    assert isinstance(result, str)


async def test_tool_call_aprobar_lead():
    """dispatch_tool_cliente('aprobar_lead', ...) calls update_lead_estado."""
    from unittest.mock import patch, AsyncMock
    import wa_handler

    with patch("wa_handler.update_lead_estado", AsyncMock(return_value={"company_name": "Test"})) as mock_update, \
         patch("wa_handler.asyncio") as mock_asyncio:
        mock_asyncio.create_task = lambda coro: coro.close() or None
        result = await wa_handler.dispatch_tool_cliente(
            "aprobar_lead",
            {"lead_id": "64f000000000000000000001", "canal": "email"},
            "user123",
        )
    mock_update.assert_awaited_once()
    assert isinstance(result, str)


# ── WA-03: Voice note transcription ──────────────────────────────────────────

async def test_voice_note_transcription_success():
    """MediaUrl0 present → httpx download → Whisper returns text."""
    from unittest.mock import patch, AsyncMock, MagicMock
    import wa_handler

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.content = b"fake-audio-bytes"

    mock_transcript = MagicMock()
    mock_transcript.text = "habló con el gerente, quedó muy interesado"

    with patch("httpx.AsyncClient") as mock_httpx_cls, \
         patch("openai.AsyncOpenAI") as mock_openai_cls:
        mock_http_instance = AsyncMock()
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=None)
        mock_http_instance.get = AsyncMock(return_value=mock_response)
        mock_httpx_cls.return_value = mock_http_instance

        mock_openai_instance = AsyncMock()
        mock_openai_instance.audio = MagicMock()
        mock_openai_instance.audio.transcriptions = MagicMock()
        mock_openai_instance.audio.transcriptions.create = AsyncMock(return_value=mock_transcript)
        mock_openai_cls.return_value = mock_openai_instance

        result = await wa_handler._transcribe_voice_note(
            "https://api.twilio.com/media/fake-url"
        )

    assert result == "habló con el gerente, quedó muy interesado"


async def test_voice_note_transcription_failure_returns_fallback():
    """httpx download failure → _transcribe_voice_note returns None (no exception)."""
    from unittest.mock import patch, AsyncMock
    import wa_handler

    with patch("httpx.AsyncClient") as mock_httpx_cls:
        mock_http_instance = AsyncMock()
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=None)
        mock_http_instance.get = AsyncMock(side_effect=Exception("Network error"))
        mock_httpx_cls.return_value = mock_http_instance

        result = await wa_handler._transcribe_voice_note(
            "https://api.twilio.com/media/fake-url"
        )

    assert result is None


# ── WA-04: asesor_interno tools ───────────────────────────────────────────────

@pytest.mark.xfail(reason="WA-04: dispatch_tool_asesor() not yet implemented", strict=False)
async def test_asesor_tool_buscar_licitaciones():
    """dispatch_tool_asesor('buscar_licitaciones', {sector, ciudad}, user_id) calls secop_radar."""
    pytest.fail("not implemented")


@pytest.mark.xfail(reason="WA-04: dispatch_tool_asesor() not yet implemented", strict=False)
async def test_asesor_tool_enriquecer_empresa():
    """dispatch_tool_asesor('enriquecer_empresa', {nit}, user_id) calls nit_enricher."""
    pytest.fail("not implemented")
