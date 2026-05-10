# Architecture Research

**Domain:** AI Voice Agent Microservice (Retell + Anthropic + Mongo)
**Researched:** 2026-05-09
**Confidence:** HIGH (Retell SDK/docs patterns, well-established webhook architecture)

## Standard Architecture

### System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        EXTERNAL CALLERS                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐    │
│  │ Landa / other│   │  Retell AI   │   │  Deudor (inbound)    │    │
│  │  services    │   │  platform    │   │  via PSTN            │    │
│  └──────┬───────┘   └──────┬───────┘   └──────────┬───────────┘    │
└─────────┼─────────────────┼──────────────────────┼────────────────┘
          │ POST /calls      │ POST /webhook         │
          │                 │ (call_started,         │
          │                 │  call_ended,           │
          │                 │  function_call)        │
┌─────────▼─────────────────▼──────────────────────▼────────────────┐
│                          HTTP LAYER  (Hono)                        │
│                                                                     │
│  ┌──────────────────┐   ┌────────────────────────────────────────┐ │
│  │  Outbound Router │   │        Webhook Router                  │ │
│  │  POST /calls     │   │  POST /webhook/retell                  │ │
│  │  Zod validation  │   │  Signature verification + Zod schema   │ │
│  └────────┬─────────┘   └─────────────────┬──────────────────────┘ │
└───────────┼─────────────────────────────────┼──────────────────────┘
            │                                 │
┌───────────▼─────────────────────────────────▼──────────────────────┐
│                       APPLICATION LAYER                             │
│                                                                     │
│  ┌──────────────────────┐   ┌────────────────────────────────────┐ │
│  │  Outbound Dialer     │   │     Webhook Event Dispatcher       │ │
│  │  - buildCallPayload  │   │  routes event_type →               │ │
│  │  - retell.calls.     │   │  call_started → CallSessionManager │ │
│  │    createPhoneCall() │   │  function_call → ToolDispatcher    │ │
│  │  - persist attempt   │   │  call_ended → CallSessionManager   │ │
│  └──────────────────────┘   └────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────┐   ┌────────────────────────────────────┐ │
│  │  Agent Config        │   │     Call Session Manager           │ │
│  │  Registry            │   │  - create/update call_attempt      │ │
│  │  campaignType →      │   │  - store transcript chunks         │ │
│  │  { systemPrompt,     │   │  - record outcome on call_ended    │ │
│  │    toolset,          │   │  - in-memory Map<callId, ctx>      │ │
│  │    retellAgentId }   │   │    (context only; Mongo is source  │ │
│  └──────────────────────┘   │     of truth)                      │ │
│                             └────────────────────────────────────┘ │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │                    Tool Dispatcher                            │  │
│  │  function_call payload → route to deterministic handler →    │  │
│  │  execute → persist side-effect → return result JSON          │  │
│  │                                                               │  │
│  │  get_debt_info | register_payment_promise | schedule_callback │  │
│  │  mark_dispute  | transfer_to_human                            │  │
│  └──────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌──────────────────────┐                                           │
│  │  Outbound Worker     │                                           │
│  │  (internal setInterval│                                          │
│  │   / BullMQ queue)    │                                           │
│  │  reads debtors →     │                                           │
│  │  calls OutboundDialer│                                           │
│  └──────────────────────┘                                           │
└─────────────────────────────────────────────────────────────────────┘
            │                                 │
┌───────────▼─────────────────────────────────▼──────────────────────┐
│                      PERSISTENCE LAYER (Mongo / Mongoose)           │
│                                                                     │
│  ┌──────────────┐ ┌──────────────────┐ ┌────────────┐ ┌─────────┐  │
│  │ call_attempts│ │payment_promises  │ │ callbacks  │ │disputes │  │
│  │ (own writes) │ │  (own writes)    │ │(own writes)│ │transfers│  │
│  └──────────────┘ └──────────────────┘ └────────────┘ └─────────┘  │
│                                                                     │
│  ┌──────────────┐                                                   │
│  │   debtors    │  ← READ ONLY (populated by other services)       │
│  └──────────────┘                                                   │
└─────────────────────────────────────────────────────────────────────┘
            ↑
            │  (shared Mongo instance, Landa ecosystem)
