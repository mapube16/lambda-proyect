# Roadmap: Hive Pixel Office — AaaS B2B Prospecting Platform

## Overview

The project migrates a working pixel art office frontend from a hand-rolled orchestrator to the real `aden-hive/hive` framework while adding the complete B2B prospecting pipeline, multi-tenant auth, a campaign configuration surface, a lead dashboard, and real-time character animations tied to live graph node events. Phases 1-2 lay the architectural foundation that everything else depends on. Phases 3-5 build the full backend pipeline. Phases 6-8 wire the frontend to real events and deliver the pilot-ready user-facing features.

Milestone v1.0 (Multi-Tenant SaaS Pipeline) adds Phases 18-22: Railway infrastructure, tenant isolation, scraping improvements, pipeline parametrization, and cost observability.

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
- [ ] **Phase 18: Infrastructure Foundation** - Railway 3-service deployment (API + Worker + Redis); ARQ job queue replaces in-process execution; API enqueues jobs and returns run_id immediately
- ⏳ **Phase 19: Tenant Isolation** - tenant_id on all MongoDB documents; all queries filtered by tenant_id; Redis pub/sub WebSocket bridge routes Worker events to the correct frontend connection **(PLANNING PHASE)**
- [x] **Phase 20: Scraping Improvements** - curl_cffi Chrome131 TLS impersonation replaces httpx; Crawl4AI compresses HTML to Markdown before LLM; DIRECTORY_DOMAINS blocklist; extract_homepage() normalization
 (completed 2026-05-28)
- [ ] **Phase 21: Pipeline Parametrization** - VerticalConfig dataclass per insurance vertical; SignalLead TypedDict contract for all signal_sources; user selects vertical at campaign configuration
- [ ] **Phase 22: Cost Observability** - CostEvent logged per LLM and Serper call with tenant_id + run_id; user can query total cost per run via API
- [ ] **Phase 24: Signal Sources Colombianas** - RUES (recent registrations) + Bright Data (LinkedIn hiring signals) + Hunter.io (decision makers) + Google Maps; Signal deduplication (fuzzy) + intent-based ranking; Quota enforcement per broker ✨ **(STANDBY: Blocks on Phase 19)**
- [ ] **Phase 25: Agentic Multi-Tenant Architecture** - MongoDB-persisted agent configs (system prompts, model, tools); hot-reload without redeploy; CobranzaOrchestrator multi-tenant with sub-agents (debtor_updater, whatsapp_notifier, identity_verifier, escalation_handler); Bandwidth/Telnyx replaces Twilio; Pipecat + Gemini Live replaces OpenAI Realtime + Assembly AI; RAG per tenant (Pinecone Starter + OpenAI embeddings + semantic chunking); Redis Upstash cache with immediate toggle invalidation

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
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 4: Scraping Safety and Output Validation
**Goal**: Scraped web content is sanitized before LLM injection and every LLM node output is validated against a schema before passing to the next node — the pipeline is hardened against prompt injection and malformed outputs
**Depends on**: Phase 3
**Requirements**: PIPE-03, PIPE-04
**Success Criteria** (what must be TRUE):
  1. Raw HTML from a scraped URL is stripped to plain text, truncated at 8,000 characters, and wrapped in structural delimiters before it reaches the LLM — confirmed by inspecting the actual prompt sent
  2. A deliberately malformed LLM response (missing required JSON field) causes the node to return a structured error, not an unhandled exception
  3. A scraped page containing prompt-injection text (e.g., "Ignore previous instructions") does not alter the pipeline's scoring behavior in a detectable way
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 5: HITL Loop
**Goal**: When the pipeline reaches `human_review`, the run suspends with durable SQLite state; the agent character freezes visually; the user can approve or reject from the dashboard and the pipeline resumes correctly
**Depends on**: Phase 4
**Requirements**: HITL-01, HITL-02, HITL-03
**Success Criteria** (what must be TRUE):
  1. When a run reaches `human_review`, a `hitl_request` WebSocket message is delivered to the user and the agent character visually enters a frozen/waiting state in the office
  2. After a server restart while a run is suspended at HITL, the pending state is recoverable from SQLite — the approve/reject buttons still function
  3. Clicking Approve resumes the pipeline from the suspended node and it completes; clicking Reject terminates the run and records the rejection outcome
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 6: Campaign Configuration
**Goal**: A user can fill the 10-variable campaign form before launching a run, the configuration persists in SQLite for reuse, and the AgentPanel always displays the current agent's name, role, and active campaign variables
**Depends on**: Phase 5
**Requirements**: CONF-01, CONF-02, CONF-03
**Success Criteria** (what must be TRUE):
  1. A user can open the campaign configuration form, fill all 10 fields with validation, and submit — the run uses those exact values
  2. After closing and reopening the browser, the user's last-saved campaign configuration is pre-populated in the form
  3. The AgentPanel sidebar shows the active agent's name, role, and current campaign variable values without requiring any navigation away from the office canvas
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 7: Lead Dashboard
**Goal**: Completed runs with score >= 70 display a full expediente card; kill switch rejections display the rejection code and evidence; all email drafts are copyable with one click
**Depends on**: Phase 6
**Requirements**: LEAD-01, LEAD-02, LEAD-03
**Success Criteria** (what must be TRUE):
  1. A successful run (score >= 70) shows a card with: numeric score, profile tier (A/B), key decisor name/title/email, detected tech stack, trigger, and the personalized email draft
  2. Clicking a copy button on an email draft places the full draft text on the clipboard with no additional steps
  3. A run that triggered a kill switch shows the specific kill switch code (e.g., `KILL_B2C`) and the text excerpt from the scraped content that justified it
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 8: Real-Time Visualization
**Goal**: Each of the 9 pipeline nodes maps to a distinct character animation state in the pixel office; state updates arrive via WebSocket without blocking the canvas render loop; pipeline errors surface as visible error states on the character — not blank screens
**Depends on**: Phase 7
**Requirements**: VIZ-01, VIZ-02, VIZ-03
**Success Criteria** (what must be TRUE):
  1. During a live run, the office character changes animation (searching, processing, writing, waiting) as each graph node transitions — observable in real time on screen
  2. The canvas game loop continues running at target frame rate while WebSocket messages are being received during an active run — no jank or freezing
  3. When a pipeline error occurs (scraping failure, LLM timeout), the character displays an error state and the office UI shows the error message — the screen does not go blank or crash
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

