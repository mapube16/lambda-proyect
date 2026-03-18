# Roadmap: Hive Pixel Office — AaaS B2B Prospecting Platform

## Overview

The project migrates a working pixel art office frontend from a hand-rolled orchestrator to the real `aden-hive/hive` framework while adding the complete B2B prospecting pipeline, multi-tenant auth, a campaign configuration surface, a lead dashboard, and real-time character animations tied to live graph node events. Phases 1-2 lay the architectural foundation that everything else depends on. Phases 3-5 build the full backend pipeline. Phases 6-8 wire the frontend to real events and deliver the pilot-ready user-facing features.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Auth Infrastructure** - JWT register/login/guard so every subsequent feature has a user identity to isolate against
- [ ] **Phase 2: Hive Adapter and Tenant Isolation** - Replace `orchestrator.py` with `HiveAdapter`; refactor `ConnectionManager` to per-user keying; namespace SharedMemory; bridge GraphExecutor events to AgentState
- [ ] **Phase 3: Prospecting Graph Definition** - Define the 9-node `prospector_b2b` GraphSpec; wire `personalidad.md` as system prompt with 10-variable interpolation; confirm URL input → run trigger
- [ ] **Phase 4: Scraping Safety and Output Validation** - Sanitize scraped content before LLM injection; validate structured JSON output at every LLM node boundary
- [ ] **Phase 5: HITL Loop** - SQLite-durable HITL gate; visual freeze on `human_review` node; approve/reject resumes pipeline
- [ ] **Phase 6: Campaign Configuration** - 10-variable campaign form with SQLite persistence; AgentPanel config transparency display
- [ ] **Phase 7: Lead Dashboard** - Expediente cards with score, decisor, email draft; kill switch rejection display; one-click email copy
- [ ] **Phase 8: Real-Time Visualization** - Map all 9 graph node states to character animations; WebSocket delivery without UI block; error states on pipeline failure

## Phase Details

### Phase 1: Auth Infrastructure
**Goal**: Users can register, log in, and have all endpoints protected by JWT so each client's data and runs are isolated from the start
**Depends on**: Nothing (first phase)
**Requirements**: AUTH-01, AUTH-02, AUTH-03
**Success Criteria** (what must be TRUE):
  1. A new user can register with email and password and receive a 201 response with no raw password stored
  2. A registered user can POST login credentials and receive a signed JWT
  3. Any REST endpoint or WebSocket handshake without a valid JWT is rejected with 401
  4. Two users logged in simultaneously cannot see each other's data
**Plans**: 3 plans

Plans:
- [ ] 01-01-PLAN.md — Wave 0 test scaffold: pytest.ini, conftest.py, 8 xfail stubs for AUTH-01/02/03
- [ ] 01-02-PLAN.md — Core auth modules: backend/auth.py (hash/JWT/dependency) and backend/database.py (aiosqlite users CRUD)
- [ ] 01-03-PLAN.md — Wire auth into main.py: auth endpoints, Depends on all routes, WS token validation, keyed ConnectionManager

### Phase 2: Hive Adapter and Tenant Isolation
**Goal**: The `aden-hive/hive` framework is installed and the single `HiveAdapter` seam replaces `orchestrator.py`; WebSocket connections are keyed by user_id; SharedMemory is namespaced; GraphExecutor node events map to AgentState — the pixel art office still loads and characters still animate
**Depends on**: Phase 1
**Requirements**: HIVE-01, HIVE-02, HIVE-03, HIVE-04, HIVE-05
**Success Criteria** (what must be TRUE):
  1. `aden-hive/hive` v0.6.0 installs cleanly and `HiveAdapter` can instantiate `AgentRunner` without import errors
  2. Starting a stub graph run for user A does not send WebSocket messages to user B's open connection
  3. A `GraphExecutor` node event (e.g., node start) triggers a WebSocket message to the correct user with the mapped `AgentState` value (THINKING, TOOL_USE, WAITING, or IDLE)
  4. The pixel art office page loads and existing character animations still function after the migration
  5. `SharedMemory` is instantiated with `namespace=f"user_{user_id}"` — confirmed in code and verified no cross-tenant key collisions in a two-user test
**Plans**: 3 plans

Plans:
- [ ] 02-01-PLAN.md — Wave 0: Clone aden-hive/hive into vendor/, install as editable package, create empty hive_adapter.py + hive_graph.py, write 11 xfail test stubs
- [ ] 02-02-PLAN.md — Wave 1: Implement HiveAdapter + hive_graph.py; EventBus subscription; event→AgentState mapping; turn 11 xfail stubs green
- [ ] 02-03-PLAN.md — Wave 2: Wire HiveAdapter into main.py; delete orchestrator.py; remove broadcast() from routes; visual sign-off checkpoint

