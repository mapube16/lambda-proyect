# Architecture Research

**Domain:** AaaS B2B prospecting platform — FastAPI + React pixel art office with Hive framework integration
**Researched:** 2026-03-17
**Confidence:** MEDIUM-HIGH (based on project documentation in negocio.md, direct code inspection of all existing files, and Hive framework structure documented by the project owner)

---

## Standard Architecture

### System Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         FRONTEND LAYER                               │
│                                                                      │
│  ┌──────────────────┐  ┌─────────────────┐  ┌────────────────────┐  │
│  │  OfficeCanvas    │  │   AgentPanel    │  │  LeadDashboard     │  │
│  │  (pixel art UI)  │  │  (controls +    │  │  (expedientes +    │  │
│  │  Characters +    │  │   config form)  │  │   HITL approvals)  │  │
│  │  bubbles +       │  │                 │  │                    │  │
│  │  animations      │  │                 │  │                    │  │
│  └────────┬─────────┘  └────────┬────────┘  └─────────┬──────────┘  │
│           │                    │                      │             │
│           └──────────────── officeStore (Zustand) ────┘             │
│                                │                                    │
│                         useWebSocket hook                           │
│                                │ WebSocket /ws                      │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────────┐
│                      FASTAPI LAYER                                   │
│                                │                                    │
│  ┌──────────────────────────────┴──────────────────────────────┐    │
│  │               ConnectionManager (WebSocket hub)              │    │
│  │  broadcast({type, agent_id, state, ...}) → all clients      │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  ┌──────────────────────────────┴──────────────────────────────┐    │
│  │                  HiveAdapter (NEW — replaces HiveOrchestrator)│   │
│  │                                                              │    │
│  │  - Holds AgentRunner instance                                │    │
│  │  - Wraps GraphExecutor events → broadcast calls             │    │
│  │  - Manages run registry (run_id → asyncio.Event for HITL)   │    │
│  │  - Exposes: start_run(), approve_lead(), reject_lead()      │    │
│  └──────────────────────────────┬──────────────────────────────┘    │
│                                 │                                    │
│  REST endpoints: /api/agents, /api/runs, /api/leads                 │
│  WebSocket: /ws  (ping, create_agent, run_task, hitl_decision)      │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────────┐
│                       HIVE FRAMEWORK LAYER                          │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │   AgentRunner   │  │  GraphExecutor  │  │   SharedMemory      │  │
│  │                 │──│                 │  │  STM / LTM / RLM    │  │
│  │  Loads          │  │  Executes node  │  │                     │  │
│  │  agent.json     │  │  graph, emits   │  │  Current prospect   │  │
│  │  (GraphSpec)    │  │  events per     │  │  Lead history       │  │
│  └─────────────────┘  │  node step      │  │  Semantic search    │  │
│                        └────────┬────────┘  └─────────────────────┘  │
│                                 │ NodeContext injected per node       │
│  ┌─────────────────┐  ┌─────────┴────────┐  ┌─────────────────────┐  │
│  │  LiteLLMProvider│  │   NodeContext    │  │   ToolRegistry      │  │
│  │                 │  │                 │  │                     │  │
│  │  Claude /        │  │  .llm           │  │  web_search_tool    │  │
│  │  GPT-4 /         │  │  .memory        │  │  web_scrape_tool    │  │
│  │  Gemini          │  │  .tools         │  │  file_system_tools  │  │
│  │  (via LiteLLM)   │  │  .run_id        │  │  custom tools       │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
                                 │
