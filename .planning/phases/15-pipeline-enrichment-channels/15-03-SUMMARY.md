---
phase: 15-pipeline-enrichment-channels
plan: 03
subsystem: outreach
tags: [whatsapp, fallback, email, historial, asyncio]

# Dependency graph
requires:
  - phase: 15-pipeline-enrichment-channels
    plan: 02
    provides: asyncio.create_task pattern, company_voice integration
provides:
  - WhatsApp branch falls back to email when phone is absent
  - Fallback historial entry pushed to MongoDB (tipo=fallback, razon=no_phone, canal_usado=email)
  - No silent drops — every WhatsApp channel decision is logged

affects:
  - 15-04 (smoke test will verify ENRICH-03 together with ENRICH-01/02)

# Tech tracking
tech-stack:
  patterns:
    - "WA fallback: phone present → send_whatsapp_text; phone absent + email → send_email + fallback historial"
    - "logger.warning for no-phone fallback (handled); logger.error for no-phone-AND-no-email (error)"
    - "fallback historial entry keys: tipo=fallback, razon=no_phone, canal_usado=email, timestamp=ISO"

key-files:
  modified:
    - backend/landa/agents/outreach.py (WhatsApp elif block replaced)
  created: []

key-decisions:
  - "logger.warning for no-phone fallback — it is a handled case, not an error"
  - "logger.error only when BOTH phone and email are absent"
  - "Fallback historial entry pushed separately from main historial_entry (different tipo)"

requirements-completed:
  - ENRICH-03: WhatsApp fallback to email with historial recording

# Metrics
duration: 5min (implementation was already in place from previous session)
completed: 2026-03-23
tasks_completed: 1
files_modified: 1

---

# Phase 15 Plan 03: WhatsApp Fallback — Summary

**Replace silent `return False` in outreach.py's WhatsApp branch with graceful fallback to email**

## Performance

- **Duration:** ~5 min (implementation was already applied in previous context window)
- **Completed:** 2026-03-23
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

### Task 1: Replace WhatsApp branch with fallback-to-email logic (DONE) ✓

`backend/landa/agents/outreach.py` WhatsApp branch (`elif canal_elegido == "whatsapp"`) now:

- **Phone present:** calls `send_whatsapp_text(phone=phone, message=message_text)`, `sent` = return value
- **Phone absent + email present:**
  - `logger.warning(...)` — handled fallback, not an error
  - calls `send_email(to=to_email, subject=..., body=..., sender_name=..., sender_email=...)`
  - pushes `fallback_entry` to `historial_conversacion` with `tipo="fallback"`, `razon="no_phone"`, `canal_usado="email"`, `timestamp=ISO`
  - `sent` = email send return value
- **Phone absent + email absent:** `logger.error(...)`, `sent = False`, no crash

## Test Results

✓ `test_outreach_whatsapp_sends_with_phone` — PASSED
✓ `test_outreach_whatsapp_fallback_to_email` — PASSED (fallback historial verified in DB)
✓ `test_outreach_no_phone_no_email` — PASSED (returns False, neither sender called)

## Files Modified

- `backend/landa/agents/outreach.py` — WhatsApp elif block replaced with graceful fallback

## Decisions Made

- **logger.warning for no-phone + email fallback** — treated as a handled degradation, not an error condition
- **logger.error for no-phone-AND-no-email** — genuinely unrecoverable; warrants error log
- **Separate fallback historial entry** — uses `tipo="fallback"` distinct from main `tipo="outreach"` entry so audit trail clearly shows the channel switch

## Deviations from Plan

None — implementation matched plan exactly.

## Issues Encountered

None — implementation was already in place when plan was executed.

## Next Phase Readiness

- ENRICH-03 satisfied
- **Phase 15 Plan 04 can begin:** Integration smoke test suite (all 7 tests green)

---

*Phase: 15-pipeline-enrichment-channels*
*Plan: 03*
*Completed: 2026-03-23*
*Next: 15-04-PLAN.md (integration smoke test)*
