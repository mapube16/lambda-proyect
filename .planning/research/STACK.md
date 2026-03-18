# Stack Research

**Domain:** AaaS B2B Prospecting Platform — Brownfield extension of FastAPI + React/Vite pixel art office
**Researched:** 2026-03-17
**Confidence:** MEDIUM — Hive framework (aden-hive/hive v0.6.0) is a private/early-access repo; internals documented via negocio.md project notes and architecture analysis. Supporting ecosystem (FastAPI, LiteLLM, MCP, JWT, Zustand) is HIGH confidence from training data.

---

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.11+ | Backend runtime | Hive framework requires 3.11+; `asyncio.TaskGroup` and `tomllib` in stdlib; existing venv is 3.11 |
| FastAPI | 0.115.x | REST API + WebSocket host | Already in codebase. Async-native, Pydantic v2 integration, WebSocket support is first-class. Keep and extend — don't replace |
| uvicorn[standard] | 0.34.x | ASGI server | Already in use. `[standard]` pulls in `uvloop` (Linux) + `httptools` for performance; websockets support included |
| aden-hive/hive | v0.6.0 (git install) | Agent graph execution engine | The entire migration target. Provides `AgentRunner`, `GraphExecutor`, `NodeContext`, `LiteLLMProvider`, `ToolRegistry`, `SharedMemory` (STM/LTM/RLM), `BuildSession`. Replaces the hand-rolled `HiveOrchestrator` |
| LiteLLM | 1.x (pulled by hive) | LLM provider abstraction | Hive uses `LiteLLMProvider` internally; gives access to 100+ models (Claude, GPT-4o, Gemini) behind one API. Use `claude-3-5-sonnet-20241022` as default for scoring/email nodes — best instruction-following |
| Pydantic | 2.6.x | Data validation / serialization | Already in models.py. Hive also uses Pydantic v2 for `GraphSpec`, `NodeSpec`, `Goal`. Keep v2, do not downgrade |
| python-jose[cryptography] | 3.3.x | JWT token creation/validation | Standard for FastAPI auth; handles HS256 for stateless session tokens in the multi-tenant layer |
| passlib[bcrypt] | 1.7.x | Password hashing | bcrypt via passlib is the FastAPI-docs standard; argon2-cffi is marginally better but passlib/bcrypt has broader ecosystem support |
| SQLite (via aiosqlite) | 3.x / 0.20.x | User + run persistence for MVP | Zero infrastructure cost for first pilot. Users, campaign configs, lead expedientes stored as rows + JSON blobs. Migrate to Postgres when multi-region or concurrent writes become a bottleneck (not for MVP) |
| aiosqlite | 0.20.x | Async SQLite driver | FastAPI is async; aiosqlite wraps sqlite3 with asyncio. Trivial to swap for asyncpg later |
| python-dotenv | 1.0.x | Env config management | Already used. Keep |
| uv | 0.4.x | Python package manager | Hive's own `quickstart.sh` uses `uv`; dramatically faster than pip for resolving Hive's large dependency tree (LiteLLM alone has 80+ transitive deps) |

### Frontend Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| React | 18.3.x | UI framework | Already in codebase. Do not upgrade to React 19 yet — `react-dom` concurrent features are not needed and 19.x has breaking changes to refs |
| TypeScript | 5.4.x | Type safety | Already in use. Upgrade from 5.3.3 to 5.4.x for minor improvements to `NoInfer` |
| Vite | 5.2.x | Build tool + dev server | Already in use. Fast HMR essential for iterating on canvas animations |
| Zustand | 4.5.x | Frontend state management | Already in use for agent state. Keep. Lightweight, no boilerplate, works well with WebSocket pushes — just call `useAgentStore.getState().updateAgent()` in the WS handler |
| @tanstack/react-query | 5.x | Server state / REST data fetching | Add for leads dashboard, campaign config CRUD, user profile endpoints. Handles caching, background refresh, loading states without hand-rolled fetch logic |

