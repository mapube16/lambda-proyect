---
phase: 16-whatsapp-conversational-advisor-bot
plan: "02"
subsystem: backend-notifications
tags: [twilio, whatsapp, notify_user, webhook, fastapi, tdd]

# Dependency graph
requires:
  - phase: 16-01
    provides: 14 xfail stubs + twilio in requirements.txt
  - landa/company_voice.py: get_or_create_company_voice for notification_channel lookup
provides:
  - notify_user() unified router in main.py (web/whatsapp/both channels)
  - POST /api/whatsapp/incoming webhook endpoint in main.py
  - send_whatsapp_text() Twilio REST helper in main.py
  - _format_wa_notification() event formatter in main.py
affects:
  - 16-03 (wa_handler.process_inbound() already implemented, webhook wires it in)
  - All lead lifecycle events now dual-channel capable via notify_user()

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "notify_user() as unified notification router — reads notification_channel from company_voice, routes web/WA/both"
    - "Deferred import inside function body (import wa_handler) — avoids ImportError when module not yet present"
    - "asyncio.create_task() for fire-and-forget webhook processing — TwiML response never blocked"

key-files:
  created: []
  modified:
    - backend/main.py
    - backend/tests/test_whatsapp.py

key-decisions:
  - "send_whatsapp_text() placed in main.py (not wa_handler.py) — needed at module level for notify_user() to call without circular imports"
  - "Only 3 lead lifecycle events replaced: lead_checkpoint, lead_archived, lead_handover — agent_state UI signals left as direct manager.send_to_user()"
  - "wa_handler import deferred inside whatsapp_incoming() function — allows Plan 02 endpoint to exist before Plan 03 creates wa_handler"

# Metrics
duration: ~4min
completed: 2026-03-24
---

# Phase 16 Plan 02: notify_user() + Webhook Endpoint Summary

**notify_user() unified router + POST /api/whatsapp/incoming webhook added to main.py — 3 lead lifecycle events now dual-channel (web/WA/both), 5 tests green (3 notify_user + 2 routing)**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-03-24T02:58:43Z
- **Completed:** 2026-03-24T03:02:46Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added `send_whatsapp_text()` Twilio REST helper to `main.py` — uses httpx AsyncClient, non-fatal (logs on failure)
- Added `_format_wa_notification()` formatter — converts lead event dicts to WhatsApp-friendly text with emojis
- Added `notify_user()` unified router — reads `notification_channel` from `company_voice`, routes: web→WS, whatsapp→WA, both→WS+WA, missing→defaults to web
- Added `from landa.company_voice import get_or_create_company_voice` import to main.py
- Replaced 3 direct `manager.send_to_user()` calls with `notify_user()`: lead_checkpoint (aprobar), lead_archived (rechazar), lead_handover (handover_tomar)
- Left 2 agent_state UI signal calls untouched (investigador/idle at L1796, outreach/idle at L1989)
- Added `POST /api/whatsapp/incoming` webhook endpoint — strips `whatsapp:` prefix, validates Twilio signature, fires asyncio.create_task() for process_inbound
- Promoted 5 xfail stubs to real passing tests: 3 notify_user routing tests + 2 webhook routing tests

## Task Commits

1. **Task 1: Add notify_user() + replace 3 send_to_user() calls** - `f10fd5d`
2. **Task 2: Add POST /api/whatsapp/incoming webhook endpoint** - `3d0ce04`

## Files Created/Modified

- `backend/main.py` — +183 lines (notify_user helpers + webhook endpoint), -10 lines (3 send_to_user replacements)
- `backend/tests/test_whatsapp.py` — promoted 5 xfail stubs to real assertions

## Decisions Made

- `send_whatsapp_text()` placed in `main.py` rather than `wa_handler.py` — required by notify_user() at module initialization scope; putting it in wa_handler would require a module-level import that doesn't exist yet in Plan 02
- Only lead lifecycle events replaced with `notify_user()`: `lead_checkpoint`, `lead_archived`, `lead_handover` — per plan's explicit DO NOT touch list (agent_state signals are UI-only)
- `import wa_handler` deferred inside function body to avoid ImportError before Plan 03 creates the module (Plan 03 was already run in a previous session, so wa_handler.py exists, but the pattern remains correct for safety)

## Deviations from Plan

### Auto-observed (not bugs)

Previous sessions had already run Plan 16-03 (wa_sessions CRUD + wa_handler.py stub). This meant:
- `wa_handler.py` already existed on disk with `validate_twilio_signature`, `get_profile`, `process_inbound`
- `test_whatsapp.py` already had WA-02 session tests as real assertions (not xfail stubs)
- `test_webhook_returns_empty_twiml` was already a real test

None of this blocked Plan 02 execution. The notify_user and routing tests were still xfail stubs and proceeded through the normal TDD RED→GREEN cycle.

## Issues Encountered

None.

## Verification Results

```
pytest -k "notify_user or routing" -v → 5 passed
pytest tests/test_whatsapp.py -v → 8 passed, 6 xfailed, 0 failed
python -c "import main; print('OK')" → OK
grep send_to_user main.py (non-def/callback) → only comment reference remains
```

## Next Phase Readiness

- Plan 16-03 (wa_handler.py full session + voice note) already complete from prior session
- Plan 16-04 (LLM tool calling) can proceed: `process_inbound()` stub in wa_handler.py calls `_call_llm_with_tools()` which needs implementing
- notify_user() is now the single notification entry point for all lead lifecycle events

---
*Phase: 16-whatsapp-conversational-advisor-bot*
*Completed: 2026-03-24*