---

## Phase 9: Client RAG + Intelligent Onboarding
**Goal**: Staff can onboard a new client by uploading any documentation (PDFs, brochures, web links, briefs); a per-client RAG is built in MongoDB Atlas Vector Search; the Queen reads that context and proposes agents, system prompts, and campaign variables; staff approves and the client account is created with everything pre-configured
**Depends on**: Phase 8
**Requirements**: RAG-01, RAG-02, RAG-03, ONB-01, ONB-02
**Success Criteria** (what must be TRUE):
  1. Staff can upload at least 3 document types (PDF, URL, plain text) for a client from the staff dashboard — all content is chunked, embedded, and stored under the client's namespace in MongoDB Atlas Vector Search
  2. After upload, the Queen generates a structured proposal: suggested agent names/roles, system prompt per agent, and all 8 campaign variables — derived exclusively from the uploaded content, not hallucinated
  3. Staff can review the proposal side-by-side with the source documents, edit any field, and approve — triggering the creation of a fully configured client account
  4. When a prospecting run starts for that client, the pipeline queries the client's RAG to enrich the Analista's context (e.g., "what pain points does this client solve?") — confirmed in LLM request log
  5. Two clients onboarded with different RAG docs produce demonstrably different agent configurations and campaign variables
**Stack**:
  - Embeddings: `text-embedding-3-small` via OpenRouter (~$0.00002/1k tokens)
  - Vector store: MongoDB Atlas Vector Search (collection: `client_knowledge`, namespace per `client_id`)
  - Ingestion: PyMuPDF (PDFs) + python-docx (Word) + existing scraper (URLs)
  - RAG query: injected into Queen context window before each campaign run
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

---

## Phase 10: Client Conversation + Lead Feedback
**Goal**: The client has a persistent chat interface inside their pixel office where they can talk to the Queen about their results — asking why a lead was rejected, requesting more like an approved one, or giving qualitative feedback — and the system extracts actionable intent from every message to propose campaign adjustments
**Depends on**: Phase 9
**Requirements**: CHAT-01, CHAT-02, CHAT-03, CHAT-04
**Success Criteria** (what must be TRUE):
  1. The client can ask natural language questions about their leads ("¿por qué rechazaste esta empresa?", "tráeme más como esta") and receive a contextual answer grounded in the actual analysis data stored in MongoDB
  2. The Queen extracts structured intent from every client message — classifying it as one of: `refine_target` (geography/industry/size), `adjust_tone` (email style), `blacklist_company`, `clone_lead` (find more like this), `campaign_feedback` (general quality signal) — stored per conversation turn
  3. After a conversation turn that contains a `refine_target` or `adjust_tone` intent, the system proposes a concrete campaign update ("¿Quieres que actualice la ciudad objetivo a Medellín?") — client confirms with one click
  4. Client feedback phrases like "muy pequeñas", "ya son clientes", "tono muy corporativo" are correctly classified into their intent category in at least 8/10 test cases
