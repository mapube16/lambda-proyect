# Phase 2: Hive Adapter and Tenant Isolation - Research

**Researched:** 2026-03-18
**Domain:** aden-hive/hive framework integration, FastAPI adapter pattern, WebSocket tenant isolation
**Confidence:** MEDIUM — core API signatures verified against live GitHub source; installation mechanics partially inferred

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| HIVE-01 | Backend installs and loads `aden-hive/hive` v0.6.0 correctly | Installation method confirmed: git clone + `uv pip install -e ./core`. Package name is `framework` (not `hive` or `aden-hive`). Python 3.11+ required. |
| HIVE-02 | `HiveAdapter` replaces `orchestrator.py` as single seam between FastAPI and Hive | AgentRunner + AgentRuntime + EventBus wiring pattern confirmed. The adapter owns all Hive imports; `main.py` imports only `HiveAdapter`. |
| HIVE-03 | `ConnectionManager` routes WebSocket messages by `user_id` (no global broadcast) | Already keyed by user_id in Phase 1. Phase 2 removes the legacy `broadcast()` call from orchestrator and wires `send_to_user(user_id, ...)` to EventBus subscription. |
| HIVE-04 | `SharedMemory` is instantiated with `namespace=f"user_{user_id}"` | CRITICAL FINDING: `SharedMemory` has NO `namespace=` parameter — it is a `@dataclass` with `_data: dict`. Namespacing must be achieved by creating ONE `SharedMemory` instance per user run, not by namespace kwarg. |
| HIVE-05 | GraphExecutor node events map to existing `AgentState` (THINKING, TOOL_USE, WAITING, IDLE) | EventBus emits `node_loop_started`, `node_loop_completed`, `tool_call_started`, `tool_call_completed`, `client_input_requested`. Exact mapping documented below. |
</phase_requirements>

---

## Summary

The `aden-hive/hive` framework (package name: `framework`, version 0.7.1 in current HEAD, v0.6.0 per project spec) is a uv workspace project — it is **not on PyPI**. It must be installed as an editable local package from a git clone using `uv pip install -e ./core`. The Python requirement is 3.11+.

The architecture for `HiveAdapter` is: a single class in `backend/hive_adapter.py` that owns all Hive imports, instantiates one `AgentRunner` per user session, constructs a `GraphSpec` + `Goal` for the stub prospector graph, subscribes to the `EventBus` via `AgentRuntime.event_bus.subscribe()`, and routes `node_loop_started` / `tool_call_started` / `client_input_requested` / `node_loop_completed` events to the correct user's WebSocket via `ConnectionManager.send_to_user(user_id, ...)`.

The critical divergence from `negocio.md` is that `SharedMemory` has no `namespace=` constructor parameter. Tenant isolation for SharedMemory is achieved by scope, not by namespace string — each run gets a fresh `SharedMemory()` instance, which is created inside `GraphExecutor.execute()` automatically and never shared across runs. HIVE-04's intent ("user_{user_id}" scoping) is satisfied by per-run isolation rather than a namespace kwarg.

**Primary recommendation:** Clone hive repo into project root or a vendor path, install with `uv pip install -e <path>/core`, write `HiveAdapter` as the single boundary class, subscribe to `EventBus` on `AgentRuntime` for node events, and use a minimal stub graph with `mock_mode=True` on `AgentRunner` for Phase 2 testing without LLM calls.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `framework` (aden-hive/hive core) | 0.7.1 (HEAD) / target v0.6.0 | AgentRunner, GraphExecutor, EventBus, SharedMemory | This IS the framework being integrated — no alternative |
| `litellm` | >=1.81.0 (hive dep) | LLM provider abstraction | Required by framework |
| `pydantic` | >=2.0 | GraphSpec, Goal, NodeSpec models | Already in project (2.5.3) |
| `mcp` | >=1.0.0 | Tool MCP protocol | Required by framework |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio.Queue` | stdlib | Bridge sync hive events → async FastAPI | Needed if event callbacks are sync |
| `pytest-asyncio` | 0.23.5 | Already installed | All async tests |
| `mongomock-motor` | 0.0.21 | Already installed | DB fixture isolation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| git clone + editable install | pip install aden-hive | aden-hive is NOT on PyPI — editable install is the only option |
| per-run SharedMemory instance | SharedMemory(namespace=user_id) | namespace= does not exist on the class — per-run instance IS the isolation mechanism |
| EventBus.subscribe() | Polling AgentRunner return value | Polling is synchronous and blocks; subscribe() is push-based and async-friendly |

### Installation
```bash
# From project root — clone hive alongside the FastAPI project (or as a git submodule)
git clone https://github.com/aden-hive/hive.git vendor/hive