```

### Component Responsibilities

| Component | Responsibility | Owns |
|-----------|----------------|------|
| **Outbound Router** | Accept `POST /calls`, validate body (debtorId, campaignType, tenantId), delegate to Outbound Dialer | Route + Zod guard |
| **Webhook Router** | Accept all Retell events, verify HMAC signature, parse event_type, delegate to Dispatcher | Auth + parse |
| **Outbound Dialer** | Resolve agent config for campaignType, call `retell.calls.createPhoneCall()`, create initial `call_attempt` doc | Call creation |
| **Webhook Event Dispatcher** | Route `call_started` / `function_call` / `call_ended` to the correct handler | Event routing |
| **Agent Config Registry** | Map `(tenantId, campaignType)` → `{ systemPrompt, toolset[], retellAgentId }` | Prompt + toolset binding |
| **Call Session Manager** | Open/update/close `call_attempt`; maintain in-memory call context map for the call lifetime | Call state lifecycle |
| **Tool Dispatcher** | Map `function_name` → handler, execute, persist side-effect, return result | Tool execution |
| **Tool Handlers** (x5) | Deterministic read/write against Mongo; each owns one side-effect collection | Business logic |
| **Outbound Worker** | Periodic scan of `debtors` (cadencia/ventana); enqueue outbound calls via Outbound Dialer | Campaign cadence |
| **Persistence Layer** | Mongoose models with `tenantId` index on every collection | Data integrity |

---

## Recommended Project Structure

```
src/
├── http/                        # Hono app + routers
│   ├── app.ts                   # Hono instance, middleware, route mount
│   ├── routes/
│   │   ├── calls.route.ts       # POST /calls (outbound trigger)
│   │   └── webhook.route.ts     # POST /webhook/retell
│   └── middleware/
│       ├── retell-signature.ts  # HMAC verification middleware
│       └── request-logger.ts    # Pino request logger
│
├── webhook/                     # Retell event handling
│   ├── dispatcher.ts            # Routes event_type → handler
│   ├── handlers/
│   │   ├── call-started.ts      # Opens call_attempt
│   │   ├── call-ended.ts        # Closes call_attempt, stores transcript
│   │   └── function-call.ts     # Delegates to ToolDispatcher
│   └── schemas/                 # Zod schemas for each Retell event shape
│       ├── call-started.schema.ts
│       ├── call-ended.schema.ts
│       └── function-call.schema.ts
│
├── tools/                       # Tool dispatcher + deterministic handlers
│   ├── dispatcher.ts            # function_name → handler map
│   ├── get-debt-info.ts
│   ├── register-payment-promise.ts
│   ├── schedule-callback.ts
│   ├── mark-dispute.ts
│   └── transfer-to-human.ts
│
├── dialer/                      # Outbound call creation
│   ├── outbound-dialer.ts       # Calls Retell SDK createPhoneCall
│   └── worker.ts                # Internal cadence worker (setInterval or BullMQ)
│
├── agent/                       # Agent configuration registry
│   ├── registry.ts              # campaignType → agentConfig resolver
│   └── configs/
│       ├── overdue.config.ts    # systemPrompt + toolset for overdue
│       └── upcoming.config.ts   # systemPrompt + toolset for upcoming
│
├── session/                     # Call session lifecycle
│   └── call-session-manager.ts  # In-memory Map + Mongo writes
│
├── db/                          # Mongoose models + connection
│   ├── connection.ts
│   └── models/
│       ├── call-attempt.model.ts
│       ├── payment-promise.model.ts
│       ├── callback.model.ts
│       ├── dispute.model.ts
│       ├── transfer.model.ts
│       └── debtor.model.ts      # Read-only reference model
│
├── lib/                         # Cross-cutting infrastructure
│   ├── logger.ts                # Pino instance with tenantId/callId/debtorId bindings
│   ├── retell-client.ts         # Singleton Retell SDK client
│   ├── env.ts                   # Zod-validated env vars
│   └── hooks/                   # Level 2 hook interfaces (no-ops)
│       ├── telemetry.hook.ts    # OTel interface — no-op implementation
│       ├── retry.hook.ts        # Retry/circuit-breaker interface — no-op
│       └── pii-redactor.hook.ts # Transcript PII redaction interface — no-op
│
└── index.ts                     # Entry point: connect DB, start HTTP, start worker
```

### Structure Rationale

- **`http/`** — Pure routing + middleware; zero business logic. Hono handlers call into `dialer/` or `webhook/`.
- **`webhook/`** — All Retell event handling is co-located. Schemas enforce contract at the edge so the rest of the app sees typed objects.
- **`tools/`** — Each tool is one file with one exported async function. The dispatcher is a simple record lookup. This makes unit testing trivial (no HTTP needed).
- **`agent/`** — Config registry is the single place that maps `campaignType` to prompt + toolset. Changing an overdue prompt means editing one file.
- **`session/`** — Isolated manager owns the in-memory call context map. Other components import it but never touch the map directly.
- **`lib/hooks/`** — Level 2 hooks live here as TypeScript interfaces + no-op implementations. Future implementors swap the no-op without touching call sites.

---

## Architectural Patterns

### Pattern 1: Retell Function-Call → Tool Dispatcher → Persist → Return

**What:** Retell sends a `function_call` webhook event synchronously. Your handler must return the tool result in the HTTP response body (Retell blocks the call until it receives the response).

**When to use:** Every time a tool is invoked during a live call.

**Trade-offs:** Simple and reliable; no async queue needed for the happy path. Failure of a tool = Retell receives an error result, agent narrates gracefully. Latency matters — keep tool handlers under 3 s or Retell times out.

```typescript
// webhook/handlers/function-call.ts
export async function handleFunctionCall(
  event: FunctionCallEvent,
  ctx: CallContext,
): Promise<RetellFunctionResult> {
  const handler = toolDispatcher[event.function_name];
  if (!handler) {
    return { result: "Tool not found", is_error: true };
  }
  return handler({ args: event.arguments, ctx });
}

