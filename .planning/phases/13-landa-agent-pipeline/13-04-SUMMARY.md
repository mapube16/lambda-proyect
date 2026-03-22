---
phase: 13-landa-agent-pipeline
plan: "04"
subsystem: landa-outreach-agent
tags: [outreach, email, whatsapp, gpt4o, company-voice, sector-profile, historial, scheduler, tdd]
dependency_graph:
  requires: [13-02, 13-03, 12-03, 12-04]
  provides: [LANDA-07, outreach-agent]
  affects: [13-05, 13-06]
tech_stack:
  added: []
  patterns: [module-level-imports-for-testability, tdd-red-green, outreach-retry-scheduling, historial-conversacion-logging]
key_files:
  created:
    - backend/landa/agents/outreach.py
    - backend/outreach_agent.py
  modified:
    - backend/tests/test_landa_pipeline.py
    - backend/landa/agents/nurturing.py
decisions:
  - "outreach.py placed in landa/agents/ (not backend root) to match test stub import path landa.agents.outreach; backend/outreach_agent.py is a re-export shim for main.py invocation"
  - "module-level imports in outreach.py and nurturing.py enable patch() targets for unit tests — lazy imports inside function body would require patching the source module instead"
  - "LANDA-08 nurturing tests also fixed (Rule 1 auto-fix): external tool pre-created nurturing.py and un-xfailed LANDA-08 stubs; patch targets were broken because nurturing.py used lazy imports"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 2
---

# Phase 13 Plan 04: Outreach Agent — Summary

**One-liner:** async run_outreach() generates GPT-4o messages with company_voice tone and sector_profile context, sends via email/whatsapp, appends to historial_conversacion, schedules 7-day retries, and transitions to nurturing after 3 failed attempts.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Write failing tests for LANDA-07 outreach agent | 921c38a | backend/tests/test_landa_pipeline.py |
| 1 (GREEN) | Create outreach_agent.py and landa/agents/outreach.py | ebd8931 | backend/landa/agents/outreach.py, backend/outreach_agent.py, backend/landa/agents/nurturing.py |
| 2 | Un-xfail LANDA-07 stubs (done inline with RED commit) | 921c38a | backend/tests/test_landa_pipeline.py |

## Verification Results

```
python -m pytest tests/test_landa_pipeline.py -k "outreach" -v 2>&1 | tail -15
  2 passed, 6 deselected, 1 warning in 0.11s

python -m pytest tests/test_landa_pipeline.py tests/test_senders.py tests/test_landa.py -v
  18 passed, 2 xfailed, 1 warning in 11.50s
```

Success criteria met:
- outreach_agent.py exists with async run_outreach(lead_id, user_id, canal, intento=1) -> bool: YES (via landa/agents/outreach.py + shim)
- Sends via email_sender or whatsapp_sender based on canal parameter: YES
- Appends to historial_conversacion in MongoDB: YES
- Schedules retry after successful send when intento < 3: YES (schedule_retry(lead_id, canal, days=7))
- Transitions to nurturing after 3 failed attempts: YES (update_lead_estado → "nurturing", motivo="sin_respuesta")
- LANDA-07 tests pass: YES (2 passed)
- No regression: YES (18 passed, 2 xfailed from Phase 12 unchanged)

## Implementation Details

### landa/agents/outreach.py — run_outreach()

1. Fetches lead from MongoDB with `ObjectId(lead_id)` + `user_id` filter
2. Loads `get_or_create_company_voice(user_id)` for brand tone and sender config
3. Loads `generate_sector_profile(sector, pais_region, "mediana")` for decisor_primario and ganchos
4. Builds system prompt via `build_system_prompt(OUTREACH_SYSTEM_TEMPLATE, {...})` with 8 variables
5. Calls `call_agent(system_prompt, user_message, TEMP_OUTREACH=0.7)` to generate message
6. Routes to `send_email()` or `send_whatsapp_text()` based on canal_elegido
7. Appends `{tipo: "outreach", canal, intento, mensaje, exito, timestamp}` to historial_conversacion
8. Sets `intento_actual = intento` on the lead document
9. If sent and intento < 3: calls `schedule_retry(lead_id, canal, days=7)`
10. If not sent and intento >= 3: sets `motivo_nurturing="sin_respuesta"`, calls `update_lead_estado(→ "nurturing")`

### backend/outreach_agent.py — shim

Re-exports `run_outreach` from `landa.agents.outreach`. Provides the top-level import path expected by main.py.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrong import location: outreach.py in landa/agents/ not backend root**

- **Found during:** Task 1 (RED phase)
- **Issue:** Plan's `files_modified` listed `backend/outreach_agent.py`, but the xfail stubs imported `from landa.agents.outreach import run_outreach`. Creating the file at `backend/outreach_agent.py` would break the test imports.
- **Fix:** Created canonical implementation at `backend/landa/agents/outreach.py` and `backend/outreach_agent.py` as a 3-line re-export shim. Both paths work.
- **Files modified:** backend/landa/agents/outreach.py (created), backend/outreach_agent.py (created shim)
- **Commit:** ebd8931

**2. [Rule 1 - Bug] nurturing.py lazy imports broke LANDA-08 test patch targets**

- **Found during:** Task 2 (GREEN phase run)
- **Issue:** An external tool (editor autocomplete) pre-created `landa/agents/nurturing.py` and un-xfailed the LANDA-08 test stubs. The nurturing.py used lazy imports inside `run_nurturing()`, so patching `landa.agents.nurturing.get_or_create_company_voice` raised `AttributeError: module has no attribute`.
- **Fix:** Moved `get_or_create_company_voice`, `generate_sector_profile`, `call_agent`, `build_system_prompt`, `TEMP_NURTURING`, `send_email`, `send_whatsapp_text` to module-level imports in nurturing.py. Removed duplicate lazy imports from function body.
- **Files modified:** backend/landa/agents/nurturing.py
- **Commit:** ebd8931

## Self-Check: PASSED

- `backend/landa/agents/outreach.py` exists: FOUND
- `backend/outreach_agent.py` exists: FOUND
- `backend/landa/agents/nurturing.py` modified (module-level imports): FOUND
- Commit 921c38a (RED): FOUND
- Commit ebd8931 (GREEN + nurturing fix): FOUND
- pytest 2 passed (LANDA-07): VERIFIED
- pytest 18 passed total, 2 xfailed (no regression): VERIFIED