# Install hive core as editable package into the existing venv
# (use uv if available, or pip with the same -e flag)
cd backend
uv pip install -e ../vendor/hive/core
# OR with standard pip:
pip install -e ../vendor/hive/core

# Verify import works (no namespace collision with framework name)
python -c "from framework.runner.runner import AgentRunner; print('OK')"
```

**Dependency concern:** `hive/core` adds `litellm>=1.81.0`, `anthropic>=0.40.0`, `mcp>=1.0.0`, `fastmcp>=2.0.0`. These are large packages. Run `pip check` after install to detect conflicts with existing `openai==1.12.0`.

---

## Architecture Patterns

### Recommended Project Structure After Phase 2
```
backend/
├── main.py              # FastAPI app — imports HiveAdapter only, no hive internals
├── hive_adapter.py      # NEW: single seam between FastAPI and framework
├── hive_graph.py        # NEW: stub GraphSpec + Goal for Phase 2 (stub nodes only)
├── orchestrator.py      # DELETED (replaced entirely by hive_adapter.py)
├── auth.py
├── database.py
├── models.py            # AgentState enum stays here — HiveAdapter maps to it
└── tests/
    └── test_hive_adapter.py  # NEW: Phase 2 test suite
```

### Pattern 1: HiveAdapter — Single Seam

**What:** One class `HiveAdapter` in `hive_adapter.py` is the only file in the project that imports anything from `framework.*`. `main.py` imports `HiveAdapter` only.

**When to use:** Always. This is the architectural rule: `main.py` never touches `AgentRunner`, `GraphExecutor`, `EventBus`, or `SharedMemory` directly.

**Example:**
```python
# Source: verified from framework/runner/runner.py and framework/runtime/agent_runtime.py
# backend/hive_adapter.py

from framework.runner.runner import AgentRunner
from framework.runtime.event_bus import EventBus, EventType
from models import AgentState

class HiveAdapter:
    def __init__(self, send_to_user_callback):
        # send_to_user_callback: async (user_id: str, message: dict) -> None
        self._send_to_user = send_to_user_callback
        self._runners: dict[str, AgentRunner] = {}  # keyed by user_id

    async def start_run(self, user_id: str, inputs: dict) -> str:
        """Create an AgentRunner for this user, subscribe to events, start run."""
        from hive_graph import build_stub_graph, build_stub_goal
        runner = AgentRunner.load(
            agent_path="./stub_agent",
            mock_mode=True,  # No real LLM calls in Phase 2
        )
        # Subscribe to node events BEFORE starting run
        runner._agent_runtime.event_bus.subscribe(
            event_types=[
                EventType.NODE_LOOP_STARTED,
                EventType.NODE_LOOP_COMPLETED,
                EventType.TOOL_CALL_STARTED,
                EventType.TOOL_CALL_COMPLETED,
                EventType.CLIENT_INPUT_REQUESTED,
            ],
            handler=self._make_event_handler(user_id),
            filter_stream=user_id,  # Only events for this user's stream
        )
        self._runners[user_id] = runner
        # Run in background task — don't await (non-blocking)
        import asyncio
        asyncio.create_task(runner.run(inputs=inputs))
        return user_id  # run_id placeholder

    def _make_event_handler(self, user_id: str):
        """Factory: returns async handler that maps AgentEvent → AgentState → WS message."""
        async def handler(event):
            state = _event_to_agent_state(event)
            if state:
                await self._send_to_user(user_id, {
                    "type": "agent_update",
                    "state": state.value,
                    "node_id": event.node_id,
                })
        return handler
