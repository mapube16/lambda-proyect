# Phase 10: Collections Voice Agent + VAPI — Planning Complete ✅

**Status:** Ready for execution  
**Planning completed:** 2026-03-25  
**Estimated execution time:** 3-4 weeks  
**Target go-live:** Single-client pilot  

---

## 📋 What's Been Done

All strategic planning is complete. You now have **4 actionable PLAN.md files** that can be executed sequentially:

✅ **10-CONTEXT.md** — Complete architectural decisions + state machine + compliance framework  
✅ **10-01-PLAN.md** — Wave 1: VAPI webhook setup + MongoDB schemas + agent stub (5 concrete tasks)  
✅ **10-02-PLAN.md** — Wave 2: LLM classifier + decision router + offer engine + tests (5 concrete tasks)  
✅ **PHASE-SUMMARY.md** — Executive overview + timeline + success metrics  

**Plus:**
- Complete Collections state machine (6 states with validated transitions)
- Debtor classification framework (4-way decision tree)
- Multi-tenant isolation model 
- Compliance audit trail design
- Pilot success metrics and unit economics

---

## 🎯 What You Can Do Right Now

### Option 1: Execute Wave 1 Immediately
All tasks in **10-01-PLAN.md** are fully specified with:
- Exact file paths and line numbers
- Concrete action code (copy-paste ready)
- Acceptance criteria (how to verify completion)
- Test commands

**Time estimate:** 3-5 days (one developer)

```bash
# Start with Task 1 from 10-01-PLAN.md
# Add vapi-python-sdk to requirements.txt and follow sequentially
```

### Option 2: Get External Review First
Share these files with team/stakeholders:
1. `10-CONTEXT.md` — Strategic decisions (read first)
2. `PHASE-SUMMARY.md` — Executive summary
3. Ask: "Does this architecture work for your collections use case?"

### Option 3: Refine Before Execution
If you want to adjust scope:
- Modify `10-CONTEXT.md` decisions (e.g., add SMS reminders to Wave 3)
- Replan `10-03-PLAN.md` and `10-04-PLAN.md` (not yet created)
- Re-estimate timeline

---

## 📁 Planning Artifacts Created

All files are in: `.planning/phases/10-collections-agent/`

```
.planning/phases/10-collections-agent/
├── 10-CONTEXT.md              Complete architecture + decisions
├── 10-01-PLAN.md              Wave 1: VAPI setup (5 tasks)
├── 10-02-PLAN.md              Wave 2: Classifier + router (5 tasks)
├── PHASE-SUMMARY.md           Executive summary + timeline
└── [10-03-PLAN.md]            Wave 3: Compliance + tools [to create on demand]
```

Each PLAN.md contains:
- Wave number & dependencies
- Detailed objectives
- Task-by-task breakdown with:
  - `<read_first>` — What to read before starting
  - `<action>` — Exact code/config to apply
  - `<acceptance_criteria>` — How to verify it worked
- Verification criteria for the wave
- `must_haves` checklist

---

## 🚀 Architecture at a Glance

**The Collections Voice Agent:**

```
VAPI Call → POST /webhooks/vapi/call-event → Classify Debtor (LLM, temp 0.3)
    ↓
Route to Action (Immediate Offer | Payment Plan | Escalate | Terminate)
    ↓
Generate Offer (Tailored to classification)
    ↓
Update Debtor State Machine (inicial → clasificado → propuesta → acuerdo → ...)
    ↓
Record in MongoDB (Full audit trail for compliance)
    ↓
Dashboard (Recovery rate %, cost per call, live metrics)
```

**Key stats from planning:**
- **4-way classification:** puede_pagar | quiere_pagar | no_puede | rechaza
- **6-state machine:** inicial → clasificado → propuesta → acuerdo → seguimiento → archivado
- **Confidence threshold:** < 0.6 → escalate to human (no fuzzy decisions)
- **Cost per call:** ≤ $0.75 USD (pilot economics)
- **Multi-tenant:** Complete isolation; each client sees only their debtors

---

## ✅ Execution Checklist

Before starting Wave 1, confirm:

- [ ] VAPI account created + API key in `.env` (get from VAPI dashboard)
- [ ] MongoDB running locally or accessible
- [ ] FastAPI server can start without errors (`cd backend && python -m uvicorn main:app --reload`)
- [ ] ngrok or tunnel ready for VAPI webhooks to reach your local server
- [ ] Team reviewed `10-CONTEXT.md` architectural decisions
- [ ] Legal teams approved compliance language in `10-CONTEXT.md`

