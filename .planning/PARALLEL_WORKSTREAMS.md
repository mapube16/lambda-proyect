# Parallel Execution Strategy: Phase 19 + Phase 24

**Date Initiated:** May 30, 2026  
**Strategy:** Parallel Planning with Sequential Execution

---

## 🎯 Overview

```
WORKSTREAM A (Primary)              WORKSTREAM B (Parallel/Standby)
═══════════════════════════════════════════════════════════════════
Phase 19: Tenant Isolation          Phase 24: Signal Sources
├─ Duration: 5 days                ├─ Duration: 18 days
├─ Status: PLANNING PHASE          ├─ Status: READY (standby)
├─ Blocks: Phase 24                ├─ Depends on: Phase 19 COMPLETE
├─ Critical Path: YES              ├─ Effort: 120+ hours
└─ Effort: 120 hours               └─ Kickoff: When Phase 19 done
```

---

## Timeline

### Week 1: Phase 19 Takes Priority

**Days 1-2: Phase 19 PLANNING PHASE**
```
Mon-Tue (Today onwards)
├─ Run /gsd-plan-phase 19
│  ├─ Discuss gray areas (tenant_id derivation, team members, etc.)
│  ├─ Create PLAN.md with 5 waves
│  └─ Output: Ready to execute
├─ Parallel: CODE REVIEW
│  ├─ Peer review Phase 19 plan (security focus)
│  ├─ Check: No data leakage possible?
│  └─ Approve or iterate
└─ Phase 24 WAITS in standby (plan already complete)
```

**Days 3-7: Phase 19 EXECUTION PHASE**
```
Wed-Sun
├─ Wave 1: Add tenant_id to all collections + indexes
├─ Wave 2: Update query layer (centralized helper)
├─ Wave 3: Migration script + verification
├─ Wave 4: Update WebSocket channels
└─ Wave 5: E2E testing + load testing
```

---

### Week 2: Phase 24 Begins (when Phase 19 at Wave 4+)

**Day 8 (next Monday): Phase 19 Enters TESTING PHASE**
```
Phase 19 status: Executing waves 4-5 (testing)
Phase 24 status: KICKOFF /gsd-plan-phase 24

Mon
├─ Phase 19: E2E tests running
├─ Phase 24: /gsd-plan-phase 24 starts
│  ├─ Clarify any spec questions
│  ├─ Finalize Wave breakdown
│  └─ Prepare for execution
└─ Tuesday: Phase 24 ready to execute (if Phase 19 complete)
```

**Days 9-12: Phase 24 EXECUTION (if Phase 19 done)**
```
If Phase 19 completes by Wed:
├─ Wed-Sun: Phase 24 EXECUTION
│  ├─ Wave 1: Backend fixes (timeouts, job_timeout, middleware, DLQ)
│  ├─ Wave 2: Signal sources (RUES, Bright Data, Hunter)
│  ├─ Wave 3: Integration (dedup, ranking, enrichment)
│  └─ Code review + merge

If Phase 19 delayed:
└─ Phase 24 waits (cannot proceed without tenant_id isolation)
```

---

## Dependency Graph

```
┌─────────────────────────────────────────────┐
│  Phase 18: Infrastructure Foundation        │
│  (Railway, ARQ, Redis) ✅ COMPLETE          │
└────────────────────┬────────────────────────┘
                     │
                     ▼
        ┌────────────────────────────┐
        │  Phase 19: Tenant          │
        │  Isolation                 │
        │  ⏳ PLANNING (NOW)          │
        │  └─ Blocker for Phase 24   │
        └────────────────┬───────────┘
                         │
        ┌────────────────▼─────────────────┐
        │  Phase 24: Signal Sources        │
        │  📋 READY (Standby)              │
        │  └─ Starts when Phase 19 done   │
        └────────────────────────────────┘
```

---

## Critical Path

**CRITICAL PATH = Phase 19** (must complete before Phase 24 can execute)

If Phase 19 takes 6 days instead of 5:
- Phase 24 starts 1 day later
- Total project timeline slips 1 day