```

### Pattern 2: EventBus Subscription for Node Events

**What:** Subscribe to `AgentRuntime.event_bus` before calling `runner.run()`. Use `filter_stream=user_id` to avoid cross-tenant event delivery.

**Key API (verified from framework/runtime/event_bus.py):**
```python
# Source: https://github.com/aden-hive/hive/blob/main/core/framework/runtime/event_bus.py

bus.subscribe(
    event_types=[EventType.NODE_LOOP_STARTED],
    handler=my_async_handler,        # async def handler(event: AgentEvent) -> None
    filter_stream="user_abc123",     # only events from this stream_id
)

# AgentEvent payload (dataclass):
# event.type        : EventType
# event.stream_id   : str   (maps to user session)
# event.node_id     : str | None
# event.execution_id: str | None
# event.data        : dict  (NODE_LOOP_STARTED has "max_iterations"; COMPLETED has "iterations")
# event.timestamp   : datetime
```

### Pattern 3: Tenant Isolation via Per-Run SharedMemory

**What:** `SharedMemory` has no namespace parameter. Isolation is by scope: `GraphExecutor.execute()` creates a fresh `SharedMemory()` per call. Never share a SharedMemory instance across users.

**What HIVE-04 means in practice:**
```python
# WRONG — SharedMemory has no namespace= constructor parameter
memory = SharedMemory(namespace=f"user_{user_id}")  # AttributeError

# CORRECT — fresh instance per run; isolation guaranteed by scope
# GraphExecutor creates this internally; we don't instantiate it ourselves.
# In HiveAdapter: each user_id → separate AgentRunner → separate execute() call
# → separate SharedMemory instance automatically.
```

**Verification test pattern:**
```python
# Confirm user_A's memory does not bleed into user_B's run
runner_a = AgentRunner.load(..., mock_mode=True)
runner_b = AgentRunner.load(..., mock_mode=True)
# Run both concurrently — their SharedMemory instances are separate objects
```

### Pattern 4: Stub Graph for Phase 2 Testing (No LLM)

**What:** A minimal `GraphSpec` with 2 nodes (start → end) that executes without LLM calls, used to verify the event/WS pipeline in isolation.

```python
# Source: verified from framework/graph/executor.py test patterns (test_graph_executor.py)
# backend/hive_graph.py

from framework.graph.edge import EdgeSpec, GraphSpec
from framework.graph.node import NodeSpec, NodeContext, NodeResult
from framework.graph.goal import Goal

def build_stub_graph() -> GraphSpec:
    """Minimal 2-node graph: stub_start -> stub_end. No LLM required."""
    nodes = [
        NodeSpec(
            id="stub_start",
            node_type="function_node",
            is_entry=True,
        ),
        NodeSpec(
            id="stub_end",
            node_type="function_node",
            is_terminal=True,
        ),
    ]
    edges = [
        EdgeSpec(source="stub_start", target="stub_end", condition="on_success"),
    ]
    return GraphSpec(nodes=nodes, edges=edges)

def build_stub_goal() -> Goal:
    return Goal(
        id="stub_goal",
        name="Phase 2 Stub",
        description="Verify HiveAdapter wiring without real LLM calls",
        success_criteria=[],
        constraints=[],
    )