┌────────────────────────────────┼────────────────────────────────────┐
│                        MCP TOOL SERVERS                              │
│                                                                      │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────┐  │
│  │  aden_tools     │  │  clay_enrichment│  │   hubspot_crm       │  │
│  │  (STDIO server) │  │  (HTTP/SSE)     │  │   (HTTP/SSE)        │  │
│  │  web_search     │  │                 │  │   (v2, out-of-scope) │  │
│  │  web_scrape     │  │  (v2)           │  │                     │  │
│  │  file_system    │  │                 │  │                     │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────┘  │
└──────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `OfficeCanvas` | Pixel art rendering, character animations, bubble states | `officeStore` (reads characters) |
| `AgentPanel` | Agent list display, task dispatch, campaign form | `officeStore`, WebSocket via `useWebSocket` |
| `LeadDashboard` | Expediente cards, HITL approve/reject buttons | WebSocket (sends `hitl_decision`) |
| `officeStore` (Zustand) | Single client-side truth: agents map, characters map, WS ref | All frontend components |
| `useWebSocket` hook | WS lifecycle, reconnect with backoff, message dispatch | `officeStore`, backend `/ws` |
| `ConnectionManager` | WebSocket hub: tracks active connections, broadcasts JSON | All connected WS clients |
| `HiveAdapter` | Bridge between Hive events and WS broadcasts; run registry; HITL gate | `ConnectionManager`, `AgentRunner`, REST handlers |
| `AgentRunner` | Loads `agent.json` (GraphSpec), boots GraphExecutor per run | `GraphExecutor`, `SharedMemory` |
| `GraphExecutor` | Executes node graph, injects `NodeContext`, respects edge conditions | `NodeContext`, `SharedMemory`, all node implementations |
| `NodeContext` | Per-node DI container: llm, memory, tools, run_id | `LiteLLMProvider`, `SharedMemory`, `ToolRegistry` |
| `SharedMemory` (STM) | Short-term state for the current prospect being processed | Nodes within same run |
| `SharedMemory` (LTM) | Persistent store of all processed leads across runs | Nodes + external queries |
| `ToolRegistry` | Tool registration and dispatch; wraps MCP client calls | MCP servers (STDIO/HTTP) |
| `LiteLLMProvider` | Unified LLM interface across Claude/GPT-4/Gemini | Hive nodes |

---

## Recommended Project Structure

```
backend/
├── main.py                       # FastAPI app, lifespan, REST + WS endpoints
├── models.py                     # Pydantic: Agent, AgentState, AgentRole (extend with ProspectorRun, Lead)
├── hive_adapter.py               # NEW: HiveAdapter — replaces orchestrator.py
├── orchestrator.py               # DEPRECATE after HiveAdapter is live
├── requirements.txt              # Add hive framework dependency
│
exports/                          # Hive agent exports (per Hive convention)
├── prospector_b2b/
│   ├── agent.json                # GraphSpec: nodes + edges for prospector pipeline
│   ├── tools.py                  # Custom tools: linkedin_scraper, etc.
│   ├── __main__.py               # CLI entry point (hive run exports/prospector_b2b)
│   └── tests/                    # Node-level tests
│
frontend/src/
├── components/
│   ├── OfficeCanvas.tsx          # KEEP AS-IS (pixel art rendering)
│   ├── AgentPanel.tsx            # EXTEND: add campaign form, config viewer
│   ├── LeadDashboard.tsx         # NEW: expediente cards + HITL approve/reject
│   └── AgentConfigModal.tsx      # NEW: click on character → see system prompt + vars
├── store/
│   └── officeStore.ts            # EXTEND: add leads map, hitl_pending flag
├── hooks/
│   ├── useWebSocket.ts           # EXTEND: handle new WS message types
│   └── useGameLoop.ts            # KEEP AS-IS
├── types/
│   └── index.ts                  # EXTEND: add ProspectorRun, Lead, HitlRequest types
└── constants.ts                  # KEEP AS-IS
```

### Structure Rationale

- **`hive_adapter.py`** is the single seam between FastAPI and the Hive framework. Nothing in `main.py` should import Hive directly — all Hive coupling lives here. This makes testing and incremental migration safe.
- **`exports/prospector_b2b/`** follows Hive's own directory convention, enabling `hive run` CLI and `hive tui` to work unchanged. The backend mounts this programmatically via `AgentRunner`.
- **`LeadDashboard.tsx`** is new but isolated — it can be added as a panel toggle without touching `OfficeCanvas.tsx`, preserving the working pixel art rendering.

---

## Architectural Patterns

