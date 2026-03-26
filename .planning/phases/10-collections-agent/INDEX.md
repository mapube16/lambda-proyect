# Phase 10: Collections Voice Agent + VAPI — Execution Ready ✅

**Planning completed:** 2026-03-25  
**Status:** Phase is fully planned and ready for immediate execution  
**Entry point:** Start in `.planning/phases/10-collections-agent/`

---

## 📚 Documentation (Read in This Order)

### 1️⃣ START HERE (5 min read)
**File:** `QUICK-START.md`  
- What is Phase 10?
- 4 waves overview
- Pre-requisites checklist
- Decision tree diagram
- Key metrics at a glance

### 2️⃣ STRATEGY & ARCHITECTURE (15 min read)
**File:** `10-CONTEXT.md`  
- Scope definition (in/out of phase)
- 10 strategic decisions explained
- 6-state collections machine diagram
- Debtor classification matrix
- Compliance rules embedded
- Multi-tenant isolation design
- 12 canonical references (what to read before coding)

### 3️⃣ EXECUTIVE SUMMARY (10 min read)
**File:** `PHASE-SUMMARY.md`  
- High-level architecture
- 4 waves with deliverables
- Integration points with existing code
- Risk mitigation
- Success metrics & pilot ROI
- Timeline (3-4 weeks total)
- Prerequisites for execution

### 4️⃣ DETAILED WAVE PLANS (For coding)

#### Wave 1: VAPI Foundation (Executable NOW)
**File:** `10-01-PLAN.md` — 5 concrete tasks
- Task 1: Add vapi-python-sdk dependency
- Task 2: Extend Pydantic models (DebitorProfile, CallSession)
- Task 3: Add MongoDB collections & indexes
- Task 4: Create VAPI webhook endpoint in FastAPI
- Task 5: Create collections.py agent stub

**Execution time:** 3-5 days (one developer)  
**Status:** READY TO START IMMEDIATELY

#### Wave 2: Decision Engine (Depends on Wave 1)
**File:** `10-02-PLAN.md` — 5 concrete tasks
- Task 1: Extend state machine for collections states
- Task 2: Implement debtor classifier (4-way: puede/quiere/no puede/rechaza)
- Task 3: Implement action router & offer generation
- Task 4: Create VAPI webhook decision dispatcher
- Task 5: Create unit tests (6 tests minimum)

**Execution time:** 5-7 days (one developer)  
**Status:** Planned, ready after Wave 1 completes

#### Wave 3: Compliance & Tools (Planned)
**Status:** NOT YET WRITTEN (can be created on demand)  
- Payment verification
- Agreement generation
- Compliance audit logging
- Escalation to human queue
- Expected: 4-6 days

#### Wave 4: Dashboard & Pilot (Planned)
**Status:** NOT YET WRITTEN (can be created on demand)  
- Collections analytics dashboard
- Multi-tenant verification
- Automatic retry scheduling
- End-to-end testing
- Pilot readiness SLA
- Expected: 3-5 days

### 5️⃣ PROJECT-LEVEL REFERENCE
**File:** `README.md`  
- What's been done
- What you can do right now (3 options)
- Planning artifacts list
- Architecture at a glance
- Execution checklist
- Wave breakdown
- Integration with existing project

---

## 🎯 Core Deliverables Completed

```
✅ Phase 10-CONTEXT.md        — Complete architectural decision document
✅ Phase 10-01-PLAN.md        — Wave 1 with 5 executable tasks
✅ Phase 10-02-PLAN.md        — Wave 2 with 5 executable tasks  
✅ PHASE-SUMMARY.md          — Executive summary + timeline + ROI
✅ README.md                 — Project-level reference
✅ QUICK-START.md            — 60-second executive summary
✅ This file                 — Index & delivery summary
```

---

## 🔑 Key Decisions Documented

