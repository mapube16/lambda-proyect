# Project Research Summary

**Project:** retell-voice - AI Voice Collections Agent
**Domain:** AI voice agent microservice for debt recovery (cobranza), LatAm/Colombia
**Researched:** 2026-05-09
**Confidence:** MEDIUM-HIGH (stack HIGH, architecture HIGH, features MEDIUM, compliance MEDIUM)

## Executive Summary

This is a production-grade AI voice microservice for automated debt collection, built on Retell AI as the telephony/voice runtime and Anthropic (via Retell LLM integration) as the conversational brain. The service exposes deterministic tool handlers (HTTP endpoints that Retell calls during live conversations) and an outbound call worker, all backed by a shared MongoDB instance. The established industry pattern: separate telephony runtime (Retell) from business logic (Node tools + Mongo), never put complex async operations inside the synchronous tool-call response window, and treat compliance constraints (calling windows, cadence limits, identity verification) as hard gates in the worker, not as conversational instructions to the LLM.

The recommended build approach follows a strict dependency order: foundation then webhook receiver + session manager then tool handlers then agent config registry then outbound dialer + HTTP routes then campaign worker then tests and hardening. Each layer is testable before the next depends on it. The two campaign types (overdue and upcoming) require separate Retell agent IDs with distinct toolsets. A single shared agent is an anti-pattern that leaks tools across campaign contexts.

The most consequential risks are: (1) compliance violations under Colombian Ley 1581 and Decreto 1746/2016 if calling-window enforcement or identity verification is incomplete before the first real pilot call, (2) webhook idempotency gaps that produce duplicate payment promises, and (3) dead air caused by slow MongoDB queries during synchronous tool calls. Legal review by a Colombia-specialized attorney is a hard prerequisite before calling real debtors.

---

## Key Findings

### Recommended Stack

The stack is decided and closed per PROJECT.md. All versions verified via npm registry on 2026-05-09.

**Core technologies:**
- Hono 4.12.18 + @hono/node-server 2.0.2: HTTP layer, lightweight, composable, faster than Express for webhook throughput
- Mongoose 9.6.2: ODM for MongoDB with typed schemas and TypeScript generics, shared with Landa ecosystem
- Zod 4.4.3: Schema validation at all edges (HTTP body, Retell webhooks, env vars), fail-fast at startup
- retell-sdk 5.22.0: Retell API client for outbound call dispatch and all webhook event types
- svix 1.93.0: Webhook signature verification (CRITICAL; Retell signs all webhooks via svix HMAC-SHA256)
- @anthropic-ai/sdk 0.95.1: Only needed if using custom LLM mode; in v1 Retell calls Claude internally
- Pino 10.3.1 + pino-http 11.0.0: Structured logging with tenantId/callId/debtorId bindings
- p-retry 8.0.0: Retry with exponential backoff (Level 2 hook, no-op in v1)
- Vitest 4.1.5: Test runner, ESM-native, no Jest/TypeScript complexity
- Biome 2.4.15: Linter + formatter in one binary

### Expected Features

**Must have (table stakes -- v1 pilot):**
- Outbound HTTP-triggered call (POST /calls) with debtorId + campaignType
- Outbound worker with calling-window enforcement (Mon-Fri 7am-7pm, Sat 8am-3pm, America/Bogota) and minimum cadence between attempts
- Inbound call reception with debtor identification by CLI + fallback to document number
- Tool get_debt_info: gate for all negotiation; returns status: data_unavailable if any critical field is null
- Tool register_payment_promise: primary pilot KPI; idempotent; Zod-validated arguments
- Tool schedule_callback: reduces abandoned calls
- Tool mark_dispute: legally required to register debtor disputes (SFC Colombia + FDCPA US)
- Tool transfer_to_human: legally required access path; mandatory threshold defined in system prompt
- call_attempt persistence with transcript, outcome enum, tool call history, duration
- Recording consent notice in first agent turn (Ley 1581/2012 requirement)
- Two campaign types (overdue / upcoming) with separate Retell agent IDs, prompts, and toolsets
- Multi-tenancy: tenantId on every document, every query
- Structured logs without PII in log fields

**Should have (v1.x after pilot validation):**
- AMD (Answering Machine Detection): amd_enabled true in outbound payload
- Recording URL stored in call_attempt (Retell already exposes it)
- Intelligent retry by outcome (no retry if promise made; retry earlier if no answer)
- Follow-up SMS post-call (requires separate SMS channel service)

**Defer to v2+:**
- Partial payment negotiation with tenant rule engine
- Real-time sentiment detection (requires audio analysis beyond transcript)
- Payment link during call (PSP integration: Wompi/PayU Colombia)
- PII redaction pipeline on transcripts (Level 2 hook interface exists in v1; implementation is v2)
- A/B prompts by campaign type with outcome instrumentation
- Recovery dashboard (Softseguros reads Mongo directly in v1)

### Architecture Approach

Three-layer structure: HTTP layer (Hono routers + middleware, zero business logic), Application layer (Webhook Event Dispatcher, Call Session Manager, Tool Dispatcher, Agent Config Registry, Outbound Dialer, Outbound Worker), and Persistence layer (Mongoose models, read-only on debtors, own writes on operational collections). The in-memory Map<callId, CallContext> is a read-through cache only; MongoDB is always the source of truth. Cross-cutting concerns (OTel, retry, PII redaction) are TypeScript interfaces with no-op implementations, swappable without touching call sites.