→ All Phase 24 effort depends on Phase 19 + Phase 18 being solid

---

## Execution Model: Best Practices

### ✅ Parallel Planning, Sequential Execution
- **Planning:** Both phases planned simultaneously (now)
  - Phase 19 PLAN.md (5 days) ← TODAY
  - Phase 24 PLAN.md (18 days) ← ALREADY COMPLETE
  
- **Execution:** Phase 19 first, then Phase 24
  - Reason: Phase 19 is blocker
  - Risk reduction: Don't build Signal Sources on unstable foundation

### ✅ Code Review Coordination
- Phase 19 review: Focus on data isolation + security
- Phase 24 review: Focus on correctness + performance
- Parallel: While Phase 19 executes, review Phase 24 code (preparation)

### ✅ Testing Strategy
- Phase 19 tests: Isolation + no data leakage + performance
- Phase 24 tests: E2E (signal→lead), load (100 concurrent), failure scenarios
- Staging: Phase 19 deployed to staging first, validated, then prod

---

## Status Dashboard

| Component | Workstream | Status | ETA |
|-----------|-----------|--------|-----|
| Phase 19 SPEC | A | ✅ Complete | — |
| Phase 19 CONTEXT | A | ✅ Complete | — |
| Phase 19 PLAN | A | ⏳ In progress | Today |
| Phase 19 Code Review | A | — | Thu |
| Phase 19 Execution | A | — | Wed-Sun |
| Phase 24 SPEC | B | ✅ Complete (CONTEXT.md) | — |
| Phase 24 PLAN | B | ✅ Complete | — |
| Phase 24 Plan Review | B | — | Fri (optional) |
| Phase 24 Execution | B | — | Mon (if 19 done) |

---

## Handoff Protocol: Phase 19 → Phase 24

**When Phase 19 achieves "COMPLETE" status:**

1. ✅ All tenant_id fields added + indexes
2. ✅ All queries updated + tested
3. ✅ E2E test passes (2 brokers, zero leakage)
4. ✅ Deployed to production
5. ✅ Phase 19 artifacts archived

**Then Phase 24 can START:**

```bash
# Trigger Phase 24 execution
/gsd-execute-phase 24 --wave 1
```

Phase 24 will:
- Assume tenant_id filtering works (can build on it)
- Add signal_leads collection (with tenant_id indexed)
- Add cost_events collection (with tenant_id indexed)
- Implement quota_enforcement (per tenant)

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Phase 19 overruns | Medium | Buffer 2 days in schedule |
| Phase 19 misses tenant isolation | Low | Code review + security audit |
| Phase 24 blocked > 1 week | Low | Phase 19 critical path monitored daily |
| Database migration fails | Low | Dry-run on staging first |
| Performance regression | Low | Load test before prod deploy |

---

## Success Metrics

### Phase 19 Success
- ✅ Zero data leakage (2-broker E2E test)
- ✅ All queries explicitly filter tenant_id
- ✅ No performance regression (p50 < 50ms)
- ✅ Deployed to production by Day 7

### Phase 24 Success (contingent on Phase 19)
- ✅ Signal sources working (RUES, Bright Data, Hunter)
- ✅ Deduplication accurate (92%+ precision)
- ✅ Quota enforcement preventing over-usage
- ✅ E2E: Signal → Lead → Email

---

## Next Actions

**Immediate (Right Now):**
1. ✅ Phase 19 SPEC.md + CONTEXT.md created
2. ✅ Phase 24 PLAN.md exists
3. ⏭️ **Run `/gsd-plan-phase 19` to create detailed task breakdown**

**Today:**
4. Distribute Phase 19 plan for review (security focus)
5. Identify any Phase 19 questions/blockers

**This Week:**
6. Execute Phase 19 Wave 1-2 (add tenant_id)
7. Execute Phase 19 Wave 3-4 (migration + testing)
8. Deploy Phase 19 to staging (verify isolation)

**Next Week (if Phase 19 complete):**
9. Deploy Phase 19 to production
10. Kickoff Phase 24 execution

