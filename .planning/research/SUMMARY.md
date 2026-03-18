# Project Research Summary

**Project:** Hive Pixel Office — AaaS B2B Prospecting Platform
**Domain:** Agents as a Service (AaaS) — B2B Sales Prospecting with Visual Agent UI
**Researched:** 2026-03-17
**Confidence:** MEDIUM (Hive framework is private/early-access; supporting stack and architecture patterns are HIGH confidence)

## Executive Summary

This is a brownfield extension of an existing FastAPI + React/Vite pixel art office application. The core work is migrating from a hand-rolled `HiveOrchestrator` to the `aden-hive/hive` v0.6.0 agent graph framework while preserving the working pixel art canvas experience. The recommended approach is to introduce a thin `HiveAdapter` seam between FastAPI and the Hive framework — this decouples the two lifecycles, isolates all framework coupling in one file, and keeps the existing WebSocket protocol intact so the frontend requires minimal changes. The prospecting pipeline (sourcing → scraping → scoring → veto → email → expediente → HITL review) maps naturally onto Hive's `GraphExecutor` node graph, and the existing `AgentState` model on the frontend already supports the four states Hive emits.

The product's primary differentiator is making AI work visible and tangible through the pixel art office metaphor. Every feature decision should reinforce this: competitors (Apollo, Clay, Hunter) show tables and async results; this platform shows live character animations tied to graph node execution, a visual HITL pause where the agent character waits for human input, and transparent kill switch reasoning. The 10-variable campaign configuration form is the product's primary input interface, and the expediente + personalized email draft is the monetizable output. These two bookends define the MVP scope.

The most significant risks are architectural, not product-level: Hive framework embeds poorly into ASGI servers without explicit async bridging; the current `ConnectionManager` broadcasts to all tenants indiscriminately; SharedMemory is not namespaced per user; and HITL state is volatile in-memory only. All four of these must be resolved in Phase 1 and Phase 2 before any client pilot — they cannot be deferred without forcing a full rewrite later.

---

## Key Findings

### Recommended Stack

The stack is largely fixed by the brownfield context. FastAPI 0.115.x, React 18.3.x, TypeScript 5.4.x, Vite 5.2.x, and Zustand 4.5.x are already in place and should not be replaced. The primary additions are: `aden-hive/hive` v0.6.0 (installed via `uv` from git), `aiosqlite` 0.20.x for async SQLite persistence, `python-jose[cryptography]` + `passlib[bcrypt]` for in-house JWT auth, and `@tanstack/react-query` v5 for the leads dashboard data layer.

**Core technologies:**
- `aden-hive/hive` v0.6.0: Agent graph execution engine — the entire migration target; provides `AgentRunner`, `GraphExecutor`, `NodeContext`, `LiteLLMProvider`, `SharedMemory`, `ToolRegistry`
- FastAPI 0.115.x: REST + WebSocket host — already in codebase, extend not replace
- `aden_tools` (Hive built-in): `web_search_tool` + `web_scrape_tool` — use first; no additional headless browser install needed
- LiteLLM (via Hive): LLM provider abstraction — `claude-3-5-sonnet-20241022` as default for scoring/email nodes; `claude-3-haiku` for extraction nodes to control cost
- aiosqlite 0.20.x: Async SQLite — zero infrastructure cost for MVP; migrate to Postgres at 3+ concurrent clients
- python-jose / passlib: In-house JWT auth — do NOT use Auth0/Clerk/Supabase for MVP; email+password JWT takes ~2h and removes vendor SLA dependency
- `@tanstack/react-query` v5: Server state for leads dashboard — handles caching, loading states without hand-rolled fetch logic

**Critical constraint:** Do not install Playwright or Crawl4AI. Do not use Next.js. Do not use SQLAlchemy ORM or Alembic. Do not call OpenAI SDK directly anywhere — all LLM calls must go through Hive's `LiteLLMProvider`.

### Expected Features

See full analysis in `.planning/research/FEATURES.md`.

**Must have (table stakes — P1, cannot demo without):**
- Session auth (login / JWT) — multi-tenant isolation before anything else
- Campaign variable config form (10 vars) — the product's primary input interface
- URL input + run trigger — the core user action
- Real-time agent state via WebSocket — the pixel office has no purpose without this
- HITL pause in the office (visual freeze + approve/reject) — the signature UX differentiator
- Expediente viewer (Markdown + score + email draft) — the monetizable deliverable
- Kill switch rejection display with reason — rejection is a successful outcome, must be visible
- Run history / lead log — clients expect to see past runs
- Click-on-agent config view — transparency differentiator; shows system prompt + campaign vars

