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

**Arquitectura:**
- Webhook entrante: `POST /api/whatsapp/incoming` (Twilio o Meta Cloud API)
- Router de notificaciones: al emitir `lead_checkpoint`, `lead_handover`, etc., el sistema consulta `company_voice.notification_channel` y enruta a WebSocket, WA, o ambos
- LLM con tool calling: intención libre → herramientas (buscar_licitaciones, aprobar_lead, rechazar_lead, ver_handover, enriquecer_nit)
- Sesiones por número de teléfono en MongoDB (reemplaza dict en memoria de whatsapp_agent.py)
- Dos perfiles de usuario: `asesor_interno` (acceso a SECOP, gestión de múltiples clientes) y `cliente` (acceso solo a sus propios leads)
**Plans:** 6/6 plans complete

Plans:
- [x] TBD (run /gsd:plan-phase 16 to break down) (completed 2026-03-26)

---

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 13 → 14 → 15 → 16

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
| 12. Landa Foundation | 4/4 | Complete   | 2026-03-22 |
| 13. Landa Agent Pipeline | 6/6 | Complete   | 2026-03-22 |
| 14. Landa API & Checkpoint UI | 7/7 | Complete   | 2026-03-23 |
| 15. Pipeline Enrichment + Real Channel Activation | 0/4 | Planned | - |
| 16. WhatsApp como Canal Completo de Landa | 6/6 | Complete   | 2026-03-26 |
