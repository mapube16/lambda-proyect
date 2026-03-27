---
phase: 17-voice-cobranza-agent
plan: "05"
subsystem: cobranza
tags: [vapi, webhooks, tool-call, call-ended, tdd, fastapi, mongodb, websocket, ley-2300]

# Dependency graph
requires:
  - phase: 17-voice-cobranza-agent
    plan: "02"
    provides: debtor_crud.py and MongoDB debtors collection with vapi_call_id index
  - phase: 17-voice-cobranza-agent
    plan: "03"
    provides: vapi_client.py with initiate_call(); call_scheduler.py for Ley 2300 compliance
provides:
  - backend/cobranza/webhooks.py with vapi_router (2 endpoints)
  - POST /api/vapi/tool-call handler dispatching consultar_deuda, registrar_promesa, escalar_a_humano
  - POST /api/vapi/call-ended handler updating debtor state, intentos, historial_llamadas, WS push
  - 11 passing TDD unit tests in test_webhooks.py
affects:
  - 17-04-PLAN (scheduler jobs that set vapi_call_id — call-ended unsets it)
  - 17-06-PLAN and beyond (dashboard reads debtor estado changes made by these handlers)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - always-200-vapi-pattern: Both Vapi endpoints wrap entire body in try/except; ALWAYS return HTTP 200
    - lazy-import-manager: "from main import manager" inside function body to avoid circular import
    - terminal-estado-guard: promesa_de_pago and escalado estados are never overwritten by endedReason mapping
    - agotado-threshold: intentos+1 >= max_intentos triggers agotado override regardless of endedReason

key-files:
  created:
    - backend/cobranza/webhooks.py
    - backend/tests/test_webhooks.py
  modified:
    - backend/main.py

key-decisions:
  - "Always HTTP 200 from both Vapi endpoints — Vapi aborts call on non-200; errors are logged and swallowed"
  - "Lazy import of manager from main inside handle_call_ended() body — prevents circular import at module load"
  - "Terminal estados (promesa_de_pago, escalado, pagado) take precedence over endedReason mapping — tool calls set state during call"
  - "agotado check uses new_intentos = current_intentos+1 >= max_intentos — fires at threshold, not over"
  - "vapi_router registered in main.py via app.include_router() before static file mount"

# Metrics
duration: 7min
completed: 2026-03-27
---

# Phase 17 Plan 05: Voice Cobranza Agent — Vapi Webhook Handlers Summary

**Vapi tool-call dispatcher and end-of-call-report processor with WebSocket debtor_update push — core of COBR-03 live call integration**

## Performance

- **Duration:** ~7 min
- **Started:** 2026-03-27T18:22:40Z
- **Completed:** 2026-03-27T18:38:20Z
- **Tasks:** 1 (TDD: RED commit + GREEN commit)
- **Files modified:** 3

## Accomplishments

- Created `backend/cobranza/webhooks.py` with `vapi_router` (2 routes):
  - `POST /api/vapi/tool-call`: dispatches 3 tools; always returns HTTP 200 even on exception
  - `POST /api/vapi/call-ended`: maps endedReason to estado; increments intentos; appends historial; pushes WS event
- `dispatch_tool()` helper handles `consultar_deuda` (returns formatted debt string), `registrar_promesa` (sets estado=promesa_de_pago), `escalar_a_humano` (sets escalado=True, estado=escalado)
- End-of-call-report logic: terminal estado guard (promesa_de_pago/escalado/pagado preserved), agotado threshold (intentos >= max_intentos), transcript truncated to 2000 chars
- Lazy import pattern for `manager` inside function body — avoids circular import with `main.py`
- Registered `vapi_router` in `main.py` with `app.include_router(_vapi_router)` before static file mount
- 11 TDD unit tests written (RED), then implementation made them all pass (GREEN)
- COBR-03 xfail stubs remain xfail — not error

## Task Commits

Each TDD phase committed atomically:

1. **Task 1 (TDD RED): Add failing tests for Vapi webhook handlers** - `ddb84b4` (test)
2. **Task 1 (TDD GREEN): Implement webhooks.py + register in main.py** - `236c40e` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/cobranza/webhooks.py` — `vapi_router` with `/api/vapi/tool-call` and `/api/vapi/call-ended`
- `backend/tests/test_webhooks.py` — 11 TDD tests, all passing
- `backend/main.py` — `app.include_router(_vapi_router)` added before static file mount

## Decisions Made

- Both Vapi endpoints always return HTTP 200 — outer try/except catches everything; Vapi aborts call on non-200 response
- Lazy import `from main import manager` inside `handle_call_ended()` function body prevents circular import at module load time
- Terminal estados (`promesa_de_pago`, `escalado`, `pagado`) are never overwritten by `endedReason` mapping — tool calls set state mid-call and take priority
- `agotado` fires when `current_intentos + 1 >= max_intentos` — at threshold (5 of 5), not over it
- `vapi_router` registered in `main.py` using `app.include_router()` before the static file mount (which must stay last)

## Deviations from Plan

None — plan executed exactly as written. All behaviors from the plan spec implemented and tested.

## Issues Encountered

None.

## User Setup Required

None — webhook endpoints are registered automatically. Vapi dashboard must be configured to point to `https://{your-domain}/api/vapi/tool-call` and `/api/vapi/call-ended` (done in 17-04 Vapi assistant config).

## Next Phase Readiness

- 17-06 and beyond: debtor `estado` fields are now updated by live Vapi calls
- COBR-03 xfail stubs in `test_cobranza.py` can be fully implemented in 17-08 integration plan
- APScheduler fallback job (from plan spec) for `llamando` debtors stuck >15 min is not yet implemented — scope for 17-06 or 17-07

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
