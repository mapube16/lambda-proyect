"""
test_landa_pipeline.py — Wave 0 stubs for Phase 13: Lead Outreach and Nurturing Agents.
LANDA-05 and LANDA-06 un-xfailed in Phase 13 Plan 02.
LANDA-07 and LANDA-08 remain xfailed until their implementation lands.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch


# ── LANDA-05: Investigador scoring with sector_profile ────────────────────────

async def test_investigador_returns_canales_with_probability(reset_db):
    """
    Scoring result must include 'canales' list where each item has
    'canal' (str) and 'probabilidad' (int 0-100).
    Asserts len(result["canales"]) >= 1 and "probabilidad" in result["canales"][0].
    """
    from landa.agents.investigador import run_investigador
    from database import get_db
    from datetime import datetime, timezone

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Tech Bogota",
        "url": "http://techbogota.com",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    mock_response = json.dumps({
        "puntaje": 82,
        "criterios": ["sector exacto", "tamano correcto"],
        "senales_intencion": ["LinkedIn activo"],
        "recomendacion_agente": "contactar ahora",
        "canales": [
            {"canal": "email", "probabilidad": 80, "razon": "correo en web"},
            {"canal": "whatsapp", "probabilidad": 55, "razon": "WA Business activo"},
        ],
    })

    sector_profile_mock = {
        "decisor_primario": "Gerente de Tecnologia",
        "ganchos": ["gancho1", "gancho2", "gancho3"],
        "objeciones": ["obj1", "obj2", "obj3", "obj4", "obj5"],
        "senales_compra": ["expansion", "licitacion abierta", "nuevo contrato"],
        "senales_reentrada": ["recontacto", "nueva solicitud", "cambio de cargo"],
        "canal_principal": "email",
        "canal_respaldo": "linkedin",
        "tono": "formal",
        "ciclo_venta": "90",
        "consideraciones_legales": "Ley 80 de contratacion publica",
    }

    with patch("landa.agents.investigador.call_agent", new=AsyncMock(return_value=mock_response)), \
         patch("landa.agents.investigador.generate_sector_profile", new=AsyncMock(return_value=sector_profile_mock)):
        result = await run_investigador(lead_id, "test_user", sector="tecnologia", pais_region="Colombia", tamano="mediana")

    assert "canales" in result
    assert len(result["canales"]) >= 1
    assert "probabilidad" in result["canales"][0]
    assert "canal" in result["canales"][0]


async def test_investigador_puntaje_in_range(reset_db):
    """
    Scoring returns 'puntaje' between 0 and 100 inclusive.
    Asserts 0 <= result["puntaje"] <= 100.
    """
    from landa.agents.investigador import run_investigador
    from database import get_db
    from datetime import datetime, timezone

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Empresa S.A.",
        "url": "http://empresa.co",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    mock_response = json.dumps({
        "puntaje": 65,
        "criterios": ["sector cercano"],
        "senales_intencion": [],
        "recomendacion_agente": "nurturing",
        "canales": [{"canal": "email", "probabilidad": 60, "razon": "disponible"}],
    })

    sector_profile_mock = {
        "decisor_primario": "Director Comercial",
        "ganchos": ["g1", "g2", "g3"],
        "senales_compra": ["s1", "s2", "s3"],
        "senales_reentrada": ["r1", "r2", "r3"],
        "canal_principal": "whatsapp",
        "tono": "semiformal",
        "ciclo_venta": "60",
    }

    with patch("landa.agents.investigador.call_agent", new=AsyncMock(return_value=mock_response)), \
         patch("landa.agents.investigador.generate_sector_profile", new=AsyncMock(return_value=sector_profile_mock)):
        result = await run_investigador(lead_id, "test_user", sector="tecnologia", pais_region="Colombia", tamano="mediana")

    assert 0 <= result["puntaje"] <= 100


# ── LANDA-06: Automatic routing post-scoring ──────────────────────────────────

async def test_routing_below_40_sets_rejected(reset_db):
    """
    Lead with puntaje < 40 gets system_state="REJECTED_BY_AI" and
    estado remains "investigando" — no estado transition happens.
    """
    from landa.agents.router import route_after_scoring
    from database import get_db
    from datetime import datetime, timezone

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Low Score Corp",
        "url": "http://lowscore.co",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    await route_after_scoring(lead_id, "test_user", puntaje=25)

    from bson import ObjectId
    doc = await db.leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["system_state"] == "REJECTED_BY_AI"
    assert doc.get("estado", "investigando") == "investigando"


async def test_routing_40_to_69_transitions_to_nurturing(reset_db):
    """
    Lead with puntaje 45 gets update_lead_estado(→ "nurturing") called.
    Asserts final estado is "nurturing".
    """
    from landa.agents.router import route_after_scoring
    from database import get_db
    from datetime import datetime, timezone

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Mid Score Corp",
        "url": "http://midscore.co",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    await route_after_scoring(lead_id, "test_user", puntaje=45)

    from bson import ObjectId
    doc = await db.leads.find_one({"_id": ObjectId(lead_id)})
    assert doc["estado"] == "nurturing"
    assert doc.get("motivo_nurturing") == "score_bajo"


# ── LANDA-07: Outreach agent sends message ────────────────────────────────────

@pytest.mark.xfail(reason="LANDA-07 not implemented yet", strict=True)
async def test_run_outreach_returns_true_on_success():
    """
    run_outreach(lead_id, user_id, "email", intento=1) returns True
    when SMTP mock succeeds. Asserts result is True.
    """
    from landa.agents.outreach import run_outreach  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-07 not implemented yet", strict=True)
async def test_run_outreach_logs_to_historial():
    """
    After run_outreach() completes, the lead document in MongoDB has
    historial_conversacion list with at least one entry containing
    {"tipo": "outreach", "canal": "email"}.
    """
    from landa.agents.outreach import run_outreach  # noqa
    assert False


# ── LANDA-08: Nurturing agent content + re-entry detection ────────────────────

@pytest.mark.xfail(reason="LANDA-08 not implemented yet", strict=True)
async def test_run_nurturing_returns_dict_with_required_keys():
    """
    run_nurturing(lead_id, user_id) returns dict with keys:
    mensaje_enviado (str), senial_detectada (bool), nuevo_estado (str).
    """
    from landa.agents.nurturing import run_nurturing  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-08 not implemented yet", strict=True)
async def test_run_nurturing_detects_reentrada_signal():
    """
    When lead's latest historial_conversacion entry contains a keyword
    from sector_profile.senales_reentrada, nurturing transitions lead
    to "checkpoint". Asserts returned nuevo_estado == "checkpoint".
    """
    from landa.agents.nurturing import run_nurturing  # noqa
    assert False