```

**IMPORTANT:** `AgentRunner.load()` expects an `agent_path` directory with an `agent.py` or `agent.json`. For stub testing, create `backend/stub_agent/agent.py` that returns the stub graph/goal. Alternatively, construct `AgentRunner(agent_path=..., graph=..., goal=..., mock_mode=True)` directly if the constructor supports it (constructor signature confirmed: `graph` and `goal` are direct parameters).

### Pattern 5: EventBus Access via _agent_runtime (Internal API Caveat)

**What:** `AgentRunner` does not expose `event_bus` publicly. Access is via `runner._agent_runtime.event_bus` — this is a private attribute.

**Risk:** Private attribute access may break on framework upgrades.

**Mitigation strategies:**
1. Pin hive to the exact commit used during development (vendor it with a lockfile)
2. Wrap in a try/except with a clear error message if `_agent_runtime` is None
3. Subscribe AFTER calling `runner._setup()` or the first `run()` — `_agent_runtime` is None until `_setup_agent_runtime()` is called internally

**Better alternative (if available):** Check if `AgentRunner._setup(event_bus=external_bus)` allows injecting an external bus before running — confirmed from source `def _setup(self, event_bus=None)`. This means we can inject our own `EventBus` instance via the internal `_setup` call, avoiding reliance on `_agent_runtime`.

```python
# Inject EventBus before run — less fragile than accessing _agent_runtime.event_bus
our_bus = EventBus()
our_bus.subscribe(event_types=[...], handler=handler)
runner._setup(event_bus=our_bus)  # internal but documented in source
result = await runner.run(inputs=inputs)
```

### Anti-Patterns to Avoid

- **Importing Hive in main.py directly:** Violates the single-seam rule. All `from framework.*` imports belong in `hive_adapter.py` only.
- **Using `manager.broadcast()` in HiveAdapter:** Phase 2 replaces the global broadcast with `send_to_user(user_id, ...)`. The legacy broadcast method stays temporarily for backward compat but must not be called from HiveAdapter.
- **Sharing one AgentRunner across users:** AgentRunner is not thread/task-safe across concurrent user sessions. Each user_id needs its own instance.
- **Awaiting runner.run() in a route handler:** This blocks the FastAPI event loop. Always wrap in `asyncio.create_task()`.
- **Constructing SharedMemory with namespace=:** This constructor parameter does not exist — it will raise `TypeError`.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Node event observation | Custom polling loop or monkey-patching | `EventBus.subscribe()` | Framework provides push-based pub/sub; polling introduces latency and coupling |
| LLM provider abstraction | Direct OpenAI client per node | `LiteLLMProvider` (framework built-in) | Framework manages retry, streaming, and 100+ model switching |
| Graph traversal logic | Custom node execution loop | `GraphExecutor.execute()` | Edge conditions (conditional, on_success, always, on_approve) are complex; framework handles retries too |
| HITL pause/resume | Manual asyncio.Event | `approval_callback` param on `AgentRunner` + `execution_paused` event | Framework has durable checkpoint/resume architecture |
| Tool execution context | Passing tools manually to each node | `ToolRegistry` | Auto-discovers tools from tools.py, handles MCP protocol |

**Key insight:** The framework's EventBus is the correct integration point for all real-time state monitoring. Any custom polling or state inspection mechanism will be slower, less accurate, and will break on framework upgrades.

---

## Common Pitfalls

### Pitfall 1: Framework Package Name Collision

**What goes wrong:** `pip install -e ./vendor/hive/core` installs a package named `framework`. If any other dependency also has a `framework` module, imports silently break.

**Why it happens:** The `core/pyproject.toml` names the package `framework` (generic name), not `aden_hive` or `hive_framework`.

**How to avoid:** After install, verify `python -c "import framework; print(framework.__file__)"` shows the hive path. Consider whether to rename the package locally in `pyproject.toml` to `aden_framework` before installing.

**Warning signs:** `ImportError: cannot import name 'AgentRunner' from 'framework'` — another `framework` package won the import resolution.

### Pitfall 2: _agent_runtime is None at Subscription Time

**What goes wrong:** `runner._agent_runtime` is `None` immediately after `AgentRunner.__init__()`. Subscribing to its event_bus before `_setup_agent_runtime()` runs causes `AttributeError: 'NoneType' object has no attribute 'event_bus'`.

**Why it happens:** `_setup_agent_runtime()` is called lazily inside `run()`, not in `__init__`.

**How to avoid:** Use `runner._setup(event_bus=our_bus)` to inject EventBus before `run()`. Or subscribe inside a `NODE_LOOP_STARTED` pre-hook if the framework exposes one.

**Warning signs:** Tests pass but no WS messages are delivered; `AttributeError` in async task logs.

### Pitfall 3: Python Version Mismatch

**What goes wrong:** `framework` requires Python 3.11+. The existing venv may be 3.10 or 3.12.

**Why it happens:** `pyproject.toml` specifies `requires-python = ">=3.11"`.

**How to avoid:** Verify `python --version` in the backend venv before installing. The project must use 3.11+.

**Warning signs:** `python_requires` error during `pip install -e`, or syntax errors from `str | None` type hints if on 3.9.

### Pitfall 4: Event Emission Skipped for event_loop Node Type

**What goes wrong:** `emit_node_loop_started` is NOT emitted for nodes with `node_type="event_loop"`. The frontend receives no state update for these nodes.

**Why it happens:** Confirmed from `test_executor_skips_events_for_event_loop_nodes` test — by design, event_loop nodes skip the event emission path.

**How to avoid:** Use `node_type="function_node"` or `"llm_node"` for prospector nodes. Reserve `node_type="event_loop"` only for the built-in conversational loop nodes.

**Warning signs:** Some nodes trigger WS messages, others are silent — check node_type in GraphSpec.

### Pitfall 5: Legacy broadcast() Still Called After Migration

**What goes wrong:** `main.py` still calls `orchestrator.set_broadcast_callback(manager.broadcast)`. After replacing HiveAdapter, this line remains and events go to ALL users.

**Why it happens:** Incomplete migration — the old orchestrator initialization block not fully removed.

**How to avoid:** Phase 2 plan must explicitly delete the `HiveOrchestrator` import, instantiation, and broadcast wiring in `main.py` as a single atomic step.

**Warning signs:** User B sees User A's state updates in the WebSocket.

### Pitfall 6: `uv` vs `pip` Incompatibility

**What goes wrong:** Hive uses `uv` workspace semantics. Installing with standard `pip` may fail on workspace member resolution (`tools` workspace dependency).

**Why it happens:** `core/pyproject.toml` has `tools (workspace)` as a dependency, which `pip` cannot resolve from a non-workspace context.

**How to avoid:** Either use `uv pip install -e ./vendor/hive/core` (resolving workspace deps), or manually install the tools package first: `pip install -e ./vendor/hive/tools` then `pip install -e ./vendor/hive/core`.

**Warning signs:** `ERROR: Could not find a version that satisfies the requirement tools`.

---

## Code Examples

Verified patterns from official sources:

### EventBus Subscribe and Handler
```python
# Source: https://github.com/aden-hive/hive/blob/main/core/framework/runtime/event_bus.py
from framework.runtime.event_bus import EventBus, EventType, AgentEvent