**Notes**:
  - Each conversation turn is stored in MongoDB (`client_conversations` collection) with extracted intents
  - Conversation history + RAG context are both injected into the Queen on each turn
  - The pixel office chat panel replaces/extends the current onboarding chat
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

---

## Phase 11: Continuous Learning Loop
**Goal**: Every client interaction (HITL decision, chat feedback, campaign result) is used to continuously improve that client's pipeline — approved leads shape the "ideal customer" embedding, rejected leads build an "avoid" profile, and detected patterns trigger automatic campaign refinement proposals
**Depends on**: Phase 10
**Requirements**: LEARN-01, LEARN-02, LEARN-03
**Success Criteria** (what must be TRUE):
  1. Every approved lead is embedded and stored in the client's `ideal_leads` vector namespace; every rejected lead with a reason is stored in `rejected_leads` — confirmed in MongoDB after each HITL action
  2. Before each new prospecting run, the pipeline computes semantic similarity between each discovered company and the client's `ideal_leads` corpus — companies above 0.75 cosine similarity get a +15 bonus to their qualification score
  3. After a client has completed 3 campaigns, the system automatically detects the top-3 patterns in approved leads (e.g., "mediana empresa, Bogotá, sector logístico") and surfaces them as a "Tu cliente ideal" card in the staff dashboard — derived from embeddings, not hardcoded rules
  4. A campaign where the learning loop is active shows a measurably higher approval rate than the client's first campaign (baseline) — documented in the run history
**Notes**:
  - "ADN del cliente ideal" = living vector centroid that updates after each approved lead
  - Blacklisted companies (from chat feedback "ya son clientes") are stored and permanently excluded from future discovery
  - The Redactor gets access to a `winning_emails` subcorpus: emails from leads that were approved AND the client later reported as replied — style transferred to future drafts
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

---

## Phase 12: Lead Lifecycle Foundation
**Goal**: Extender el pipeline existente con la infraestructura para que el sistema pueda continuar trabajando después del HITL: máquina de estados de 8 etapas, `sector_profiles` para mejor scoring, `company_voice` para mensajes con voz de marca, APScheduler para reintentos automáticos y nurturing mensual, y builder de variables de prompt — todo integrado en archivos existentes, sin módulo separado
**Depends on**: Phase 11
**Requirements**: LANDA-01, LANDA-02, LANDA-03, LANDA-04
**Success Criteria** (what must be TRUE):
  1. Un lead puede transitar por los 8 estados válidos (investigando → checkpoint → pausado → outreach → handover → nurturing → congelado → archivado) y se rechazan transiciones inválidas
  2. `sector_profiles` se genera automáticamente con GPT-4o dado un sector + región, devolviendo los campos del esquema del Documento B (decisor, ganchos, señales, etc.)
  3. APScheduler persiste y ejecuta acciones programadas (`reintento`, `nurturing`, `notificacion`) sobreviviendo reinicios del servidor
  4. `build_system_prompt()` reemplaza correctamente todas las `[VARIABLES]` de un template con el diccionario de valores, marcando vacías como `[inferida — KEY]`
**Plans**: 4 plans

Plans:
- [ ] 12-01-PLAN.md — Wave 0: xfail stubs for all LANDA-01 through LANDA-04 requirements
- [ ] 12-02-PLAN.md — Wave 1: Lead state machine (8 estados + 14 transiciones) en backend/state_machine.py + nuevos campos en leads + índices MongoDB
- [ ] 12-03-PLAN.md — Wave 1: sector_profiles GPT-4o (temp=0.2, cache 30d) en backend/sector_profiles.py + company_voice sync desde client_profiles en backend/company_voice.py
- [ ] 12-04-PLAN.md — Wave 2: APScheduler + scheduled_actions en backend/scheduler.py + build_system_prompt en backend/context_builder.py + wiring en main.py lifespan

