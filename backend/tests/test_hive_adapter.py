"""
Phase 2 test suite — HiveAdapter, tenant isolation, event mapping.
Wave 0: All tests are strict xfail (scaffold). Turn green in Plans 02 and 03.
"""
import pytest


# ─── HIVE-01: Framework installs and imports cleanly ──────────────────────────

@pytest.mark.xfail(strict=True, reason="HIVE-01: framework not yet imported in hive_adapter")
async def test_hive_import_ok():
    """AgentRunner imports without ImportError."""
    assert False, "HIVE-01: from framework.runner.runner import AgentRunner — not yet verified"


@pytest.mark.xfail(strict=True, reason="HIVE-01: AgentRunner not yet instantiated")
async def test_agent_runner_instantiates():
    """AgentRunner(mock_mode=True) constructs without error."""
    assert False, "HIVE-01: AgentRunner instantiation — not yet implemented"


# ─── HIVE-02: HiveAdapter is the only seam ────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="HIVE-02: hive_adapter.py not yet implemented")
async def test_hive_adapter_is_only_seam():
    """main.py contains zero 'from framework' imports."""
    assert False, "HIVE-02: seam enforcement — hive_adapter.py not yet implemented"


@pytest.mark.xfail(strict=True, reason="HIVE-02: HiveAdapter.start_run() not yet implemented")
async def test_start_run_no_error():
    """HiveAdapter.start_run(user_id, inputs) completes without raising."""
    assert False, "HIVE-02: start_run — HiveAdapter not yet implemented"


# ─── HIVE-03: WebSocket routing by user_id ────────────────────────────────────

@pytest.mark.xfail(strict=True, reason="HIVE-03: WS isolation not yet implemented")
async def test_ws_isolation_user_a_not_b():
    """Event for user_a is NOT delivered to user_b's WebSocket connection."""
    assert False, "HIVE-03: WS isolation — HiveAdapter not yet wired to ConnectionManager"


@pytest.mark.xfail(strict=True, reason="HIVE-03: WS delivery not yet implemented")
async def test_ws_delivery_correct_user():
    """Event for user_a IS delivered to user_a's WebSocket connection."""
    assert False, "HIVE-03: WS delivery — HiveAdapter not yet wired to ConnectionManager"


# ─── HIVE-04: Per-run SharedMemory isolation ──────────────────────────────────

@pytest.mark.xfail(strict=True, reason="HIVE-04: SharedMemory isolation not yet implemented")
async def test_shared_memory_per_run_isolation():
    """Two concurrent AgentRunner instances have separate SharedMemory objects."""
    assert False, "HIVE-04: SharedMemory isolation — HiveAdapter not yet implemented"


# ─── HIVE-05: EventBus events map to AgentState ───────────────────────────────

@pytest.mark.xfail(strict=True, reason="HIVE-05: event mapping not yet implemented")
async def test_event_maps_to_thinking():
    """NODE_LOOP_STARTED event produces AgentState.THINKING WS message."""
    assert False, "HIVE-05: NODE_LOOP_STARTED → THINKING — not yet implemented"


@pytest.mark.xfail(strict=True, reason="HIVE-05: event mapping not yet implemented")
async def test_event_maps_to_tool_use():
    """TOOL_CALL_STARTED event produces AgentState.TOOL_USE WS message."""
    assert False, "HIVE-05: TOOL_CALL_STARTED → TOOL_USE — not yet implemented"


@pytest.mark.xfail(strict=True, reason="HIVE-05: event mapping not yet implemented")
async def test_event_maps_to_waiting():
    """NODE_LOOP_COMPLETED event produces AgentState.WAITING WS message."""
    assert False, "HIVE-05: NODE_LOOP_COMPLETED → WAITING — not yet implemented"


@pytest.mark.xfail(strict=True, reason="HIVE-05: HITL event mapping not yet implemented")
async def test_event_maps_to_waiting_hitl():
    """CLIENT_INPUT_REQUESTED event produces AgentState.WAITING WS message."""
    assert False, "HIVE-05: CLIENT_INPUT_REQUESTED → WAITING — not yet implemented"