bus = EventBus()

async def on_node_started(event: AgentEvent):
    # event.node_id: str | None
    # event.stream_id: str  (use as user_id discriminator)
    # event.data: {"max_iterations": N}
    print(f"Node {event.node_id} started in stream {event.stream_id}")

sub_id = bus.subscribe(
    event_types=[EventType.NODE_LOOP_STARTED, EventType.NODE_LOOP_COMPLETED],
    handler=on_node_started,
    filter_stream="user_abc123",  # tenant filter
)
```

### AgentEvent → AgentState Mapping
```python
# Source: models.py (existing) + event types from EVENT_TYPES.md
from framework.runtime.event_bus import EventType
from models import AgentState

def _event_to_agent_state(event) -> AgentState | None:
    mapping = {
        EventType.NODE_LOOP_STARTED:    AgentState.THINKING,
        EventType.TOOL_CALL_STARTED:    AgentState.TOOL_USE,
        EventType.TOOL_CALL_COMPLETED:  AgentState.THINKING,   # back to thinking after tool
        EventType.NODE_LOOP_COMPLETED:  AgentState.WAITING,
        EventType.CLIENT_INPUT_REQUESTED: AgentState.WAITING,  # HITL pause
        # execution_completed → IDLE when run finishes
        EventType.EXECUTION_COMPLETED:  AgentState.IDLE,
        EventType.EXECUTION_FAILED:     AgentState.ERROR,      # maps to existing ERROR state
    }
    return mapping.get(event.type)
```

### GraphExecutor Constructor (for direct use)
```python
# Source: https://github.com/aden-hive/hive/blob/main/core/framework/graph/executor.py
from framework.graph.executor import GraphExecutor
from framework.runtime.event_bus import EventBus