| Decision | Impact | Reference |
|----------|--------|-----------|
| Use VAPI (not Twilio+Assembly+ElevenLabs) | Faster go-live, single API | 10-CONTEXT.md §#1 |
| 4-way classifier (puede/quiere/no_puede/rechaza) | Better conversion, lower friction | 10-CONTEXT.md §#4 |
| Confidence threshold 0.6 → escalate | No bad commitments, human approval gate | 10-CONTEXT.md §#5 |
| Temperature 0.3 for classifier | Deterministic, auditable, consistent | 10-CONTEXT.md §#5 |
| 6-state linear machine (inicial→archivado) | Matches real workflow, natural validation | 10-CONTEXT.md §#3 |
| Full call recording + immutable log | Compliance defense + continuous improvement | 10-CONTEXT.md §#7 |
| Per-client MongoDB isolation | Complete multi-tenant security | 10-CONTEXT.md §#12 |
| No payment processor in Phase 10 | Keep MVP lean, defer to Phase 11 | 10-CONTEXT.md §#8 |

---

## 📋 Execution Path

### Path A: Start Wave 1 Right Now ⚡
1. Read: `QUICK-START.md` (5 min)
2. Read: `10-01-PLAN.md` (10 min)
3. Execute: Tasks 1-5 in sequence (3-5 days)
4. Verify: All acceptance criteria pass
5. Commit: Push to git
6. Proceed: Start Wave 2

### Path B: Get Stakeholder Buy-In First 📌
1. Share: `QUICK-START.md` + `PHASE-SUMMARY.md` to team
2. Q&A: Answer questions about strategy  
3. Review: Legal/compliance signs off on 10-CONTEXT.md
4. Approve: Proceed with execution
5. Execute: Start Wave 1

### Path C: Adjust Scope or Timeline 🔄
1. Review: `10-CONTEXT.md` decisions
2. Modify: Adjust scope or constraints
3. Re-plan: Create 10-03-PLAN.md and 10-04-PLAN.md
4. Re-estimate: Adjust timeline
5. Execute: Start Wave 1 (adjusted)

---

## 💡 Pre-Execution Setup (DO THIS FIRST)

Before starting Wave 1 tasks, setup your environment:

```bash
# 1. Create VAPI account
# → Go to https://vapi.ai
# → Get API key
# → Create ngrok account (for webhooks)

# 2. Setup environment
cd ~Desktop/hive-pixel-office
echo "VAPI_API_KEY=your_key_here" >> .env
echo "VAPI_WEBHOOK_URL=$(ngrok url)" >> .env

# 3. Start ngrok (in separate terminal)
ngrok http 8001

# 4. Verify FastAPI runs
cd backend
python -m uvicorn main:app --reload
# Should see: "Uvicorn running on http://127.0.0.1:8001"

# 5. Verify MongoDB
# Should have test collections: debtors, call_sessions
mongo
> db.debtors.count()
> db.call_sessions.count()

# 6. Ready?
cd ..
cat .planning/phases/10-collections-agent/10-01-PLAN.md
```

---

## 🎓 Learning Path (For Team)

**If new to project, read in order:**
1. `.planning/PROJECT.md` — Project mission
2. `.planning/ROADMAP.md` — Phases 1-9 context
3. `10-CONTEXT.md` — This phase's strategy
4. `10-01-PLAN.md` — First wave tasks

**If familiar with project:**
1. `QUICK-START.md` — 5 min overview
2. `10-01-PLAN.md` — Start executing

---

## 🚀 Wave Execution Timeline