### Pattern 1: HiveAdapter as Event Bridge

**What:** A thin adapter class wraps `AgentRunner`/`GraphExecutor` and translates internal Hive node lifecycle events into `ConnectionManager.broadcast()` calls. The adapter registers an async callback (or async generator hook) on the GraphExecutor before each run begins.

**When to use:** Any time a Hive execution event needs to reach the WebSocket layer. This is the only place that coupling lives.

**Trade-offs:** Adds one layer of indirection, but decouples Hive internals from FastAPI entirely. GraphExecutor API changes only require changes in `hive_adapter.py`.

**Example:**
```python
# hive_adapter.py
class HiveAdapter:
    def __init__(self, broadcast_fn):
        self._broadcast = broadcast_fn
        self._runner = AgentRunner("exports/prospector_b2b")
        self._hitl_events: dict[str, asyncio.Event] = {}
        self._hitl_decisions: dict[str, str] = {}

    async def _on_node_event(self, event: NodeEvent):
        """Called by GraphExecutor on each node state change."""
        await self._broadcast({
            "type": "agent_update",
            "agent_id": event.node_id,
            "state": self._map_hive_state(event.state),
            "current_tool": event.tool_name,
            "tool_status": event.tool_status,
        })
        if event.state == "hitl_waiting":
            await self._broadcast({
                "type": "hitl_request",
                "run_id": event.run_id,
                "agent_id": event.node_id,
                "expediente": event.context.get("expediente"),
            })

    def _map_hive_state(self, hive_state: str) -> str:
        mapping = {
            "running": "thinking",
            "tool_call": "tool_use",
            "hitl_waiting": "waiting",
            "complete": "idle",
            "error": "error",
        }
        return mapping.get(hive_state, "idle")
```

### Pattern 2: HITL as asyncio.Event Gate

**What:** When `human_review` node executes inside GraphExecutor, it awaits an `asyncio.Event` stored in a registry keyed by `run_id`. The FastAPI WebSocket handler receives a `hitl_decision` message from the client, looks up the event, stores the decision, and sets the event. The waiting Hive node unblocks, reads the decision from context, and routes accordingly.

**When to use:** Any node that must pause graph execution and wait for human input without blocking the event loop.

**Trade-offs:** Clean non-blocking suspension. Requires the `run_id` to be passed through context to the `human_review` node so it can look up its own gate. Event objects are held in memory — runs that disconnect before deciding need a timeout or persistence strategy.

**Example:**
```python
# hive_adapter.py — HITL gate
async def start_run(self, run_id: str, input_vars: dict):
    gate = asyncio.Event()
    self._hitl_events[run_id] = gate
    asyncio.create_task(
        self._runner.run(run_id=run_id, inputs=input_vars,
                         on_node_event=self._on_node_event,
                         hitl_gate=gate)
    )

async def resolve_hitl(self, run_id: str, decision: str):
    self._hitl_decisions[run_id] = decision
    event = self._hitl_events.get(run_id)
    if event:
        event.set()
```

```python
# human_review node inside agent.json execution
async def execute(self, ctx: NodeContext) -> dict:
    gate: asyncio.Event = ctx.runtime["hitl_gate"]
    await gate.wait()                          # suspends coroutine, does NOT block thread
    decision = ctx.runtime["hitl_decisions"][ctx.run_id]
    return {"approved": decision == "approve"}
```

### Pattern 3: NodeContext State → AgentState Mapping

**What:** Hive's GraphExecutor emits node lifecycle events with states like `running`, `tool_call`, `hitl_waiting`, `complete`, `error`. The `HiveAdapter._map_hive_state()` method translates these into the four frontend `AgentState` values (`thinking`, `tool_use`, `waiting`, `idle`, `error`) that `officeStore` already understands.

**When to use:** Every GraphExecutor event subscription. The mapping is the contract between the Hive layer and the frontend animation layer.

**Trade-offs:** The existing frontend animation logic (`officeStore.ts` `getBubbleType`, character state transitions) requires no changes because the same four AgentState strings are reused. The HITL state maps to `waiting`, which already has a bubble animation.