### Phase 13: Lead Outreach & Nurturing Agents
**Goal**: Después de que el humano aprueba un lead, el sistema envía automáticamente el primer mensaje (Email o WhatsApp) con la voz de marca del cliente; leads rechazados o sin respuesta entran a un ciclo mensual de nurturing; el scoring del Investigador existente se enriquece con sector_profile para análisis de canal con probabilidades
**Depends on**: Phase 12
**Requirements**: LANDA-05, LANDA-06, LANDA-07, LANDA-08
**Success Criteria** (what must be TRUE):
  1. Cuando `hitl_status` pasa a `"approved"`, el sistema envía automáticamente un mensaje al lead por el canal elegido (Email o WhatsApp) usando la voz de empresa del cliente
  2. Leads con puntaje 40-69 pasan a nurturing; ≥70 van a checkpoint; <40 se descartan — el routing es automático post-scoring
  3. Un lead en nurturing recibe contenido mensual diferenciado según su `motivo_nurturing`; si responde con señal de reentrada, vuelve a checkpoint automáticamente
  4. El scoring del pipeline existente retorna `canales[]` con probabilidad por canal, usando señales del sector_profile
**Plans**: 6 plans

Plans:
- [ ] 13-01-PLAN.md — Wave 0: xfail stubs for LANDA-05 through LANDA-08
- [ ] 13-02-PLAN.md — Wave 1: Investigador scoring enrichment with sector_profile + automatic routing (LANDA-05, LANDA-06)
- [ ] 13-03-PLAN.md — Wave 1: email_sender.py + whatsapp_sender.py (LANDA-07)
- [ ] 13-04-PLAN.md — Wave 2: outreach_agent.py run_outreach() (LANDA-07)
- [ ] 13-05-PLAN.md — Wave 2: nurturing_agent.py run_nurturing() (LANDA-08)
- [ ] 13-06-PLAN.md — Wave 3: HITL hook integration + scheduler dispatch (LANDA-07, LANDA-08)

### Phase 14: Landa API & Checkpoint UI
**Goal**: El humano puede revisar leads en checkpoint desde el frontend (aprobar/pausar/rechazar + elegir canal), tomar control de un handover, y reportar resultado de llamada — con notificaciones automáticas vía Slack y WhatsApp
**Depends on**: Phase 13
**Requirements**: LANDA-09, LANDA-10, LANDA-11, LANDA-12
**Success Criteria** (what must be TRUE):
  1. `GET /api/leads/checkpoint` devuelve leads con puntaje, criterios, señales y canales con probabilidades; `POST /api/leads/{id}/decision` procesa aprobar/pausar/rechazar y dispara la transición de estado correcta
  2. `GET /api/leads/{id}/handover` devuelve el paquete completo (hilo, calificación, sugerencia de cierre); `POST /api/leads/{id}/handover/tomar` pausa el agente en ese lead
  3. `POST /api/leads/{id}/reporte-llamada` procesa los 4 resultados (bien/mas_o_menos/mal/no_pude) y ejecuta la lógica interna correcta (nurturing, reintento, handover, etc.)
  4. El frontend muestra la pantalla de checkpoint con cards de leads, botones aprobar/pausar/rechazar, selector de canal, y se actualiza en tiempo real via WebSocket
**Plans**: 7 plans

Plans:
- [ ] 14-01-PLAN.md — Wave 0: xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] 14-02-PLAN.md — Wave 1: GET /api/leads/checkpoint + POST /api/leads/{id}/decision (LANDA-09)
- [ ] 14-03-PLAN.md — Wave 1: GET+POST /handover + POST /reporte-llamada (LANDA-10, LANDA-11)
- [ ] 14-04-PLAN.md — Wave 1: POST /api/staff/clients/{id}/sources (LANDA-12 backend)
- [ ] 14-05-PLAN.md — Wave 2: officeStore + useWebSocket Landa event handlers (LANDA-12)
- [ ] 14-06-PLAN.md — Wave 2: CheckpointModal + HandoverModal components (LANDA-12)
- [ ] 14-07-PLAN.md — Wave 3: Wire AgentPanel + StaffDashboard + visual checkpoint (LANDA-12)

### Phase 15: Pipeline Enrichment + Real Channel Activation
**Goal**: El pipeline del investigador lee `fuentes_habilitadas` de `company_voice` para activar SECOP realmente (B), enriquece leads con datos del NIT colombiano antes de generar el expediente (C), y el canal WhatsApp funciona end-to-end al extraer el teléfono del decisor durante el análisis (A)
**Depends on**: Phase 14
**Requirements**: ENRICH-01, ENRICH-02, ENRICH-03

