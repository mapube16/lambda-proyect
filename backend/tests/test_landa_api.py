"""
test_landa_api.py — Phase 14: Lead Lifecycle API & Checkpoint UI.
Tests cover LANDA-09, LANDA-10, LANDA-11.
"""
import pytest
from datetime import datetime, timezone


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _register_and_login(async_client=None, email="landa_user@test.com", password="pass1234"):
    """Insert user directly and return (token, user_id)."""
    from datetime import timezone
    from database import get_db
    import auth
    result = await get_db().users.insert_one({
        "email": email,
        "hashed_password": auth.hash_password(password),
        "role": "client",
        "created_at": datetime.now(timezone.utc),
    })
    user_id = str(result.inserted_id)
    token = auth.create_access_token({"sub": user_id, "role": "client"})
    return token, user_id


async def _insert_lead(user_id: str, estado: str = "checkpoint", **extra) -> str:
    """Insert a lead directly into the mock DB and return its string id."""
    from database import get_db
    doc = {
        "user_id": user_id,
        "company_name": extra.pop("company_name", "Test Corp SA"),
        "estado": estado,
        "puntaje": extra.pop("puntaje", 85),
        "criterios": extra.pop("criterios", ["sector_fit", "tamano_correcto"]),
        "señales": extra.pop("señales", ["visito_pricing"]),
        "canales": extra.pop("canales", [{"canal": "email", "probabilidad": 0.8}]),
        "decisor": extra.pop("decisor", "CEO"),
        "estado_updated_at": datetime.now(timezone.utc),
        **extra,
    }
    result = await get_db().leads.insert_one(doc)
    return str(result.inserted_id)


# ── LANDA-09: Checkpoint Review Endpoint + Decision API ───────────────────────

async def test_checkpoint_returns_leads_with_canales(async_client, reset_db):
    """GET /api/leads/checkpoint returns list with puntaje, criterios, señales, canales fields."""
    token, user_id = await _register_and_login(async_client)
    await _insert_lead(user_id)

    resp = await async_client.get(
        "/api/leads/checkpoint",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) == 1
    lead = data[0]
    assert "puntaje" in lead
    assert "criterios" in lead
    assert "canales" in lead
    assert lead["puntaje"] == 85
    assert lead["canales"] == [{"canal": "email", "probabilidad": 0.8}]


