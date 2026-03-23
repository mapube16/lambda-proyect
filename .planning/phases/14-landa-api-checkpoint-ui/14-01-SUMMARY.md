---
phase: 14-landa-api-checkpoint-ui
plan: "01"
subsystem: backend/tests
tags: [tdd, xfail, landa-api, checkpoint, handover, call-report]
dependency_graph:
  requires: []
  provides: [test-contracts-landa-09, test-contracts-landa-10, test-contracts-landa-11]
  affects: [backend/tests/test_landa_api.py]
tech_stack:
  added: []
  patterns: [xfail-stub, import-inside-body, asyncio-auto-mode]
key_files:
  created:
    - backend/tests/test_landa_api.py
  modified: []
decisions:
  - "Used raise NotImplementedError as stub body (consistent with plan spec) rather than assert False used in test_landa.py — both work for xfail strict=True"
  - "Added @pytest.mark.asyncio decorator on each stub even though asyncio_mode=auto covers it — matches plan pattern exactly and makes intent explicit"
metrics:
  duration: ~3 min
  completed: "2026-03-22"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 14 Plan 01: Lead Lifecycle API xfail Scaffold Summary

**One-liner:** 8 strict xfail test stubs establishing TDD contracts for LANDA-09 checkpoint/decision API, LANDA-10 handover package, and LANDA-11 call report endpoints.

## What Was Built

Created `backend/tests/test_landa_api.py` with 8 `pytest.mark.xfail(strict=True)` stubs. Each stub:
- Uses the import-inside-body pattern so collection succeeds even when the production module is absent
- References the exact production path (`from main import app`) that Wave 1 will implement against
- Uses `raise NotImplementedError` as the body so the test reliably fails until implementation exists

## Verification

```
collected 8 items
8 xfailed, 1 warning in 0.62s
```

All 8 tests collected, all xfailed, 0 errors, 0 passes.

## Stub Inventory

| # | Test Name | Requirement | Endpoint |
|---|-----------|-------------|----------|
| 1 | test_checkpoint_returns_leads_with_canales | LANDA-09 | GET /api/leads/checkpoint |
| 2 | test_decision_aprobar_transitions_to_outreach | LANDA-09 | POST /api/leads/{id}/decision |
| 3 | test_decision_rechazar_transitions_to_nurturing | LANDA-09 | POST /api/leads/{id}/decision |
| 4 | test_decision_pausar_transitions_to_pausado | LANDA-09 | POST /api/leads/{id}/decision |
| 5 | test_handover_get_returns_package | LANDA-10 | GET /api/leads/{id}/handover |
| 6 | test_handover_tomar_cancels_actions | LANDA-10 | POST /api/leads/{id}/handover/tomar |
| 7 | test_reporte_mal_transitions_nurturing | LANDA-11 | POST /api/leads/{id}/reporte-llamada |
| 8 | test_reporte_nopude_ocupado_schedules_retry | LANDA-11 | POST /api/leads/{id}/reporte-llamada |

## Deviations from Plan

None - plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| 34e92d5 | test(14-01): add 8 xfail stubs for LANDA-09, LANDA-10, LANDA-11 |

## Self-Check: PASSED

- [x] `backend/tests/test_landa_api.py` exists
- [x] pytest shows 8 xfailed, 0 errors
- [x] Commit 34e92d5 exists
