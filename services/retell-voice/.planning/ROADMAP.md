# Roadmap: retell-voice

**Project:** retell-voice — AI voice collections agent (cobranza)
**Created:** 2026-05-09
**Granularity:** Fine (9 phases)
**Coverage:** 58/58 v1 requirements mapped

---

## Phases

- [ ] **Phase 1: Foundation** — Env validation, health endpoints, CI, logging, graceful shutdown, Dockerfile
- [ ] **Phase 2: Data Model** — All Mongoose schemas, indexes, multi-tenant scoping helper, migrations
- [ ] **Phase 3: Webhook Receiver + Session** — HMAC verification, event dispatcher, CallSessionManager, idempotency
- [ ] **Phase 4: Tool Handlers (Read)** — `get_debt_info` with Zod validation, latency guard, data_unavailable handling
- [ ] **Phase 5: Tool Handlers (Write)** — `register_payment_promise`, `schedule_callback`, `mark_dispute`, `transfer_to_human` — all idempotent
- [ ] **Phase 6: Custom LLM + Agent Config** — Anthropic integration, prompt builder, campaignType registry, Conversation Flow docs
- [ ] **Phase 7: Outbound Dialer + HTTP Routes** — `POST /calls`, outbound worker, compliance gates (calling window, cadence, AMD)
- [ ] **Phase 8: Inbound + Level 2 Hooks** — Inbound webhook resolution, extension interfaces (outbox, OTel, flags, redactor)
- [ ] **Phase 9: Tests + Hardening** — Vitest suites for all layers, compliance checklist gate, pilot readiness

---

## Phase Details

### Phase 1: Foundation
**Goal**: The service boots safely, rejects bad configuration before handling any traffic, and deploys to Railway with observable health
**Depends on**: Nothing
**Requirements**: FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05, FOUND-06, FOUND-07, FOUND-08
**Success Criteria** (what must be TRUE):
  1. Starting the service with a missing or invalid env var causes immediate process exit with a clear error message before accepting any connection
  2. `GET /health` returns 200 and `GET /ready` returns 200 (with Mongo connected) or 503 (Mongo down) — observable from Railway health check panel
  3. SIGTERM causes in-flight requests to drain and Mongoose connection to close cleanly (no abrupt kill)
  4. `docker build` produces a final image under 200 MB; `railway up` deploys successfully with env vars configured
  5. GitHub Actions pipeline runs Biome lint + TypeScript typecheck + Vitest on every PR and blocks merge on failure
**Plans**: TBD

### Phase 2: Data Model
**Goal**: All collections, schemas, and indexes exist before any handler writes data — multi-tenancy is structurally enforced, not a convention
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08
**Success Criteria** (what must be TRUE):
  1. A Mongoose query constructed without `tenantId` fails at compile time via the typed `tenantQuery(tenantId)` helper — the TypeScript compiler rejects it
  2. Migration script creates all indexes on deploy; running it twice is idempotent (no duplicate index error)
  3. All five collections (`tenants`, `call_attempts`, `call_events`, `payment_promises`, `callbacks`) have unique indexes and compound `tenantId`-first indexes as specified
  4. A `call_attempts` document can be inspected in Mongo Compass and shows `tenantId`, `callId`, `campaignType`, `transcript`, `promptVersion`, `toolCalls[]` populated correctly
**Plans**: TBD

### Phase 3: Webhook Receiver + Session
**Goal**: Retell can deliver signed webhook events and they are dispatched to typed handlers without duplication — the foundation all tools depend on
**Depends on**: Phase 2
**Requirements**: WEB-01, WEB-02, WEB-03, WEB-04, WEB-05
**Success Criteria** (what must be TRUE):
  1. A webhook request with an invalid or missing svix signature returns 401 and no DB write occurs
  2. Sending the same `call_started` event twice creates exactly one `call_attempt` document (upsert idempotency verified in Mongo)
  3. `call_started`, `function_call`, and `call_ended` events route to their respective typed handlers; an unknown event type logs a warning and returns 200
  4. The webhook route responds within 3 seconds on any valid payload (observable via Railway response-time logs)
**Plans**: TBD

### Phase 4: Tool Handlers (Read)
**Goal**: `get_debt_info` returns live, accurate debt data within latency budget — or explicitly signals unavailability so the agent never hallucinates amounts
**Depends on**: Phase 3
**Requirements**: TOOL-01, TOOL-06, TOOL-07
**Success Criteria** (what must be TRUE):
  1. Calling `get_debt_info` with a valid `debtor_id` returns `{saldo, vencimiento, ultimoPago}` populated from the live `debtors` collection — no caching
  2. Calling `get_debt_info` when any critical field (`saldo`, `vencimiento`) is null returns `{status: "data_unavailable"}` — never returns partial data that could be misrepresented
  3. A Zod-invalid input (wrong type, missing field) is rejected with a typed error before any DB query runs
  4. p95 latency of `get_debt_info` measured in unit tests with a seeded Mongo is under 800ms
**Plans**: TBD

### Phase 5: Tool Handlers (Write)
**Goal**: All four write tools persist their outcomes exactly once regardless of how many times Retell retries the same tool call
**Depends on**: Phase 4
**Requirements**: TOOL-02, TOOL-03, TOOL-04, TOOL-05
**Success Criteria** (what must be TRUE):
  1. Invoking `register_payment_promise` twice with the same `(callAttemptId, toolCallId)` produces exactly one `payment_promises` document (verified in Mongo after two identical calls)
  2. `schedule_callback` and `mark_dispute` are idempotent under the same key — second invocation returns the existing record, no duplicate
  3. `transfer_to_human` sets `call_attempt.outcome = "transferred"` and does not create a duplicate write on retry
  4. Every write tool validates its input with Zod before touching the DB — invalid arguments return a typed error and no partial write occurs