**Success Criteria** (what must be TRUE):
  1. Activar `secop_adjudicados` en StaffDashboard hace que el Investigador incluya empresas de SECOP en la siguiente run — verificable en los logs del servidor
  2. Después de scoring, `enrich_nit()` se llama con el NIT de la empresa (si existe) y los datos enriquecidos (`contratos_secop`, `valor_total_contratado`, `razon_social_rues`) aparecen en el expediente del lead en MongoDB
  3. Seleccionar canal "whatsapp" en CheckpointModal resulta en un mensaje real enviado si el investigador extrajo el teléfono del decisor; si no hay teléfono, el sistema hace fallback a email y lo registra

**Plans**: 4 plans

Plans:
- [ ] 15-01-PLAN.md — Wave 0: 7 xfail stubs for ENRICH-01, ENRICH-02, ENRICH-03 in backend/tests/test_enrichment.py
- [ ] 15-02-PLAN.md — Wave 1: SECOP bridge + NIT enrichment (hive_tools.py, prospector.py, database.py) (ENRICH-01, ENRICH-02)
- [ ] 15-03-PLAN.md — Wave 1: WhatsApp fallback to email in outreach.py (ENRICH-03)
- [ ] 15-04-PLAN.md — Wave 2: Integration smoke + human checkpoint (ENRICH-01, ENRICH-02, ENRICH-03)

### Phase 16: WhatsApp como Canal Completo de Landa

**Goal**: Cualquier cliente de Landa puede elegir operar su flujo completo desde WhatsApp — recibir notificaciones de checkpoint/handover, aprobar/rechazar leads, reportar llamadas y configurar campañas via conversación. Los asesores internos de Landa también pueden buscar prospectos SECOP y gestionar leads desde WhatsApp. La web (pixel art office) y WhatsApp son canales equivalentes — el usuario elige.
**Depends on**: Phase 15
**Requirements**: WA-01, WA-02, WA-03, WA-04

**Success Criteria** (what must be TRUE):
  1. Cuando un lead llega a checkpoint, si el cliente tiene `notification_channel` = "whatsapp" o "both", recibe un mensaje WA con el resumen del lead y puede responder "aprobar email", "pausar" o "rechazar" — la respuesta ejecuta `POST /api/leads/{id}/decision` correctamente
  2. Cuando un lead entra en handover (prospecto respondió), el cliente recibe un mensaje WA con el hilo de conversación y puede responder "tomar control" — ejecuta `POST /api/leads/{id}/handover/tomar`
  3. Un asesor interno puede escribir "empresas de construcción en Bogotá en SECOP" y recibir una lista de prospectos con NIT, decisor y valor de contratos — conversación multi-turno con contexto
  4. El cliente puede configurar su `notification_channel` ("web", "whatsapp", "both") desde el StaffDashboard y la preferencia persiste — sin necesidad de tocar código

**Plans:** 6/6 plans complete

Plans:
- [x] TBD (run /gsd:plan-phase 16 to break down) (completed 2026-03-26)

---

### Phase 17: Voice Cobranza Agent

**Goal**: Cualquier cliente de Landa puede comprar el agente de cobranza, subir su cartera de deudores via CSV o ingreso manual, configurar la estrategia de cobro via onboarding conversacional, y el sistema ejecuta llamadas outbound automatizadas — negociando pagos, registrando promesas, y mostrando el estado de cada deudor en tiempo real en el dashboard.
**Depends on**: Phase 16
**Requirements**: COBR-01, COBR-02, COBR-03, COBR-04

**Success Criteria** (what must be TRUE):
  1. Un usuario puede subir un CSV con deudores (nombre, teléfono, monto, vencimiento) o agregarlos manualmente — los registros aparecen en su dashboard con estado `pendiente`
  2. El onboarding conversacional le pregunta al usuario sobre su cartera (tipo de deuda, tono, urgencia) y la Queen propone una estrategia de llamadas que el usuario puede aprobar
  3. Al aprobar la campaña, el agente inicia llamadas outbound via Vapi — durante la llamada puede consultar la deuda, negociar y registrar promesas de pago usando tool calls a los endpoints de Landa
  4. El dashboard muestra el estado de cada deudor en tiempo real: `pendiente → llamando → promesa_de_pago → pagado → sin_contacto`, con historial de intentos y notas

**Plans**: 8 plans