// tools/dispatcher.ts
export const toolDispatcher: Record<string, ToolHandler> = {
  get_debt_info: getDebtInfo,
  register_payment_promise: registerPaymentPromise,
  schedule_callback: scheduleCallback,
  mark_dispute: markDispute,
  transfer_to_human: transferToHuman,
};

// tools/register-payment-promise.ts
export async function registerPaymentPromise({ args, ctx }: ToolInput) {
  const doc = await PaymentPromise.create({
    tenantId: ctx.tenantId,
    callAttemptId: ctx.callAttemptId,
    debtorId: ctx.debtorId,
    amount: args.amount,
    promisedDate: args.promisedDate,
  });
  await CallAttempt.updateOne(
    { _id: ctx.callAttemptId },
    { $push: { toolCalls: { name: "register_payment_promise", result: doc._id } } },
  );
  return { result: `Promesa registrada: ${doc._id}` };
}
```

### Pattern 2: campaignType as Agent Config Discriminator

**What:** A registry maps `(campaignType)` → `{ systemPrompt, toolset, retellAgentId }`. The Outbound Dialer resolves config before creating the call. Retell uses the resolved `agentId`, which already has the correct LLM prompt and tools configured on the Retell platform.

**When to use:** Any time you need divergent conversation logic without duplicating the service.

**Trade-offs:** Adding a new campaign type = add one config file + register in the map. The trade-off is that prompt changes require a code deploy (not a DB update). For v1 pilot, this is acceptable; a DB-driven registry is a future upgrade.

```typescript
// agent/registry.ts
type AgentConfig = {
  retellAgentId: string;
  systemPrompt: string;   // stored here for logging/audit — Retell uses its own copy
  toolset: string[];      // tool names enabled for this campaign
};

const AGENT_CONFIGS: Record<string, AgentConfig> = {
  overdue: {
    retellAgentId: env.RETELL_AGENT_ID_OVERDUE,
    systemPrompt: overduePrompt,
    toolset: ["get_debt_info", "register_payment_promise", "mark_dispute", "transfer_to_human"],
  },
  upcoming: {
    retellAgentId: env.RETELL_AGENT_ID_UPCOMING,
    systemPrompt: upcomingPrompt,
    toolset: ["get_debt_info", "schedule_callback", "transfer_to_human"],
  },
};