### Auth (Multi-Tenant)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| python-jose[cryptography] | 3.3.x | JWT signing/verification | Backend issues JWTs on login; middleware validates them. Self-contained, no external service dependency for MVP. Each token carries `user_id` used to scope Hive runs and lead data |
| passlib[bcrypt] | 1.7.x | Hashing passwords at rest | Do NOT store plain passwords; bcrypt with work factor 12 is standard |

**Do NOT use Auth0 / Clerk / Supabase Auth for MVP.** The negocio.md doc lists them as options, but they add external vendor dependency, monthly cost, and OAuth complexity you don't need for a single-pilot client. Implement email+password JWT in-house; takes ~2h with FastAPI and pays off in zero SLA dependency. Migrate to Supabase Auth in v2 when you have 10+ clients.

### MCP Tools (Web Scraping / Search)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| aden_tools (Hive built-in) | v0.6.0 | `web_search_tool` + `web_scrape_tool` + `file_system_toolkits` | Built into Hive's `tools/` package. `web_search_tool` uses Brave Search API; `web_scrape_tool` uses a headless fetch + HTML extraction pipeline. Use these first — no additional install needed |
| mcp (Model Context Protocol SDK) | 1.x | MCP client transport layer | Hive's `MCPClient` uses the official MCP Python SDK for STDIO and HTTP transport. Pull in automatically with Hive install |
| httpx | 0.27.x | Async HTTP for custom tool calls | Already a transitive dependency of FastAPI/openai. Use for any custom enrichment endpoint calls within function_nodes |

**Do NOT install Playwright / Crawl4AI separately.** The `web_scrape_tool` in aden_tools covers the scraping need. Adding another headless browser stack doubles memory usage and creates process management complexity inside FastAPI's async loop.

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | 0.0.9 | Form data parsing | Needed by FastAPI for login form POST endpoint |
| anyio | 4.x | Async primitives | Transitive dep of FastAPI/Hive; use `anyio.from_thread.run_sync` if you need to call sync Hive code from async context |
| structlog | 24.x | Structured logging | Replace bare `print()` calls in main.py and orchestrator.py with structured JSON logs. Critical for debugging agent graph executions in production |
| pytest-asyncio | 0.24.x | Async test runner | Testing `GraphExecutor` runs requires async test contexts |
| pytest | 8.x | Test framework | Standard |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| uv | Package management | `uv pip install -e "git+https://github.com/aden-hive/hive.git@v0.6.0#egg=hive"` installs Hive from git in editable mode |
| hive tui | Interactive agent debugger | Hive's built-in TUI for stepping through graph executions; use during scoring/veto node development |
| hive shell | REPL for testing nodes in isolation | Faster than running the full FastAPI server when iterating on prompt logic |

---

## How aden-hive/hive Integrates with Existing FastAPI Stack

The integration is an internal replacement, not a wrapper. The existing `main.py` surface area stays largely intact; only `orchestrator.py` is gutted and rebuilt.

**Integration pattern:**

```
FastAPI (main.py)
├── /api/agents         → still works; now reads from HiveSessionManager
├── /api/agents/{id}/task  → calls AgentRunner.run(agent_id, input)
├── /ws                 → WebSocket still broadcasts; HiveExecutor emits events
│
└── HiveSessionManager (new orchestrator.py)
    ├── AgentRunner     → loads agent.json GraphSpec, manages runs per user
    ├── GraphExecutor   → executes nodes; emits state events to FastAPI WS broadcast
    ├── NodeContext     → injects LiteLLMProvider + ToolRegistry + SharedMemory per node
    └── ToolRegistry    → registers aden_tools MCP server (web_search, web_scrape)
```

**Key wiring point:** `GraphExecutor` needs a hook to emit `agent_update` WebSocket events as nodes change state (THINKING → TOOL_USE → WAITING). Wire this via an event callback:

```python
async def on_node_state_change(node_id: str, state: str, tool: str | None):
    await manager.broadcast({
        "type": "agent_update",
        "agent_id": node_id,
        "state": state,
        "current_tool": tool
    })

executor = GraphExecutor(spec=graph_spec, on_state_change=on_node_state_change)
```

This keeps the existing frontend `useWebSocket.ts` hook working without changes — it still receives the same `agent_update` message shape.

---

## Installation

```bash
# 1. Install uv (replaces pip for this project)
pip install uv

# 2. Install Hive from git (requires access to aden-hive/hive)
uv pip install "git+https://github.com/aden-hive/hive.git@v0.6.0#egg=hive[tools]"

# 3. Add new backend dependencies
uv pip install \
  fastapi==0.115.5 \
  uvicorn[standard]==0.34.0 \
  pydantic==2.6.4 \
  python-jose[cryptography]==3.3.0 \
  passlib[bcrypt]==1.7.4 \
  aiosqlite==0.20.0 \
  python-multipart==0.0.9 \
  structlog==24.4.0 \
  httpx==0.27.0

# 4. Dev / test dependencies
uv pip install -D pytest==8.3.0 pytest-asyncio==0.24.0

# 5. Frontend — add react-query
cd frontend && npm install @tanstack/react-query@5
```

---

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| aden-hive/hive (AgentRunner + GraphExecutor) | LangGraph, CrewAI, custom orchestrator | Only if aden-hive/hive proves uninstallable or lacks async support for the HITL node — LangGraph has first-class async + interrupt support but requires full rewrite of agent definitions |
| SQLite + aiosqlite (MVP) | Supabase (Postgres + Auth + Storage) | When you have 3+ concurrent clients, need multi-region, or want row-level security built in |
| python-jose JWT (in-house auth) | Auth0 / Clerk | When you have 10+ clients and need SSO, social login, or MFA without building it yourself |
| aden_tools web_scrape_tool | Crawl4AI, Playwright, Firecrawl | Only if `web_scrape_tool` can't handle JavaScript-rendered pages; Firecrawl is the best paid fallback ($20/month) |
| LiteLLMProvider via Hive | Direct OpenAI SDK (current) | Never — current SDK is what we're replacing. LiteLLM adds model fallback and cost routing with zero added complexity |
| Zustand (frontend) | Redux, Jotai, Context API | Jotai is valid if state shape becomes very granular (atom per node); Redux is overkill for this scope |
| @tanstack/react-query | SWR | Either works; react-query has better DevTools, mutation API, and is more widely documented for FastAPI + React patterns |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| OpenAI SDK directly in orchestrator | The entire migration goal is to replace it with Hive's LiteLLMProvider. Using both creates two competing LLM call paths and breaks SharedMemory tracking | aden-hive/hive `LiteLLMProvider` + `NodeContext.llm` |
| Celery + Redis for task queue | Overkill for MVP. Adds two infrastructure services, complex worker management, and serialization issues with Pydantic v2 models. FastAPI's `asyncio.create_task()` (already in main.py) handles background graph execution adequately for single-tenant pilot | `asyncio.create_task()` wrapping `AgentRunner.run()` |
| Next.js (frontend) | negocio.md suggests it; but the existing frontend is React/Vite and the pixel art canvas is already working. Migrating to Next.js would break the canvas game loop, add SSR complexity that serves no purpose (this is not a public-facing marketing site), and costs 1-2 weeks | Keep React + Vite |
| SQLAlchemy ORM | Heavy abstraction for what is essentially user profiles + JSON blobs of lead data. Migrations become burdensome early. Raw aiosqlite + dataclasses is faster to ship for MVP | aiosqlite with raw SQL or a thin query builder |
| Alembic | Companion to SQLAlchemy ORM; see above. For SQLite MVP, manage schema manually | Manual `CREATE TABLE IF NOT EXISTS` in startup lifespan |
| Playwright inside FastAPI process | Spawning browser processes from within the ASGI event loop causes blocking and process isolation issues. `web_scrape_tool` from aden_tools should be used first | aden_tools `web_scrape_tool`; Firecrawl API as fallback |
| React 19 | Breaking changes to refs, `use()` hook semantics, and concurrent mode behavior not yet stabilized in the ecosystem (mid-2026). Not needed for canvas-based UI | React 18.3.x |