**Should have (differentiators — P2, add post-pilot):**
- Score breakdown UI with per-criterion reasoning
- Agent character animations tied to each graph node (sourcing, scraping, scoring, email)
- Campaign variable template library for repeat campaigns
- Rejection analytics panel (kill switch frequency by campaign config)
- In-browser notification for HITL ready state

**Defer to v2+:**
- Direct email sending (deliverability is a separate product; legal risk in Colombia)
- CRM push (HubSpot/Salesforce) — each is a mini-integration; export JSON manually for now
- LinkedIn scraping — ToS violation risk
- Multi-agent batch processing (> 1 URL) — validate single-run cost and reliability first
- Agent builder UI — clients need prospecting results, not agent construction
- Self-improving graph evolution — requires evaluation harness that does not exist yet

### Architecture Approach

The architecture uses a strict layered boundary: `HiveAdapter` is the single seam between FastAPI and the Hive framework. Nothing in `main.py` imports Hive directly. `GraphExecutor` node lifecycle events are translated by `HiveAdapter._map_hive_state()` into the four `AgentState` values the frontend already understands (`thinking`, `tool_use`, `waiting`, `idle`). HITL suspension is implemented via `asyncio.Event` gate stored in a run registry, with durable state written to SQLite before suspension. The pixel art canvas (`OfficeCanvas.tsx`) is preserved as-is; new features (`LeadDashboard.tsx`, `AgentConfigModal.tsx`) are additive panels.

See full diagrams and data flow in `.planning/research/ARCHITECTURE.md`.

**Major components:**
1. `HiveAdapter` (new `hive_adapter.py`) — replaces `orchestrator.py`; holds `AgentRunner`, bridges GraphExecutor events to WebSocket broadcast, manages HITL gate registry
2. `GraphExecutor` (Hive) — executes the `prospector_b2b` node graph; injects `NodeContext` (LLM + memory + tools) per node
3. `ConnectionManager` (extended) — must be refactored to key connections by `user_id` before any prospecting runs are wired
4. `officeStore` (Zustand, extended) — add `leads` map and `hitlPending` map; `LeadDashboard` subscribes to these slices
5. `LeadDashboard.tsx` (new) — renders expediente cards, approve/reject buttons, kill switch reasons; consumes `hitl_request` and `run_complete` WS messages
6. `exports/prospector_b2b/agent.json` (new) — GraphSpec defining the 9-node pipeline per `negocio.md`
7. SQLite via aiosqlite — persists users, run records, expedientes, HITL pending state

### Critical Pitfalls

See full analysis in `.planning/research/PITFALLS.md`.

1. **Hive framework is not a drop-in for FastAPI async** — never call `GraphExecutor.execute()` directly in a WebSocket handler or REST endpoint. Always wrap in `asyncio.create_task()` with proper cancellation handling. Address in Phase 1 before any UI wiring.

2. **WebSocket broadcast has no tenant isolation** — the current `ConnectionManager.broadcast()` sends to all connections. Key `active_connections` by `user_id` from day one. Fixing this after auth is added requires a full rewrite of the WS routing layer.

3. **SharedMemory is not namespaced per user** — a global `SharedMemory()` instance contaminates cross-tenant state. Always instantiate with `namespace=f"user_{user_id}"`. Address in Phase 1 during framework integration.

4. **HITL state is volatile** — an `asyncio.Event` in memory is lost on server restart. Write `(run_id, node_id, expediente, status)` to SQLite before suspending the HITL gate. Address in Phase 2 before the `human_review` node is built.

5. **Scraped content is prompt injection surface** — `{{contenido_scrapeado}}` is injected unsanitized into the LLM. Strip HTML to plain text, truncate to 8,000 characters, wrap in structural delimiters before injection. Validate LLM output against a strict JSON schema — reject malformed output, do not parse it leniently.

---

## Implications for Roadmap

The dependency chain from FEATURES.md is the primary driver of phase order: auth must exist before campaign config, campaign config before run trigger, run trigger before HITL, HITL before expediente viewer. The architecture build order from ARCHITECTURE.md reinforces this: Hive integration infrastructure must be stable before any UI is wired to real events. Security and tenant isolation issues from PITFALLS.md are Phase 1 concerns — deferring them forces rewrites.

### Phase 1: Foundation — Hive Integration and Tenant Infrastructure

**Rationale:** The three "never" technical debts (global singleton orchestrator, flat WebSocket broadcast, unnamespaced SharedMemory) must be eliminated before any prospecting logic is built. Fixing these after the pipeline is wired is a full rewrite. This phase proves the brownfield migration is feasible without breaking the existing pixel art office.

**Delivers:** Working `HiveAdapter` skeleton wired to a stub graph; tenant-keyed `ConnectionManager`; per-user `SharedMemory` namespace convention; in-house JWT auth (login/register endpoints); existing pixel art office still functions.

