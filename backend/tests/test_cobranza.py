"""
test_cobranza.py — Phase 17: Voice Cobranza Agent.
Tests cover COBR-01 (debtor ingestion), COBR-02 (onboarding + campaign setup),
COBR-03 (Vapi integration), COBR-04 (dashboard + reporting).
"""
import io
import pytest
import pytest_asyncio
import database
from bson import ObjectId
from datetime import datetime, timezone
from mongomock_motor import AsyncMongoMockClient


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
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.fixture(autouse=True)
def bypass_vapi_signature():
    """Bypass HMAC signature check for vapi webhook calls in cobranza tests."""
    from unittest.mock import patch
    with patch("cobranza.webhooks.verify_vapi_webhook_signature", return_value=True), \
         patch("cobranza.webhooks.extract_signature_from_headers", return_value="dummy-sig"):
        yield


# ── Auth helpers ──────────────────────────────────────────────────────────────

async def register_and_login(client=None, email="cobr_test@example.com", password="testpass123"):
    """Insert a test user and return the auth header dict."""
    from datetime import timezone
    import auth as _auth
    result = await database.get_db().users.insert_one({
        "email": email,
        "hashed_password": _auth.hash_password(password),
        "role": "client",
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = _auth.create_access_token({"sub": user_id, "role": "client"})
    return {"Authorization": f"Bearer {token}"}


async def get_user_id_for_email(email: str) -> str:
    """Look up the user_id in the mock DB for the given email."""
    user = await database.get_user_by_email(email)
    assert user is not None
    # get_user_by_email returns {"id": str(_id), ...} (not "_id")
    return str(user["id"])


async def enable_cobranza_for_user(user_id: str) -> None:
    """Set cobranza_enabled=True on company_voice for a user (simulates staff action)."""
    db = database.get_db()
    now = datetime.now(timezone.utc)
    await db.company_voice.update_one(
        {"user_id": user_id},
        {"$set": {"cobranza_enabled": True, "updated_at": now},
         "$setOnInsert": {"user_id": user_id, "created_at": now}},
        upsert=True,
    )


# ── COBR-01: Debtor Ingestion ─────────────────────────────────────────────────

async def test_cobr_01_csv_upload(async_client):
    """CSV upload with valid 2-row CSV returns 201 {created:2, errors:[]}."""
    headers = await register_and_login(async_client, "csv_user@example.com")
    csv_content = (
        "nombre,telefono,monto,vencimiento\n"
        "Juan Perez,+573001234567,500000,2026-06-01\n"
        "Maria Lopez,+573009876543,300000,2026-05-15\n"
    ).encode("utf-8")
    files = {"file": ("debtors.csv", io.BytesIO(csv_content), "text/csv")}
    resp = await async_client.post("/api/cobranza/debtors/csv", files=files, headers=headers)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["created"] == 2
    assert body["errors"] == []


async def test_cobr_01_manual_add(async_client):
    """Manual debtor creation returns 201 + debtor with estado='pendiente'."""
    headers = await register_and_login(async_client, "manual_user@example.com")
    payload = {
        "nombre": "Juan Garcia",
        "telefono": "+573001234567",
        "monto": 500000,
        "vencimiento": "2026-06-01",
    }
    resp = await async_client.post("/api/cobranza/debtors", json=payload, headers=headers)
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "debtor" in body
    assert body["debtor"]["estado"] == "pendiente"


# ── COBR-02: Onboarding + Campaign Setup ─────────────────────────────────────

async def test_cobr_02_queen_propone_estrategia(async_client):
    """POST /api/cobranza/onboarding/start returns 200 with structured estrategia."""
    headers = await register_and_login(async_client, "onboard_user@example.com")
    resp = await async_client.post(
        "/api/cobranza/onboarding/start",
        json={"descripcion": "Tengo 50 deudores morosos de cartera pequeña"},
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "estrategia" in body
    estrategia = body["estrategia"]
    # Queen returns a structured proposal with at minimum these keys
    for key in ("tono", "frecuencia_dias", "max_intentos", "guion"):
        assert key in estrategia, f"Missing key '{key}' in estrategia: {estrategia}"


async def test_cobr_02_approve_saves_campaign(async_client):
    """POST /api/cobranza/onboarding/approve saves estrategia and returns campaign_id + ok."""
    email = "approve_user@example.com"
    headers = await register_and_login(async_client, email)
    user_id = await get_user_id_for_email(email)
    await enable_cobranza_for_user(user_id)

    estrategia = {
        "tono": "profesional",
        "frecuencia_dias": 2,
        "max_intentos": 5,
        "guion": {
            "saludo": "Hola, le llamo de parte de...",
            "propuesta": "Tiene una deuda pendiente de...",
            "objeciones": "Entiendo su situación...",
            "cierre": "Muchas gracias por su atención.",
        },
    }
    resp = await async_client.post(
        "/api/cobranza/onboarding/approve",
        json={"estrategia": estrategia},
        headers=headers,
    )
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["ok"] is True
    assert "campaign_id" in body


# ── COBR-03: Vapi Integration ─────────────────────────────────────────────────

async def test_cobr_03_tool_call_consultar_deuda(async_client):
    """POST /api/vapi/tool-call consultar_deuda returns 200 + results list."""
    # Insert a debtor directly into DB
    db = database.get_db()
    debtor_doc = {
        "user_id": "test_user_id",
        "nombre": "Test Debtor",
        "telefono": "+573001234567",
        "monto": 750000,
        "vencimiento": datetime(2026, 7, 1, tzinfo=timezone.utc),
        "estado": "pendiente",
        "intentos": 0,
        "max_intentos": 5,
        "historial_llamadas": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.debtors.insert_one(debtor_doc)
    debtor_id = str(result.inserted_id)

    payload = {
        "message": {
            "type": "tool-calls",
            "call": {
                "id": "call_test_001",
                "assistantOverrides": {
                    "variableValues": {"debtor_id": debtor_id}
                },
            },
            "toolWithToolCallList": [
                {
                    "name": "consultar_deuda",
                    "toolCall": {
                        "id": "tc_001",
                        "parameters": {"debtor_id": debtor_id},
                    },
                }
            ],
        }
    }
    resp = await async_client.post("/api/vapi/tool-call", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "results" in body
    assert len(body["results"]) == 1
    assert body["results"][0]["toolCallId"] == "tc_001"
    # Result string should mention the monto
    result_str = body["results"][0]["result"]
    assert "750" in result_str or "Deuda" in result_str


async def test_cobr_03_call_ended_updates_estado(async_client):
    """POST /api/vapi/call-ended updates debtor estado in DB to sin_contacto."""
    db = database.get_db()
    debtor_doc = {
        "user_id": "test_user_id",
        "nombre": "Test Debtor Ended",
        "telefono": "+573001234567",
        "monto": 300000,
        "vencimiento": datetime(2026, 8, 1, tzinfo=timezone.utc),
        "estado": "llamando",
        "vapi_call_id": "c_test_ended",
        "intentos": 0,
        "max_intentos": 5,
        "historial_llamadas": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    result = await db.debtors.insert_one(debtor_doc)
    debtor_id = result.inserted_id

    payload = {
        "message": {
            "type": "end-of-call-report",
            "call": {"id": "c_test_ended"},
            "endedReason": "no-answer",
            "durationSeconds": 0,
            "artifact": {"transcript": "", "recordingUrl": ""},
        }
    }
    resp = await async_client.post("/api/vapi/call-ended", json=payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"

    # Verify debtor estado updated in DB
    updated = await db.debtors.find_one({"_id": debtor_id})
    assert updated is not None
    assert updated["estado"] == "sin_contacto"


# ── COBR-04: Dashboard + Reporting ───────────────────────────────────────────

async def test_cobr_04_list_debtors_filterable(async_client):
    """GET /api/cobranza/debtors?estado=pendiente returns only pendiente debtors."""
    email = "list_user@example.com"
    headers = await register_and_login(async_client, email)
    user_id = await get_user_id_for_email(email)

    db = database.get_db()
    now = datetime.now(timezone.utc)
    # Insert 2 pendiente + 1 pagado
    await db.debtors.insert_many([
        {
            "user_id": user_id,
            "nombre": "Debtor A",
            "telefono": "+573001111111",
            "monto": 100000,
            "vencimiento": datetime(2026, 6, 1, tzinfo=timezone.utc),
            "estado": "pendiente",
            "intentos": 0,
            "max_intentos": 5,
            "historial_llamadas": [],
            "created_at": now,
            "updated_at": now,
        },
        {
            "user_id": user_id,
            "nombre": "Debtor B",
            "telefono": "+573002222222",
            "monto": 200000,
            "vencimiento": datetime(2026, 7, 1, tzinfo=timezone.utc),
            "estado": "pendiente",
            "intentos": 0,
            "max_intentos": 5,
            "historial_llamadas": [],
            "created_at": now,
            "updated_at": now,
        },
        {
            "user_id": user_id,
            "nombre": "Debtor C",
            "telefono": "+573003333333",
            "monto": 300000,
            "vencimiento": datetime(2026, 5, 1, tzinfo=timezone.utc),
            "estado": "pagado",
            "intentos": 3,
            "max_intentos": 5,
            "historial_llamadas": [],
            "created_at": now,
            "updated_at": now,
        },
    ])

    resp = await async_client.get("/api/cobranza/debtors?estado=pendiente", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert isinstance(body, list), f"Expected list, got {type(body)}"
    assert len(body) == 2, f"Expected 2 pendiente debtors, got {len(body)}"
    for debtor in body:
        assert debtor["estado"] == "pendiente"


async def test_cobr_04_debtor_detail_historial(async_client):
    """GET /api/cobranza/debtors/{id} returns debtor with historial_llamadas key."""
    email = "detail_user@example.com"
    headers = await register_and_login(async_client, email)
    user_id = await get_user_id_for_email(email)

    db = database.get_db()
    now = datetime.now(timezone.utc)
    result = await db.debtors.insert_one({
        "user_id": user_id,
        "nombre": "Detail Debtor",
        "telefono": "+573001234567",
        "monto": 500000,
        "vencimiento": datetime(2026, 9, 1, tzinfo=timezone.utc),
        "estado": "pendiente",
        "intentos": 0,
        "max_intentos": 5,
        "historial_llamadas": [],
        "created_at": now,
        "updated_at": now,
    })
    debtor_id = str(result.inserted_id)

    resp = await async_client.get(f"/api/cobranza/debtors/{debtor_id}", headers=headers)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "debtor" in body
    assert "historial_llamadas" in body["debtor"]
    assert isinstance(body["debtor"]["historial_llamadas"], list)
