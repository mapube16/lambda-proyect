---
phase: 17-voice-cobranza-agent
plan: "06"
subsystem: cobranza
tags: [apscheduler, cobranza, ley-2300, campaign-scheduler, mongodb, motor]

# Dependency graph
requires:
  - phase: 17-02
    provides: debtor_crud.py — debtor document structure and estado fields
  - phase: 17-03
    provides: call_scheduler.py (is_contact_allowed_now, has_been_contacted_today) and vapi_client.py (initiate_call)
provides:
  - campaign_scheduler.py with 3 APScheduler interval jobs and register_cobranza_jobs()
affects:
  - 17-08-PLAN (main.py integration — calls register_cobranza_jobs after scheduler.start())

# Tech tracking
tech-stack:
  added: []
  patterns:
    - apscheduler-interval-pattern: scheduler.add_job(fn, "interval", minutes=N, id="...", replace_existing=True)
    - fire-and-forget-task: asyncio.create_task(safe_initiate_call(...)) — non-blocking call dispatch from sync job loop
    - agotado-guard: intentos >= max_intentos check sets estado=agotado, skips call — prevents runaway retries
    - frecuencia-dias-guard: days_since_ultimo_contacto < frecuencia_dias check prevents over-contacting post-vencimiento debtors
    - rescue-pattern: 15-min cutoff query on updated_at resets llamando to sin_contacto — handles Pitfall 7 (Vapi webhook intermittent)

key-files:
  created:
    - backend/cobranza/campaign_scheduler.py
  modified: []

key-decisions:
  - "register_cobranza_jobs() accepts scheduler as parameter — no module-level landa.scheduler import — avoids circular import"
  - "asyncio.create_task() for fire-and-forget call dispatch — consistent with Phase 14 approve_lead pattern"
  - "safe_initiate_call resets estado to pendiente on Vapi error — debtor stays eligible for next job run"
  - "rescue_stuck_llamando_job resets to sin_contacto (not pendiente) — debtor needs re-contact, not initial contact"
  - "pytz import is lazy inside post_vencimiento_job for naive-datetime handling — avoids top-level import overhead"

# Metrics
duration: 5min
completed: 2026-03-27
---

# Phase 17 Plan 06: Voice Cobranza Agent — Campaign Scheduler Summary

**Three APScheduler interval jobs (pre-vencimiento reminder, post-vencimiento retry, stuck-llamando rescue) with Ley 2300 compliance guards and register_cobranza_jobs() for main.py integration**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-27T18:22:26Z
- **Completed:** 2026-03-27T18:27:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `backend/cobranza/campaign_scheduler.py` with 3 async APScheduler jobs:
  - `pre_vencimiento_job` (60-min interval): contacts `pendiente` debtors whose `vencimiento` is within the next 3 days; checks `is_contact_allowed_now()` and `has_been_contacted_today()` before each call
  - `post_vencimiento_job` (60-min interval): retries `pendiente` and `sin_contacto` debtors past due; enforces `intentos >= max_intentos` → `agotado` transition; respects `frecuencia_dias` from campaign config
  - `rescue_stuck_llamando_job` (10-min interval): resets debtors stuck in `llamando` for more than 15 minutes back to `sin_contacto` — handles Pitfall 7 (Vapi end-of-call-report intermittent)
- `safe_initiate_call()` helper wraps `initiate_call()`: stores `vapi_call_id` on success, resets `estado=pendiente` on failure
- `register_cobranza_jobs(scheduler)` accepts the scheduler as a parameter — no circular import with `landa.scheduler`
- All 8 COBR xfail stubs remain xfailed (0 errors) after adding the file

## Task Commits

Each task was committed atomically:

1. **Task 1: campaign_scheduler.py — 3 APScheduler jobs** - `cd16a91` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/cobranza/campaign_scheduler.py` — 3 job functions + safe_initiate_call helper + register_cobranza_jobs()

## Decisions Made

- `register_cobranza_jobs()` accepts scheduler as parameter — no module-level import of `landa.scheduler` to avoid circular import; called in `main.py` lifespan after `start_scheduler()`
- `asyncio.create_task()` for fire-and-forget Vapi call dispatch — consistent with Phase 14 `approve_lead` fire-and-forget pattern; avoids blocking the job loop
- `safe_initiate_call` resets `estado` to `pendiente` on Vapi error — debtor remains in retry pool for next job run
- `rescue_stuck_llamando_job` resets to `sin_contacto` (not `pendiente`) — debtor needs a re-contact attempt, not an initial one
- `pytz` lazy-imported inside `post_vencimiento_job` body for naive-datetime UTC localize — mirrors `call_scheduler.py` convention

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — `register_cobranza_jobs` is wired in `main.py` in Plan 17-08. No external configuration needed for this file alone.

## Next Phase Readiness

- 17-07 (Vapi webhook handler) can import `safe_initiate_call` if needed or use `vapi_client.initiate_call` directly
- 17-08 (main.py integration) can call `register_cobranza_jobs(scheduler)` in the FastAPI lifespan after `start_scheduler()`
- COBR-03 requirement is implemented; xfail stubs remain for 17-08 integration test upgrade

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