**Addresses:** Session auth table stake; per-user agent isolation requirement

**Avoids:** Pitfall 1 (Hive not drop-in), Pitfall 2 (flat broadcast), Pitfall 5 (unnamespaced memory)

**Research flag:** NEEDS RESEARCH — Hive v0.6.0 callback API for `on_node_event` and `ctx.runtime` dict injection must be verified against actual framework source after install. Do not assume the API signatures shown in ARCHITECTURE.md are exact.

### Phase 2: Prospecting Pipeline — Core Agent Graph

**Rationale:** With the Hive integration boundary stable and auth in place, the 9-node prospector graph can be built incrementally. Scraping reliability must be validated before scoring is built — discovering that `web_scrape_tool` fails against Cloudflare sites after the scoring node is complete wastes an entire phase.

**Delivers:** Full `exports/prospector_b2b/agent.json` graph executing: `sourcing_node` → `scraping_node` → `scoring_node` → `veto_router` → `spiced_analyzer` → `jtbd_deducer` → `email_composer` → `expediente_generator` → `human_review`. HITL durable state in SQLite. Prompt injection sanitization on `contenido_scrapeado`. Structured JSON output validation at each LLM node.

**Addresses:** URL input + run trigger; real-time agent state; HITL pause; expediente + email draft; kill switch rejection display

**Avoids:** Pitfall 3 (volatile HITL), Pitfall 4 (prompt injection), Pitfall 7 (monolithic prompt fragility), Pitfall 8 (anti-bot scraping failures)

**Uses:** LiteLLM `claude-3-5-sonnet-20241022` (scoring, email), `claude-3-haiku` (sourcing, scraping); `aden_tools` MCP server; aiosqlite for run + expediente persistence

**Research flag:** NEEDS RESEARCH — validate `web_scrape_tool` against real Colombian B2B company URLs with Cloudflare before committing to it as the sole scraping mechanism. Have Firecrawl API fallback plan ready ($20/month).

### Phase 3: UI and Visualization Integration

**Rationale:** Backend pipeline events are now real and reliable. Connect them to the frontend. The canvas render storm pitfall (Zustand Map clone at 60fps) must be addressed before connecting real Hive events to character animations.

**Delivers:** `LeadDashboard.tsx` with expediente cards + HITL approve/reject; `AgentConfigModal.tsx` for click-on-agent config view; run history / lead log; agent character animations mapped to graph node states; Zustand state architecture refactored to separate animation clock from agent data clock.

**Addresses:** Expediente viewer; email draft with copy; run history; click-on-agent config view; agent character animations (P2)

**Avoids:** Pitfall 6 (Zustand Map clone render storm); UX pitfall of frozen character with no feedback on failure

**Standard patterns:** React/Zustand integration, WebSocket message dispatch — well-documented; skip phase research.

### Phase 4: Campaign Configuration and Multi-Tenant Polish

**Rationale:** The pipeline is working end-to-end. Now add the user-facing configuration surface and production-readiness hardening for the pilot client.

**Delivers:** Campaign variable config form (10 vars) with validation and confirmation screen before launch; per-user campaign config persistence in SQLite; run history with outcome and score; rate limiting on run endpoints; CORS locked to production domain; structured logging (structlog); error states and retry UX for failed runs.

**Addresses:** Campaign variable config form table stake; confirmation UX before launch; production security hardening (CORS `*` removal, rate limiting, API key safety)

**Avoids:** Technical debt items flagged in PITFALLS.md: `CORS allow_origins=["*"]`, no rate limiting, `asyncio.sleep()` mock tools still present, API keys in frontend env vars

**Standard patterns:** FastAPI form validation, Pydantic, SQLite CRUD — well-documented; skip phase research.

### Phase 5: Validation Features and v1.x Enhancements

**Rationale:** First pilot client is running. Add features triggered by real usage: score breakdown (when clients ask "why 72 points?"), campaign template library (when they run 3+ configurations), rejection analytics (when they have 20+ runs and ask about patterns), in-browser HITL notifications.

**Delivers:** Score breakdown UI with per-criterion scorecard; campaign variable template library; rejection analytics panel with kill switch frequency chart; in-browser `Notification API` alert for HITL pending.

**Addresses:** P2 features in prioritization matrix

**Standard patterns:** Chart rendering, CRUD for named templates — well-documented; skip phase research.

### Phase Ordering Rationale

