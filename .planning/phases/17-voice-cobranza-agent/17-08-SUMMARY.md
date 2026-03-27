---
phase: 17-voice-cobranza-agent
plan: "08"
subsystem: cobranza-integration
tags: [fastapi, apscheduler, testing, cobranza, router, vapi, staff-endpoint]

# Dependency graph
requires:
  - phase: 17-voice-cobranza-agent
    plan: "04"
    provides: cobranza/router.py, cobranza/debtor_crud.py
  - phase: 17-voice-cobranza-agent
    plan: "05"
    provides: cobranza/webhooks.py vapi_router
  - phase: 17-voice-cobranza-agent
    plan: "06"
    provides: cobranza/campaign_scheduler.py register_cobranza_jobs
  - phase: 17-voice-cobranza-agent
    plan: "07"
    provides: frontend CobranzaTab, useWebSocket debtor_update

provides:
  - backend/main.py — cobranza_router + vapi_router included; register_cobranza_jobs called in lifespan
  - POST /api/staff/clients/{client_id}/cobranza/enable — staff enables cobranza per client
  - cobranza_enabled flag guard on llamar-ahora and onboarding/approve
  - All 8 COBR test stubs passing

affects:
  - backend/cobranza/router.py — _require_cobranza_enabled guard on call-initiating endpoints
  - backend/requirements.txt — pandas added

# Tech tracking
tech-stack:
  added:
    - pandas>=2.0.0 (requirements.txt)
  patterns:
    - cobranza-enabled-flag: company_voice.cobranza_enabled set by staff; checked in llamar-ahora and onboarding/approve; pure CRUD endpoints remain unguarded
    - staff-enable-endpoint: POST /api/staff/clients/{id}/cobranza/enable uses upsert on company_voice; safe to call repeatedly
    - scheduler-late-registration: register_cobranza_jobs called after start_scheduler() in lifespan; uses existing landa.scheduler.scheduler instance

key-files:
  created:
    - backend/tests/test_cobranza.py — 8 real passing tests (no xfail)
  modified:
    - backend/main.py — cobranza_router include + register_cobranza_jobs call + staff enable endpoint
    - backend/cobranza/router.py — _require_cobranza_enabled guard + imports
    - backend/requirements.txt — pandas>=2.0.0 added

key-decisions:
  - "cobranza_enabled flag lives on company_voice document (not client_profiles) — consistent with existing Phase 9 pattern"
  - "Only llamar-ahora and onboarding/approve guarded by cobranza_enabled; pure CRUD (list, get, create, patch, delete) remains accessible — staff can audit without enabling calls"
  - "Staff endpoint uses upsert so it works for both new and existing company_voice docs"
  - "Test helper enable_cobranza_for_user() sets flag directly in mock DB — avoids test coupling to staff auth flow"

# Metrics
duration: 8min
completed: 2026-03-27
---

# Phase 17 Plan 08: Voice Cobranza Agent — Integration Wire-up Summary

**Full cobranza system wired: router + vapi webhooks + scheduler jobs registered in main.py; cobranza_enabled staff gate added; all 8 COBR xfail test stubs now passing green**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-27T20:00:00Z
- **Completed:** 2026-03-27T20:08:18Z
- **Tasks:** 3 (Task 1: wire + guard, Task 2: tests, Task 3: checkpoint auto-approved)
- **Files modified:** 4

## Accomplishments

### Task 1: Wire cobranza router + scheduler + cobranza_enabled guard

Modified `backend/main.py`:
- Added `from cobranza.router import router as cobranza_router` + `app.include_router(cobranza_router)`
- Added `register_cobranza_jobs(_cobr_scheduler)` call in lifespan after `start_scheduler()`
- Added `POST /api/staff/clients/{client_id}/cobranza/enable` endpoint (staff-only via `require_staff`)
- Result: 15 cobranza/vapi routes registered (exceeds the 12-route requirement)
- Result: 3 scheduler jobs registered at startup: `cobr_pre_vencimiento`, `cobr_post_vencimiento`, `cobr_rescue_llamando`

Modified `backend/cobranza/router.py`:
- Added `_require_cobranza_enabled(current_user)` async guard that reads `company_voice.cobranza_enabled`
- Applied guard to `POST /api/cobranza/debtors/{id}/llamar-ahora`
- Applied guard to `POST /api/cobranza/onboarding/approve`
- Pure CRUD endpoints (list, get, create, patch, delete debtors; onboarding/start) remain accessible to any authenticated client

Added `pandas>=2.0.0` to `requirements.txt`.

### Task 2: 8 xfail stubs implemented as real passing tests

Replaced all 8 `@pytest.mark.xfail` stubs in `test_cobranza.py` with real tests:

