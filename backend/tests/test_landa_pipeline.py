"""
test_landa_pipeline.py — Wave 0 xfail stubs for Phase 13: Lead Outreach and Nurturing Agents.
Each test will be un-xfailed as the corresponding implementation lands.
"""
import pytest


# ── LANDA-05: Investigador scoring with sector_profile ────────────────────────

@pytest.mark.xfail(reason="LANDA-05 not implemented yet", strict=True)
async def test_investigador_returns_canales_with_probability():
    """
    Scoring result must include 'canales' list where each item has
    'canal' (str) and 'probabilidad' (int 0-100).
    Asserts len(result["canales"]) >= 1 and "probabilidad" in result["canales"][0].
    """
    from landa.agents.investigador import run_investigador  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-05 not implemented yet", strict=True)
async def test_investigador_puntaje_in_range():
    """
    Scoring returns 'puntaje' between 0 and 100 inclusive.
    Asserts 0 <= result["puntaje"] <= 100.
    """
    from landa.agents.investigador import run_investigador  # noqa
    assert False


# ── LANDA-06: Automatic routing post-scoring ──────────────────────────────────

@pytest.mark.xfail(reason="LANDA-06 not implemented yet", strict=True)
async def test_routing_below_40_sets_rejected():
    """
    Lead with puntaje < 40 gets system_state="REJECTED_BY_AI" and
    estado remains "investigando" — no estado transition happens.
    """
    from landa.agents.router import route_after_scoring  # noqa
    assert False


@pytest.mark.xfail(reason="LANDA-06 not implemented yet", strict=True)
async def test_routing_40_to_69_transitions_to_nurturing():
    """
    Lead with puntaje 45 gets update_lead_estado(→ "nurturing") called.
    Asserts final estado is "nurturing".
    """
    from landa.agents.router import route_after_scoring  # noqa
    assert False


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