async def test_decision_aprobar_transitions_to_outreach(async_client, reset_db):
    """POST /api/leads/{id}/decision {decision:'aprobar', canal_elegido:'email'} transitions estado to 'outreach'."""
    token, user_id = await _register_and_login(async_client)
    lead_id = await _insert_lead(user_id)

    resp = await async_client.post(
        f"/api/leads/{lead_id}/decision",
        json={"decision": "aprobar", "canal_elegido": "email"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nuevo_estado"] == "outreach"
    assert body["lead_id"] == lead_id

    # Verify DB state
    from database import get_db
    from bson import ObjectId
    doc = await get_db().leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "outreach"


async def test_decision_rechazar_transitions_to_nurturing(async_client, reset_db):
    """POST /api/leads/{id}/decision {decision:'rechazar', motivo:'no_fit'} transitions estado to 'nurturing'."""
    token, user_id = await _register_and_login(async_client)
    lead_id = await _insert_lead(user_id)

    resp = await async_client.post(
        f"/api/leads/{lead_id}/decision",
        json={"decision": "rechazar", "motivo": "no_fit"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nuevo_estado"] == "nurturing"

    # Verify DB state and motivo_nurturing
    from database import get_db
    from bson import ObjectId
    doc = await get_db().leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "nurturing"
    assert doc["motivo_nurturing"] == "no_fit"


async def test_decision_pausar_transitions_to_pausado(async_client, reset_db):
    """POST /api/leads/{id}/decision {decision:'pausar'} transitions estado to 'pausado'."""
    token, user_id = await _register_and_login(async_client)
    lead_id = await _insert_lead(user_id)

    resp = await async_client.post(
        f"/api/leads/{lead_id}/decision",
        json={"decision": "pausar"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["nuevo_estado"] == "pausado"

    # Verify DB state
    from database import get_db
    from bson import ObjectId
    doc = await get_db().leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "pausado"


# ── LANDA-10: Human Handover Package ─────────────────────────────────────────

async def test_handover_get_returns_package(async_client, reset_db):
    """GET /api/leads/{id}/handover returns {lead, hilo_conversacion, calificacion_original, sugerencia_cierre}."""
    from unittest.mock import AsyncMock, patch
    token, user_id = await _register_and_login(async_client, "handover_get@test.com")
    lead_id = await _insert_lead(user_id, estado="outreach", historial_conversacion=[])

    with patch("landa.core.context.call_agent", new=AsyncMock(return_value="Llama mañana")):
        resp = await async_client.get(
            f"/api/leads/{lead_id}/handover",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "lead" in body
    assert "hilo_conversacion" in body
    assert "calificacion_original" in body
    assert "sugerencia_cierre" in body
    assert body["sugerencia_cierre"] == "Llama mañana"


async def test_handover_tomar_cancels_actions(async_client, reset_db):
    """POST /api/leads/{id}/handover/tomar calls cancel_lead_actions and sets estado='handover'."""
    from unittest.mock import AsyncMock, patch
    from database import get_db
    from bson import ObjectId

    token, user_id = await _register_and_login(async_client, "handover_tomar@test.com")
    lead_id = await _insert_lead(user_id, estado="outreach", canal_elegido="email")

    cancel_mock = AsyncMock(return_value=0)
    schedule_mock = AsyncMock(return_value="action123")

    with patch("landa.scheduler.cancel_lead_actions", cancel_mock), \
         patch("landa.scheduler.schedule_retry", schedule_mock):
        resp = await async_client.post(
            f"/api/leads/{lead_id}/handover/tomar",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["estado"] == "handover"
    cancel_mock.assert_called_once_with(lead_id)
    schedule_mock.assert_called_once()
    doc = await get_db().leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "handover"


# ── LANDA-11: Call Report Endpoint ───────────────────────────────────────────

async def test_reporte_mal_transitions_nurturing(async_client, reset_db):
    """POST /api/leads/{id}/reporte-llamada {resultado:'mal', detalle:'no_interesa'} transitions to nurturing."""
    from database import get_db
    from bson import ObjectId

    token, user_id = await _register_and_login(async_client, "reporte_mal@test.com")
    lead_id = await _insert_lead(user_id, estado="handover")

    resp = await async_client.post(
        f"/api/leads/{lead_id}/reporte-llamada",
        json={"resultado": "mal", "detalle": "no_interesa"},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    doc = await get_db().leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "nurturing"
    assert doc["motivo_nurturing"] == "no_interesa"


async def test_reporte_nopude_ocupado_schedules_retry(async_client, reset_db):
    """POST /api/leads/{id}/reporte-llamada {resultado:'no_pude', sub_tipo:'ocupado'} schedules retry in 1 day."""
    from unittest.mock import AsyncMock, patch

    token, user_id = await _register_and_login(async_client, "reporte_nopude@test.com")
    lead_id = await _insert_lead(user_id, estado="handover", canal_elegido="telefono")

    schedule_mock = AsyncMock(return_value="sched_nopude")

    with patch("landa.scheduler.schedule_retry", schedule_mock):
        resp = await async_client.post(
            f"/api/leads/{lead_id}/reporte-llamada",
            json={"resultado": "no_pude", "sub_tipo": "ocupado"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    schedule_mock.assert_called_once()
    call_args = schedule_mock.call_args
    # days=1 for ocupado — could be positional or keyword
    assert (call_args.kwargs.get("days") == 1) or (len(call_args.args) >= 3 and call_args.args[2] == 1)