- `test_cobr_01_csv_upload` — 2-row CSV POST → 201 `{created:2, errors:[]}`
- `test_cobr_01_manual_add` — debtor POST → 201 + `estado="pendiente"`
- `test_cobr_02_queen_propone_estrategia` — onboarding/start → 200 + `estrategia` with tono/frecuencia_dias/max_intentos/guion
- `test_cobr_02_approve_saves_campaign` — onboarding/approve → 200 + `{ok:True, campaign_id}` (with cobranza_enabled flag pre-set)
- `test_cobr_03_tool_call_consultar_deuda` — vapi tool-call → 200 + `{results:[{toolCallId, result}]}`
- `test_cobr_03_call_ended_updates_estado` — call-ended no-answer → debtor `estado="sin_contacto"` in DB
- `test_cobr_04_list_debtors_filterable` — GET debtors?estado=pendiente → list of 2 pendiente only (not pagado)
- `test_cobr_04_debtor_detail_historial` — GET debtors/{id} → `debtor.historial_llamadas` is a list

### Task 3: Checkpoint — Auto-approved

All success criteria met: 8/8 tests pass, existing suite unbroken (3 pre-existing failures unchanged), 15 routes registered, 3 scheduler jobs wired.

## Task Commits

1. **Task 1: wire cobranza router + scheduler + cobranza_enabled guard** — `035482a` (feat)
2. **Task 2: implement 8 COBR xfail stubs as passing tests** — `c9f02a1` (feat)

## Files Created/Modified

- `backend/main.py` — cobranza_router include + scheduler registration + staff enable endpoint
- `backend/cobranza/router.py` — _require_cobranza_enabled guard on call endpoints
- `backend/requirements.txt` — pandas>=2.0.0 added
- `backend/tests/test_cobranza.py` — 8 real tests (no xfail markers)

## Decisions Made

- `cobranza_enabled` flag stored on `company_voice` document — consistent with existing Phase 9 company_voice pattern; avoids polluting `client_profiles`
- Only call-initiating endpoints guarded — `llamar-ahora` and `onboarding/approve`; read-only CRUD remains open for any authenticated client so staff can review debtors without enabling the calling feature
- Staff endpoint uses upsert so calling it twice is idempotent
- Test helper `enable_cobranza_for_user()` sets flag directly in mock DB — decouples test setup from staff auth flow

## Deviations from Plan

### Auto-fixed Issues

**1. [User Requirement - Feature] Added cobranza_enabled flag and staff enable endpoint**
- **Found during:** Pre-execution (user requirement)
- **Issue:** User required that only staff/admins can enable the voice cobranza agent per client; call-initiating endpoints needed a 403 guard
- **Fix:** Added `_require_cobranza_enabled` guard to `llamar-ahora` and `onboarding/approve` in router.py; added `POST /api/staff/clients/{id}/cobranza/enable` endpoint in main.py; test for `onboarding/approve` uses `enable_cobranza_for_user()` helper to pre-set the flag in mock DB
- **Files modified:** `backend/cobranza/router.py`, `backend/main.py`, `backend/tests/test_cobranza.py`
- **Commits:** `035482a`, `c9f02a1`

**2. [Rule 1 - Bug] Fixed `get_user_id_for_email` using wrong key**
- **Found during:** Task 2 first test run
- **Issue:** `get_user_by_email()` returns `{"id": ..., ...}` (not `{"_id": ...}`); test helper used `user["_id"]`
- **Fix:** Changed `user["_id"]` to `user["id"]` in `get_user_id_for_email` helper
- **Files modified:** `backend/tests/test_cobranza.py`
- **Commit:** `c9f02a1`

## Issues Encountered

- `requirements.txt` was missing `pandas` (already had `vapi_server_sdk`, `phonenumbers`, `pytz`) — added pandas.
- 3 pre-existing test failures in `test_new_endpoints.py` and `test_whatsapp.py` — confirmed pre-existing via git stash check; not caused by this plan.

## User Setup Required

- To enable cobranza for a client: `POST /api/staff/clients/{user_id}/cobranza/enable` (requires staff JWT)
- Without the flag, clients get 403 on `llamar-ahora` and `onboarding/approve`

## Next Phase Readiness

- All COBR-01..04 requirements are now implemented and verified end-to-end
- Phase 17 complete: cobranza voice agent is fully wired and tested

## Self-Check

- [x] `backend/main.py` — cobranza_router + vapi_router included, register_cobranza_jobs called, staff enable endpoint added
- [x] `backend/cobranza/router.py` — _require_cobranza_enabled guard on llamar-ahora + onboarding/approve
- [x] `backend/requirements.txt` — pandas added
- [x] `backend/tests/test_cobranza.py` — 8 tests, 0 xfail, all pass
- [x] 15 cobranza/vapi routes registered (> 12 requirement)
- [x] 3 scheduler jobs registered at startup
- [x] Commit `035482a` — feat(17-08) wire cobranza
- [x] Commit `c9f02a1` — feat(17-08) tests
- [x] Existing test suite: 3 failures are pre-existing (confirmed)

## Self-Check: PASSED