export function resolveAgentConfig(campaignType: string): AgentConfig {
  const config = AGENT_CONFIGS[campaignType];
  if (!config) throw new Error(`Unknown campaignType: ${campaignType}`);
  return config;
}
```

### Pattern 3: Level 2 Hooks as Interface + No-op

**What:** Each cross-cutting concern (OTel, retry, PII redaction) is defined as a TypeScript interface and injected at construction time. The default implementation is a no-op. The real implementation can be swapped in without changing call sites.

**When to use:** Any capability that is required later but not now.

**Trade-offs:** Adds a small layer of indirection. The payoff is zero rework when implementing OTel or retry later — you replace one file.

```typescript
// lib/hooks/telemetry.hook.ts
export interface TelemetryHook {
  startSpan(name: string, attrs: Record<string, string>): Span;
  endSpan(span: Span, outcome: string): void;
}

export const noopTelemetry: TelemetryHook = {
  startSpan: () => ({ id: "noop" } as Span),
  endSpan: () => {},
};

// lib/hooks/retry.hook.ts
export interface RetryHook {
  withRetry<T>(fn: () => Promise<T>, opts?: RetryOpts): Promise<T>;
}

export const noopRetry: RetryHook = {
  withRetry: (fn) => fn(),
};

// lib/hooks/pii-redactor.hook.ts
export interface PiiRedactorHook {
  redact(transcript: string): string;
}

export const noopPiiRedactor: PiiRedactorHook = {
  redact: (t) => t,
};
```

---

## Data Flow

### Outbound Call Flow

```
POST /calls
  { tenantId, debtorId, campaignType }
        │
        ▼ Zod validate
  calls.route.ts
        │
        ▼
  OutboundDialer.dial(tenantId, debtorId, campaignType)
        │
        ├─ AgentRegistry.resolveAgentConfig(campaignType)
        │    → { retellAgentId, systemPrompt, toolset }
        │
        ├─ MongoDB: debtors.findOne({ _id: debtorId, tenantId })
        │    → debtor phone number
        │
        ├─ retell.calls.createPhoneCall({
        │      from_number, to_number,
        │      agent_id: retellAgentId,
        │      metadata: { tenantId, debtorId, campaignType }
        │    })
        │    → { call_id }
        │
        └─ MongoDB: call_attempts.insertOne({
               callId, tenantId, debtorId, campaignType,
               status: "initiated", startedAt: now()
             })
             → HTTP 202 { callId }

--- Retell platform dials the phone ---

POST /webhook/retell  event_type: call_started
        │
        ▼ HMAC verify + Zod parse
  Dispatcher → call-started.handler
        │
        └─ CallSessionManager.open(callId, { tenantId, debtorId, campaignType })
             - in-memory Map set
             - MongoDB: call_attempts.updateOne({ callId }, { status: "active" })

--- During call: Retell sends function_call events synchronously ---

POST /webhook/retell  event_type: function_call
        │
        ▼ HMAC verify + Zod parse
  Dispatcher → function-call.handler
        │
        ├─ CallSessionManager.getContext(callId) → ctx { tenantId, debtorId, ... }
        │
        ├─ ToolDispatcher[function_name](args, ctx)
        │    ├─ execute business logic (read debtors / write side-effect collection)
        │    ├─ MongoDB: write payment_promise / callback / dispute / transfer
        │    └─ MongoDB: call_attempts $push toolCall record
        │
        └─ return { result: "..." }   ← Retell blocks until this response arrives

--- Call ends ---

POST /webhook/retell  event_type: call_ended
        │
        ▼ HMAC verify + Zod parse
  Dispatcher → call-ended.handler
        │
        ├─ CallSessionManager.close(callId)
        │    - in-memory Map delete
        │    - MongoDB: call_attempts.updateOne({
        │          status: "completed",
        │          endedAt, duration,
        │          transcript: piiRedactor.redact(event.transcript),
        │          outcome: deriveOutcome(toolCallsInAttempt)
        │        })
        └─ HTTP 200 (Retell discards body on call_ended)
```

### Inbound Call Flow

```
Deudor dials → Retell PSTN number
        │
        Retell identifies number, routes to agent configured
        for inbound (separate Retell agent or same agent)
        │
POST /webhook/retell  event_type: call_started
        │
        ├─ event.metadata.from_number = deudor's phone
        │
        ├─ call-started.handler:
        │    MongoDB: debtors.findOne({ phone: from_number, tenantId })
        │    → if found: open CallSession with debtorId
        │    → if not found: open with debtorId: null
        │         (agent will ask for ID; tool get_debt_info handles lookup)
        │
        └─ (same event chain as outbound from here)
