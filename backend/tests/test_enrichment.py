"""
test_enrichment.py — Phase 15: Pipeline Enrichment + Real Channel Activation.

Requirement areas:
  ENRICH-01: SECOP flag resolution (bridge from company_voice to discover_companies flags)
  ENRICH-02: NIT enrichment (async background task saves nit_data to lead)
  ENRICH-03: WhatsApp outreach fallback (channel routing when phone present/absent)
"""
import asyncio
import os
import sys
import types

import pytest
from unittest.mock import AsyncMock, patch

# hive_tools imports framework.llm.provider at module level.
# vendor/hive/core is in the venv (via _framework.pth) but not in .venv.
# Add it manually so ENRICH-01/02 tests can import make_prospecting_registry.
_vendor_core = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../vendor/hive/core"))
if _vendor_core not in sys.path:
    sys.path.insert(0, _vendor_core)


# ── ENRICH-01: SECOP flag resolution ──────────────────────────────────────────


async def test_secop_flag_from_company_voice(reset_db):
    """
    When company_voice.fuentes_habilitadas contains 'secop_adjudicados',
    _discover_companies calls prospector.discover_companies with use_secop=True,
    even when campaign.use_secop=False.
    """
    from hive_tools import make_prospecting_registry

    mock_discover = AsyncMock(return_value=[])
    mock_send = AsyncMock()

    # prospector has heavy deps (bs4, ddgs) not in .venv — inject a stub module
    fake_prospector = types.ModuleType("prospector")
    fake_prospector.discover_companies = mock_discover

    registry = make_prospecting_registry(
        campaign={"use_secop": False, "use_secop_radar": False},
        gmaps_key="fake",
        openrouter_key="fake",
        user_id="test_user",
        run_id="run1",
        send_to_user=mock_send,
        save_lead=None,
    )

    cv = {"fuentes_habilitadas": ["secop_adjudicados"]}

    with patch.dict(sys.modules, {"prospector": fake_prospector}), \
         patch("landa.company_voice.get_or_create_company_voice", new=AsyncMock(return_value=cv)):
        executor = registry._tools["discover_companies"].executor
        await executor({"industria": "logistica", "ciudad": "Bogotá"})

    mock_discover.assert_awaited_once()
    assert mock_discover.call_args.kwargs.get("use_secop") is True


async def test_secop_flag_fallback_to_campaign(reset_db):
    """
    When company_voice fails to load (exception), _discover_companies falls back
    to campaign.use_secop=True so discover_companies is still called with use_secop=True.
    """
    from hive_tools import make_prospecting_registry

    mock_discover = AsyncMock(return_value=[])
    mock_send = AsyncMock()

    fake_prospector = types.ModuleType("prospector")
    fake_prospector.discover_companies = mock_discover

    registry = make_prospecting_registry(
        campaign={"use_secop": True, "use_secop_radar": False},
        gmaps_key="fake",
        openrouter_key="fake",
        user_id="test_user",
        run_id="run1",
        send_to_user=mock_send,
        save_lead=None,
    )

    with patch.dict(sys.modules, {"prospector": fake_prospector}), \
         patch("landa.company_voice.get_or_create_company_voice", new=AsyncMock(side_effect=Exception("DB down"))):
        executor = registry._tools["discover_companies"].executor
        await executor({"industria": "logistica", "ciudad": "Bogotá"})

    mock_discover.assert_awaited_once()
    assert mock_discover.call_args.kwargs.get("use_secop") is True


# ── ENRICH-02: NIT enrichment ─────────────────────────────────────────────────


