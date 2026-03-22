"""
test_landa.py — Wave 0 xfail stubs for Phase 12: Landa Foundation.
Each test will be un-xfailed as the corresponding implementation lands.
"""
import pytest


# ── LANDA-01: Lead State Machine ──────────────────────────────────────────────

@pytest.mark.xfail(reason="LANDA-01 not implemented yet", strict=True)
async def test_lead_estado_valid_transition():
    """
    update_lead_estado(lead_id, user_id, "checkpoint") on a lead in state
    "investigando" must succeed and persist the new state.
    """
    from landa.state_machine import VALID_TRANSITIONS, update_lead_estado  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-01 not implemented yet", strict=True)
async def test_lead_estado_invalid_transition_raises():
    """
    update_lead_estado(lead_id, user_id, "handover") on a lead in state
    "investigando" must raise ValueError — direct jump is not a valid transition.
    """
    from landa.state_machine import update_lead_estado  # noqa
    assert False


# ── LANDA-02: sector_profiles Generation ─────────────────────────────────────

@pytest.mark.xfail(reason="LANDA-02 not implemented yet", strict=True)
async def test_generate_sector_profile_returns_schema():
    """
    generate_sector_profile("tecnologia", "Colombia", "mediana") must return a
    dict containing all required keys: decisor_primario, ganchos, objeciones,
    senales_compra, senales_reentrada, canal_principal, tono, ciclo_venta.
    """
    from landa.sector_profiles import generate_sector_profile  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-02 not implemented yet", strict=True)
async def test_generate_sector_profile_uses_cache():
    """
    Calling generate_sector_profile twice with the same args within 30 days
    must return the same document from DB without calling GPT a second time.
    """
    from landa.sector_profiles import generate_sector_profile  # noqa
    assert False


# ── LANDA-03: APScheduler + scheduled_actions ─────────────────────────────────

@pytest.mark.xfail(reason="LANDA-03 not implemented yet", strict=True)
async def test_schedule_retry_creates_job():
    """
    schedule_retry(lead_id="abc", canal="email", days=7) must insert a
    document in scheduled_actions with tipo="reintento" and estado="pendiente".
    """
    from landa.scheduler import schedule_retry  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-03 not implemented yet", strict=True)
async def test_cancel_lead_actions_removes_jobs():
    """
    After schedule_retry + schedule_nurturing for lead "abc",
    cancel_lead_actions("abc") must leave zero scheduled_actions docs for that lead_id.
    """
    from landa.scheduler import schedule_retry, schedule_nurturing, cancel_lead_actions  # noqa
    assert False


# ── LANDA-04: build_system_prompt Variable Template Builder ───────────────────

@pytest.mark.xfail(reason="LANDA-04 not implemented yet", strict=True)
async def test_build_system_prompt_replaces_all_vars():
    """
    build_system_prompt("[SECTOR] opera en [PAIS_REGION]", {"SECTOR": "tech", "PAIS_REGION": "Colombia"})
    must return "tech opera en Colombia".
    """
    from landa.core.context import build_system_prompt  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-04 not implemented yet", strict=True)
async def test_build_system_prompt_marks_missing_vars():
    """
    build_system_prompt("[SECTOR] opera en [PAIS_REGION]", {"SECTOR": "tech"})
    must return "tech opera en [inferida — PAIS_REGION]" (missing key → inferida marker).
    """
    from landa.core.context import build_system_prompt  # noqa
    assert False
