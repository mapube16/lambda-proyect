---
phase: 17-voice-cobranza-agent
plan: "01"
subsystem: testing
tags: [pytest, xfail, cobranza, vapi, mongomock]

# Dependency graph
requires:
  - phase: 16-whatsapp-conversational-advisor-bot
    provides: xfail stub pattern (strict=False, lazy import inside fixture body)
provides:
  - 8 xfail stubs (2 per requirement) covering COBR-01 through COBR-04
  - Nyquist-compliant test scaffold for all Phase 17 plans
affects:
  - 17-02-PLAN (debtor ingestion implementation)
  - 17-03-PLAN (onboarding + campaign setup)
  - 17-04-PLAN (Vapi integration)
  - 17-05-PLAN (dashboard + reporting)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - xfail-stub-scaffold: strict=False xfail stubs with NotImplementedError body; async_client uses lazy import inside fixture body to avoid collection-time ImportError before cobranza/ exists

key-files:
  created:
    - backend/tests/test_cobranza.py
  modified: []

key-decisions:
  - "strict=False on all xfail markers — stubs show as xfail not failures, CI never blocks on unimplemented cobranza features"
  - "reset_db autouse fixture duplicated in test_cobranza.py (not imported from conftest) — self-contained per-test MongoDB isolation, mirrors Phase 16-01 pattern"
  - "async_client uses lazy import of main.app inside fixture body to prevent collection-time ImportError before cobranza/ package exists"
  - "raise NotImplementedError used as xfail stub body — semantically accurate for unimplemented endpoints, consistent with Phase 14-01 decision"

patterns-established:
  - "Wave-0 xfail scaffold for Phase 17: 2 stubs per requirement, strict=False, lazy import, NotImplementedError body"

requirements-completed: [COBR-01, COBR-02, COBR-03, COBR-04]

# Metrics
duration: 2min
completed: 2026-03-27
---

# Phase 17 Plan 01: Voice Cobranza Agent — Test Scaffold Summary

**8 xfail stubs (2 per requirement) covering COBR-01 through COBR-04 with mongomock isolation and lazy import pattern, importable before cobranza/ package exists**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-27T17:19:48Z
- **Completed:** 2026-03-27T17:21:30Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `backend/tests/test_cobranza.py` with 8 xfail stubs covering all 4 Phase 17 requirements
- All stubs use `strict=False` so CI never blocks on unimplemented cobranza features
- Lazy import of `main.app` inside `async_client` fixture body prevents collection-time ImportError before `cobranza/` module is created
- File is importable and collects cleanly with pytest (verified: 8 xfailed, 0 errors)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write 8 xfail stubs for COBR-01 through COBR-04** - `63c4318` (test)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/tests/test_cobranza.py` — 8 xfail stubs for COBR-01 through COBR-04 with reset_db and async_client fixtures

## Decisions Made

- `strict=False` on all xfail markers — stubs show as xfail not failures; CI never blocks on unimplemented cobranza features (consistent with Phase 16-01 decision)
- `reset_db` autouse fixture duplicated in `test_cobranza.py` (not imported from conftest) — self-contained per-test MongoDB isolation
- `async_client` uses lazy import of `main.app` inside fixture body — prevents collection-time `ImportError` before `cobranza/` package exists
- `raise NotImplementedError` as stub body — semantically accurate, consistent with Phase 14-01 established pattern

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Test scaffold in place: all subsequent Phase 17 plans have pre-existing automated verify targets
- 17-02 (debtor ingestion) can now remove xfail from `test_cobr_01_*` tests as it implements COBR-01
- 17-03 (onboarding) can remove xfail from `test_cobr_02_*` as it implements COBR-02
- 17-04 (Vapi integration) can remove xfail from `test_cobr_03_*` as it implements COBR-03
- 17-05 (dashboard) can remove xfail from `test_cobr_04_*` as it implements COBR-04

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
