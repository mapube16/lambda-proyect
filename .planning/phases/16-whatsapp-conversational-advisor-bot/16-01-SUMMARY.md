---
phase: 16-whatsapp-conversational-advisor-bot
plan: "01"
subsystem: testing
tags: [twilio, whatsapp, pytest, xfail, tdd]

# Dependency graph
requires:
  - phase: 15-pipeline-enrichment-channels
    provides: nit_enricher and secop_radar modules referenced in WA-04 stubs
provides:
  - twilio>=9.0.0 in requirements.txt ready for wa_handler.py import
  - 14 xfail stubs in test_whatsapp.py covering WA-01 through WA-04 contracts
affects:
  - 16-02 (webhook + routing implementation must pass notify_user and routing tests)
  - 16-03 (wa_handler session CRUD must pass session and webhook tests)
  - 16-04 (LLM tool calling must pass tool_call and voice_note tests)
  - 16-05 (asesor_interno tools must pass asesor tests)

# Tech tracking
tech-stack:
  added: [twilio>=9.0.0]
  patterns:
    - "xfail stub pattern with strict=False — stubs report xfail not error, non-blocking for CI"
    - "reset_db autouse fixture in test file mirrors conftest.py — per-test MongoDB isolation without conftest dependency"
    - "async_client fixture uses lazy from main import app inside fixture body to avoid collection-time import errors"

key-files:
  created:
    - backend/tests/test_whatsapp.py
  modified:
    - backend/requirements.txt

key-decisions:
  - "strict=False on all xfail markers — stubs show as xfail not xpass/fail, ensuring CI never blocks on unimplemented features"
  - "reset_db autouse fixture duplicated in test_whatsapp.py (not imported from conftest.py) — self-contained file reduces cross-file coupling"
  - "async_client fixture uses lazy import inside body to avoid app-import errors during test collection when wa_handler not yet created"

patterns-established:
  - "Wave 0 xfail scaffold: create all stubs first, subsequent plans remove xfail markers as they implement"
  - "Keyword naming discipline: test names contain exact keywords matching VALIDATION.md -k filters"

requirements-completed: [WA-01, WA-02, WA-03, WA-04]

# Metrics
duration: 5min
completed: 2026-03-23
---

# Phase 16 Plan 01: WhatsApp TDD Foundation Summary

**14 xfail stubs covering WA-01..WA-04 contract (notify_user routing, webhook, wa_sessions CRUD, LLM tool calling, voice notes, asesor_interno) plus twilio>=9.0.0 in requirements.txt**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-23T04:54:03Z
- **Completed:** 2026-03-23T04:59:00Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments
- Added `twilio>=9.0.0` to `backend/requirements.txt` — Twilio SDK available for wa_handler.py import in plan 16-02
- Created `backend/tests/test_whatsapp.py` with 14 xfail stubs across 4 requirements (WA-01 through WA-04)
- All 14 stubs collect and report as xfail — no import errors, no collection failures
- All 7 keyword filters from VALIDATION.md (`notify_user`, `routing`, `session`, `webhook`, `tool_call`, `voice_note`, `asesor`) match at least one test each

## Task Commits

Each task was committed atomically:

1. **Task 1: Add twilio dependency and create xfail test stubs** - `8d64d06` (test)

**Plan metadata:** _(pending final commit)_

## Files Created/Modified
- `backend/requirements.txt` - Appended `twilio>=9.0.0` after apscheduler line
- `backend/tests/test_whatsapp.py` - 14 xfail stubs for WA-01..WA-04 with reset_db autouse fixture

## Decisions Made
- `strict=False` on all xfail markers so collection never blocks — stubs show as xfail not failures
- `reset_db` autouse fixture duplicated in file rather than imported from conftest.py for self-contained isolation
- Lazy `from main import app` inside `async_client` fixture body prevents app-import errors during collection before wa_handler exists

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 16-02 can begin: webhook route `/api/whatsapp/incoming`, `notify_user()` routing, and `wa_handler.py` skeleton must turn the `routing`, `notify_user`, `webhook` xfails green
- Twilio package available in requirements.txt for immediate use
- All test contracts (function signatures, return types, behaviors) documented in xfail docstrings

---
*Phase: 16-whatsapp-conversational-advisor-bot*
*Completed: 2026-03-23*
