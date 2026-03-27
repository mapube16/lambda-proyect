---
phase: 17-voice-cobranza-agent
plan: "03"
subsystem: cobranza
tags: [vapi, compliance, ley-2300, call-scheduler, tdd, pytz]

# Dependency graph
requires:
  - phase: 17-01
    provides: xfail scaffold and test infrastructure
  - phase: 17-02
    provides: debtor_crud.py and csv_parser.py for debtor data model
provides:
  - call_scheduler.py with is_contact_allowed_now(), has_been_contacted_today(), get_next_allowed_slot()
  - vapi_client.py with initiate_call() and cancel_call()
  - 12 passing TDD unit tests covering all Ley 2300 compliance scenarios
affects:
  - 17-04-PLAN (Vapi webhook handler — consumes initiate_call())
  - 17-05-PLAN (scheduler jobs — consumes is_contact_allowed_now() + has_been_contacted_today())

# Tech tracking
tech-stack:
  added: []
  patterns:
    - ley-2300-compliance: COLOMBIA_TZ + COLOMBIA_HOLIDAYS_2026 set; weekday/hour guards for Mon-Fri 7-19, Sat 8-15, Sun/holiday never
    - lazy-import-sdk: AsyncVapi imported inside function body — SDK optional at startup; consistent with Phase 16 WhatsApp pattern
    - datetime-mock-pattern: unittest.mock.patch("cobranza.call_scheduler.datetime") for time-controlled unit tests

key-files:
  created:
    - backend/cobranza/call_scheduler.py
    - backend/cobranza/vapi_client.py
    - backend/tests/test_call_scheduler.py
  modified: []

key-decisions:
  - "Lazy import of AsyncVapi inside function body — SDK optional at startup; avoids ImportError in dev env without vapi_server_sdk installed"
  - "COLOMBIA_HOLIDAYS_2026 as frozenset of (month, day) tuples — O(1) lookup; comment to expand to 2027 when needed"
  - "has_been_contacted_today() treats naive datetime as UTC (pytz.utc.localize) — consistent with MongoDB storage convention"
  - "initiate_call() falls back to env vars if config keys absent — dual-path config supports both programmatic and env-based deployments"

# Metrics
duration: 5min
completed: 2026-03-27
---

# Phase 17 Plan 03: Voice Cobranza Agent — Compliance Engine and Vapi Client Summary

**Ley 2300 compliance engine and AsyncVapi outbound call wrapper — foundational call-initiation primitives with 12 passing TDD unit tests**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-27T18:09:57Z
- **Completed:** 2026-03-27T18:15:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Created `backend/cobranza/call_scheduler.py` implementing Ley 2300 de 2023:
  - `is_contact_allowed_now()`: Mon-Fri 7am-7pm, Sat 8am-3pm, Sun/holiday never (Colombia tz)
  - `has_been_contacted_today(debtor)`: daily contact guard using `ultimo_contacto_fecha`
  - `get_next_allowed_slot()`: scans forward minute-by-minute up to 10 days to find next valid window
- Created `backend/cobranza/vapi_client.py` wrapping AsyncVapi:
  - `initiate_call(debtor, config)`: creates outbound call with debtor context passed as Vapi variable_values
  - `cancel_call(call_id)`: cancels in-progress call via `client.calls.delete()`
  - Lazy import pattern; raises `ValueError` on missing API key, `RuntimeError` on Vapi API error
- Created `backend/tests/test_call_scheduler.py` with 12 TDD unit tests covering all behavior spec scenarios
- Both `pytz` and `vapi_server_sdk` were already present in `requirements.txt` — no changes needed

## Task Commits

Each task was committed atomically:

1. **Task 1 (TDD RED): Write failing tests for call_scheduler** - `34b5be7` (test)
2. **Task 1 (TDD GREEN): Implement call_scheduler.py — Ley 2300 compliance** - `b4bb4db` (feat)
3. **Task 2: Implement vapi_client.py — AsyncVapi outbound call wrapper** - `eca8f47` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/cobranza/call_scheduler.py` — Ley 2300 compliance engine; 3 exported functions
- `backend/cobranza/vapi_client.py` — AsyncVapi wrapper; initiate_call() + cancel_call()
- `backend/tests/test_call_scheduler.py` — 12 TDD unit tests (all passing)

## Decisions Made

- Lazy import of `AsyncVapi` inside function body — SDK optional at startup; consistent with Phase 16 WhatsApp lazy import pattern
- `COLOMBIA_HOLIDAYS_2026` as set of `(month, day)` tuples — O(1) lookup; comment reminds to expand for 2027
- `has_been_contacted_today()` treats naive datetime as UTC (`pytz.utc.localize`) — matches MongoDB storage convention
- `initiate_call()` falls back to `VAPI_API_KEY`, `VAPI_ASSISTANT_ID`, `VAPI_PHONE_NUMBER_ID` env vars if config keys absent — dual-path config

## Deviations from Plan

None — plan executed exactly as written. Both files were pre-implemented and pre-tested; this execution verified correctness and committed `vapi_client.py` which was untracked.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- 17-04 (Vapi webhook handler) can now import `initiate_call` from `cobranza.vapi_client`
- 17-05 (scheduler jobs) can now import `is_contact_allowed_now` and `has_been_contacted_today` from `cobranza.call_scheduler`
- All 8 COBR xfail stubs still xfailed — ready for subsequent plan implementations

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