Plans:
- [x] 17-01-PLAN.md — Wave 1: xfail test stubs for COBR-01/02/03/04 (Nyquist scaffold)
- [x] 17-02-PLAN.md — Wave 2: Debtor CRUD + CSV upload + manual entry endpoints
- [x] 17-03-PLAN.md — Wave 2: Ley 2300 compliance engine + Vapi client wrapper
- [x] 17-04-PLAN.md — Wave 3: Cobranza Queen onboarding + campaign approval + llamar-ahora
- [x] 17-05-PLAN.md — Wave 3: Vapi webhooks (tool-call + call-ended handlers)
- [x] 17-06-PLAN.md — Wave 3: APScheduler campaign jobs (pre/post-vencimiento + rescue fallback)
- [x] 17-07-PLAN.md — Wave 4: Frontend CobranzaTab (debtor table + filters + detail modal + real-time WS)
- [x] 17-08-PLAN.md — Wave 5: Wire main.py + turn xfail stubs green + human-verify checkpoint

---

## Milestone v1.0 — Multi-Tenant SaaS Pipeline

### Phase 18: Infrastructure Foundation

**Goal**: The platform runs as 3 separate Railway services (API, Worker, Redis); prospecting campaigns are enqueued as ARQ jobs so the API returns a run_id immediately and the Worker processes jobs without blocking the API
**Depends on**: Phase 17
**Requirements**: INFRA-01, INFRA-02, INFRA-03

**Success Criteria** (what must be TRUE):
  1. Developer can deploy API service, Worker service, and Redis service independently on Railway from a single repo — each service starts without errors in Railway logs
  2. Submitting a prospecting campaign via `POST /api/campaigns` returns a `run_id` immediately (< 200ms) without waiting for pipeline execution
  3. The Worker service picks up an enqueued ARQ job from Redis and executes the prospecting pipeline without any code running in the API process — verified by checking that no pipeline logic executes in the API process during a run
  4. If the Worker process is restarted mid-run, incomplete jobs are re-queued and resume — the API service remains fully responsive throughout

**Plans**: 3 plans

Plans:
- [x] 18-01-PLAN.md — Wave 0: xfail test stubs for INFRA-01/02/03 in backend/tests/test_infra.py
- [x] 18-02-PLAN.md — Wave 1: ARQ worker.py + arq_pool.py + POST /api/prospect enqueue + UUID run_id in database.py (INFRA-02, INFRA-03)
- [ ] 18-03-PLAN.md — Wave 2: Redis pub/sub WS bridge + railway.toml/railway-worker.toml + 3-service deploy checkpoint (INFRA-01, INFRA-02)

### Phase 19: Tenant Isolation

**Goal**: Every MongoDB document carries tenant_id and all queries are filtered so tenants cannot see each other's data; Worker events reach only the WebSocket connection belonging to the originating tenant via Redis pub/sub
**Depends on**: Phase 18
**Requirements**: TENANT-01, TENANT-02, TENANT-03, TENANT-04

**Success Criteria** (what must be TRUE):
  1. Every document written to campaigns, leads, and company_voice collections contains a `tenant_id` field equal to the authenticated user's user_id — confirmed by inspecting MongoDB documents after a run
  2. A query executed as tenant A returns zero results that belong to tenant B — verified by seeding two tenants with overlapping data and confirming each only sees their own
  3. Worker events published to `ws:{tenant_id}:{run_id}` are delivered only to the WebSocket connection authenticated as that tenant — a connection authenticated as tenant B receives no events from tenant A's run
  4. Disconnecting and reconnecting the frontend WebSocket resubscribes to the correct tenant's Redis channel and resumes receiving events for any active run

**Plans**: TBD

### Phase 20: Scraping Improvements

**Goal**: The scraper bypasses anti-bot protections using Chrome131 TLS impersonation; scraped HTML is compressed to Markdown before LLM analysis (~80% token reduction); aggregator domains are filtered before scraping; blog/directory URLs are normalized to company homepages
**Depends on**: Phase 18
**Requirements**: SCRAPE-01, SCRAPE-02, SCRAPE-03, SCRAPE-04

**Success Criteria** (what must be TRUE):
  1. Fetching a Cloudflare-protected Colombian B2B website with curl_cffi AsyncSession(impersonate="chrome131") returns the actual page HTML — the same request with httpx returns a bot-detection page
  2. A scraped HTML page passed through Crawl4AI produces a Markdown string with at least 70% fewer characters than the original HTML — the Markdown still contains all key company information (name, services, contact)
  3. Serper results for a query that would return ciencuadras.com or computrabajo.com are filtered out before any scraping attempt — zero requests are made to DIRECTORY_DOMAINS entries
  4. Calling `extract_homepage("https://blog.acme.com/article/123")` returns `"https://acme.com"` — blog post and directory listing URLs are normalized to root domains