bus = EventBus()
executor = GraphExecutor(
    runtime=runtime,
    llm=llm_provider,           # None for mock/stub
    tools=tool_list,            # [] for stub
    event_bus=bus,              # inject our bus
    stream_id=user_id,          # tenant discriminator
    execution_id=str(uuid4()),
)
result = await executor.execute(
    graph=graph_spec,
    goal=goal,
    input_data={"empresa_url": "..."},
    validate_graph=False,       # skip validation in Phase 2 stub
)
# result.session_state["memory"] — full memory snapshot
# result.session_state["execution_path"] — traversed node IDs
```

### AgentRunner Constructor (direct, bypassing load())
```python
# Source: https://github.com/aden-hive/hive/blob/main/core/framework/runner/runner.py
from framework.runner.runner import AgentRunner
from pathlib import Path

runner = AgentRunner(
    agent_path=Path("./stub_agent"),
    graph=stub_graph,
    goal=stub_goal,
    mock_mode=True,             # No real LLM calls
    storage_path=Path(f"/tmp/hive_runs/{user_id}"),  # per-user storage
    interactive=False,          # Required for server use (no stdin prompts)
    skip_credential_validation=True,  # Phase 2 stub — no real API keys needed
)
```

### SharedMemory — Correct Usage
```python
# Source: https://github.com/aden-hive/hive/blob/main/core/framework/graph/node.py
from framework.graph.node import SharedMemory

# Per-run instantiation (GraphExecutor does this internally)
memory = SharedMemory()
memory.write("current_prospect", {"url": "https://example.com"}, validate=False)
val = memory.read("current_prospect")
snapshot = memory.read_all()  # returns dict copy
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled `HiveOrchestrator` with OpenAI Swarm | `AgentRunner` + `GraphExecutor` + `EventBus` | Phase 2 migration | Replaces ~280 lines of mock orchestrator with real graph execution |
| Global `manager.broadcast()` for all WS messages | `manager.send_to_user(user_id, msg)` per tenant | Phase 1 added send_to_user; Phase 2 removes broadcast | Cross-tenant WS leakage eliminated |
| Direct OpenAI client in orchestrator | `LiteLLMProvider` via framework | Phase 2 | Model-agnostic; supports Claude, GPT-4, Gemini without code changes |
| Single shared state dict in HiveOrchestrator | Per-run `SharedMemory` instances | Phase 2 | True isolation — user A's state cannot bleed into user B |

**Deprecated/outdated:**
- `orchestrator.py` (`HiveOrchestrator`): Remove entirely in Phase 2. No compatibility shim needed.
- `orchestrator.set_broadcast_callback(manager.broadcast)`: Remove from `main.py` lifespan.
- `openai==1.12.0` in requirements.txt: May be removable after Phase 2 if no other code uses it directly. Keep for now; remove in Phase 3 cleanup.

---

## Open Questions

1. **EventBus subscription before _setup_agent_runtime() — exact timing**
   - What we know: `_agent_runtime` is None after `__init__`. `_setup(event_bus=external_bus)` accepts a bus.
   - What's unclear: Does `runner._setup(event_bus=bus)` need to be called explicitly, or does `runner.run()` call it automatically (possibly ignoring the external bus if one isn't pre-injected)?
   - Recommendation: Test this first in a scratch script after install. If `_setup()` is auto-called by `run()`, inject via `runner._setup(event_bus=bus)` before `run()`. If that doesn't work, construct `GraphExecutor` directly (bypassing AgentRunner) with `event_bus=bus`.

2. **pip vs uv install — workspace dep `tools`**
   - What we know: `core/pyproject.toml` lists `tools (workspace)` as dependency. Standard pip may not resolve this.
   - What's unclear: Whether `pip install -e ./vendor/hive/core` resolves the tools workspace member automatically or fails.
   - Recommendation: Wave 0 plan item — test install in a clean venv and document exact command that works before writing any adapter code.

3. **hive v0.6.0 vs current HEAD (v0.7.1)**
   - What we know: negocio.md references v0.6.0. GitHub HEAD is v0.7.1. No v0.6.0 tag was confirmed.
   - What's unclear: Whether there is a `v0.6.0` git tag that matches the API documented in negocio.md, or whether we should pin to HEAD.
   - Recommendation: `git tag -l` in the cloned repo. If `v0.6.0` tag exists, pin to it. If not, use HEAD and update the requirement spec.

