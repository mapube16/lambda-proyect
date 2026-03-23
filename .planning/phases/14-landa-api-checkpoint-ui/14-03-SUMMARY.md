---
phase: 14-landa-api-checkpoint-ui
plan: "03"
subsystem: backend/main.py
tags: [landa-api, handover, reporte-llamada, tdd, lead-lifecycle]
dependency_graph:
  requires: [14-01, 14-02]
  provides: [LANDA-10-endpoints, LANDA-11-endpoints]
  affects: [backend/main.py, backend/tests/test_landa_api.py]
tech_stack:
  added: []
  patterns: [import-inside-body, fire-and-forget-asyncio, try-except-non-fatal, tdd-red-green]
key_files:
  created: []
  modified:
    - backend/main.py
    - backend/tests/test_landa_api.py
decisions:
  - "call_agent adapted to actual signature (system_prompt, user_message) — plan showed incorrect (prompt, system=) form; wrapped in try/except since it raises RuntimeError on missing creds rather than returning empty string"
  - "no_pude/incorrecto sets buscar_numero_alternativo=True flag without state transition (RESEARCH pitfall 4 honored)"
  - "schedule_retry(canal='notificacion_48h', days=2) for 48h handover no-report job per RESEARCH pitfall 2"
  - "handover state reachable only from outreach per VALID_TRANSITIONS; test inserts leads in outreach estado"
  - "nurturing reachable from handover per VALID_TRANSITIONS; test_reporte_mal inserts leads in handover estado"
metrics:
  duration: ~12 min
  completed: "2026-03-23"
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 14 Plan 03: Handover and Reporte-Llamada API Summary

**One-liner:** Three REST endpoints completing the LANDA-10/11 lead lifecycle surface — handover package retrieval, human takeover with scheduler cancel + 48h job, and call outcome logging with 5 sub-cases.

## What Was Built

### GET /api/leads/{lead_id}/handover

Returns a handover package containing:
- `lead`: full MongoDB document (with `_id` serialized to string)
- `hilo_conversacion`: `historial_conversacion` array from lead doc
- `calificacion_original`: `{puntaje, criterios, canales}` extracted from lead
- `sugerencia_cierre`: AI-generated 2-3 sentence closing suggestion via `call_agent` — returns `""` if `OPENAI_API_KEY` not set (non-fatal try/except)

### POST /api/leads/{lead_id}/handover/tomar

1. Calls `cancel_lead_actions(lead_id)` to cancel all pending APScheduler jobs
2. Calls `update_lead_estado(→ "handover")` — raises HTTP 400 on invalid transition
3. Calls `schedule_retry(canal="notificacion_48h", days=2)` for 48h no-report job
4. Emits `{"type": "lead_handover", "lead_id", "empresa", "canal"}` WebSocket event
5. Returns `{"status": "ok", "lead_id", "estado": "handover"}`

### POST /api/leads/{lead_id}/reporte-llamada

Handles 5 sub-cases via `resultado` + `sub_tipo`:

| resultado | sub_tipo | Action |
|-----------|----------|--------|
| `mal` | — | `update_lead_estado(→ "nurturing")` + set `motivo_nurturing` |
| `no_pude` | `ocupado`/`apagado` | `schedule_retry(days=1)` |
| `no_pude` | `incorrecto` | Set `buscar_numero_alternativo=True` flag (no state transition) |
| `no_pude` | `corto` | `schedule_retry(days=7)` |
| `bien`/`mas_o_menos` | — | `asyncio.create_task()` fire-and-forget AI interpretation |

Always emits `{"type": "agent_state", "state": "idle"}` WebSocket event and returns 200.

## Test Results

```
4 passed, 4 deselected, 1 warning in 2.07s
```

All 8 tests in `test_landa_api.py` pass (4 LANDA-09 from plan 02, 4 LANDA-10/11 from this plan).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Incorrect call_agent signature in plan action spec**
- **Found during:** Task 1 implementation
- **Issue:** Plan showed `call_agent(prompt, system="...", model="...")` but actual `landa/core/context.py` signature is `call_agent(system_prompt, user_message, temperature, model)`. Additionally, plan stated it "returns '' on missing creds" but it actually raises `RuntimeError`.
- **Fix:** Used correct positional signature `call_agent(system_prompt, user_message)` and wrapped both GET /handover call and _interpret_and_act() in try/except to suppress RuntimeError gracefully.
- **Files modified:** backend/main.py
- **Commit:** cbd680e

## Commits

| Hash | Message |
|------|---------|
| cbd680e | feat(14-03): implement GET+POST /handover and POST /reporte-llamada endpoints |

## Self-Check: PASSED

- [x] `backend/main.py` contains `reporte-llamada` endpoint (line 1805)
- [x] `backend/main.py` contains `get_handover` (line 1713) and `handover/tomar` (line 1759)
- [x] `backend/tests/test_landa_api.py` has 4 real tests replacing xfail stubs
- [x] `pytest tests/test_landa_api.py -k "handover or reporte"` → 4 passed
- [x] `pytest tests/test_landa_api.py` → 8 passed
- [x] `python -c "import main"` → no import errors
- [x] Commit cbd680e exists