async def test_nit_enrichment_saved_to_lead(reset_db):
    """
    When analyze_company returns a json_payload with a nit field and save_lead
    returns a lead_id, enrich_nit is called and update_lead_nit_data is called
    with the enriched result.
    """
    from hive_tools import make_prospecting_registry

    lead_id = "abc123"
    enriched_data = {"razon_social": "Test Corp SAS", "estado": "activo"}

    mock_save_lead = AsyncMock(return_value=lead_id)
    mock_send = AsyncMock()
    mock_enrich_nit = AsyncMock(return_value=enriched_data)
    mock_update_nit = AsyncMock()

    analyze_result = {
        "url": "http://testcorp.co",
        "status": "success",
        "markdown": "# Test Corp",
        "json_payload": {
            "nit": "900123456",
            "score": 80,
            "empresa": "Test Corp",
            "decisor": {"nombre": "Juan", "cargo": "CEO"},
            "es_sector_correcto": True,
            "tamano_estimado": "mediana",
        },
    }

    # Inject stub modules for heavy-dep packages not in .venv
    fake_prospector = types.ModuleType("prospector")
    fake_prospector.analyze_company = AsyncMock(return_value=analyze_result)
    fake_nit_enricher = types.ModuleType("nit_enricher")
    fake_nit_enricher.enrich_nit = mock_enrich_nit

    registry = make_prospecting_registry(
        campaign={"use_secop": False},
        gmaps_key="fake",
        openrouter_key="fake",
        user_id="test_user",
        run_id="run1",
        send_to_user=mock_send,
        save_lead=mock_save_lead,
    )

    with patch.dict(sys.modules, {"prospector": fake_prospector, "nit_enricher": fake_nit_enricher}), \
         patch("database.update_lead_nit_data", new=mock_update_nit):
        executor = registry._tools["analyze_company"].executor
        await executor({"url": "http://testcorp.co", "title": "Test Corp"})
        # Allow the background NIT asyncio.create_task to complete
        await asyncio.sleep(0.1)

    mock_enrich_nit.assert_awaited_once_with("900123456")
    mock_update_nit.assert_awaited_once_with(lead_id, enriched_data)


async def test_nit_enrichment_skipped_when_no_nit(reset_db):
    """
    When analyze_company returns a json_payload with no nit field,
    enrich_nit is never called — no background task fires.
    """
    from hive_tools import make_prospecting_registry

    mock_save_lead = AsyncMock(return_value="lead_xyz")
    mock_send = AsyncMock()
    mock_enrich_nit = AsyncMock(return_value={})

    analyze_result = {
        "url": "http://nonit.co",
        "status": "success",
        "markdown": "# No NIT Corp",
        "json_payload": {
            # no "nit" key
            "score": 60,
            "empresa": "No NIT Corp",
            "decisor": {"nombre": "Ana", "cargo": "Directora"},
            "es_sector_correcto": True,
        },
    }

    fake_prospector = types.ModuleType("prospector")
    fake_prospector.analyze_company = AsyncMock(return_value=analyze_result)
    fake_nit_enricher = types.ModuleType("nit_enricher")
    fake_nit_enricher.enrich_nit = mock_enrich_nit

    registry = make_prospecting_registry(
        campaign={"use_secop": False},
        gmaps_key="fake",
        openrouter_key="fake",
        user_id="test_user",
        run_id="run1",
        send_to_user=mock_send,
        save_lead=mock_save_lead,
    )

    with patch.dict(sys.modules, {"prospector": fake_prospector, "nit_enricher": fake_nit_enricher}):
        executor = registry._tools["analyze_company"].executor
        await executor({"url": "http://nonit.co", "title": "No NIT Corp"})
        await asyncio.sleep(0.1)

    mock_enrich_nit.assert_not_awaited()


# ── ENRICH-03: WhatsApp outreach fallback ─────────────────────────────────────

from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