4. **mock_mode=True behavior on AgentRunner**
   - What we know: Constructor parameter `mock_mode: bool = False` confirmed.
   - What's unclear: What mock_mode actually does — does it stub LLM calls, skip all external I/O, or just skip credential validation? Does it still emit EventBus events?
   - Recommendation: Examine `runner.py` around `mock_mode` usage after install. If EventBus events are not emitted in mock_mode, use `FakeEventBus` pattern from `test_graph_executor.py` directly.

---

## Validation Architecture

> nyquist_validation is true — section required.

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| Config file | `backend/pytest.ini` (asyncio_mode = auto) |
| Quick run command | `cd backend && python -m pytest tests/test_hive_adapter.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| HIVE-01 | `import AgentRunner` succeeds; no ImportError | smoke | `pytest tests/test_hive_adapter.py::test_hive_import_ok -x` | Wave 0 |
| HIVE-01 | `AgentRunner(mock_mode=True)` instantiates without error | unit | `pytest tests/test_hive_adapter.py::test_agent_runner_instantiates -x` | Wave 0 |
| HIVE-02 | `HiveAdapter` exists; `main.py` has zero `from framework` imports | static/unit | `pytest tests/test_hive_adapter.py::test_hive_adapter_is_only_seam -x` | Wave 0 |
| HIVE-02 | Starting a run via `HiveAdapter.start_run()` does not raise | integration | `pytest tests/test_hive_adapter.py::test_start_run_no_error -x` | Wave 0 |
| HIVE-03 | WS message for user_A NOT delivered to user_B's connection | integration | `pytest tests/test_hive_adapter.py::test_ws_isolation_user_a_not_b -x` | Wave 0 |
| HIVE-03 | WS message IS delivered to user_A's connection | integration | `pytest tests/test_hive_adapter.py::test_ws_delivery_correct_user -x` | Wave 0 |
| HIVE-04 | Two concurrent runs have separate SharedMemory objects (no shared reference) | unit | `pytest tests/test_hive_adapter.py::test_shared_memory_per_run_isolation -x` | Wave 0 |
| HIVE-05 | `node_loop_started` event produces `AgentState.THINKING` WS message | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_thinking -x` | Wave 0 |
| HIVE-05 | `tool_call_started` event produces `AgentState.TOOL_USE` WS message | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_tool_use -x` | Wave 0 |
| HIVE-05 | `node_loop_completed` event produces `AgentState.WAITING` WS message | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_waiting -x` | Wave 0 |
| HIVE-05 | `client_input_requested` event produces `AgentState.WAITING` WS message | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_waiting_hitl -x` | Wave 0 |

### Which Tests Need Real Hive Framework vs. Mocks

| Test Group | Needs Real Hive? | Why |
|------------|-----------------|-----|
| HIVE-01 (import smoke) | YES — real install | Cannot mock the import itself |
| HIVE-01 (instantiation) | YES — real install | Tests actual constructor |
| HIVE-02 (seam enforcement) | NO — static analysis | `grep` or `ast.parse` checks for forbidden imports in main.py |
| HIVE-02 (start_run) | YES — real AgentRunner with mock_mode=True | Tests real integration path |
| HIVE-03 (WS isolation) | NO — mock AgentRunner + FakeEventBus | Tests ConnectionManager routing only |
| HIVE-04 (SharedMemory isolation) | NO — mock or direct SharedMemory() instantiation | SharedMemory is a simple dataclass |
| HIVE-05 (event mapping) | NO — FakeEventBus + HiveAdapter | Tests `_event_to_agent_state()` logic only |

### Test Isolation Strategy for Tenant Tests

The HIVE-03 and HIVE-04 tests are the critical multi-tenant isolation tests. Strategy:

```python
# Pattern: Two async WS clients, two users, one run each
async def test_ws_isolation_user_a_not_b():
    received_by_b = []

    # Wire up two "connections" in ConnectionManager
    mock_ws_a = MockWebSocket()
    mock_ws_b = MockWebSocket()
    manager = ConnectionManager()
    await manager.connect(mock_ws_a, user_id="user_a")
    await manager.connect(mock_ws_b, user_id="user_b")

    # Fire an event for user_a only
    fake_event = FakeAgentEvent(stream_id="user_a", type=EventType.NODE_LOOP_STARTED, node_id="stub_start")
    adapter = HiveAdapter(send_to_user_callback=manager.send_to_user)
    await adapter._make_event_handler("user_a")(fake_event)

    # user_b must have received nothing
    assert len(mock_ws_b.sent_messages) == 0
    assert len(mock_ws_a.sent_messages) == 1
