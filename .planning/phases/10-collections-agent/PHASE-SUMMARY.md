# Phase 10: Collections Voice Agent + VAPI — Executive Summary

**Status:** Phase planned & ready for execution  
**Total waves:** 4  
**Estimated effort:** 3-4 weeks (single developer)  
**Go-live target:** Single-client pilot  
**Success metrics:**  60%+ call connect rate | 30%+ agreement rate | 100% compliance pass rate

---

## Phase Overview

**Objective:** Ship a production-ready **Collections Voice Agent** that automates debt recovery calls using VAPI, enabling SaaS clients to recover delinquent balances at scale with minimal manual overhead and full legal compliance.

**Strategic value:**
- Opens new revenue stream (collections-as-a-service) alongside B2B prospecting
- Demonstrates agent scalability (from research/outreach → speech/decisions)
- Validates VAPI + LLM decision-making pattern for future voice products
- Generates high-margin recurring income (% recovery fee + monthly SaaS base)

---

## Execution Plan

### Wave 1: Foundation & VAPI Integration (10-01-PLAN.md)
**Duration:** 3-5 days  
**Deliverable:** VAPI webhook infrastructure + MongoDB collections + agent stub

| Task | Details |
|------|---------|
| Dependencies | vapi-python-sdk, FastAPI POST handler, MongoDB indexes |
| Acceptance | Webhook events persisted; zero syntax errors |
| Tests | POST mock VAPI event → MongoDB record verified |

**Output:** FastAPI ready to dispatch logic; collections agent skeleton in place.

---

### Wave 2: Decision Engine & State Machine (10-02-PLAN.md)
**Duration:** 5-7 days  
**Deliverable:** LLM classifier, 4-way routing, offer generation, state transitions

| Task | Details |
|------|---------|
| Classifier | Temperature 0.3; {puede_pagar\|quiere_pagar\|no_puede\|rechaza} |
| Confidence | < 0.6 → escalate to human (no fuzzy decisions) |
| State machine | 6 states: inicial→clasificado→propuesta→acuerdo→seguimiento→archivado |
| Offer engine | Tailored terms per classification (immediate\|30d\|60d\|90d) |
| Tests | 6x unit tests; all passing |

**Output:** Core agent logic complete; classified debtors routed to appropriate strategies.

---

### Wave 3: Collections Tools & Compliance (10-03-PLAN.md planned)
**Duration:** 4-6 days  
**Deliverable:** Payment verification, agreement generation, compliance audit

| Component | Details |
|-----------|---------|
| Verification | Check payment capacity; call duration limits; contact frequency |
| Agreements | Template → PDF; signature capture stub for Phase 11 |
| Compliance | FCRA/LGDP/local rules enforced in system prompt |
| Audit trail | Every call recorded & transcribed; decision log immutable |
| Escalation | Human queue integration (Phase 11; stub for now) |

**Output:** Collections rules engine + audit-ready call logs.

---

### Wave 4: Dashboard, Multi-Tenant, & SLA (10-04-PLAN.md planned)
**Duration:** 3-5 days  
**Deliverable:** Analytics dashboard + client isolation + pilot-ready SLA

| Feature | Details |
|---------|---------|
| Dashboard | Recovery rate %, cost per call, call outcomes, debtor breakdown |
| Multi-tenant | Each client sees only their debtors/calls/agreements |
| Scheduling | Automatic retry logic (3-day, 7-day, 30-day intervals) |
| Monitoring | Uptime tracking, latency alerts, compliance violations |
| Testing | End-to-end test with 50-100 debtors; SLA verification |

**Output:** Production-ready; ready for single-client pilot.

---

## Architecture Snapshot

```
┌─────────────────────────────────────────────────────────┐
│        COLLECTIONS VOICE AGENT (Phase 10)               │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  VAPI calls → POST /webhooks/vapi/call-event            │
│          ↓                                               │
│  CLASSIFY_DEBTOR (LLM, temp 0.3)                       │
│  ├─ puede_pagar → immediate payment                    │
│  ├─ quiere_pagar → friendly reminder                   │
│  ├─ no_puede → payment plan (30/60/90d)               │
│  └─ rechaza → escalate OR archive                      │
│          ↓                                               │
│  ROUTE_ACTION (state machine)                           │
│  ├─ Update debtor estado                               │
│  ├─ Log decision                                        │
│  └─ Generate offer                                      │
│          ↓                                               │
│  GENERATE_OFFER (template + variables)                 │
│  ├─ Offer script (voice-friendly)                      │
│  ├─ Agreement document (Markdown → PDF Phase 11)       │
│  └─ Payment link (placeholder)                         │
│          ↓                                               │
│  MongoDB (per-client isolated)                          │
│  ├─ call_sessions (immutable audit)                    │
│  ├─ debtors (estado machine states)                    │
│  └─ agreements (signed documents)                      │
│          ↓                                               │
│  Dashboard (React frontend)                             │
│  ├─ Recovery rate %                                     │
│  ├─ Cost per call / cost per agreement                 │
│  ├─ Live call monitor                                   │
│  └─ Debtor breakdown by outcome                        │
│                                                          │
└─────────────────────────────────────────────────────────┘
```

