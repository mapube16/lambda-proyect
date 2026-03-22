---
phase: 13-landa-agent-pipeline
plan: "01"
subsystem: landa-tests
tags: [testing, xfail, wave-0, landa, pipeline]
dependency_graph:
  requires: []
  provides: [wave-0-stubs-13]
  affects: [13-02, 13-03, 13-04, 13-05, 13-06]
tech_stack:
  added: []
  patterns: [pytest-xfail-strict, wave-0-tdd]
key_files:
  created:
    - backend/tests/test_landa_pipeline.py
  modified: []
decisions:
  - "All 8 stubs use assert False as body with strict=True xfail so they report xfailed (not xpassed) until implementation lands"
  - "Import statements placed inside test bodies so collection succeeds even though modules do not exist yet"
metrics:
  duration: "~5 minutes"
  completed: "2026-03-22"
  tasks_completed: 1
  tasks_total: 1
  files_created: 1
  files_modified: 0
---

# Phase 13 Plan 01: Wave 0 xfail stubs for Lead Outreach & Nurturing Agents — Summary

**One-liner:** 8 strict xfail stubs covering LANDA-05 through LANDA-08 (investigador scoring, routing, outreach, nurturing) with import-inside-body pattern so pytest collects cleanly without module errors.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Write 8 xfail stubs in test_landa_pipeline.py | 368b79a | backend/tests/test_landa_pipeline.py |

## Verification Results

```
pytest tests/test_landa_pipeline.py -v
  8 xfailed, 1 warning in 0.60s

pytest tests/test_landa_pipeline.py tests/test_landa.py -v
  6 passed, 10 xfailed, 1 warning in 1.50s
```

Success criteria met:
- test_landa_pipeline.py exists with 8 stubs
- All stubs use strict=True xfail
- pytest: 8 xfailed, 0 errors, 0 passed
- No regression in test_landa.py (6 passed, 2 xfailed unchanged)

## Stubs Created

**LANDA-05 (Investigador scoring):**
- `test_investigador_returns_canales_with_probability` — canales list with canal + probabilidad fields
- `test_investigador_puntaje_in_range` — puntaje between 0 and 100

**LANDA-06 (Routing post-scoring):**
- `test_routing_below_40_sets_rejected` — puntaje < 40 → REJECTED_BY_AI, no estado transition
- `test_routing_40_to_69_transitions_to_nurturing` — puntaje 45 → estado "nurturing"

**LANDA-07 (Outreach agent):**
- `test_run_outreach_returns_true_on_success` — returns True on SMTP mock success
- `test_run_outreach_logs_to_historial` — appends {tipo: outreach, canal: email} to historial_conversacion

**LANDA-08 (Nurturing agent):**
- `test_run_nurturing_returns_dict_with_required_keys` — returns dict with mensaje_enviado, senial_detectada, nuevo_estado
- `test_run_nurturing_detects_reentrada_signal` — keyword match in historial → nuevo_estado == "checkpoint"

## Deviations from Plan

None — plan executed exactly as written.

## Self-Check: PASSED

- `backend/tests/test_landa_pipeline.py` exists: FOUND
- Commit 368b79a: FOUND
- pytest: 8 xfailed, 0 errors: VERIFIED
