"""
test_webhooks.py — TDD tests for COBR-03: Vapi webhook handlers.

Tests for:
  - POST /api/vapi/tool-call (consultar_deuda, registrar_promesa, escalar_a_humano, unknown tool, exception)
  - POST /api/vapi/call-ended (estado mapping, intentos increment, WS push, agotado, unknown call_id)
"""
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
import database
from mongomock_motor import AsyncMongoMockClient
from bson import ObjectId


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Fresh in-memory MongoDB per test."""
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    await database.get_db().debtors.drop()


@pytest_asyncio.fixture
async def async_client():
    from main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest_asyncio.fixture
async def sample_debtor():
    """Insert a debtor in MongoDB and return its document."""
    db = database.get_db()
    debtor_id = ObjectId()
    call_id = "call_test_123"
    now = datetime.now(timezone.utc)
    doc = {
        "_id": debtor_id,
        "user_id": "user_abc",
        "nombre": "Juan Deudor",
        "telefono": "+573001234567",
        "monto": 500000.0,
        "vencimiento": datetime(2026, 6, 30, tzinfo=timezone.utc),
        "estado": "llamando",
        "vapi_call_id": call_id,
        "intentos": 1,
        "max_intentos": 5,
        "historial_llamadas": [],
        "escalado": False,
        "notas": None,
        "ultimo_contacto_fecha": None,
        "created_at": now,
        "updated_at": now,
    }
    await db.debtors.insert_one(doc)
    return {"debtor_id": str(debtor_id), "call_id": call_id, "doc": doc}


# ── Tool-call tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tool_call_consultar_deuda_returns_200_with_monto(async_client, sample_debtor):
    """POST /api/vapi/tool-call consultar_deuda returns HTTP 200 and result contains monto."""
    debtor_id = sample_debtor["debtor_id"]
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "call_xxx",
                "assistantOverrides": {
                    "variableValues": {"debtor_id": debtor_id}
                }
            },
            "toolWithToolCallList": [
                {
                    "name": "consultar_deuda",
                    "toolCall": {"id": "tc_001", "parameters": {"debtor_id": debtor_id}}
                }
            ]
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    assert len(body["results"]) == 1
    result_str = body["results"][0]["result"]
    assert "500" in result_str or "500,000" in result_str or "500.000" in result_str
    assert body["results"][0]["toolCallId"] == "tc_001"


@pytest.mark.asyncio
async def test_tool_call_unknown_tool_returns_200(async_client):
    """POST /api/vapi/tool-call with unknown tool name returns HTTP 200 with not-recognized message."""
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "call_xxx", "assistantOverrides": {}},
            "toolWithToolCallList": [
                {
                    "name": "herramienta_inventada",
                    "toolCall": {"id": "tc_002", "parameters": {}}
                }
            ]
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body
    result_str = body["results"][0]["result"]
    assert "no reconocida" in result_str.lower() or "herramienta" in result_str.lower()


@pytest.mark.asyncio
async def test_tool_call_exception_returns_200(async_client):
    """POST /api/vapi/tool-call exception inside dispatch still returns HTTP 200."""
    # Pass malformed debtor_id to force exception in ObjectId()
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {"id": "call_xxx", "assistantOverrides": {}},
            "toolWithToolCallList": [
                {
                    "name": "consultar_deuda",
                    "toolCall": {"id": "tc_003", "parameters": {"debtor_id": "not-a-valid-objectid!!!"}}
                }
            ]
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200
    body = resp.json()
    assert "results" in body


@pytest.mark.asyncio
async def test_tool_call_registrar_promesa_updates_estado(async_client, sample_debtor):
    """registrar_promesa tool updates debtor estado to promesa_de_pago."""
    debtor_id = sample_debtor["debtor_id"]
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "call_xxx",
                "assistantOverrides": {"variableValues": {"debtor_id": debtor_id}}
            },
            "toolWithToolCallList": [
                {
                    "name": "registrar_promesa",
                    "toolCall": {
                        "id": "tc_004",
                        "parameters": {
                            "debtor_id": debtor_id,
                            "monto_prometido": 500000,
                            "fecha_prometida": "2026-07-01"
                        }
                    }
                }
            ]
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200

    # Verify debtor estado was updated in DB
    db = database.get_db()
    updated = await db.debtors.find_one({"_id": ObjectId(debtor_id)})
    assert updated["estado"] == "promesa_de_pago"


@pytest.mark.asyncio
async def test_tool_call_escalar_a_humano_sets_escalado(async_client, sample_debtor):
    """escalar_a_humano tool sets debtor escalado=True and estado=escalado."""
    debtor_id = sample_debtor["debtor_id"]
    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "call_xxx",
                "assistantOverrides": {"variableValues": {"debtor_id": debtor_id}}
            },
            "toolWithToolCallList": [
                {
                    "name": "escalar_a_humano",
                    "toolCall": {
                        "id": "tc_005",
                        "parameters": {"debtor_id": debtor_id, "motivo": "cliente muy enojado"}
                    }
                }
            ]
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200

    db = database.get_db()
    updated = await db.debtors.find_one({"_id": ObjectId(debtor_id)})
    assert updated["estado"] == "escalado"
    assert updated["escalado"] is True


# ── Call-ended tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_call_ended_no_answer_sets_sin_contacto(async_client, sample_debtor):
    """POST /api/vapi/call-ended with no-answer sets debtor estado=sin_contacto."""
    call_id = sample_debtor["call_id"]

    with patch("main.manager") as mock_manager:
        mock_manager.send_to_user = AsyncMock()
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id},
                "endedReason": "no-answer",
                "artifact": {"transcript": "No contestó.", "recordingUrl": "https://rec.url/1"},
                "durationSeconds": 12
            }
        }
        resp = await async_client.post("/api/vapi/call-ended", json=payload)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}

    db = database.get_db()
    updated = await db.debtors.find_one({"vapi_call_id": {"$exists": False}})
    # After call-ended, vapi_call_id is unset
    debtor_id = ObjectId(sample_debtor["debtor_id"])
    updated = await db.debtors.find_one({"_id": debtor_id})
    assert updated["estado"] == "sin_contacto"
    assert updated["intentos"] == 2  # was 1, incremented by 1


@pytest.mark.asyncio
async def test_call_ended_keeps_promesa_de_pago(async_client, sample_debtor):
    """If debtor already in promesa_de_pago estado, call-ended keeps that estado."""
    debtor_id = ObjectId(sample_debtor["debtor_id"])
    db = database.get_db()

    # Pre-set estado to promesa_de_pago (simulates tool call having set it)
    await db.debtors.update_one({"_id": debtor_id}, {"$set": {"estado": "promesa_de_pago"}})

    call_id = sample_debtor["call_id"]
    with patch("main.manager") as mock_manager:
        mock_manager.send_to_user = AsyncMock()
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id},
                "endedReason": "customer-ended-call",
                "artifact": {"transcript": "Sí pago mañana.", "recordingUrl": ""},
                "durationSeconds": 45
            }
        }
        resp = await async_client.post("/api/vapi/call-ended", json=payload)

    assert resp.status_code == 200
    updated = await db.debtors.find_one({"_id": debtor_id})
    assert updated["estado"] == "promesa_de_pago"


@pytest.mark.asyncio
async def test_call_ended_pushes_ws_event(async_client, sample_debtor):
    """POST /api/vapi/call-ended pushes debtor_update WS event to debtor user_id."""
    call_id = sample_debtor["call_id"]

    with patch("main.manager") as mock_manager:
        mock_manager.send_to_user = AsyncMock()
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id},
                "endedReason": "no-answer",
                "artifact": {"transcript": "", "recordingUrl": ""},
                "durationSeconds": 0
            }
        }
        resp = await async_client.post("/api/vapi/call-ended", json=payload)

    assert resp.status_code == 200
    mock_manager.send_to_user.assert_called_once()
    call_args = mock_manager.send_to_user.call_args
    user_id_arg = call_args[0][0]
    event_arg = call_args[0][1]
    assert user_id_arg == "user_abc"
    assert event_arg["type"] == "debtor_update"
    assert "debtor_id" in event_arg
    assert "estado" in event_arg


@pytest.mark.asyncio
async def test_call_ended_unknown_call_id_returns_ok(async_client):
    """POST /api/vapi/call-ended with unknown call_id returns HTTP 200 {ok: True} without error."""
    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "call_nonexistent_xyz"},
            "endedReason": "no-answer",
            "artifact": {"transcript": "", "recordingUrl": ""},
            "durationSeconds": 0
        }
    }
    resp = await async_client.post("/api/vapi/call-ended", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@pytest.mark.asyncio
async def test_call_ended_agotado_when_max_intentos_reached(async_client, sample_debtor):
    """POST /api/vapi/call-ended sets estado=agotado when new intentos >= max_intentos."""
    debtor_id = ObjectId(sample_debtor["debtor_id"])
    db = database.get_db()

    # Set intentos to max_intentos - 1 (so after +1 it equals max)
    await db.debtors.update_one({"_id": debtor_id}, {"$set": {"intentos": 4, "max_intentos": 5}})

    call_id = sample_debtor["call_id"]
    with patch("main.manager") as mock_manager:
        mock_manager.send_to_user = AsyncMock()
        payload = {
            "message": {
                "type": "end-of-call-report",
                "call": {"id": call_id},
                "endedReason": "no-answer",
                "artifact": {"transcript": "", "recordingUrl": ""},
                "durationSeconds": 0
            }
        }
        resp = await async_client.post("/api/vapi/call-ended", json=payload)

    assert resp.status_code == 200
    updated = await db.debtors.find_one({"_id": debtor_id})
    assert updated["estado"] == "agotado"


@pytest.mark.asyncio
async def test_call_ended_non_report_type_returns_ok(async_client):
    """POST /api/vapi/call-ended with message.type != end-of-call-report returns {ok: True}."""
    payload = {
        "message": {
            "type": "speech-update",
            "call": {"id": "call_xxx"},
        }
    }
    resp = await async_client.post("/api/vapi/call-ended", json=payload)
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