**Major components:**
1. Webhook Event Dispatcher: routes call_started / function_call / call_ended to typed handlers after HMAC verification
2. Tool Dispatcher: maps function_name to deterministic handler; each handler is one async function, one Mongo write, Zod-validated inputs, must return result within Retell 3-5s timeout
3. Agent Config Registry: maps campaignType to { retellAgentId, systemPrompt, toolset[] }; separate Retell agents per campaign type is mandatory (not optional)
4. Call Session Manager: opens/updates/closes call_attempt documents; maintains in-memory call context; recovers from restarts by re-hydrating from Mongo
5. Outbound Worker: setInterval for pilot scale; upgrade to BullMQ + Redis at 100+ concurrent calls; validates calling window and cadence before every createPhoneCall

### Critical Pitfalls

1. **Hallucination on partial debt data**: get_debt_info must return { status: data_unavailable } when any critical field is null. System prompt must explicitly forbid the agent from inferring amounts. Unit-tested with null-field inputs before any real call.

2. **Webhook non-idempotency**: Retell retries on timeout/5xx. Use findOneAndUpdate upsert + unique index on callId for call_attempts; compound unique index { callId, toolInvocationId } for payment_promises. Always respond 200 within 3 seconds.

3. **Dead air from slow tool execution**: Compound indexes required: { tenantId, phoneNumber } on debtors. Configure Retell filler_phrase on tools. Target p95 < 800ms. Keep Railway instance warm with /health ping every 5 minutes.

4. **Compliance violations (calling window + identity)**: Worker must enforce timezone-aware calling windows and verify debtor identity before mentioning the debt. A third party who receives debt information is an immediate legal violation under Ley 1581/2012. Legal review required before pilot.

5. **Multi-tenancy silent corruption**: Every Mongoose query must include tenantId as the first filter. Missing tenantId works during single-tenant pilot and silently leaks data when tenant 2 onboards. Enforce via typed query helper from day one; grep check in CI.

---

## Implications for Roadmap

### Phase 1: Foundation -- DB Models, Lib, Infrastructure
**Rationale:** Everything imports from here. Env validation, logger, Retell client singleton, Mongoose connection, and schemas with tenantId compound indexes cannot be retrofitted.
**Delivers:** src/db/, src/lib/ (env, logger, retell-client, Level 2 hook no-ops), Railway deploy scaffold, /health endpoint
**Addresses:** Multi-tenancy foundation, PII-aware logging, cold start prevention
**Avoids:** tenantId-less queries, cold start dead air, missing index pitfalls

### Phase 2: Webhook Receiver + Session Manager
**Rationale:** Tools need a live call context. HMAC verification must be in place before any tool can be trusted. Idempotency established here, not retrofitted after tools are built.
**Delivers:** src/http/, src/webhook/ (dispatcher + schemas + call-started/call-ended handlers), src/session/ (CallSessionManager with Mongo upsert + in-memory map)
**Avoids:** Webhook duplication, non-idempotent call_attempt creation, missing signature verification (security critical)

### Phase 3: Tool Handlers -- Core Business Logic
**Rationale:** Highest-value business logic; fully testable without outbound calls. Each tool is an independent async function with Zod-validated inputs, unit testable in isolation with mock context.
**Delivers:** src/tools/ -- all 5 handlers (get_debt_info, register_payment_promise, schedule_callback, mark_dispute, transfer_to_human) + dispatcher
**Implements:** Deterministic tool pattern (Zod validate then DB read/write then return result within 3s timeout)
**Avoids:** Hallucination from partial data, corrupted documents from malformed LLM arguments, tool response timeout

### Phase 4: Agent Config Registry + Prompt Engineering
**Rationale:** Needed by both outbound dialer and webhook handler for toolset resolution. Prompts require iteration; isolated phase allows changes without touching service logic.
**Delivers:** src/agent/ -- registry + overdue.config.ts + upcoming.config.ts with system prompts, max_duration_seconds configured, tone examples for both campaign types
**Avoids:** Infinite conversation loops (max_duration), tone complaints from debtors, tool leakage between campaign types (separate Retell agent IDs mandatory)
**Research flag:** Cobranza tone calibration in Colombian Spanish needs review by a collections-domain expert and 5-10 test transcripts before pilot

### Phase 5: Outbound Dialer + HTTP Routes
**Rationale:** Ties all components together. First point where an end-to-end call can be triggered in sandbox.
**Delivers:** src/dialer/outbound-dialer.ts, HTTP routes for POST /calls and POST /webhook/retell, sandbox end-to-end call test
**Avoids:** Raw port exposure (always use PORT env var), using axios as HTTP client (use SDK natives)

### Phase 6: Outbound Worker + Compliance Gates
**Rationale:** Worker is last because it depends on the dialer being proven correct. A buggy worker can trigger hundreds of real calls.
**Delivers:** src/dialer/worker.ts -- setInterval with concurrency limit, calling-window check (America/Bogota), weekly attempt counter per debtor, AMD configuration in outbound payload
**Avoids:** Calls outside legal hours (SFC Colombia violation), voicemail false positives, race condition with simultaneous calls to same debtor (partial unique index)
**Research flag:** Ley 2300/2023 attempt frequency limits are MEDIUM confidence -- verify with Colombian attorney before go-live

### Phase 7: Tests, Hardening, Pilot Readiness
**Rationale:** Surfaces are now fully known. Compliance checklist must pass before any real debtor is called.
**Delivers:** Vitest suites for all tools + webhook handlers + session manager; PITFALLS checklist verification; Biome clean; legal review completed
**Avoids:** All critical pitfalls via explicit test cases (null data hallucination, double-webhook idempotency, tenant isolation, voicemail outcome detection)