---

## Stack Patterns by Variant

**If Hive's `web_scrape_tool` can't handle a JavaScript-heavy target site:**
- Use Firecrawl API (`https://api.firecrawl.dev/v0/scrape`) via httpx inside a custom `function_node`
- $20/month for 500 pages — adequate for pilot
- Do NOT install Playwright; the process isolation cost is too high

**If the HITL node needs to pause execution > 1 hour (async suspension):**
- The `hitl_node` in Hive pauses the GraphExecutor and emits a WebSocket event
- Store the suspended run state in SQLite (`run_id`, `suspended_at`, `resume_payload_schema`)
- Resume endpoint: `POST /api/runs/{run_id}/resume` → calls `GraphExecutor.resume(run_id, approval)`
- Do NOT use Redis-backed task queues for this; SQLite row lock is sufficient for MVP concurrency

**If `claude-3-5-sonnet-20241022` is too expensive per run:**
- Use `claude-3-haiku-20240307` for sourcing_node and scraping_node (structured extraction, not creative)
- Reserve Sonnet for scoring_node, email_composer, spiced_analyzer (where quality directly impacts conversion)
- LiteLLMProvider makes this a per-node config change

**If multi-tenant data isolation is needed before Postgres migration:**
- SQLite database per user (`users/{user_id}/data.db`) using aiosqlite
- Simple, no shared write lock, no row-level security complexity
- Limit: breaks down at ~50 concurrent users due to file handle management

---

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| pydantic==2.6.x | fastapi==0.115.x | FastAPI 0.115 dropped Pydantic v1 support entirely — do not use FastAPI < 0.100 with Pydantic v2 |
| aden-hive/hive v0.6.0 | Python 3.11, 3.12 | Tested on 3.11; 3.12 should work but verify with `hive tui` after install |
| python-jose==3.3.0 | cryptography>=3.4 | `[cryptography]` extra installs the correct backend; do not use PyJWT as a substitute — different API |
| aiosqlite==0.20.x | Python 3.11+ | Uses `asyncio.run_in_executor`; compatible with FastAPI's event loop |
| @tanstack/react-query==5.x | React 18.x | React Query v5 dropped React 16/17 support; v5 API is breaking vs v4 (no `useQuery({queryKey, queryFn})` destructuring change applies to v5 syntax — use `{ data, isLoading }` from `useQuery`) |
| zustand==4.5.x | React 18.x | No breaking changes expected through React 18.3 |

---

## Sources

- `negocio.md` (project file) — Hive framework architecture, component inventory, agent.json schema, MCP tool list, node types (HIGH confidence — authored by project owner)
- `backend/main.py`, `backend/orchestrator.py`, `backend/models.py` — existing stack baseline (HIGH confidence — direct code inspection)
- `frontend/package.json` — existing frontend dependencies (HIGH confidence — direct inspection)
- FastAPI documentation pattern (training data, MEDIUM confidence) — JWT auth, WebSocket, lifespan pattern
- LiteLLM model support (training data, MEDIUM confidence) — verify current model IDs at docs.litellm.ai
- aden-hive/hive GitHub (https://github.com/aden-hive/hive) — not directly accessible during research; architecture inferred from negocio.md and project docs (LOW confidence for exact API signatures — verify with `hive --help` after install)

---

*Stack research for: AaaS B2B Prospecting Platform (Hive Pixel Office)*
*Researched: 2026-03-17*