```
Week 1: Wave 1 (VAPI webhook + DB)
├─ Day 1: Tasks 1-2 (models + database)
├─ Day 2: Tasks 3-4 (webhook + endpoints)
├─ Day 3-5: Task 5 (agent stub) + verification
└─ Status: ✅ Wave 1 complete

Week 2: Wave 2 (Decision engine)
├─ Day 1-2: Task 1-2 (state machine + classifier)
├─ Day 3-4: Tasks 3-4 (router + webhooks)
├─ Day 5: Task 5 (tests + verification)
└─ Status: ✅ Wave 2 complete

Week 3: Wave 3 (Compliance) [Planned]
├─ Days 1-4: Tools implementation
├─ Day 5: Verification
└─ Status: ✅ Wave 3 complete

Week 4: Wave 4 (Dashboard + Pilot) [Planned]
├─ Days 1-3: Dashboard + multi-tenant
├─ Day 4: End-to-end testing
├─ Day 5: Pilot launch
└─ Status: ✅ PILOT READY
```

---

## ✅ What's Ready vs. Not Yet Written

| Component | Status | Location |
|-----------|--------|----------|
| Phase strategy | ✅ Complete | 10-CONTEXT.md |
| Wave 1 plan | ✅ Complete | 10-01-PLAN.md |
| Wave 2 plan | ✅ Complete | 10-02-PLAN.md |
| Wave 3 plan | 📋 Template ready | (can create on demand) |
| Wave 4 plan | 📋 Template ready | (can create on demand) |
| Unit tests | ✅ Spec'd in 10-02-PLAN.md | backend/tests/test_collections.py |
| Models | ✅ Spec'd in 10-01-PLAN.md | backend/models.py |
| Database | ✅ Spec'd in 10-01-PLAN.md | backend/database.py |
| Webhook handler | ✅ Spec'd in 10-01-PLAN.md | backend/main.py |
| Collections agent | ✅ Spec'd in 10-02-PLAN.md | backend/landa/agents/collections.py |

---

## 🎯 Success = Plan Execution

✅ All plans use GSD format:
- Wave assignments (1-4)
- Concrete tasks with line numbers
- `<read_first>` (what to review before coding)
- `<action>` (exact code to apply)
- `<acceptance_criteria>` (how to verify completion)

✅ Every task is actionable (not subjective)

✅ Every acceptance criterion is grep-verifiable

✅ Dependencies are explicit

✅ Parallel execution identified where possible

---

## 📞 Questions?

**Should I start now?** → Yes, if VAPI account + .env ready  
**Should I change the plan?** → Modify 10-CONTEXT.md first  
**What if I get stuck?** → Check acceptance_criteria for exact requirements  
**Can I run waves in parallel?** → Wave 1 & 2 sequential; Waves 3-4 can parallel after 2  
**How long does full Phase 10 take?** → 3-4 weeks (all 4 waves)  
**What's the ROI?** → 9000% on pilot (100 debtors, $9k recovered, $75 cost)  

---

## 📂 File Structure

```
.planning/phases/10-collections-agent/
│
├── QUICK-START.md           ← START HERE (5 min)
├── 10-CONTEXT.md            ← Strategy document (15 min)
├── PHASE-SUMMARY.md         ← Executive overview (10 min)
│
├── 10-01-PLAN.md            ← Wave 1 (EXECUTABLE NOW, 5 tasks)
├── 10-02-PLAN.md            ← Wave 2 (depends on 1, 5 tasks)
│
├── README.md                ← Project-level guide
├── [10-03-PLAN.md]          ← Wave 3 (not yet written)
├── [10-04-PLAN.md]          ← Wave 4 (not yet written)
│
└── INDEX.md                 ← This file
```

---

## 🏁 Next Step

Pick one:

**Option 1: Start executing** → `cd .planning/phases/10-collections-agent && cat 10-01-PLAN.md`

**Option 2: Review strategy** → `cat 10-CONTEXT.md`

**Option 3: Check executive summary** → `cat PHASE-SUMMARY.md`

**Option 4: Get quick overview** → `cat QUICK-START.md`

---

*Phase 10: Collections Voice Agent + VAPI*  
*Planning complete. Ready for execution.*  
*Generated: 2026-03-25*  

🚀 **Ready to build.**