**Plans**: 4 plans

Plans:
- [x] 20-01-PLAN.md — Wave 0: Create backend/Dockerfile.worker (Playwright base image); update railway-worker.toml; add crawl4ai>=0.4.21 + tldextract==5.3.1 + curl_cffi==0.15.0 to requirements.txt
- [x] 20-02-PLAN.md — Wave 1: Add html_to_compressed_markdown(), extract_homepage(), _NON_HOME_SUBDOMAINS; expand LOW_QUALITY_DISCOVERY_DOMAINS (~35 new domains)
- [x] 20-03-PLAN.md — Wave 1: Replace httpx.AsyncClient with curl_cffi AsyncSession in scrape_url(); wire html_to_compressed_markdown() and extract_homepage()
- [x] 20-04-PLAN.md — Wave 2: Fix discovery query bug — strengthen _DIRECTOR_PROMPT + add industria guard in _discover_companies()

### Phase 21: Pipeline Parametrization

**Goal**: The pipeline is parametrized by insurance vertical so the correct signal_sources, scoring weights, and prompt fragments load automatically at runtime; all signal_sources return a uniform SignalLead contract; users select a vertical when configuring a campaign
**Depends on**: Phase 18
**Requirements**: VERTICAL-01, VERTICAL-02, VERTICAL-03, SIGNAL-01, SIGNAL-02

**Success Criteria** (what must be TRUE):
  1. A user can select an insurance vertical (desempleo, arrendamiento, empresarial) in the campaign configuration form before launching a run — the selection is persisted with the campaign document
  2. A run configured with vertical "desempleo" loads different signal_sources than a run configured with "arrendamiento" — confirmed by comparing the signal_source list in server logs for both runs
  3. Every signal_source (including the Serper source) returns objects that satisfy the SignalLead TypedDict: company_name, url, industry, city, source fields are all present and non-null
  4. Adding a new signal_source requires only implementing the SignalLead TypedDict contract and registering it in VerticalConfig — no changes to pipeline orchestration code

**Plans**: TBD
**UI hint**: yes

### Phase 22: Cost Observability

**Goal**: Every LLM and Serper API call logs a CostEvent with tenant_id and run_id; users can query the total cost of any run via API endpoint
**Depends on**: Phase 19
**Requirements**: COST-01, COST-02, COST-03

**Success Criteria** (what must be TRUE):
  1. After a complete prospecting run, `GET /api/runs/{run_id}/cost` returns the total cost in USD for that run — including a breakdown by model (GPT-4o calls) and Serper credits used
  2. Every GPT-4o call during a run writes a CostEvent document to MongoDB with tenant_id, run_id, model, input_tokens, output_tokens, and cost_usd — confirmed by querying the cost_events collection after a run
  3. Every Serper query during a run writes a CostEvent with tenant_id, run_id, and credits_used — confirmed by querying the cost_events collection
  4. Two tenants running concurrent campaigns accumulate CostEvents separately — querying by tenant_id returns only that tenant's costs

**Plans**: TBD

### Phase 23: Intelligent prospecting chat with NL input and company knowledge base

**Goal:** Replace the manual 10-field campaign form with a single-turn natural-language chat that extracts prospecting parameters via LLM, persists a per-tenant prospecting_knowledge collection (product description + ICP + signal history), injects that context into every NL extraction, and closes the feedback loop by appending approved/rejected lead signals automatically when the user makes checkpoint decisions.
**Requirements**: NL-01, NL-02, KB-01, KB-02, KB-03, SIGNAL-FB-01, UI-01, UI-02, UI-03, UI-04
**Depends on:** Phase 22
**Plans:** 1/5 plans executed

Plans:
- [ ] 23-01-PLAN.md - Wave 1: Nyquist xfail test scaffold (8 stubs covering NL/KB/SIGNAL-FB)
- [ ] 23-02-PLAN.md - Wave 2: extract_campaign_from_nl + prospecting_knowledge CRUD + /api/chat/prospect + /api/knowledge endpoints
- [ ] 23-03-PLAN.md - Wave 3: Fire-and-forget signal feedback hook on POST /api/leads/{id}/decision
- [x] 23-04-PLAN.md - Wave 3: NLProspectInput + ExtractedParamsCard + KnowledgeBasePanel + LearningBadge in AgentPanel.tsx
- [ ] 23-05-PLAN.md - Wave 4: Backend+frontend health gates + human-verify end-to-end checkpoint