async def test_outreach_whatsapp_sends_with_phone(reset_db):
    """
    When canal_elegido=whatsapp and phone is present, send_whatsapp_text is called
    and run_outreach returns True (the mock's return value).
    """
    from landa.agents.outreach import run_outreach
    from database import get_db

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "WA Corp",
        "url": "http://wacorp.co",
        "estado": "checkpoint",
        "canal_elegido": "whatsapp",
        "decisor": {
            "nombre": "Pedro Ruiz",
            "cargo": "Director",
            "phone": "+573001234567",
            "email": "pedro@wacorp.co",
        },
        "intento_actual": 0,
        "historial_conversacion": [],
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    company_voice_mock = {
        "remitentes": [{"nombre": "Landa Bot", "email": "bot@landa.co"}],
        "industria_objetivo": "Tecnología",
        "ciudad_objetivo": "Bogotá",
        "dolor_operativo": "Procesos manuales",
        "solucion_ofrecida": "Automatización",
        "tono_comunicacion": "profesional",
    }
    sector_profile_mock = {
        "decisor_primario": "Director Comercial",
        "ganchos": ["ahorro"],
        "canal_principal": "whatsapp",
        "tono": "formal",
    }

    mock_send_wa = AsyncMock(return_value=True)

    with patch("landa.agents.outreach.call_agent", new=AsyncMock(return_value="Hola Pedro!")), \
         patch("landa.agents.outreach.get_or_create_company_voice", new=AsyncMock(return_value=company_voice_mock)), \
         patch("landa.agents.outreach.generate_sector_profile", new=AsyncMock(return_value=sector_profile_mock)), \
         patch("landa.agents.outreach.send_whatsapp_text", new=mock_send_wa), \
         patch("landa.agents.outreach.schedule_retry", new=AsyncMock(return_value="sched1")):
        result = await run_outreach(lead_id, "test_user", "whatsapp", intento=1)

    assert result is True
    mock_send_wa.assert_awaited_once()


async def test_outreach_whatsapp_fallback_to_email(reset_db):
    """
    When canal_elegido=whatsapp and phone is empty but email is available,
    send_email is called, sent reflects its return value (True), and a
    fallback historial entry is pushed with tipo=fallback, razon=no_phone,
    canal_usado=email.
    """
    from landa.agents.outreach import run_outreach
    from database import get_db
    from bson import ObjectId

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "No Phone S.A.",
        "url": "http://nophone.co",
        "estado": "checkpoint",
        "canal_elegido": "whatsapp",
        "decisor": {
            "nombre": "María López",
            "cargo": "Gerente",
            "email": "maria@nophone.co",
            # no phone field
        },
        "intento_actual": 0,
        "historial_conversacion": [],
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    company_voice_mock = {
        "remitentes": [{"nombre": "Landa Bot", "email": "bot@landa.co"}],
        "industria_objetivo": "Finanzas",
        "ciudad_objetivo": "Medellín",
        "dolor_operativo": "Costos altos",
        "solucion_ofrecida": "Reducción",
        "tono_comunicacion": "semiformal",
    }
    sector_profile_mock = {
        "decisor_primario": "Gerente Financiero",
        "ganchos": ["eficiencia"],
        "canal_principal": "email",
        "tono": "formal",
    }

    mock_send_email = AsyncMock(return_value=True)
    mock_send_wa = AsyncMock(return_value=False)

    with patch("landa.agents.outreach.call_agent", new=AsyncMock(return_value="Estimada María...")), \
         patch("landa.agents.outreach.get_or_create_company_voice", new=AsyncMock(return_value=company_voice_mock)), \
         patch("landa.agents.outreach.generate_sector_profile", new=AsyncMock(return_value=sector_profile_mock)), \
         patch("landa.agents.outreach.send_whatsapp_text", new=mock_send_wa), \
         patch("landa.agents.outreach.send_email", new=mock_send_email), \
         patch("landa.agents.outreach.schedule_retry", new=AsyncMock(return_value="sched2")):
        result = await run_outreach(lead_id, "test_user", "whatsapp", intento=1)

    # send_email must be called (fallback), not send_whatsapp_text
    assert result is True
    mock_send_email.assert_awaited_once()
    mock_send_wa.assert_not_awaited()

    # Fallback historial entry must exist in DB
    doc = await db.leads.find_one({"_id": ObjectId(lead_id)})
    historial = doc.get("historial_conversacion", [])
    fallback_entries = [e for e in historial if e.get("tipo") == "fallback"]
    assert len(fallback_entries) >= 1
    fe = fallback_entries[0]
    assert fe.get("razon") == "no_phone"
    assert fe.get("canal_usado") == "email"
    assert "timestamp" in fe


