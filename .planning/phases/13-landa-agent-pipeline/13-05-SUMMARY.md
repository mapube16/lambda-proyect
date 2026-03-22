---
phase: 13-landa-agent-pipeline
plan: "05"
subsystem: landa-nurturing
tags: [nurturing, monthly-cycle, reentrada-detection, motivo-differentiation, email, whatsapp]
dependency_graph:
  requires: [13-02, 13-03, landa-state-machine, landa-company-voice, landa-sector-profiles]
  provides: [nurturing-agent-13]
  affects: [phase-14-scheduler-integration]
tech_stack:
  added: []
  patterns: [module-level-imports-for-patchability, motivo-based-content-strategy, reentrada-keyword-detection]
key_files:
  created:
    - backend/landa/agents/nurturing.py
    - backend/nurturing_agent.py
  modified:
    - backend/tests/test_landa_pipeline.py
decisions:
  - "nurturing.py placed at backend/landa/agents/nurturing.py (matching test stub imports) with backend/nurturing_agent.py as re-export shim"
  - "Module-level imports for get_or_create_company_voice, generate_sector_profile, call_agent, send_email, send_whatsapp_text enable standard unittest.mock.patch targeting"
  - "send_email and send_whatsapp_text remain lazy imports inside run_nurturing for lazy resolution — linter promoted them to module level which required patch target update in tests"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 2
  files_modified: 1
---

# Phase 13 Plan 05: Nurturing Agent — Summary

**One-liner:** Monthly nurturing loop agent with 4 motivo-differentiated content strategies, keyword-based re-entry signal detection from sector_profile, and automatic estado transitions to checkpoint or archivado.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create nurturing agent | 9fdc61a | backend/landa/agents/nurturing.py, backend/nurturing_agent.py |
| 2 | Un-xfail LANDA-08 stubs | f4dfec4 | backend/tests/test_landa_pipeline.py |

## Verification Results

```
pytest tests/test_landa_pipeline.py tests/test_senders.py tests/test_landa.py -v
  tests/test_landa_pipeline.py::test_investigador_returns_canales_with_probability PASSED
  tests/test_landa_pipeline.py::test_investigador_puntaje_in_range PASSED
  tests/test_landa_pipeline.py::test_routing_below_40_sets_rejected PASSED
  tests/test_landa_pipeline.py::test_routing_40_to_69_transitions_to_nurturing PASSED
  tests/test_landa_pipeline.py::test_run_outreach_returns_true_on_success PASSED
  tests/test_landa_pipeline.py::test_run_outreach_logs_to_historial PASSED
  tests/test_landa_pipeline.py::test_run_nurturing_returns_dict_with_required_keys PASSED
  tests/test_landa_pipeline.py::test_run_nurturing_detects_reentrada_signal PASSED
  tests/test_senders.py::test_send_email_returns_true_on_success PASSED
  tests/test_senders.py::test_send_email_returns_false_when_creds_missing PASSED
  tests/test_senders.py::test_send_whatsapp_returns_true_on_success PASSED
  tests/test_senders.py::test_send_whatsapp_returns_false_when_creds_missing PASSED
  tests/test_landa.py::test_lead_estado_valid_transition PASSED
  tests/test_landa.py::test_lead_estado_invalid_transition_raises PASSED
  tests/test_landa.py::test_generate_sector_profile_returns_schema XFAIL
  tests/test_landa.py::test_generate_sector_profile_uses_cache XFAIL
  tests/test_landa.py::test_schedule_retry_creates_job PASSED
  tests/test_landa.py::test_cancel_lead_actions_removes_jobs PASSED
  tests/test_landa.py::test_build_system_prompt_replaces_all_vars PASSED
  tests/test_landa.py::test_build_system_prompt_marks_missing_vars PASSED
  18 passed, 2 xfailed in 0.56s
```

Success criteria met:
- nurturing_agent.py exists with async run_nurturing(lead_id, user_id) -> dict
- Returns {mensaje_enviado, senial_detectada, nuevo_estado}
- 4 motivo-differentiated content strategies (score_bajo, rechazado_humano, sin_respuesta, respuesta_negativa)
- Detects senales_reentrada from sector_profile in lead historial (reversed scan for latest respuesta_lead)
- Transitions to checkpoint on signal; transitions to archivado when ciclo_nurturing >= 12 with no signal
- Increments ciclo_nurturing and logs historial entry on each cycle
- All 8 LANDA-05 through LANDA-08 tests pass (0 xfailed in pipeline suite)

## Module Created

**backend/landa/agents/nurturing.py:**
- `run_nurturing(lead_id, user_id) -> dict`
- Module-level imports: `get_or_create_company_voice`, `generate_sector_profile`, `call_agent`, `send_email`, `send_whatsapp_text`
- Loads lead from DB, generates company_voice + sector_profile
- Builds differentiated prompt via `_MOTIVO_INSTRUCTIONS[motivo]`
- Calls LLM via `call_agent` at TEMP_NURTURING=0.6
- Sends via email (with subject) or whatsapp based on canal_elegido
- Logs historial entry with tipo="nurturing", ciclo, motivo, exito
- Scans reversed historial for latest "respuesta_lead" entry to detect re-entry keywords
- State transitions: signal -> checkpoint, ciclo >= 12 -> archivado, else stays nurturing
- Returns {mensaje_enviado (empty string if send failed), senial_detectada, nuevo_estado}

**backend/nurturing_agent.py:**
- Re-export shim: `from landa.agents.nurturing import run_nurturing`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Module-level imports required for test patchability**
- **Found during:** Task 2 (test execution)
- **Issue:** Plan provided code with lazy function-body imports for `get_or_create_company_voice`, `generate_sector_profile`, `call_agent`, `send_email`. These cannot be patched via `unittest.mock.patch` since they don't exist as module attributes at patch time.
- **Fix:** Linter promoted all four to module-level imports. Test patch targets updated from `landa.core.context.call_agent` / `email_sender.send_email` to `landa.agents.nurturing.call_agent` / `landa.agents.nurturing.send_email`.
- **Files modified:** backend/landa/agents/nurturing.py, backend/tests/test_landa_pipeline.py
- **Commits:** 9fdc61a, f4dfec4

**2. [Rule 3 - Blocking] Correct module location**
- **Found during:** Task 1 analysis
- **Issue:** Plan frontmatter listed `backend/nurturing_agent.py` as the artifact, but test stubs imported `from landa.agents.nurturing import run_nurturing`. These are incompatible.
- **Fix:** Created implementation at `backend/landa/agents/nurturing.py` (matching test imports); created `backend/nurturing_agent.py` as a re-export shim (satisfying plan artifact spec). Both paths work.
- **Files modified:** n/a (design decision pre-implementation)

## Self-Check: PASSED

- `backend/landa/agents/nurturing.py` exists: FOUND
- `backend/nurturing_agent.py` exists: FOUND
- Commit 9fdc61a: FOUND
- Commit f4dfec4: FOUND
- pytest 18 passed, 2 xfailed, 0 errors: VERIFIED
