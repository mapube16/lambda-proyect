---
phase: 16-whatsapp-conversational-advisor-bot
plan: "03"
subsystem: database
tags: [twilio, whatsapp, mongodb, motor, sessions, tdd]

# Dependency graph
requires:
  - phase: 16-whatsapp-conversational-advisor-bot
    plan: "01"
    provides: xfail stubs for WA-02 session and webhook tests, twilio>=9.0.0 in requirements.txt
  - phase: 16-whatsapp-conversational-advisor-bot
    plan: "02"
    provides: POST /api/whatsapp/incoming endpoint that webhook test calls
provides:
  - database.py: get_or_create_wa_session() and update_wa_session() CRUD functions
  - database.py: TTL index on wa_sessions.updated_at (86400s) and unique index on wa_sessions.phone
  - backend/wa_handler.py: validate_twilio_signature(), get_profile(), process_inbound() skeleton
  - wa_handler.py _send_reply(): Twilio REST API reply helper with 1600-char truncation
affects:
  - 16-04 (LLM tool calling plan imports get_or_create_wa_session, update_wa_session, and process_inbound)
  - 16-05 (asesor_interno tools also depend on session CRUD and process_inbound)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "wa_sessions upsert pattern: find_one_and_update with $setOnInsert avoids concurrent duplicate creation"
    - "Sliding window via two-phase: push new turn, then trim to last 10 if len > 10 (mongomock-compatible)"
    - "validate_twilio_signature permissive fallback: returns True when TWILIO_ACCOUNT_SID/TOKEN not set — allows local dev without Twilio"
    - "get_profile lookup order: company_voice.wa_phone_number → WA_STAFF_NUMBERS env var → None (unknown)"
    - "process_inbound fire-and-forget: called via asyncio.create_task() from /api/whatsapp/incoming, never blocks TwiML"

key-files:
  created:
    - backend/wa_handler.py
  modified:
    - backend/database.py
    - backend/tests/test_whatsapp.py

key-decisions:
  - "Two-phase sliding window in update_wa_session: $push then trim if >10 — mongomock does not support $push with $slice in a single op"
  - "find_one_and_update with return_document=True for upsert: motor equivalent of ReturnDocument.AFTER, no extra import needed"
  - "validate_twilio_signature returns True when creds not set — allows all test environments to work without Twilio credentials"
  - "get_profile uses lazy import of database inside function body — avoids circular import since wa_handler is imported by main.py"
  - "process_inbound stubs _transcribe_voice_note and _call_llm_with_tools as None/placeholder — implemented in Plans 04-05"

patterns-established:
  - "wa_sessions document schema: phone, user_id, profile, history (max 10), updated_at (TTL field)"
  - "Profile types: 'cliente' (from company_voice) and 'asesor_interno' (from WA_STAFF_NUMBERS)"

requirements-completed: [WA-01, WA-02]

# Metrics
duration: 8min
completed: 2026-03-24
---

# Phase 16 Plan 03: WhatsApp Sessions CRUD and wa_handler Skeleton Summary

**wa_sessions CRUD with TTL index in database.py (upsert + 10-turn sliding window) plus wa_handler.py skeleton with Twilio signature validation, profile lookup, and process_inbound stub**

## Performance

- **Duration:** ~8 min
- **Started:** 2026-03-24T02:59:06Z
- **Completed:** 2026-03-24T03:07:00Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Added `get_or_create_wa_session()` to database.py: upsert-based creation using `$setOnInsert`, concurrent-safe, returns existing doc if phone found
- Added `update_wa_session()` to database.py: appends turn and trims history to last 10 (sliding window), updates TTL clock via `updated_at`
- Added wa_sessions TTL index (86400s) and unique phone index to `init_db()`
- Created `backend/wa_handler.py` with all three required exports: `validate_twilio_signature`, `get_profile`, `process_inbound`
- Replaced 3 xfail stubs in test_whatsapp.py with real assertions: 2 session tests + 1 webhook test — all green

## Task Commits

Each task was committed atomically:

1. **Task 1: Add wa_sessions CRUD to database.py** - `b6100fe` (feat)
2. **Task 2: Create backend/wa_handler.py skeleton** - `57d170e` (feat)

**Plan metadata:** _(pending final commit)_

## Files Created/Modified
- `backend/database.py` - Added get_or_create_wa_session(), update_wa_session(), TTL index in init_db()
- `backend/wa_handler.py` - New file: validate_twilio_signature(), get_profile(), process_inbound() + private helpers
- `backend/tests/test_whatsapp.py` - Replaced 3 xfail stubs with real assertions (session x2, webhook x1)

## Decisions Made
- Two-phase sliding window in `update_wa_session`: push first, then trim if `len > 10` — mongomock doesn't support `$push` with `$slice` in a single update op
- `find_one_and_update` with `return_document=True` for upsert session: motor equivalent of ReturnDocument.AFTER, no extra ReturnDocument import needed
- `validate_twilio_signature` returns True when TWILIO_ACCOUNT_SID/TOKEN not set — permissive fallback for local dev and test environments
- Lazy `from database import get_db` inside `get_profile()` body — avoids circular import since wa_handler is imported by main.py at module level
- `process_inbound` stubs `_transcribe_voice_note` (returns None) and `_call_llm_with_tools` (returns placeholder string) — implementations deferred to Plans 04-05

## Deviations from Plan

None — plan executed exactly as written.

Note: The `/api/whatsapp/incoming` endpoint required by `test_webhook_returns_empty_twiml` was already present in main.py from Plan 02 (which ran in parallel). No additional main.py changes were needed.

## Issues Encountered
- `test_hive_adapter.py::test_hive_adapter_is_only_seam` fails with UnicodeDecodeError when reading main.py — confirmed pre-existing issue unrelated to this plan's changes. Out of scope per deviation boundary rules.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Plan 16-04 can begin: `process_inbound()` skeleton is in place, session CRUD is working — LLM tool calling implementation can replace the `_call_llm_with_tools` stub
- Plan 16-05 can begin in parallel: asesor_interno tool dispatch can also replace `_call_llm_with_tools` stub behavior
- All 3 plan success criteria met: `pytest -k "session"` → 2 passed, `pytest -k "webhook"` → 1 passed, imports clean

---
*Phase: 16-whatsapp-conversational-advisor-bot*
*Completed: 2026-03-24*

## Self-Check: PASSED

- FOUND: backend/wa_handler.py
- FOUND: backend/database.py
- FOUND: .planning/phases/16-whatsapp-conversational-advisor-bot/16-03-SUMMARY.md
- FOUND commits: b6100fe (Task 1), 57d170e (Task 2)
- Exports verified: database.get_or_create_wa_session, database.update_wa_session, wa_handler.validate_twilio_signature, wa_handler.get_profile, wa_handler.process_inbound