| Hive Node State | Frontend AgentState | Character Visual |
|-----------------|--------------------|--------------------|
| `running` | `thinking` | Thinking bubble, typing animation |
| `tool_call` | `tool_use` | Tool bubble with tool name, typing animation |
| `hitl_waiting` | `waiting` | Waiting bubble, idle animation |
| `complete` | `idle` | No bubble, wander behavior |
| `error` | `error` | Error bubble, idle animation |

---

## Data Flow

### Prospector Run Flow

```
User (browser)
    │ POST /api/runs  { campaign_vars, company_url }
    ▼
HiveAdapter.start_run(run_id, input_vars)
    │ asyncio.create_task(AgentRunner.run(..., on_node_event=...))
    ▼
GraphExecutor begins node traversal
    │
    ├─ sourcing_node executes
    │      NodeContext.tools.execute("web_search_tool", ...)
    │      → HiveAdapter._on_node_event(state="tool_call", tool="web_search_tool")
    │      → ConnectionManager.broadcast({type:"agent_update", state:"tool_use"})
    │      → officeStore.updateAgent → character walks to seat, types, shows tool bubble
    │
    ├─ scraping_node executes (web_scrape_tool)
    │      same event chain
    │
    ├─ scoring_node + veto_router execute
    │      if score < 70: GraphExecutor routes to end_rejected
    │      → broadcast({type:"run_rejected", run_id, reason})
    │
    ├─ spiced_analyzer → jtbd_deducer → email_composer → expediente_generator
    │      each emits agent_update events → character animations continue
    │
    └─ human_review node
           → _on_node_event(state="hitl_waiting")
           → broadcast({type:"hitl_request", run_id, expediente: {...}})
           → LeadDashboard renders expediente card with Approve/Reject buttons
           → await gate.wait()  ← coroutine suspended here

User clicks Approve or Reject in LeadDashboard
    │ WebSocket: {type:"hitl_decision", run_id, decision:"approve"}
    ▼
HiveAdapter.resolve_hitl(run_id, "approve")
    │ gate.set() → human_review node unblocks
    ▼
GraphExecutor routes on_approve → crm_pusher (v2) or end_approved
    │ broadcast({type:"run_complete", run_id, lead_data})
    ▼
Frontend: LeadDashboard moves card to "approved" list
          officeStore.updateAgent(state:"idle") → character wanders
```

### WebSocket Message Protocol (Extended)

```
Backend → Frontend (broadcast):
  { type: "initial_state",  agents: Agent[] }
  { type: "agent_update",   agent_id, state, current_tool, tool_status }
  { type: "agent_created",  agent: Agent }
  { type: "agent_removed",  agent_id }
  { type: "hitl_request",   run_id, agent_id, expediente: {...} }
  { type: "run_rejected",   run_id, reason, empresa }
  { type: "run_complete",   run_id, lead_data: {...} }

Frontend → Backend (send):
  { type: "ping" }
  { type: "create_agent",   name, role }
  { type: "run_task",       agent_id, task }
  { type: "hitl_decision",  run_id, decision: "approve" | "reject" }
  { type: "start_run",      campaign_vars: {...}, company_url }
```

### MCP Tool Call Chain

```
Node executes inside GraphExecutor
    ↓ ctx.tools.execute("web_search_tool", {query: "..."})
ToolRegistry routes to MCPClient
    ↓ STDIO/HTTP call to aden_tools MCP server
aden_tools server (uv run python -m aden_tools.mcp_server)
    ↓ Returns tool result JSON
NodeContext delivers result back to node function
    ↓ Node stores result via ctx.memory.set("scraped_content", ...)
SharedMemory (STM) — available to subsequent nodes in same run
```

---

## Suggested Build Order

Build order is driven by dependency: each layer depends on the one below it being stable.