**Plans**: TBD

### Phase 6: Custom LLM + Agent Config
**Goal**: The voice agent converses with the right tone for each campaign type, identifies itself and warns about recording, and routes tool calls through the registry
**Depends on**: Phase 5
**Requirements**: LLM-01, LLM-02, LLM-03, LLM-04, LLM-05, LLM-06, LLM-07, AGENT-01, AGENT-02, AGENT-03, AGENT-04
**Success Criteria** (what must be TRUE):
  1. A `call_started` event for `campaignType=overdue` produces a system prompt that includes the overdue-specific tone and forbids inventing amounts; `upcoming` produces a distinct, softer prompt — verifiable by inspecting the built prompt string in tests
  2. The agent's first spoken turn always contains identity disclosure ("Soy [nombre], agente de cobranza de...") and recording notice — present in the system prompt and confirmed in sandbox transcripts
  3. `call_attempts.promptVersion` is populated on every call with a deterministic version string (e.g., SHA or semver tag) — inspectable in Mongo
  4. Anthropic SDK is called with at least one `cache_control` breakpoint on the system prompt — verified via SDK request payload in unit tests
  5. The Conversation Flow (identity verification, transfer-to-human, despedida nodes) is documented in repo as a JSON export or structured markdown
**Plans**: TBD

### Phase 7: Outbound Dialer + HTTP Routes
**Goal**: Calls can be triggered on demand and by the worker — and the worker never dials outside legal hours or exceeds the tenant's weekly cadence limit
**Depends on**: Phase 6
**Requirements**: OUT-01, OUT-02, OUT-03, OUT-04, OUT-05, OUT-06, OUT-07, OUT-08
**Success Criteria** (what must be TRUE):
  1. `POST /calls` with a valid `{tenantId, debtorExternalId, campaignType}` body triggers an outbound call via retell-sdk and returns the `callId` — verifiable in Railway logs and Retell dashboard
  2. The worker running at 09:00 America/Bogota on a weekday dispatches calls; the same worker at 21:00 or on a Sunday dispatches zero calls — observable via worker log output in tests
  3. A debtor who has already received 2 calls this week (matching `cadenceMaxPerWeek=2` in tenant config) receives no additional call from the worker that day
  4. Two concurrent worker ticks racing to call the same debtor result in exactly one outbound call (race condition prevented by partial unique index)
  5. Outbound call payload includes `amd_enabled: true` — AMD active for all outbound calls
**Plans**: TBD

### Phase 8: Inbound + Level 2 Hooks
**Goal**: Inbound calls are handled gracefully with debtor identification, and all Level 2 extension points exist as typed interfaces with no-op defaults
**Depends on**: Phase 7
**Requirements**: IN-01, IN-02, L2-01, L2-02, L2-03, L2-04
**Success Criteria** (what must be TRUE):
  1. An inbound call from a registered phone number resolves to the correct `tenantId` and `debtorExternalId` before the first agent turn
  2. An inbound call from an unknown number does not crash the handler — it proceeds with `debtorExternalId = "unknown"` and logs a warning
  3. The `outbox` field exists on `call_events` write operations and the `outbox` collection is defined — no consumer, but the structure is in place
  4. Calling `getFlag(tenantId, "any_key")` returns `false` without throwing; calling `otelSpan("op_name", fn)` executes `fn` without error and without an exporter configured
**Plans**: TBD

### Phase 9: Tests + Hardening
**Goal**: Every critical path has a Vitest suite, the compliance checklist passes, and the service is ready for the Softseguros pilot
**Depends on**: Phase 8
**Requirements**: TEST-01, TEST-02, TEST-03, TEST-04, TEST-05
**Success Criteria** (what must be TRUE):
  1. `vitest run` passes with zero failures — all tool tests (valid input, malformed input, `data_unavailable`), webhook tests (invalid signature, replay, malformed payload), prompt builder tests (overdue/upcoming), worker tests (calling window, cadence), and multi-tenant scoping tests pass
  2. A query constructed without `tenantId` in the tenant-scoping test fails to compile (TypeScript error) — confirmed by `tsc --noEmit` in CI
  3. Sending the same webhook event twice in a test produces exactly one DB document — idempotency confirmed by test assertion
  4. The compliance pre-flight checklist (identity disclosure, recording notice, calling window enforcement, AMD enabled, no PII in INFO logs) is verified by tests or documented manual gate — blocking pilot go-live
**Plans**: TBD

---

## Progress Table

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/? | Not started | - |
| 2. Data Model | 0/? | Not started | - |
| 3. Webhook Receiver + Session | 0/? | Not started | - |
| 4. Tool Handlers (Read) | 0/? | Not started | - |
| 5. Tool Handlers (Write) | 0/? | Not started | - |
| 6. Custom LLM + Agent Config | 0/? | Not started | - |
| 7. Outbound Dialer + HTTP Routes | 0/? | Not started | - |
| 8. Inbound + Level 2 Hooks | 0/? | Not started | - |
| 9. Tests + Hardening | 0/? | Not started | - |

---

*Roadmap created: 2026-05-09*
*Last updated: 2026-05-09*