```

### State Management — Mongo vs In-Memory

```
In-Memory Map<callId, CallContext>:
  { tenantId, debtorId, campaignType, callAttemptId }
  ├── Lives only for the duration of a call
  ├── Purpose: avoid a Mongo lookup on every function_call event
  ├── Populated on call_started, deleted on call_ended
  └── NOT source of truth — Mongo is

MongoDB call_attempts:
  ├── Source of truth for all call state
  ├── Survives restarts (in-memory is lost on crash)
  ├── Queried on call_ended to derive final outcome
  └── Recovery: if callId missing from Map (restart mid-call),
       handler re-hydrates from Mongo before proceeding
```

---

## Multi-Tenancy in the Data Model

Every writable collection carries `tenantId` as the first indexed field. All queries include it.

```typescript
// db/models/call-attempt.model.ts
const callAttemptSchema = new Schema({
  tenantId:     { type: String, required: true, index: true },
  callId:       { type: String, required: true, unique: true },
  debtorId:     { type: ObjectId, ref: "Debtor", required: true },
  campaignType: { type: String, enum: ["overdue", "upcoming"], required: true },
  status:       { type: String, enum: ["initiated","active","completed","failed"] },
  startedAt:    Date,
  endedAt:      Date,
  duration:     Number,   // seconds
  transcript:   String,   // PII-redacted on write
  outcome:      String,   // payment_promised | callback_scheduled | dispute | transferred | no_contact
  toolCalls:    [{ name: String, result: Mixed, calledAt: Date }],
});

callAttemptSchema.index({ tenantId: 1, debtorId: 1 });
callAttemptSchema.index({ tenantId: 1, createdAt: -1 });
```

Same pattern for `payment_promises`, `callbacks`, `disputes`, `transfers` — `tenantId` always first in compound indexes.

---

## Build Order (argumentado)

```
Phase 1 — Foundation
  db/ models + connection
  lib/ env, logger, retell-client, hooks (no-ops)
  Reason: everything else imports from here; must be stable first.

Phase 2 — Webhook Core (inbound event processing)
  webhook/ schemas + dispatcher
  session/ call-session-manager
  webhook/handlers/ call-started + call-ended
  Reason: tools need a live call context to test against; the session
          manager is a prerequisite for all tool integration.

Phase 3 — Tools
  tools/ dispatcher + all 5 handlers
  Reason: tools are independent of outbound; testable in isolation
          with mock ctx. This is the highest-value business logic.

Phase 4 — Agent Config Registry
  agent/ registry + overdue.config + upcoming.config
  Reason: needed by both outbound dialer and webhook (for toolset
          validation). Separate phase because prompts need iteration.

Phase 5 — Outbound Dialer + HTTP routes
  dialer/ outbound-dialer
  http/ app + routes/calls.route + webhook.route
  Reason: ties everything together; first point where a real end-to-end
          call can be triggered.

Phase 6 — Outbound Worker
  dialer/ worker
  Reason: last because it depends on the dialer being proven correct.
          A buggy worker can make hundreds of calls — test dialer first.

Phase 7 — Tests + Hardening
  Vitest suites for tools, webhook handlers, session manager
  Zod schema edge cases
  Reason: written last because the component surfaces are now known,
          but critical before pilot go-live.