async def test_outreach_no_phone_no_email(reset_db):
    """
    When canal_elegido=whatsapp and both phone and email are absent,
    run_outreach returns False without crashing. Neither send_whatsapp_text
    nor send_email is called.
    """
    from landa.agents.outreach import run_outreach
    from database import get_db

    db = get_db()
    ins = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Ghost Corp",
        "url": "http://ghost.co",
        "estado": "checkpoint",
        "canal_elegido": "whatsapp",
        "decisor": {
            "nombre": "Fantasma",
            "cargo": "CEO",
            # no phone, no email
        },
        "intento_actual": 0,
        "historial_conversacion": [],
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(ins.inserted_id)

    company_voice_mock = {
        "remitentes": [],
        "industria_objetivo": "Misterio",
        "ciudad_objetivo": "Bogotá",
        "dolor_operativo": "",
        "solucion_ofrecida": "",
        "tono_comunicacion": "profesional",
    }
    sector_profile_mock = {
        "decisor_primario": "CEO",
        "ganchos": [],
        "canal_principal": "whatsapp",
        "tono": "formal",
    }

    mock_send_email = AsyncMock(return_value=True)
    mock_send_wa = AsyncMock(return_value=True)

    with patch("landa.agents.outreach.call_agent", new=AsyncMock(return_value="Hola Fantasma")), \
         patch("landa.agents.outreach.get_or_create_company_voice", new=AsyncMock(return_value=company_voice_mock)), \
         patch("landa.agents.outreach.generate_sector_profile", new=AsyncMock(return_value=sector_profile_mock)), \
         patch("landa.agents.outreach.send_whatsapp_text", new=mock_send_wa), \
         patch("landa.agents.outreach.send_email", new=mock_send_email):
        result = await run_outreach(lead_id, "test_user", "whatsapp", intento=1)

    assert result is False
    mock_send_wa.assert_not_awaited()
    mock_send_email.assert_not_awaited()


# ── ENRICH-01: SECOP Source Bridge ────────────────────────────────────────────

@pytest.mark.xfail(reason="ENRICH-01: investigador reads secop_adjudicados flag from company_voice")
async def test_investigador_includes_secop_when_enabled(reset_db):
    """When fuentes_habilitadas='secop_adjudicados' in company_voice, investigator includes SECOP."""
    pass


@pytest.mark.xfail(reason="ENRICH-01: SECOP source disabled via flag")
async def test_investigador_excludes_secop_when_disabled(reset_db):
    """When secop_adjudicados not in fuentes_habilitadas, investigator skips SECOP."""
    pass


# ── ENRICH-02: NIT Enrichment ─────────────────────────────────────────────────

@pytest.mark.xfail(reason="ENRICH-02: enrich_nit called after scoring")
async def test_nit_enrichment_called_post_scoring(reset_db):
    """After lead scoring, enrich_nit(nit) is called if company NIT extracted."""
    pass


@pytest.mark.xfail(reason="ENRICH-02: NIT data persisted in expediente")
async def test_nit_enrichment_stores_data_in_expediente(reset_db):
    """Enriched RUES + SECOP + Supersociedades data stored in lead.expediente_json."""
    pass


@pytest.mark.xfail(reason="ENRICH-02: NIT enrichment handles missing NIT gracefully")
async def test_nit_enrichment_skipped_if_no_nit(reset_db):
    """If no NIT extracted, system continues without enrichment error."""
    pass


# ── ENRICH-03: WhatsApp Fallback ──────────────────────────────────────────────

@pytest.mark.xfail(reason="ENRICH-03: WhatsApp fallback when phone missing")
async def test_whatsapp_fallback_to_email_no_phone(reset_db):
    """If investigador didn't extract phone, outreach sends via email + logs fallback."""
    pass


@pytest.mark.xfail(reason="ENRICH-03: Fallback decision audit trail")
async def test_whatsapp_fallback_logged_for_audit(reset_db):
    """Fallback from WhatsApp→Email is logged with reason."""
    pass