---

## 📊 Wave Breakdown

| Wave | Duration | Deliverable | Go/No-Go |
|------|----------|-------------|----------|
| **1** | 3-5 days | VAPI webhook + MongoDB + agent stub | ✅ Ready to execute |
| **2** | 5-7 days | Classifier + router + offer engine | ✅ Planned, depends on Wave 1 |
| **3** | 4-6 days | Compliance tools + escalation | 📋 Planned (10-03-PLAN.md not yet created) |
| **4** | 3-5 days | Dashboard + multi-tenant + pilot | 📋 Planned (10-04-PLAN.md not yet created) |

---

## 🎓 What Each Wave Delivers

### Wave 1: VAPI Foundation
- FastAPI endpoint receives VAPI events
- MongoDB stores call sessions durably
- Agent module stub ready for logic
- Zero syntax errors; ready for Wave 2

### Wave 2: Decision Intelligence  
- LLM classifier returns 4-way classification
- Confidence threshold triggers escalation
- Debtor state machine transitions correctly
- Offers generated tailored to classification
- 6 unit tests covering all paths

### Wave 3: Compliance & Tools [Planned]
- Payment verification service
- Agreement document generation
- Legal compliance rules enforced
- Escalation to human queue (stub for Phase 11)
- Full audit trail immutable

### Wave 4: Production Ready [Planned]
- Analytics dashboard (recovery %, cost, outcomes)
- Multi-tenant isolation verified
- Automatic retry scheduling
- End-to-end testing (50-100 debtors)
- SLA monitoring + alerting
- **Ready for pilot launch**

---

## 💡 Key Decisions Embedded

✅ **VAPI** over Twilio+Assembly+ElevenLabs (faster go-live, single integration point)  
✅ **Temperature 0.3** for classification (deterministic, auditable, consistent)  
✅ **Confidence threshold 0.6** (escalate fuzzy cases to human, no bad commitments)  
✅ **6-state machine** (matches real collections workflow, natural validation points)  
✅ **Per-client MongoDB** (full multi-tenant isolation)  
✅ **Full call recording** (compliance + analysis)  
✅ **No immediate payment processor** (Phase 11, keep MVP lean)  

---

## 🎯 Success Metrics (Pilot)

**Operational:**
- 60%+ calls connect (reached human voice)
- 30%+ agreement rate (of connections)
- 100% compliance pass (zero legal complaints)
- ≤ $0.75 cost per call

**Financial (100 debtors):**
- 60 connections × 30% = 18 agreements
- 18 × $500 avg = $9,000 recovered
- Cost: ~$100 (100 calls × $0.75)
- **ROI: 9000%**

---

## 🔗 Integration with Existing Project

**Reuses from Phase 9 (Landa):**
- State machine pattern + validation logic
- Agent context builder (`build_system_prompt`)
- LLM calling pattern (`call_agent`)
- MongoDB persistence architecture
- WebSocket broadcast infrastructure

**New to project:**
- VAPI integration (voice I/O)
- Collections-specific tools (verification, offers, escalation)
- Compliance audit logging

**Not in Phase 10 (Phase 11+):**
- Human agent queue management
- Payment processor integration
- SMS/WhatsApp reminders
- Credit bureau reporting

---

## 📞 Support & Questions

**If you're stuck on a task:**
1. Check acceptance_criteria (tells you exactly what to verify)
2. Run the test command listed (should pass if done correctly)
3. Check for typos in file paths / function names
4. Ask Claude for help on specific task

**If you want to adjust scope:**
- Modify `10-CONTEXT.md` decisions
- Re-plan the affected waves
- Re-estimate timeline

**If you want to parallelize:**
- Waves 1-2 are sequential (2 depends on 1)
- Waves 3-4 can start after Wave 2 completes
- Within a wave, tasks are sequential (each builds on prev)

---

## 📝 Next Command

When ready to start execution:

```bash
# Enter Phase 10 directory
cd .planning/phases/10-collections-agent/

# Start with Wave 1
cat 10-01-PLAN.md

# Execute each task in order
# Verify acceptance criteria after each task
# Commit work to git at wave completion
```

---

*Phase 10 planning complete.*  
*Ready for execution: 2026-03-25*  
*Questions? Review CONTEXT.md or ping team.*