```

### Sampling Rate
- **Per task commit:** `cd backend && python -m pytest tests/test_hive_adapter.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -q`
- **Phase gate:** Full suite green (21 existing + new hive tests) before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_hive_adapter.py` — 11 test stubs covering HIVE-01 through HIVE-05 (all xfail initially)
- [ ] `backend/hive_adapter.py` — file must exist (even empty) for import tests
- [ ] `backend/hive_graph.py` — stub GraphSpec + Goal definitions
- [ ] `backend/stub_agent/` — minimal agent directory for `AgentRunner.load()` (if used)
- [ ] Framework install: `pip install -e ../vendor/hive/core` — must be in requirements.txt as `framework @ file:../vendor/hive/core` or added to venv — confirm exact syntax in Wave 0

---

## Sources

### Primary (HIGH confidence)
- GitHub: `aden-hive/hive/core/framework/graph/executor.py` — GraphExecutor constructor, execute() signature, SharedMemory instantiation (no namespace= param confirmed), event emission calls
- GitHub: `aden-hive/hive/core/framework/runtime/event_bus.py` — EventBus constructor, subscribe() full signature, event subscription pattern
- GitHub: `aden-hive/hive/core/framework/runtime/EVENT_TYPES.md` — Complete event type catalog with payload structures
- GitHub: `aden-hive/hive/core/framework/graph/node.py` — SharedMemory dataclass (no namespace field), NodeContext, NodeResult
- GitHub: `aden-hive/hive/core/framework/runner/runner.py` — AgentRunner constructor, mock_mode param, _agent_runtime=None pattern, _setup(event_bus=) method
- GitHub: `aden-hive/hive/core/framework/runtime/agent_runtime.py` — AgentRuntime.event_bus property, subscribe_to_events() method, external EventBus injection
- GitHub: `aden-hive/hive/core/pyproject.toml` — package name `framework`, version 0.7.1, python >=3.11, dependencies
- GitHub: `aden-hive/hive/core/tests/test_graph_executor.py` — FakeEventBus pattern, DummyRuntime, stub node testing patterns
- DeepWiki: https://deepwiki.com/adenhq/hive — Cross-reference for API surface and architecture overview

### Secondary (MEDIUM confidence)
- GitHub: `aden-hive/hive/core/framework/__init__.py` — public exports list (AgentRunner, AgentOrchestrator confirmed public)
- GitHub: `aden-hive/hive` README — "not installed via pip"; uv workspace; Python 3.11+ requirement
- GitHub: `aden-hive/hive/core/README.md` — editable install via `uv pip install -e .`

### Tertiary (LOW confidence — flag for validation)
- negocio.md reference to `v0.6.0`: No git tag confirmed; HEAD is v0.7.1. Version discrepancy unresolved.
- `runner._setup(event_bus=bus)` pre-injection behavior: Confirmed method exists; exact runtime behavior when called before `run()` not verified by test inspection.
- `mock_mode=True` EventBus emission behavior: mock_mode confirmed as constructor parameter; whether events are still emitted in mock_mode is inferred from AgentRunner patterns but not directly verified.

---

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM — package identified (not on PyPI), install method confirmed (editable from clone), dependency list verified from pyproject.toml; exact install command needs validation in clean venv
- Architecture: MEDIUM-HIGH — GraphExecutor constructor, EventBus subscribe API, NodeContext structure all verified from source. _agent_runtime private access is confirmed but carries upgrade risk.
- Pitfalls: HIGH — SharedMemory namespace= absence is confirmed from source (not an inference). Event type skipping for event_loop nodes confirmed from test. Package name collision is a real risk (package named "framework").
- HIVE-04 namespace finding: HIGH — SharedMemory dataclass fields confirmed; no namespace field present.

**Research date:** 2026-03-18
**Valid until:** 2026-04-17 (30 days — framework is under active development; re-verify if hive is updated)
