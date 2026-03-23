"""
test_landa_api.py — Wave 0 xfail stubs for Phase 14: Lead Lifecycle API & Checkpoint UI.
Stubs cover LANDA-09, LANDA-10, LANDA-11. Each will be un-xfailed as the
corresponding implementation lands in Wave 1.
"""
import pytest


# ── LANDA-09: Checkpoint Review Endpoint + Decision API ───────────────────────

@pytest.mark.xfail(strict=True, reason="LANDA-09: GET /api/leads/checkpoint not yet implemented")
@pytest.mark.asyncio
async def test_checkpoint_returns_leads_with_canales():
    """GET /api/leads/checkpoint returns list with puntaje, criterios, señales, canales fields."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="LANDA-09: POST /api/leads/{id}/decision not yet implemented")
@pytest.mark.asyncio
async def test_decision_aprobar_transitions_to_outreach():
    """POST /api/leads/{id}/decision {decision:'aprobar', canal_elegido:'email'} transitions estado to 'outreach'."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="LANDA-09: POST /api/leads/{id}/decision not yet implemented")
@pytest.mark.asyncio
async def test_decision_rechazar_transitions_to_nurturing():
    """POST /api/leads/{id}/decision {decision:'rechazar', motivo:'no_fit'} transitions estado to 'nurturing'."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="LANDA-09: POST /api/leads/{id}/decision not yet implemented")
@pytest.mark.asyncio
async def test_decision_pausar_transitions_to_pausado():
    """POST /api/leads/{id}/decision {decision:'pausar'} transitions estado to 'pausado'."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


# ── LANDA-10: Human Handover Package ─────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="LANDA-10: GET /api/leads/{id}/handover not yet implemented")
@pytest.mark.asyncio
async def test_handover_get_returns_package():
    """GET /api/leads/{id}/handover returns {lead, hilo_conversacion, calificacion_original, sugerencia_cierre}."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="LANDA-10: POST /api/leads/{id}/handover/tomar not yet implemented")
@pytest.mark.asyncio
async def test_handover_tomar_cancels_actions():
    """POST /api/leads/{id}/handover/tomar calls cancel_lead_actions and sets estado='handover'."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


# ── LANDA-11: Call Report Endpoint ───────────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="LANDA-11: POST /api/leads/{id}/reporte-llamada not yet implemented")
@pytest.mark.asyncio
async def test_reporte_mal_transitions_nurturing():
    """POST /api/leads/{id}/reporte-llamada {resultado:'mal', detalle:'no_interesa'} transitions to nurturing."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="LANDA-11: POST /api/leads/{id}/reporte-llamada not yet implemented")
@pytest.mark.asyncio
async def test_reporte_nopude_ocupado_schedules_retry():
    """POST /api/leads/{id}/reporte-llamada {resultado:'no_pude', sub_tipo:'ocupado'} schedules retry in 1 day."""
    from httpx import AsyncClient, ASGITransport
    from main import app
    raise NotImplementedError