```
1. HiveAdapter skeleton (no real Hive yet)
   └── Replace orchestrator.py with hive_adapter.py stub
   └── Preserves all existing WS behavior while migration begins
   └── Validate: existing pixel art office still works

2. Hive framework installation + agent.json scaffold
   └── pip install aden-hive (or clone + pip install -e)
   └── Create exports/prospector_b2b/agent.json with GraphSpec
   └── Validate: hive run exports/prospector_b2b --dry-run works

3. GraphExecutor ↔ HiveAdapter event bridge
   └── Implement _on_node_event callback registration
   └── Implement _map_hive_state translation
   └── Validate: running a graph emits correct WS broadcasts

4. MCP tools setup (web_search_tool + web_scrape_tool)
   └── Configure mcp_servers.json pointing to aden_tools
   └── Register tools in ToolRegistry
   └── Validate: sourcing_node + scraping_node execute with real data

5. Core prospector nodes (sourcing → scraping → scoring → veto)
   └── Implement node functions using NodeContext API
   └── Embed personalidad.md logic into scoring_node/veto_router
   └── Validate: end-to-end rejection path works

6. Output nodes (spiced → jtbd → email_composer → expediente_generator)
   └── Implements all of personalidad.md Módulos 3-4
   └── Validate: approved prospect produces expediente JSON + Markdown

7. HITL asyncio.Event gate
   └── Implement HiveAdapter.start_run / resolve_hitl
   └── Add hitl_decision WS message handler in main.py
   └── Validate: graph pauses at human_review, resumes on approve

8. Frontend LeadDashboard + HITL UI
   └── New component consuming hitl_request + run_complete messages
   └── Approve/Reject buttons send hitl_decision back
   └── Validate: full loop from company URL to approved lead

9. Campaign configuration UI
   └── AgentConfigModal: click character → see system prompt + 10 variables
   └── Campaign form in AgentPanel: submit sends start_run WS message
   └── Validate: pilot user can configure and launch from the office UI

10. Auth (Supabase / Auth0)
    └── Add per-user isolation to run registry and SharedMemory LTM
    └── Build last — authentication context doesn't unblock any prior step
```

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 1-5 concurrent users (MVP) | Single FastAPI process, in-memory run registry, SQLite for leads, aden_tools STDIO is fine |
| 5-50 concurrent users | Move run registry to Redis (asyncio.Event → Redis pub/sub for HITL), PostgreSQL for leads, run aden_tools as persistent HTTP server |
| 50+ concurrent users | Separate FastAPI process from Hive worker pool, task queue (Celery + Redis) for graph execution, per-user Hive agent isolation via run namespaces |

### Scaling Priorities

1. **First bottleneck:** LLM latency per node. Multiple nodes run sequentially per prospect. At 5+ simultaneous runs, OpenAI/Anthropic rate limits hit first. Mitigation: semaphore limiting concurrent LLM calls; LiteLLM retry/fallback config.
2. **Second bottleneck:** `asyncio.create_task` for runs on a single event loop. At 10+ simultaneous long-running graphs, the main FastAPI process event loop saturates. Mitigation: offload graph execution to a background worker process communicating via Redis queue.

---

## Anti-Patterns

### Anti-Pattern 1: Importing Hive Directly in main.py

**What people do:** `from core.framework.executor import GraphExecutor` in `main.py`, spreading Hive coupling across the entire FastAPI app.

**Why it's wrong:** Any Hive API change (it is v0.6.0, pre-1.0) breaks uncontained surface area. Testing becomes impossible without a full Hive runtime.

**Do this instead:** All Hive imports live exclusively in `hive_adapter.py`. `main.py` only calls `hive_adapter.start_run()`, `hive_adapter.resolve_hitl()`. This is the seam.

### Anti-Pattern 2: Blocking the FastAPI Event Loop with Graph Execution

**What people do:** `await runner.run(...)` directly in a REST endpoint or WebSocket handler, blocking the entire server while a multi-node graph runs.

**Why it's wrong:** A single prospect run can take 30-90 seconds (multiple LLM calls + web scraping). Every other WebSocket connection freezes during that time.

**Do this instead:** `asyncio.create_task(runner.run(...))` in the adapter. The run executes concurrently. Progress is pushed back via the broadcast callback, not returned from the endpoint.

