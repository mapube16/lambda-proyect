---
phase: 17-voice-cobranza-agent
plan: "04"
subsystem: cobranza
tags: [fastapi, openai, gpt-4o, cobranza, onboarding, queen, ley-2300, tdd]

# Dependency graph
requires:
  - phase: 17-voice-cobranza-agent
    plan: "02"
    provides: router.py base, debtor_crud.py
  - phase: 17-voice-cobranza-agent
    plan: "03"
    provides: call_scheduler.py (Ley 2300), vapi_client.py (initiate_call)
provides:
  - cobranza/cobranza_queen.py with generate_cobranza_proposal()
  - POST /api/cobranza/onboarding/start — Queen strategy proposal
  - POST /api/cobranza/onboarding/approve — save estrategia to cobranza_config
  - POST /api/cobranza/debtors/{id}/llamar-ahora — Ley 2300 guarded manual call
affects:
  - 17-05-PLAN (webhook handlers use cobranza_config stored here)
  - 17-08-PLAN (router registration in main.py)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - queen-json-object-pattern: openai.AsyncOpenAI + response_format={"type":"json_object"} + temperature=0.4 — mirrors queen_proposal.py exactly
    - cobranza-config-upsert: db.cobranza_config.update_one({user_id}, {$set: {estrategia, updated_at}}, upsert=True) — user_id as campaign key
    - fire-and-forget: asyncio.create_task(_initiate_call_and_update(...)) — non-blocking 202 response for llamar-ahora

key-files:
  created:
    - backend/cobranza/cobranza_queen.py
    - backend/tests/test_cobranza_queen.py
  modified:
    - backend/cobranza/router.py

key-decisions:
  - "empresa_nombre fetched from get_client_profile at request time — not stored in Queen module"
  - "Fallback on ANY exception (not just missing key) — OpenAI network errors never surface to user"
  - "llamar-ahora returns 202 immediately; Vapi call result updates debtor async via asyncio.create_task"
  - "cobranza_config uses user_id as upsert key — one campaign config per tenant"

# Metrics
duration: 9min
completed: 2026-03-27
---

# Phase 17 Plan 04: Voice Cobranza Agent — Queen Onboarding + Llamar-Ahora Summary

**OpenAI gpt-4o Queen generates collection strategy proposals; 3 new REST endpoints for conversational onboarding and manual call initiation with Ley 2300 compliance**

## Performance

- **Duration:** ~9 min
- **Started:** 2026-03-27T18:22:30Z
- **Completed:** 2026-03-27T18:31:00Z
- **Tasks:** 2 (Task 1 TDD with RED/GREEN phases)
- **Files modified:** 3

## Accomplishments

- Created `backend/cobranza/cobranza_queen.py`:
  - `generate_cobranza_proposal(user_description, empresa_nombre)` — calls gpt-4o with `response_format={"type":"json_object"}` at temperature 0.4
  - Clamps `frecuencia_dias` to [1,3] and `max_intentos` to [1,10]
  - Returns safe fallback dict on missing `OPENAI_API_KEY` or any exception — never raises to caller
  - `empresa_nombre` interpolated into system prompt so Queen personalizes script with real company name
- Created `backend/tests/test_cobranza_queen.py` — 11 TDD unit tests (all passing):
  - Import check, fallback key presence, saludo empresa_nombre injection, clamping high/low, mocked OpenAI parse, exception-to-fallback
- Extended `backend/cobranza/router.py` with 3 new endpoints:
  - `POST /api/cobranza/onboarding/start` — Queen call returns `{"estrategia": {...}}`
  - `POST /api/cobranza/onboarding/approve` — upserts to `cobranza_config` collection, returns `{"campaign_id": user_id, "ok": True}`
  - `POST /api/cobranza/debtors/{id}/llamar-ahora` — Ley 2300 time/daily guards, fire-and-forget `asyncio.create_task`, returns 202
- Plan verification: `test_cobr_02_queen_propone_estrategia` and `test_cobr_02_approve_saves_campaign` both xfailed (not errored)
- Full test suite: 23 passed, 8 xfailed, 0 errors

## Task Commits

Each task committed atomically:

1. **Task 1 TDD RED: Failing tests for cobranza_queen** - `0568a7c` (test)
2. **Task 1 TDD GREEN: Implement cobranza_queen.py** - `ea3faec` (feat)
3. **Task 2: Onboarding + llamar-ahora endpoints** - `3f56b3c` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/cobranza/cobranza_queen.py` — Queen strategy proposal; `generate_cobranza_proposal()` with gpt-4o json_object, clamping, fallback
- `backend/tests/test_cobranza_queen.py` — 11 TDD unit tests (all passing)
- `backend/cobranza/router.py` — 3 new endpoints appended; new imports: datetime/timezone, generate_cobranza_proposal, is_contact_allowed_now, has_been_contacted_today, initiate_call, get_client_profile

## Decisions Made

- `empresa_nombre` fetched live from `get_client_profile` at request time — avoids stale data in Queen module
- Fallback triggers on ANY exception (network errors, JSON parse failure, missing key) — OpenAI errors never surface as 500 to user
- `llamar-ahora` returns 202 immediately; Vapi call result updates debtor estado async via `asyncio.create_task`
- `cobranza_config` uses `user_id` as upsert key — one campaign config per tenant, overwrites on re-approval

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- 17-05 (Vapi webhook handlers) can read `cobranza_config` via `db.cobranza_config.find_one({"user_id": user_id})`
- 17-06 (campaign scheduler) can use `estrategia.frecuencia_dias` and `max_intentos` from saved config
- 17-08 (router registration) will include `cobranza.router` in `main.py`
- COBR-02 xfail stubs remain xfailed — will be promoted in 17-08 integration plan

## Self-Check

- [x] `backend/cobranza/cobranza_queen.py` — created
- [x] `backend/tests/test_cobranza_queen.py` — created
- [x] `backend/cobranza/router.py` — modified (3 endpoints added)
- [x] Commit `0568a7c` — test(17-04) TDD RED
- [x] Commit `ea3faec` — feat(17-04) cobranza_queen.py
- [x] Commit `3f56b3c` — feat(17-04) router endpoints

## Self-Check: PASSED

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