### Phase 25: Agentic Multi-Tenant Architecture

**Goal**: MongoDB-persisted agent configuration (system prompts, model, tools, rules) enables hot-reload without redeploy; CobranzaOrchestrator provides multi-tenant voice orchestration with 4 sub-agents; Bandwidth or Telnyx replaces Twilio (40-60% cost reduction); Pipecat + Gemini Live replaces OpenAI Realtime + Assembly AI for true streaming voice; RAG per tenant using Pinecone Starter + OpenAI text-embedding-3-small with semantic chunking; Redis Upstash cache with immediate invalidation for on/off toggles
**Depends on**: Phase 19
**Requirements**: AGENT-CFG-01, AGENT-CFG-02, AGENT-CFG-03, VOICE-01, VOICE-02, RAG-01, RAG-02, CACHE-01
**Success Criteria** (what must be TRUE):
  1. Changing `voice_system_prompt` in MongoDB for a tenant reflects in the next voice call without any redeploy
  2. Setting `modules.voice = false` for a tenant stops new voice calls within 1 request (immediate Redis cache invalidation)
  3. 10 concurrent tenants each with their own agent_instances can run voice calls simultaneously, with no cross-tenant data leakage
  4. A voice call uses Bandwidth or Telnyx (not Twilio) — confirmed by outbound call SID format or provider billing dashboard
  5. Pipecat + Gemini Live pipeline achieves <500ms TTFB on first agent utterance
  6. RAG document uploaded for tenant A is not retrievable by tenant B (Pinecone namespace isolation)
  7. Sub-agents (debtor_updater, whatsapp_notifier, identity_verifier, escalation_handler) execute successfully when called from voice agent tools

**Plans**: 5 plans

Plans:
- [x] 25-01-PLAN.md — Wave 1: MongoDB collections CRUD + Redis cache layer (tenant_config.py, config_cache.py, database.py indexes, xfail scaffold, deps)
- [ ] 25-02-PLAN.md — Wave 2: CobranzaOrchestrator + 4 sub-agents (direct dispatch, user_id isolation)
- [ ] 25-03-PLAN.md — Wave 3: Telnyx + Gemini Live voice pipeline (hot-reload prompt, TeXML webhook)
- [ ] 25-04-PLAN.md — Wave 3: RAG service (Pinecone namespace per user_id, ingest + search)
- [ ] 25-05-PLAN.md — Wave 4: Tenant admin API + ARQ log_debtor_communication + wiring

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16 → 17 → 18 → 19 → 20 → 21 → 22

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Auth Infrastructure | 3/3 | Complete | 2026-03-18 |
| 2. Hive Adapter and Tenant Isolation | 3/3 | Complete | 2026-03-19 |
| 3. Prospecting Graph Definition | - | Complete | 2026-03-19 |
| 4. Scraping Safety and Output Validation | - | Partial (~70%) | - |
| 5. HITL Loop | - | Partial (post-hoc only) | - |
| 6. Campaign Configuration | - | Complete | 2026-03-19 |
| 7. Lead Dashboard | - | Partial (copy button missing) | - |
| 8. Real-Time Visualization | - | Partial (basic states only) | - |
| 9. Client RAG + Intelligent Onboarding | 1/1 | Complete | 2026-03-20 |
| 10. Client Conversation + Lead Feedback | 1/1 | Complete | 2026-03-20 |
| 11. Continuous Learning Loop | 1/1 | Complete | 2026-03-20 |
| 12. Landa Foundation | 4/4 | Complete | 2026-03-22 |
| 13. Landa Agent Pipeline | 6/6 | Complete | 2026-03-22 |
| 14. Landa API & Checkpoint UI | 7/7 | Complete | 2026-03-23 |
| 15. Pipeline Enrichment + Real Channel Activation | 0/4 | Planned | - |
| 16. WhatsApp como Canal Completo de Landa | 6/6 | Complete | 2026-03-26 |
| 17. Voice Cobranza Agent | 8/8 | Complete | 2026-03-27 |
| 18. Infrastructure Foundation | 2/3 | In Progress|  |
| 19. Tenant Isolation | 0/TBD | Not started | - |
| 20. Scraping Improvements | 4/4 | Complete    | 2026-05-28 |
| 21. Pipeline Parametrization | 0/TBD | Not started | - |
| 22. Cost Observability | 0/TBD | Not started | - |