```

---

## Anti-Patterns

### Anti-Pattern 1: Storing Full Call State Only In-Memory

**What people do:** Keep all call context (transcript chunks, tool call history) in a Node.js Map. Skip Mongo writes until call_ended.

**Why it's wrong:** If the process crashes or Railway restarts mid-call, all state is lost. On call_ended the handler has nothing to write.

**Do this instead:** Write to Mongo on every state-changing event (call_started creates the doc, each function_call appends to it, call_ended closes it). The in-memory Map is only a read-through cache for callId → ctx to avoid per-event Mongo lookups.

### Anti-Pattern 2: One Retell Agent for Both Campaign Types

**What people do:** Use a single Retell agent with a very long conditional system prompt ("if the user has overdue debt, then... otherwise...").

**Why it's wrong:** Retell uses the agent's configured toolset to decide which functions to offer the LLM. A single agent means all tools are always visible, which leaks `register_payment_promise` into upcoming calls and `schedule_callback` into overdue calls. The LLM may call tools that don't apply.

**Do this instead:** Create two separate Retell agents (overdue, upcoming) with distinct toolsets configured on the Retell platform. The Agent Config Registry maps campaignType → the correct agentId. Prompt and toolset isolation is clean.

### Anti-Pattern 3: Synchronous Mongo Write Blocking Retell's Function Call Response

**What people do:** Await complex aggregation queries or multi-document transactions inside a tool handler before returning to Retell.

**Why it's wrong:** Retell has a tool response timeout (~3–5 s). Complex writes block the response and cause Retell to time out, resulting in the agent telling the user something went wrong.

**Do this instead:** Keep tool handlers to a single targeted write + one optional read. If you need denormalization or complex reporting, do it asynchronously in a post-call job, not inside the synchronous tool handler.

### Anti-Pattern 4: Forgetting tenantId in Queries

**What people do:** Query `CallAttempt.findOne({ callId })` without `tenantId`.

**Why it's wrong:** Works fine with one tenant (piloto), breaks data isolation when tenant #2 onboards.

**Do this instead:** All queries take `ctx.tenantId` as the first filter. Enforce this via a Mongoose plugin or a typed query helper that requires tenantId:

```typescript
// db/query-helpers.ts
export function tenantQuery(tenantId: string, filter: object) {
  return { tenantId, ...filter };
}
// Usage: CallAttempt.findOne(tenantQuery(ctx.tenantId, { callId }))
```

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **Retell AI** | Retell Node SDK (`retell.calls.createPhoneCall`, `retell.calls.list`) + HMAC webhook verification | Webhook signature key from env `RETELL_API_KEY`. Keep SDK client as singleton in `lib/retell-client.ts`. |
| **Anthropic** | Via Retell (Retell calls Claude internally as the LLM for the agent) — no direct Anthropic SDK calls from this service in v1 | If switching to custom LLM mode, Anthropic SDK would be used in a `/llm-websocket` endpoint |
| **MongoDB** | Mongoose connection string from `MONGODB_URI` env var. Shared instance with Landa. | Use separate DB name or collection prefix to avoid conflicts. Read-only on `debtors`. |
| **Railway** | Deploy via `Dockerfile` or `nixpacks`. Env vars injected at runtime. | No secret manager needed for pilot. `PORT` env var for Hono listen. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| `http/` ↔ `dialer/` | Direct function call (import) | Router calls `OutboundDialer.dial()` |
| `http/` ↔ `webhook/` | Direct function call (import) | Router calls `Dispatcher.handle()` |
| `webhook/` ↔ `session/` | Direct function call | Handlers call `CallSessionManager` |
| `webhook/` ↔ `tools/` | Direct function call | function-call handler calls `ToolDispatcher` |
| `tools/` ↔ `db/` | Mongoose models (import) | Each tool imports only its relevant model |
| `dialer/` ↔ `agent/` | Direct function call | Worker/Dialer calls `AgentRegistry.resolveAgentConfig()` |
| `*` ↔ `lib/hooks/` | Interface injection (constructor param or module-level singleton) | No-op by default; swap implementations without touching call sites |

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| 0–100 concurrent calls (pilot) | Single Railway instance, in-process worker with `setInterval`, Mongo shared instance — sufficient |
| 100–1000 concurrent calls | Replace `setInterval` worker with BullMQ + Redis queue; add Railway horizontal scaling; Mongo Atlas dedicated cluster |
| 1000+ concurrent calls | Separate outbound-worker process; MongoDB read replicas; Retell concurrency limits become the bottleneck — negotiate enterprise plan |

### Scaling Priorities

1. **First bottleneck:** Retell concurrency limit per account. At ~50 simultaneous calls, check Retell plan limits before any infra change.
2. **Second bottleneck:** MongoDB write throughput on `call_attempts` (transcript append on every function_call). Batch transcript writes or write transcript only on call_ended if latency allows.

---

## Sources

- Retell AI documentation — webhook event schema and function call flow (knowledge cutoff Aug 2025, HIGH confidence for stable patterns)
- Retell Node SDK (`retell-sdk` npm package) — `calls.createPhoneCall` API shape
- Hono documentation — routing and middleware patterns
- Mongoose documentation — schema design with compound indexes
- Project `PROJECT.md` requirements — `tenantId`, tools, campaign types, Level 2 hooks

---
*Architecture research for: AI Voice Agent Microservice (Retell + Anthropic + Mongo)*
*Researched: 2026-05-09*
