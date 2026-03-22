"""
test_landa.py — Wave 0 xfail stubs for Phase 12: Landa Foundation.
Each test will be un-xfailed as the corresponding implementation lands.
"""
import pytest


# ── LANDA-01: Lead State Machine ──────────────────────────────────────────────

async def test_lead_estado_valid_transition(async_client, reset_db):
    """update_lead_estado transitions investigando → checkpoint successfully."""
    from landa.state_machine import VALID_TRANSITIONS, update_lead_estado
    # Insert a test lead directly
    from database import get_db
    from datetime import datetime, timezone
    db = get_db()
    result = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Test Corp",
        "url": "http://test.com",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(result.inserted_id)

    updated = await update_lead_estado(lead_id, "test_user", "checkpoint")
    assert updated["estado"] == "checkpoint"
    assert "checkpoint" in VALID_TRANSITIONS["investigando"]


async def test_lead_estado_invalid_transition_raises(async_client, reset_db):
    """update_lead_estado raises ValueError for invalid transition investigando → handover."""
    from landa.state_machine import update_lead_estado
    import pytest
    from database import get_db
    from datetime import datetime, timezone
    db = get_db()
    result = await db.leads.insert_one({
        "user_id": "test_user",
        "company_name": "Test Corp",
        "url": "http://test.com",
        "estado": "investigando",
        "created_at": datetime.now(timezone.utc),
    })
    lead_id = str(result.inserted_id)

    with pytest.raises(ValueError, match="handover"):
        await update_lead_estado(lead_id, "test_user", "handover")


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

async def test_schedule_retry_creates_job(reset_db):
    """schedule_retry inserts a scheduled_actions doc with tipo=reintento."""
    from landa.scheduler import schedule_retry
    from database import get_db

    action_id = await schedule_retry("lead_abc", "email", days=7)
    assert action_id is not None

    db = get_db()
    doc = await db.scheduled_actions.find_one({"lead_id": "lead_abc"})
    assert doc is not None
    assert doc["tipo"] == "reintento"
    assert doc["estado"] == "pendiente"


async def test_cancel_lead_actions_removes_jobs(reset_db):
    """cancel_lead_actions sets all pending actions to cancelado."""
    from landa.scheduler import schedule_retry, schedule_nurturing, cancel_lead_actions
    from database import get_db

    await schedule_retry("lead_xyz", "email", days=7)
    await schedule_nurturing("lead_xyz", mes=1)

    cancelled = await cancel_lead_actions("lead_xyz")
    assert cancelled == 2

    db = get_db()
    pending = await db.scheduled_actions.find(
        {"lead_id": "lead_xyz", "estado": "pendiente"}
    ).to_list(length=100)
    assert len(pending) == 0


# ── LANDA-04: build_system_prompt Variable Template Builder ───────────────────

def test_build_system_prompt_replaces_all_vars():
    """build_system_prompt replaces all [KEY] placeholders."""
    from landa.core.context import build_system_prompt
    result = build_system_prompt(
        "[SECTOR] opera en [PAIS_REGION]",
        {"SECTOR": "tech", "PAIS_REGION": "Colombia"}
    )
    assert result == "tech opera en Colombia"


def test_build_system_prompt_marks_missing_vars():
    """build_system_prompt marks missing keys as [inferida — KEY]."""
    from landa.core.context import build_system_prompt
    result = build_system_prompt(
        "[SECTOR] opera en [PAIS_REGION]",
        {"SECTOR": "tech"}
    )
    assert result == "tech opera en [inferida — PAIS_REGION]"