---

## Integration Points

**With existing Hive infrastructure:**
- State machine pattern reused from Phase 9 (Landa)
- Agent context building reused from `core/context.py`
- MongoDB persistence layer (Phase 1 database schema)
- WebSocket broadcasting (Phase 2 orchestrator events)
- Auth isolation (Phase 1 user model)

**New integrations:**
- VAPI voice API (webhook + call lifecycle)
- LLM classification (temp 0.3 determinism)
- Payment provider stub (Stripe/local bridge in Phase 11)

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| VAPI webhook delays | Built-in replay logic; durable MongoDB queue |
| LLM classification errors | Confidence threshold + human escalation |
| Compliance violations | Hard-coded legal rules; audit trail; pre-approved prompts |
| Cross-tenant data leak | MongoDB indexes per user_id; no raw phone sharing |
| Call recording liability | GDPR-compliant storage; automatic retention policy |

---

## Success Metrics (Pilot)

**Operational:**
- Call connect rate: ≥ 60% (reached human on phone)
- Call classification accuracy: ≥ 80% (manual audit vs. agent decision)
- Agreement rate: ≥ 30% (of successful connects → commitment received)
- Call duration: 3-8 minutes average
- Cost per call: ≤ $0.75 USD (VAPI + agent + infra)
- Cost per agreement: ≤ $2.50 USD (= $0.75 ÷ 0.30)

**Compliance:**
- 100% call recording + transcription
- 0 legal complaints during pilot
- 100% audit trail completeness
- 0 LGDP violations (per legal review)

**Financial (pilot debtor count: 100):**
- Total debtors called: 100
- Connections: 60 (60%)
- Agreements reached: 18 (30% of connects)
- Average commitment: $500 USD
- Total recovered: $9,000 USD
- Cost of campaign: $100 USD (100 calls × $0.75 + overhead)
- **ROI: 9000%**

---

## Timeline

| Week | Wave | Deliverable | Go/No-Go |
|------|------|-------------|----------|
| W1 | 1 | VAPI webhook + MongoDB + stub agent | Green |
| W2 | 2 | Classifier + router + offer engine + tests | Green |
| W3 | 3 | Compliance tools + escalation + audit | Green |
| W4 | 4 | Dashboard + multi-tenant + SLA + pilot testing | Green → Pilot Launch |

---

## Prerequisites for Execution

**Before starting Wave 1:**
- [ ] VAPI account created + API key in `.env`
- [ ] MongoDB collections `debtors` and `call_sessions` exist
- [ ] FastAPI server running on `localhost:8001` or accessible IP
- [ ] Team has read Phase 9 (Landa foundation) and understands state machine pattern
- [ ] Legal review completed for system prompt (compliance statements)

**Testing environment:**
- [ ] Local MongoDB instance
- [ ] ngrok or similar for VAPI webhook callback
- [ ] Mock debtor data (50-100 test records)
- [ ] Test phone numbers for call simulation

---

## File Structure

```
.planning/phases/10-collections-agent/
├── 10-CONTEXT.md          ← Strategic & architectural decisions
├── 10-01-PLAN.md          ← Wave 1: VAPI + MongoDB setup
├── 10-02-PLAN.md          ← Wave 2: Decision engine + classifier
├── 10-03-PLAN.md          ← Wave 3: Compliance + tools [planned]
├── 10-04-PLAN.md          ← Wave 4: Dashboard + pilot [planned]
└── 10-REQUIREMENTS.md     ← Phase requirements mapping [to be created]

backend/
├── landa/agents/collections.py  [new]
├── models.py                     [extended]
├── database.py                   [extended]
├── main.py                       [extended]
└── tests/test_collections.py     [new]
```

---

## Next Steps

1. **Review & Approve**
   - Stakeholders review 10-CONTEXT.md + 10-01-PLAN.md
   - Confirm VAPI account details + compliance sign-off

2. **Execute Wave 1** (10-01-PLAN.md)
   - Run all tasks in parallel if possible
   - Acceptance criteria verified
   - Commit to `.planning/phases/10-collections-agent/`

3. **Execute Wave 2** (10-02-PLAN.md)
   - Once Wave 1 acceptance passes
   - Full decision engine + tests

4. **Pivot or Proceed?**
   - After Wave 2, evaluate classifier accuracy with real debtor conversations
   - Adjust prompts if needed
   - Proceed to Wave 3 (compliance) or iterate

5. **Pilot Launch** (after Wave 4)
   - Upload 100 debtors
   - Run 50-call test batch
   - Collect metrics
   - Iterate or scale to next client

---

*Phase: 10-collections-agent*  
*Created: 2026-03-25*  
*Updated: [on completion of each wave]*
