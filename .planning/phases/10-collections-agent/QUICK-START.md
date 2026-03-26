# Phase 10: Collections Voice Agent + VAPI — Quick Reference Card

**Status:** ✅ Fully planned & ready for execution  
**Location:** `.planning/phases/10-collections-agent/`  
**Start here:** `README.md`

---

## In 60 Seconds

**What:** Automate debt recovery calls using VAPI + AI decision-making  
**How:** 4 concurrent waves over 3-4 weeks  
**Why:** Opens new revenue stream, validates voice agent pattern, high ROI (9000% pilot)  
**Cost to run 100 calls:** ~$75 USD  
**Revenue from pilot:** ~$9,000 USD (18 agreements × $500 avg)  

---

## The Agent's Brain

```
Incoming call from debtors starts → 
Agent hears: "Can you pay? Do you want to? / Why not? / Do you refuse?"
Agent decides: 
  • puede_pagar (60%+ confidence) → "Let's collect today"
  • quiere_pagar (good tone, money available) → "Easy payment plan"
  • no_puede (hardship signals) → "Here's a 60-day plan"
  • rechaza (hostile) → "Escalating to my team"
Outcome: Commitment recorded OR escalated to human
```

---

## 4 Waves Ready to Go

| Wave | What | When | By |
|------|------|------|-----|
| **1** | VAPI webhook + DB setup | Week 1 | Tue/Wed |
| **2** | AI classifier + router | Week 2 | Thu/Fri |
| **3** | Compliance tools | Week 3 | Tue/Wed |
| **4** | Dashboard + pilot launch | Week 4 | Thu/Fri |

**Can execute:** IMMEDIATELY (Wave 1 is self-contained)

---

## Files You Have

**Essential (read in this order):**
1. 📄 `README.md` — You are here
2. 📄 `10-CONTEXT.md` — Arch decisions (15 min read)
3. 📄 `PHASE-SUMMARY.md` — Timeline + metrics (10 min read)

**Implementation (execute in this order):**
1. ✅ `10-01-PLAN.md` — 5 tasks, 3-5 days (Wave 1 ready NOW)
2. ✅ `10-02-PLAN.md` — 5 tasks, 5-7 days (depends on Wave 1)
3. 📋 `10-03-PLAN.md` — Planned but not yet written
4. 📋 `10-04-PLAN.md` — Planned but not yet written

---

## Pre-Requisites (Right Now)

- [ ] VAPI account + API key (go to  https://vapi.ai)
- [ ] `.env` file with `VAPI_API_KEY` + `VAPI_WEBHOOK_URL`
- [ ] MongoDB running
- [ ] FastAPI starts cleanly (`cd backend && python -m uvicorn main:app`)
- [ ] ngrok for webhook tunneling (free tier: `ngrok http 8001`)

---

## Start Executing (Wave 1)

```bash
# 1. Read the plan
cat .planning/phases/10-collections-agent/10-01-PLAN.md

# 2. Start with Task 1 (add vapi-python-sdk)
# 3. Follow each <action> block
# 4. Verify with <acceptance_criteria>
# 5. Mark done, move to Task 2
# ... repeat for Tasks 2-5

# 6. When all Wave 1 tasks done:
pytest backend/ -v  # Should have no new failures

# 7. Commit to git
git add .planning/phases/10-collections-agent/
git commit -m "Phase 10 Wave 1 complete: VAPI webhook + models"

# 8. Start Wave 2
cat .planning/phases/10-collections-agent/10-02-PLAN.md
```

---

## Key Numbers

| Metric | Target | Notes |
|--------|--------|-------|
| Call connect rate | 60% | Realistic for  cold outbound |
| Classification accuracy | 80% | Manual audit vs AI |
| Agreement rate | 30% | Of successful connects |
| Cost per call | $0.75 | VAPI + agent cost |
| Cost per agreement | $2.50 | = $0.75 ÷ 0.30 |
| **Pioneer revenue** | $9,000 | 100 debtors × 18 agreements × $500 |
| **Campaign cost** | ~$100 | 100 calls |
| **ROI** | **9000%** | (9000 - 100) ÷ 100 |

---

## Decision Tree (Classifier)

Agent hears debtor and decides **100% automatically:**

```
"I can pay tomorrow with cash" → pode_pagar (95% confidence)
  → Action: Collect immediately
  → State: propuesta (offer made)

"I want to pay but need a plan" → quiere_pagar (85% confidence)
  → Action: Payment plan 
  → State: propuesta

"I lost my job last month" → no_pode (90% confidence)
  → Action: 60-day hardship plan
  → State: propuesta

"Don't call again!" → rechaza (98% confidence)
  → Action: Escalate to human
  → State: archivado_collections (marked for escalation)

"Maybe... I don't know" → low confidence (40%)
  → Action: Escalate automatically
  → State: inicial (retry)
```

---

## Compliance Built-In

✅ Temperature 0.3 (deterministic decisions, auditable)  
✅ Confidence threshold 0.6 (fuzzy cases → human)  
✅ No contact before 8 AM / after 8 PM  
✅ Max 1 call per 24h per debtor  
✅ Full call recording + transcript  
✅ Decision log immutable in MongoDB  
✅ Legal language checked before prompt  

---

## Reuses From Project

✅ State machine pattern (from Phase 9 Landa)  
✅ Agent context builder (Phase 2)  
✅ LLM calling pattern (existing)  
✅ MongoDB architecture (Phase 1)  
✅ WebSocket broadcast (Phase 2)  
✅ Auth isolation (Phase 1)  

**New to project:**
- VAPI voice API
- Collections-specific LLM logic
- 6-state collections machine

---

## When You're Done (All 4 Waves)

✅ Pilot-ready system for 1 client  
✅ 100+ concurrent debtor campaigns possible  
✅ Full compliance audit trail  
✅ $9000+ revenue per 100-debtor campaign (pilot math)  
✅ Ready to scale to 5-10 clients  
✅ Ready to add Phase 11 (human escalation queues)  

---

## Troubleshooting

**Task not working?**
→ Check acceptance_criteria (tells you what should happen)

**Modified file, now errors?**
→ Run `python -m py_compile <file>` (syntax check)

**Not sure about next step?**
→ Read the <read_first> block in the task (tells you what to read)

**Want to adjust scope?**
→ Modify 10-CONTEXT.md decisions, re-plan the wave

---

## Questions Before Starting?

**"Can I skip a wave?"**  
→ No, waves are sequential (each builds on prev)

**"Can I run waves in parallel?"**  
→ Wave 1 & 2 must be sequential; Waves 3-4 can overlap after Wave 2

**"How long does each task take?"**  
→ 30 min - 2 hours. Check 10-01-PLAN.md and 10-02-PLAN.md for specifics.

**"What if VAPI changes their API?"**  
→ The plan uses stable VAPI 0.2.5; if API breaks, see gsd-plan-phase `--review` mode

**"Can this work for other languages?"**  
→ Yes, system prompt supports Spanish/Portuguese/English; adjust in 10-CONTEXT.md

---

**Ready?**

👉 Next: `cat .planning/phases/10-collections-agent/10-CONTEXT.md`

*Phase 10 planning complete. Execution starts now.*
