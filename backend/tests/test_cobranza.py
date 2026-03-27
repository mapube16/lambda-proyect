"""
test_cobranza.py — Phase 17: Voice Cobranza Agent.
Tests cover COBR-01 (debtor ingestion), COBR-02 (onboarding + campaign setup),
COBR-03 (Vapi integration), COBR-04 (dashboard + reporting).

All tests start as xfail stubs. Each plan removes xfail as it implements the feature.
"""
import pytest
import pytest_asyncio
import database
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


# ── COBR-01: Debtor Ingestion ─────────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="COBR-01 not implemented yet")
async def test_cobr_01_csv_upload(async_client):
    """CSV upload with valid rows returns 201 + list of created debtor IDs + error report for invalid rows."""
    raise NotImplementedError(
        "COBR-01: CSV upload with valid rows returns 201 + list of created debtor IDs"
        " + error report for invalid rows"
    )


@pytest.mark.xfail(strict=False, reason="COBR-01 not implemented yet")
async def test_cobr_01_manual_add(async_client):
    """Manual debtor creation with valid payload returns 201 + debtor with estado='pendiente'."""
    raise NotImplementedError(
        "COBR-01: Manual debtor creation with valid payload returns 201 + debtor with estado='pendiente'"
    )


# ── COBR-02: Onboarding + Campaign Setup ─────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="COBR-02 not implemented yet")
async def test_cobr_02_queen_propone_estrategia(async_client):
    """POST /api/cobranza/onboarding/start triggers Queen proposal and returns structured estrategia JSON."""
    raise NotImplementedError(
        "COBR-02: POST /api/cobranza/onboarding/start triggers Queen proposal"
        " and returns structured estrategia JSON"
    )


@pytest.mark.xfail(strict=False, reason="COBR-02 not implemented yet")
async def test_cobr_02_approve_saves_campaign(async_client):
    """POST /api/cobranza/onboarding/approve saves estrategia to MongoDB and returns campaign_id."""
    raise NotImplementedError(
        "COBR-02: POST /api/cobranza/onboarding/approve saves estrategia to MongoDB"
        " and returns campaign_id"
    )


# ── COBR-03: Vapi Integration ─────────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="COBR-03 not implemented yet")
async def test_cobr_03_tool_call_consultar_deuda(async_client):
    """POST /api/vapi/tool-call with 'consultar_deuda' tool returns HTTP 200 + result string containing monto."""
    raise NotImplementedError(
        "COBR-03: POST /api/vapi/tool-call with 'consultar_deuda' tool returns"
        " HTTP 200 + result string containing monto"
    )


@pytest.mark.xfail(strict=False, reason="COBR-03 not implemented yet")
async def test_cobr_03_call_ended_updates_estado(async_client):
    """POST /api/vapi/call-ended with end-of-call-report updates debtor estado and pushes debtor_update WS event."""
    raise NotImplementedError(
        "COBR-03: POST /api/vapi/call-ended with end-of-call-report updates debtor estado"
        " and pushes debtor_update WS event"
    )


# ── COBR-04: Dashboard + Reporting ───────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="COBR-04 not implemented yet")
async def test_cobr_04_list_debtors_filterable(async_client):
    """GET /api/cobranza/debtors returns paginated debtor list filterable by estado."""
    raise NotImplementedError(
        "COBR-04: GET /api/cobranza/debtors returns paginated debtor list filterable by estado"
    )


@pytest.mark.xfail(strict=False, reason="COBR-04 not implemented yet")
async def test_cobr_04_debtor_detail_historial(async_client):
    """GET /api/cobranza/debtors/{id} returns full debtor detail with historial_llamadas array."""
    raise NotImplementedError(
        "COBR-04: GET /api/cobranza/debtors/{id} returns full debtor detail"
        " with historial_llamadas array"
    )
