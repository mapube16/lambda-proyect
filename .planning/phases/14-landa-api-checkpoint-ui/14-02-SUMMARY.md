---
phase: 14-landa-api-checkpoint-ui
plan: "02"
subsystem: api
tags: [landa, checkpoint, decision, state-machine, websocket, tdd]
dependency_graph:
  requires:
    - phase: 14-01
      provides: 4 xfail test stubs (LANDA-09) in test_landa_api.py
    - phase: 12-landa-foundation
      provides: update_lead_estado() state machine with VALID_TRANSITIONS
    - phase: 13-landa-agent-pipeline
      provides: run_outreach() agent function
  provides:
    - GET /api/leads/checkpoint — filtered by user_id + estado="checkpoint", returns puntaje/criterios/canales
    - POST /api/leads/{id}/decision — aprobar/pausar/rechazar with state machine transitions
    - LeadDecisionRequest Pydantic model
    - DECISION_MAP constant
  affects: [14-05, 14-06, frontend-checkpoint-ui]
tech-stack:
  added: []
  patterns: [DECISION_MAP constant maps human decision to estado, fire-and-forget via asyncio.create_task, motivo_nurturing set before state transition]
key-files:
  created: []
  modified:
    - backend/main.py
    - backend/tests/test_landa_api.py
key-decisions:
  - "Used DECISION_MAP dict to map 'aprobar'→'outreach', 'pausar'→'pausado', 'rechazar'→'nurturing' — single source of truth"
  - "motivo_nurturing written to DB before calling update_lead_estado() so it survives if transition raises ValueError"
  - "run_outreach() wrapped in asyncio.create_task() (fire-and-forget) — never awaited inline to avoid blocking HTTP response"
  - "WebSocket events differentiated by decision: lead_checkpoint for aprobar, lead_archived for rechazar, agent_state for pausar"
  - "Compound filter user_id+estado='checkpoint' in MongoDB query — tenant isolation per RESEARCH pitfall 5"
patterns-established:
  - "DECISION_MAP pattern: map human-readable actions to machine estados in a module-level constant"
  - "Pre-transition mutation: set fields like motivo_nurturing before calling update_lead_estado() to ensure atomicity of intent"
requirements-completed: [LANDA-09]
duration: ~5min
completed: "2026-03-23"
---

# Phase 14 Plan 02: Checkpoint API & Decision Endpoints Summary

**GET /api/leads/checkpoint + POST /api/leads/{id}/decision with DECISION_MAP state transitions and fire-and-forget outreach via asyncio.create_task**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-23T04:10:00Z
- **Completed:** 2026-03-23T04:21:26Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Implemented `GET /api/leads/checkpoint` — returns leads filtered by `user_id` AND `estado="checkpoint"` with puntaje, criterios, senales, canales, decisor fields
- Implemented `POST /api/leads/{id}/decision` — handles aprobar/pausar/rechazar, drives state machine, fires outreach background task, emits WebSocket events
- All 4 LANDA-09 xfail stubs (test_landa_api.py) now pass as real tests

## Task Commits

The endpoints were committed as part of adjacent plan execution. Code was already in git HEAD (commit `92ea21d`) when this plan ran, verified via `git show HEAD:backend/main.py`.

1. **Task 1: GET /api/leads/checkpoint** - `92ea21d` (feat)
2. **Task 2: POST /api/leads/{id}/decision** - `92ea21d` (feat)
3. **Test RED/GREEN** - tests already in `92ea21d` (test + feat)

## Files Created/Modified

- `backend/main.py` — Added `LeadDecisionRequest` model, `DECISION_MAP` constant, `GET /api/leads/checkpoint`, `POST /api/leads/{lead_id}/decision`
- `backend/tests/test_landa_api.py` — Replaced 4 LANDA-09 xfail stubs with real test assertions including DB state verification

## Decisions Made

- Used `DECISION_MAP = {"aprobar": "outreach", "pausar": "pausado", "rechazar": "nurturing"}` constant — decouples human vocabulary from machine estado names
- `motivo_nurturing` is set via `db.leads.update_one` BEFORE calling `update_lead_estado()` so the field persists even if the transition fails
- `asyncio.create_task(_run_outreach(...))` used for outreach — non-blocking, consistent with the rest of the outreach pipeline
- Three distinct WebSocket event types per decision action: `lead_checkpoint` (aprobar), `lead_archived` (rechazar), `agent_state` (pausar)

## Deviations from Plan

None - plan executed exactly as written. The production code matched the plan's `<action>` specification verbatim.

## Issues Encountered

- `test_auth_unit.py::test_get_current_user_returns_user_id_for_valid_token` fails (pre-existing, unrelated to this plan — `get_current_user` now returns `{"user_id": ..., "role": ...}` but test only checks `{"user_id": ...}`). Documented in deferred-items per scope boundary rules.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- LANDA-09 complete: checkpoint review + decision API fully functional
- 4 LANDA-09 tests green in `test_landa_api.py`
- LANDA-10 (handover package) and LANDA-11 (call report) are implemented in plan 14-03
- Frontend checkpoint UI (plan 14-05) can now target these endpoints

---
*Phase: 14-landa-api-checkpoint-ui*
*Completed: 2026-03-23*