### Anti-Pattern 3: Rebuilding HITL with HTTP Polling

**What people do:** Frontend polls `GET /api/runs/{id}/status` every 2 seconds to check if a run is waiting for HITL input.

**Why it's wrong:** The WebSocket connection is already open. Polling adds latency, server load, and complexity. The HITL state change is an event — treat it as one.

**Do this instead:** Backend broadcasts `hitl_request` over the existing WebSocket. Frontend renders the approval UI reactively when this message arrives. Decision is sent back over the same WebSocket.

### Anti-Pattern 4: Storing Lead State Only in SharedMemory

**What people do:** All lead/expediente data lives in Hive's SharedMemory (STM/LTM), accessed only through NodeContext.

**Why it's wrong:** SharedMemory is designed for agent-internal state during execution. It is not a queryable database. The LeadDashboard needs to list, filter, and retrieve leads without triggering a graph run.

**Do this instead:** When `expediente_generator` node completes, write the final lead JSON to a persistent store (SQLite or PostgreSQL) via a FastAPI endpoint or direct DB write. SharedMemory is for intra-run state; the DB is for the product's lead catalog.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| aden_tools (web_search, web_scrape) | MCP STDIO server, spawned by Hive ToolRegistry | Must be installed: `uv run python -m aden_tools.mcp_server`. Requires Brave Search API key for web_search_tool. |
| LiteLLM → Claude/GPT-4 | LiteLLMProvider inside NodeContext | Set `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`. LiteLLM handles retry/fallback between providers. |
| Supabase Auth (v2) | FastAPI dependency injection on WS endpoint | Add `user_id` to WebSocket handshake header; validate JWT in `ConnectionManager.connect()`. |
| HubSpot CRM (v2) | MCP HTTP/SSE server | Out of scope for MVP. Placeholder `crm_pusher` node can write to local DB instead. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `main.py` ↔ `HiveAdapter` | Direct async method calls | HiveAdapter is a singleton initialized in FastAPI lifespan, replacing the current orchestrator init pattern. |
| `HiveAdapter` ↔ `GraphExecutor` | Callback injection (`on_node_event` async callable) | The exact callback API depends on Hive v0.6.0 internals. Verify callback registration signature before implementation (confidence: MEDIUM — based on project docs, not code inspection of the framework itself). |
| `human_review node` ↔ `HiveAdapter` | Shared asyncio.Event via `ctx.runtime` dict | The `runtime` dict is injected into NodeContext at run start. This is the lowest-coupling HITL mechanism that avoids any Hive-internal HITL API assumptions. |
| `GraphExecutor nodes` ↔ `SharedMemory` | `ctx.memory.get/set` | STM is cleared per run. LTM persists. Use STM for intra-pipeline data (scraped content, score), LTM for cross-run lead history. |
| `Frontend officeStore` ↔ `LeadDashboard` | Zustand store slices | Add `leads: Map<string, Lead>` and `hitlPending: Map<string, HitlRequest>` to the store. `LeadDashboard` subscribes to these slices; `useWebSocket` populates them from WS messages. |

---

## Sources

- Project documentation: `negocio.md` (Hive framework component map, node graph, memory layers, MCP tools) — HIGH confidence for component names and structure
- Direct code inspection: `backend/main.py`, `backend/orchestrator.py`, `backend/models.py` — HIGH confidence for existing API surface
- Direct code inspection: `frontend/src/store/officeStore.ts`, `frontend/src/hooks/useWebSocket.ts`, `frontend/src/types/index.ts` — HIGH confidence for frontend state and WS protocol
- Hive framework reference: `negocio.md` cites `aden-hive/hive` v0.6.0, GitHub: https://github.com/aden-hive/hive — MEDIUM confidence (framework not installed in venv; exact callback API unverified against source code)
- FastAPI + WebSocket async patterns: training knowledge verified against existing working code — HIGH confidence

---

*Architecture research for: Hive Pixel Office — FastAPI + Hive framework integration*
*Researched: 2026-03-17*
