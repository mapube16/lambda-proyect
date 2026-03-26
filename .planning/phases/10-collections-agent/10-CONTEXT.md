# Phase 10: Collections Voice Agent + VAPI - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning
**Source:** Strategic expansion beyond B2B prospecting into debt recovery

---

## Phase Boundary

**What this phase delivers:**

A production-ready **Collections Voice Agent** that automates debt recovery calls using VAPI for real-time voice synthesis, speech recognition, and call management. The agent makes intelligent, compliant decisions in real time (debtor classification, tone adaptation, offer generation, escalation) and outputs structured data (payment commitments, agreement documents, compliance logs) suitable for multi-tenant SaaS delivery.

**In scope:**
- VAPI webhook integration (call lifecycle: incoming → STT → agent decision → TTS → termination)
- Collections state machine (6 states: inicial → clasificado → propuesta → acuerdo → seguimiento → archivado)
- Real-time debtor classification (puede pagar / quiere pagar / no puede / rechaza)
- Dynamic offering engine (immediate payment, payment plans, escalation to human)
- Payment verification tools and agreement generation
- Full compliance audit trail (call recordings, transcripts, decision logs)
- Per-client collections configuration (credit policies, offer templates, escalation rules)
- Analytics dashboard (recovery rate %, cost per peso recovered, call duration, outcomes)
- Multi-tenant isolation (each client's debtors, campaigns, recordings separate)

**Out of scope:**
- Manual human agent queuing / call transfer protocol (v2 — Phase 11)
- Integration with accounting systems (SAP, NetSuite) — v2
- SMS/WhatsApp payment reminders — v2 (handle via separate nurturing agent)
- Credit scoring external APIs — v2
- Carrier fraud detection — v2

---

## Implementation Decisions

### Core Architecture

**1. VAPI as the Voice Transport**
- Decision: Use VAPI (not Twilio+Assembly+ElevenLabs) as single integrated stack
- Rationale: VAPI provides real-time STT/TTS, call management, webhooks, and call recording natively — no multi-API orchestration
- Trade-off: Vendor lock-in + cost efficiency vs. multi-provider flexibility
- Outcome: Fast go-live, transparent per-call billing, no latency overhead

**2. Collections Agent as a Landa Core Service**
- Decision: Implement as `landa/agents/collections.py` (parallel structure to outreach.py, nurturing.py)
- Rationale: Reuse existing Landa infrastructure (state_machine.py, core/context.py, MongoDBpersistence)
- Outcome: Consistent architecture, shared telemetry, easy A/B testing vs. other agents

**3. 6-State Collections Machine**
- Decision: Linear lead states: inicial → clasificado → propuesta → acuerdo → seguimiento → archivado
- Rationale: Matches real collections workflow; state boundaries = natural validation points
- Outcome: (See detailed state machine below)

### Decision Engine

**4. Debtor Classification (4-Way Decision Tree)**
- Decision: First call action is always 100% automated classification
- Categories:
  - **"Puede pagar"** (Can pay, high probability) → Immediate offer path
  - **"Quiere pagar"** (Wants to pay, low documentation) → Friendly reminder path
  - **"No puede pagar"** (Cannot pay, voices hardship) → Payment plan path (30/60/90 days)
  - **"Rechaza contacto"** (Refuses, agitated, legal request) → Escalate to human + flag
- Rationale: Different tone and strategy per category minimizes friction and improves conversion
- Outcome: Tone is never harsh, always adaptive

**5. Dynamic Tone & Offer Adaptation**
- Temperature for decision node: 0.3 (strict, deterministic)
- System prompt signature: Empathy-first framing, legal language embedded, no pressure tactics
- Rationale: Compliance dept. must pre-approve system prompt; high consistency required
- Outcome: Calls are replicable, auditable, defensible

**6. Escalation Trigger Matrix**
- Decision: Escalate to human agent if:
  - Debtor refuses contact (flag: `legal_request_detected`)
  - Debtor reports fraud / unknown debt (flag: `fraud_claim`)
  - Agent confidence < 60% on classification
  - Call duration > 15 minutes (agent stuck in loop)
  - Payment verification fails (external API timeout)
- Rationale: Minimize wasted calls, protect reputation, reduce legal risk
- Outcome: Scaling human agents only on high-value / high-risk calls

### Data & Compliance

**7. Call Recording & Full Transcript Storage**
- Decision: All calls recorded + AI transcript + decision log in MongoDB
- Fields per session:
  - `call_uuid`: VAPI call ID
  - `debtor_id`: debtor reference
  - `recording_url`: S3 or VAPI storage
  - `transcript`: STT output
  - `decision_log`: [{ timestamp, state, prompt, response, action }]
  - `compliance_flags`: [fraud_claim, legal_request, agitation_level]
  - `outcome`: (payment_committed | plan_agreed | escalated | rejected | error)
- Rationale: Legal defense, dispute resolution, continuous improvement
- Outcome: 24/7 audit trail for regulators

**8. Payment Verification & Agreement Generation**
- Decision: No immediate payment processor integration (Phase 11)
- Instead: Generate `payment_link` (placeholder) + agreement document (Markdown → PDF)
- Agreement template: Pre-approved by legal; variables injected (debtor name, amount, terms)
- Rationale: Avoid PCI compliance burden in MVP; slow integration with accounting later
- Outcome: Debtors get tangible agreement; backend handles document lifecycle

**9. Legal Compliance Controls**
- Decision: Hard constraints embedded in agent system prompt:
  - No contact before 8 AM or after 8 PM (client timezone)
  - No contact more than 1 time per 24h per debtor (unless debtor initiated)
  - No threats or aggressive language (monitored via content filter)
  - No mention of credit score damage (varies by jurisdiction)
- Rationale: FCRA / LGDP / local regulations differ per client; settings must be per-client
- Outcome: Client configures rules at onboarding; agent enforces

### Integration Points

**10. VAPI Webhook to Agent State Machine**
- Decision: Backend HTTP server exposes POST `/webhooks/vapi/call-event`
- VAPI events:
  - `initialized`: Call started → state = `inicial`
  - `message`: User speech received + STT result
  - `tool_call`: Agent decided to take action (offer, escalate, etc.)
  - `ended`: Call terminated → state = `archivado` + record final outcome
- Rationale: VAPI manages audio; backend manages business logic
- Outcome: Decoupled; easy to swap VAPI for another provider later

**11. Debtor Data Source & List Management**
- Decision: Debtors ingested via CSV upload or API endpoint (staff/client can upload)
- Schema: debtor_id, name, phone, email, amount_owed, due_date, contact_history
- Process: Staff → upload → parse → create `debtor` documents in MongoDB
- Activation: Client clicks "Start campaign" → agents begin calling (respects scheduling rules)
- Rationale: Flexible intake; no hard-coding debtor lists
- Outcome: Portable between clients and campaigns

### Multi-Tenant Isolation

**12. Campaign-Scoped Collections Runs**
- Decision: Collections = a new "campaign type" alongside prospecting campaigns
- Schema: `campaign { type: "collections", client_id, name, policy: {...}, started_at, paused }`
- Each client sees only their debtors, calls, agreements, payments
- Rationale: Leverage existing campaign infrastructure
- Outcome: Auth already validates user_id → client_id isolation

---

## Debtor State Machine

```
┌─────────────┐
│   inicial   │  Debtor record created; first call not yet made
└──────┬──────┘
       │ [Call initiated]
       ▼
┌─────────────────────┐
│   clasificado       │  Call 1: Debtor categorized (puede/quiere/no puede/rechaza)
└──────┬──────────────┘
       │ [Based on classification]
       ├─────────────────────────────────┬────────────────────┬──────────────┐
       │                                 │                    │              │
       ▼ [Puede/Quiere]                   ▼ [No puede]       ▼ [Rechaza]    │
┌─────────────────┐               ┌──────────────┐      ┌──────────┐       │
│   propuesta     │               │   propuesta  │      │ archivado│       │
│ (immediate)     │               │ (plan 30/60) │      │ (HITL)   │       │
└───────┬─────────┘               └─────┬────────┘      └──────────┘       │
        │ [Offer sent]                   │                                  │
        │                                │                                  │
        ▼                                ▼                                  │
┌──────────────────────────────────────────────────────────────┐            │
│                        acuerdo                              │            │
│  (Payment commitment received; agreement document signed)   │            │
└──────────┬──────────────────────────────────────────────────┘            │
           │ [Document signed or commitment confirmed]                    │
           │                                                              │
           ▼                                                              │
┌─────────────────┐                                                       │
│   seguimiento   │  Debtor entered payment schedule; follow-up calls    │
└────┬────────────┘  at agreed intervals                                 │
     │ [Schedule complete OR default] ──────────┬──────────────────────┐  │
     │                                          │                      │  │
     ▼ [Success]                    ▼ [Default]      ▼ [Error]          ▼  
┌──────────┐                  ┌──────────┐  Retry next day       [Restart
│archivado │                  │archivado │  or → human escalation  propuesta
│(Paid)    │                  │(Written  │                            or
└──────────┘                  │off)      │                         escalated]
                              └──────────┘
```

---

## the agent's Discretion

**System Prompt Tuning:**
- Initial tone to strike (e.g., "Friendly but firm" vs. "Empathetic and patient")
- Which debtor profiles get immediate retry vs. waiting period
- Language preferences (Spanish, Portuguese, English per client region)

**Escalation Sensitivity:**
- Confidence threshold for "confident classification" (pilot: 60%, can be tuned)
- Max call duration before forced escalation (pilot: 15 min)

**Offer Template Customization:**
- Payment plan terms (10%, 30%, 50% down vs. full deferral)
- Max extension period (30, 60, 90 days)
- Late fee forgiveness logic

**Call Campaign Scheduling:**
- Business hours per debtor contact attempt (configurable per client region)
- Retry intervals (immediate, 3-day, 7-day, 30-day)

---

## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Collections-Specific Specs & Decisions

- `personalidad.md` — Tones and framing used in prospecting; reuse empathy framework
- `.planning/ROADMAP.md` — Phases 1-9 completed; understand state machine pattern from Phase 9 (Landa foundation)
- `backend/landa/state_machine.py` — Source of truth for state transitions; study transition validation logic
- `backend/landa/core/context.py` — Agent system prompt building; reuse `build_system_prompt()` and `call_agent()`

### Infrastructure & APIs

- `backend/database.py` — MongoDB models; add `debtors` and `call_sessions` collections
- `backend/models.py` — Pydantic schemas; add `CollectionsRun`, `DebtorProfile`, `CallSession`
- `backend/auth.py` — User isolation; ensure new collections endpoints are guarded by `get_current_user`
- `backend/main.py` — FastAPI setup; add `/api/collections/*` route group

### VAPI Integration

- VAPI docs: https://docs.vapi.ai/ (webhook structure, call events, STT/TTS parameters)
- VAPI pricing: $0.50 base + $0.016/min STT + $0.016/min TTS + storage (critical forunit economics)
- VAPI webhook format: POST to your backend with `call_id`, `transcript`, `messages[]`

### Compliance & Legal

- Project compliance file: `backend/compliance_policy.md` (if exists; if not, will be created in Phase 10 execution)
- FCRA regulations (USA): Fair Debt Collection Practices Act — no harassment
- LGPDP (Brazil): Lei Geral de Proteção de Dados
- Local regulations by client region (configurable per campaign)

### Existing Landa Patterns

- `backend/landa/agents/outreach.py` — Template for collections.py structure
- `backend/landa/agents/nurturing.py` — Decision logic patterns
- `backend/landa/scheduler.py` — Retry logic (adapt for call scheduling)
- Tests: `backend/tests/test_landa.py` — Unit test pattern to follow

---

## Specific Ideas

### Initial MVP Features

1. **Single Debtor List Upload** → CSV with phone, name, amount (10-100 debtors)
2. **Single Campaign Run** → Start → all debtors called in sequence
3. **Simple Dashboard** → Live call count, success rate, pending agreements
4. **Manual Payment Link Entry** → When agreement reached, system outputs link; staff manually sends

### Pilot Client Profile (Recommended)

- **Industry:** Finance or B2B services (comfortable with automated collections)
- **Debtor count:** 50-300 (small enough to debug, large enough to validate economics)
- **Debt amount:** $500-$5000 USD equiv (collections worth the overhead)
- **Region:** Colombia or Brazil (Spanish/Portuguese support, regulatory clarity)

### Success Metrics (Per Pilot Client)

- **Call connect rate:** ≥ 60% (reached a human voice)
- **Classification accuracy:** ≥ 80% (debtor type guessed correctly per manual audit)
- **Agreement rate (of connects):** ≥ 30% (of calls that reached humans, % that got commitment)
- **Cost per call:** ≤ $0.75 USD (agent cost + VAPI cost + infra overhead)
- **Cost per agreement:** ≤ $2.50 USD (= $0.75 ÷ 0.30)
- **Compliance pass rate:** 100% (zero legal complaints in pilot period)

---

## Deferred Ideas

**Not in Phase 10, planned for later milestones:**

- Multi-language LLM routing (Claude 3.5 Haiku for Spanish, GPT-4o for context-heavy English)
- Human escalation queue management
- Payment processor integration (Stripe, Fintech local)
- SMS / WhatsApp payment reminder reminders
- Credit bureau reporting (Experian, Data Bureau)
- A/B testing framework for tones & offers
- Advanced analytics (customer lifetime value, repeat call patterns)
- Compliance auto-reporting (daily compliance summaries for legal review)

---

*Phase: 10-collections-agent*
*Context gathered: 2026-03-25 via strategic brief*