- Phase 1 before Phase 2: Three blocking architectural issues (flat broadcast, unnamespaced memory, Hive lifecycle mismatch) must be clean before any prospecting logic is layered on top. Fixing them post-hoc after 9 nodes are wired is a full rewrite.
- Phase 2 before Phase 3: Real backend events must exist before UI animation states are meaningful. Building `LeadDashboard.tsx` against mock data and then rewiring it to real events doubles the work.
- Phase 3 before Phase 4: The user cannot interact with the campaign form until the pipeline it submits to is real and observable. Building the form first produces a UI for a non-functional system.
- Phase 4 before Phase 5: Production-readiness hardening (rate limiting, CORS, logging) must precede pilot client access. P2 features are additive and can be delivered during or after the pilot.

### Research Flags

**Needs phase-level research:**
- **Phase 1:** Hive v0.6.0 callback API signatures — `on_node_event`, `ctx.runtime` dict, `AgentRunner.run()` parameter shape. These are documented in `negocio.md` but not verified against the installed framework source. Run `hive --help` and inspect source after install before committing to the architecture patterns in ARCHITECTURE.md.
- **Phase 2:** `web_scrape_tool` anti-bot capability — test against 5 real Colombian B2B URLs before building the scoring node. Determine if Firecrawl fallback is needed from the start.

**Standard patterns (skip research-phase):**
- **Phase 3:** React/Zustand/WebSocket UI patterns — well-documented, existing codebase provides baseline
- **Phase 4:** FastAPI CRUD, Pydantic validation, JWT auth — well-documented in FastAPI official docs and existing codebase
- **Phase 5:** Chart libraries, template CRUD — standard patterns

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Supporting ecosystem (FastAPI, LiteLLM, SQLite, React) is HIGH. Hive v0.6.0 is LOW — private repo, API signatures inferred from project docs not from installed source. Verify after install. |
| Features | HIGH | Sourced directly from `personalidad.md`, `negocio.md`, `PROJECT.md` authored by the project owner. Kill switch logic, scoring criteria, expediente schema, and 10-variable form are all specified in primary sources. |
| Architecture | MEDIUM-HIGH | Layer boundaries, component responsibilities, and WebSocket protocol are HIGH (direct code inspection). Hive callback API and `ctx.runtime` injection pattern are MEDIUM — inferred from negocio.md, not verified against framework source. |
| Pitfalls | HIGH | Based on direct code analysis (confirmed flat broadcast, confirmed Map clone on every update, confirmed mock tools, confirmed no tenant-keyed connections). Not speculative. |

**Overall confidence:** MEDIUM — the product scope and architecture approach are clear; the single gap is Hive framework API verification, which requires install.

### Gaps to Address

- **Hive v0.6.0 exact API:** `AgentRunner.run()` signature, `on_node_event` callback registration, and `ctx.runtime` dict injection are documented in `negocio.md` but must be verified against the installed framework before Phase 1 architecture is finalized. Run `pip install` + `hive --help` + inspect source in first implementation session.
- **`web_scrape_tool` JavaScript rendering capability:** Unknown whether `aden_tools` handles Cloudflare-protected sites. Test against 5 real Colombian B2B URLs in Phase 2 before building the scoring node that depends on scraped content.
- **LiteLLM model IDs:** `claude-3-5-sonnet-20241022` and `claude-3-haiku-20240307` are correct as of training data. Verify current IDs at docs.litellm.ai before first LLM call — Anthropic model naming has changed historically.
- **Colombia-specific legal compliance:** Email compliance under Ley 1581 (Colombia's data protection law) is relevant to the v2 email-sending feature. Not a blocker for v1 copy-only output, but must be researched before SendGrid integration.

---

## Sources

### Primary (HIGH confidence)
- `personalidad.md` — 4-module agent system prompt; kill switch logic, scoring criteria, expediente schema, 10 campaign variables
- `negocio.md` — Hive framework architecture, node graph design, MCP tool list, node types, BuildSession, SharedMemory layers
- `PROJECT.md` — validated requirements, out-of-scope items, key decisions, pilot client context
- `backend/main.py`, `backend/orchestrator.py`, `backend/models.py` — existing backend stack baseline and confirmed issues
- `frontend/src/store/officeStore.ts`, `frontend/src/hooks/useWebSocket.ts`, `frontend/src/types/index.ts` — frontend state, WS protocol, confirmed Map clone issue

### Secondary (MEDIUM confidence)
- FastAPI documentation patterns (training data) — JWT auth, WebSocket, lifespan pattern
- LiteLLM model support (training data) — verify model IDs at docs.litellm.ai
- Competitor analysis (training data) — Apollo.io, Clay, Hunter.io feature sets; may be outdated
- AaaS / HITL design patterns (training data) — WebSocket state, multi-tenant isolation

### Tertiary (LOW confidence)
- aden-hive/hive GitHub (https://github.com/aden-hive/hive) — not directly inspected; architecture inferred from negocio.md. Exact API signatures unverified. Validate during Phase 1 install.

---
*Research completed: 2026-03-17*
*Ready for roadmap: yes*