### Phase 3: Prospecting Graph Definition
**Goal**: The full 9-node `prospector_b2b` graph executes end-to-end against a real company URL with `personalidad.md` loaded as system prompt and 10 campaign variables interpolated
**Depends on**: Phase 2
**Requirements**: PIPE-01, PIPE-02, PIPE-05
**Success Criteria** (what must be TRUE):
  1. User can submit a company URL via the REST endpoint and a prospecting run starts (run_id returned)
  2. All 9 nodes execute in sequence: `sourcing_node` → `scraping_node` → `scoring_node` → `veto_router` → `spiced_analyzer` → `jtbd_deducer` → `email_composer` → `expediente_generator` → `human_review` — confirmed in server logs
  3. The system prompt sent to the central prospector node contains the interpolated values of all 10 campaign variables (verified in LLM request log)
  4. A run triggered with a real Colombian B2B URL reaches the `human_review` node without crashing
**Plans**: TBD

### Phase 4: Scraping Safety and Output Validation
**Goal**: Scraped web content is sanitized before LLM injection and every LLM node output is validated against a schema before passing to the next node — the pipeline is hardened against prompt injection and malformed outputs
**Depends on**: Phase 3
**Requirements**: PIPE-03, PIPE-04
**Success Criteria** (what must be TRUE):
  1. Raw HTML from a scraped URL is stripped to plain text, truncated at 8,000 characters, and wrapped in structural delimiters before it reaches the LLM — confirmed by inspecting the actual prompt sent
  2. A deliberately malformed LLM response (missing required JSON field) causes the node to return a structured error, not an unhandled exception
  3. A scraped page containing prompt-injection text (e.g., "Ignore previous instructions") does not alter the pipeline's scoring behavior in a detectable way
**Plans**: TBD

### Phase 5: HITL Loop
**Goal**: When the pipeline reaches `human_review`, the run suspends with durable SQLite state; the agent character freezes visually; the user can approve or reject from the dashboard and the pipeline resumes correctly
**Depends on**: Phase 4
**Requirements**: HITL-01, HITL-02, HITL-03
**Success Criteria** (what must be TRUE):
  1. When a run reaches `human_review`, a `hitl_request` WebSocket message is delivered to the user and the agent character visually enters a frozen/waiting state in the office
  2. After a server restart while a run is suspended at HITL, the pending state is recoverable from SQLite — the approve/reject buttons still function
  3. Clicking Approve resumes the pipeline from the suspended node and it completes; clicking Reject terminates the run and records the rejection outcome
**Plans**: TBD

### Phase 6: Campaign Configuration
**Goal**: A user can fill the 10-variable campaign form before launching a run, the configuration persists in SQLite for reuse, and the AgentPanel always displays the current agent's name, role, and active campaign variables
**Depends on**: Phase 5
**Requirements**: CONF-01, CONF-02, CONF-03
**Success Criteria** (what must be TRUE):
  1. A user can open the campaign configuration form, fill all 10 fields with validation, and submit — the run uses those exact values
  2. After closing and reopening the browser, the user's last-saved campaign configuration is pre-populated in the form
  3. The AgentPanel sidebar shows the active agent's name, role, and current campaign variable values without requiring any navigation away from the office canvas
**Plans**: TBD

### Phase 7: Lead Dashboard
**Goal**: Completed runs with score >= 70 display a full expediente card; kill switch rejections display the rejection code and evidence; all email drafts are copyable with one click
**Depends on**: Phase 6
**Requirements**: LEAD-01, LEAD-02, LEAD-03
**Success Criteria** (what must be TRUE):
  1. A successful run (score >= 70) shows a card with: numeric score, profile tier (A/B), key decisor name/title/email, detected tech stack, trigger, and the personalized email draft
  2. Clicking a copy button on an email draft places the full draft text on the clipboard with no additional steps
  3. A run that triggered a kill switch shows the specific kill switch code (e.g., `KILL_B2C`) and the text excerpt from the scraped content that justified it
**Plans**: TBD

### Phase 8: Real-Time Visualization
**Goal**: Each of the 9 pipeline nodes maps to a distinct character animation state in the pixel office; state updates arrive via WebSocket without blocking the canvas render loop; pipeline errors surface as visible error states on the character — not blank screens
**Depends on**: Phase 7
**Requirements**: VIZ-01, VIZ-02, VIZ-03
**Success Criteria** (what must be TRUE):
  1. During a live run, the office character changes animation (searching, processing, writing, waiting) as each graph node transitions — observable in real time on screen
  2. The canvas game loop continues running at target frame rate while WebSocket messages are being received during an active run — no jank or freezing
  3. When a pipeline error occurs (scraping failure, LLM timeout), the character displays an error state and the office UI shows the error message — the screen does not go blank or crash
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Auth Infrastructure | 3/3 | Complete | 2026-03-18 |
| 2. Hive Adapter and Tenant Isolation | 0/3 | Not started | - |
| 3. Prospecting Graph Definition | 0/TBD | Not started | - |
| 4. Scraping Safety and Output Validation | 0/TBD | Not started | - |
| 5. HITL Loop | 0/TBD | Not started | - |
| 6. Campaign Configuration | 0/TBD | Not started | - |
| 7. Lead Dashboard | 0/TBD | Not started | - |
| 8. Real-Time Visualization | 0/TBD | Not started | - |
