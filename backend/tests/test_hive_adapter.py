"""
Phase 2 test suite — HiveAdapter, tenant isolation, event mapping.
Plan 02: all 11 tests turn green.
"""
import ast
import asyncio
import os
import sys
import pytest
from pathlib import Path
from unittest.mock import MagicMock

# vendor/hive/core provides the framework.* packages (via _framework.pth in venv, but not .venv)
_vendor_core = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../vendor/hive/core"))
if _vendor_core not in sys.path:
    sys.path.insert(0, _vendor_core)


# ─── HIVE-01: Framework installs and imports cleanly ──────────────────────────

async def test_hive_import_ok():
    """AgentRunner imports without ImportError."""
    from framework.runner.runner import AgentRunner  # noqa: F401


async def test_agent_runner_instantiates():
    """AgentRunner(mock_mode=True) constructs without error."""
    from framework.runner.runner import AgentRunner
    from hive_graph import build_stub_graph, build_stub_goal
    runner = AgentRunner(
        agent_path=Path("/tmp/hive_stub/test_user"),
        graph=build_stub_graph(),
        goal=build_stub_goal(),
        mock_mode=True,
        interactive=False,
        skip_credential_validation=True,
    )
    assert runner is not None


# ─── HIVE-02: HiveAdapter is the only seam ────────────────────────────────────

async def test_hive_adapter_is_only_seam():
    """main.py contains zero 'from framework' imports (static AST check)."""
    main_source = Path("main.py").read_text(encoding="utf-8")
    tree = ast.parse(main_source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not node.module.startswith("framework"), (
                f"main.py has forbidden import: from {node.module} — "
                "all framework imports must be in hive_adapter.py"
            )


async def test_start_run_no_error():
    """HiveAdapter.start_run(user_id, inputs) completes without raising."""
    from hive_adapter import HiveAdapter
    messages_sent = []

    async def mock_send(user_id: str, message: dict):
        messages_sent.append((user_id, message))

    adapter = HiveAdapter(send_to_user_callback=mock_send)
    run_id = await adapter.start_run("test_user", {"empresa_url": "https://example.com"})
    assert run_id is not None
    await asyncio.sleep(0.05)  # let background task start


# ─── HIVE-03: WebSocket routing by user_id ────────────────────────────────────

async def test_ws_isolation_user_a_not_b():
    """Event for user_a is NOT delivered to user_b's WebSocket connection."""
    from hive_adapter import HiveAdapter
    from framework.runtime.event_bus import EventType

    user_a_received = []
    user_b_received = []

    async def mock_send(user_id: str, message: dict):
        if user_id == "user_a":
            user_a_received.append(message)
        elif user_id == "user_b":
            user_b_received.append(message)

    adapter = HiveAdapter(send_to_user_callback=mock_send)
    handler_a = adapter._make_event_handler("user_a")
    fake_event = MagicMock()
    fake_event.type = EventType.NODE_LOOP_STARTED
    fake_event.node_id = "stub_start"
    await handler_a(fake_event)

    assert len(user_b_received) == 0, "user_b must receive NO messages from user_a's event"
    assert len(user_a_received) == 1


async def test_ws_delivery_correct_user():
    """Event for user_a IS delivered to user_a's WebSocket connection."""
    from hive_adapter import HiveAdapter
    from framework.runtime.event_bus import EventType

    received = []

    async def mock_send(user_id: str, message: dict):
        received.append((user_id, message))

    adapter = HiveAdapter(send_to_user_callback=mock_send)
    handler_a = adapter._make_event_handler("user_a")
    fake_event = MagicMock()
    fake_event.type = EventType.NODE_LOOP_STARTED
    fake_event.node_id = "stub_start"
    await handler_a(fake_event)

    assert len(received) == 1
    assert received[0][0] == "user_a"
    msg = received[0][1]
    assert msg["type"] == "agent_update"
    assert msg["state"] == "thinking"


# ─── HIVE-04: Per-run SharedMemory isolation ──────────────────────────────────

async def test_shared_memory_per_run_isolation():
    """Two start_run() calls create two separate AgentRunner instances."""
    from hive_adapter import HiveAdapter

    async def mock_send(user_id: str, message: dict):
        pass

    adapter = HiveAdapter(send_to_user_callback=mock_send)
    await adapter.start_run("user_a", {})
    await adapter.start_run("user_b", {})

    runner_a = adapter._runs.get("user_a")
    runner_b = adapter._runs.get("user_b")
    assert runner_a is not None
    assert runner_b is not None
    assert runner_a is not runner_b, "Each user must have a separate AgentRunner instance"


# ─── HIVE-05: EventBus events map to AgentState ───────────────────────────────

async def test_event_maps_to_thinking():
    """NODE_LOOP_STARTED event produces AgentState.THINKING."""
    from hive_adapter import _event_to_agent_state
    from framework.runtime.event_bus import EventType
    from models import AgentState
    fake = MagicMock()
    fake.type = EventType.NODE_LOOP_STARTED
    assert _event_to_agent_state(fake) == AgentState.THINKING


async def test_event_maps_to_tool_use():
    """TOOL_CALL_STARTED event produces AgentState.TOOL_USE."""
    from hive_adapter import _event_to_agent_state
    from framework.runtime.event_bus import EventType
    from models import AgentState
    fake = MagicMock()
    fake.type = EventType.TOOL_CALL_STARTED
    assert _event_to_agent_state(fake) == AgentState.TOOL_USE


async def test_event_maps_to_waiting():
    """NODE_LOOP_COMPLETED event produces AgentState.WAITING."""
    from hive_adapter import _event_to_agent_state
    from framework.runtime.event_bus import EventType
    from models import AgentState
    fake = MagicMock()
    fake.type = EventType.NODE_LOOP_COMPLETED
    assert _event_to_agent_state(fake) == AgentState.WAITING


async def test_event_maps_to_waiting_hitl():
    """CLIENT_INPUT_REQUESTED event produces AgentState.WAITING."""
    from hive_adapter import _event_to_agent_state
    from framework.runtime.event_bus import EventType
    from models import AgentState
    fake = MagicMock()
    fake.type = EventType.CLIENT_INPUT_REQUESTED
    assert _event_to_agent_state(fake) == AgentState.WAITING
