---
phase: 12-landa-foundation
plan: "02"
subsystem: landa-state-machine
tags: [state-machine, mongodb, landa, wave-1]
dependency_graph:
  requires: [LANDA-01-stub]
  provides: [LANDA-01-impl, landa-package, landa-indexes]
  affects: [backend/landa/state_machine.py, backend/database.py, backend/tests/test_landa.py]
tech_stack:
  added: []
  patterns: [8-state-machine, hardcoded-transitions, motor-async, mongomock-motor-tests]
key_files:
  created:
    - backend/landa/__init__.py
    - backend/landa/state_machine.py
  modified:
    - backend/database.py
    - backend/tests/test_landa.py
decisions:
  - "VALID_TRANSITIONS is a hardcoded dict[str, set[str]] — not DB-driven — per Documento B Sección 5.5"
  - "update_lead_estado validates both lead existence (404-like) and transition legality before writing"
  - "archivado maps to empty set() making it a terminal state by construction"
metrics:
  duration: "~8 min"
  completed_date: "2026-03-22"
  tasks_completed: 2
  files_created: 2
  files_modified: 2
---

# Phase 12 Plan 02: Landa Foundation — State Machine Summary

**One-liner:** 8-state lead lifecycle state machine in `backend/landa/state_machine.py` with hardcoded VALID_TRANSITIONS map, plus 6 MongoDB indexes and 13 Landa fields added to database.py.

## What Was Built

### backend/landa/__init__.py
Empty package init — makes `landa` importable from the `backend/` working directory.

### backend/landa/state_machine.py

- `VALID_TRANSITIONS: dict[str, set[str]]` — hardcoded per Documento B Sección 5.5; 8 states, 10 valid edges
- `ALL_ESTADOS: frozenset[str]` — derived from VALID_TRANSITIONS keys for O(1) validation
- `async update_lead_estado(lead_id, user_id, new_estado) -> dict` — validates estado name, fetches lead (raises if missing), checks transition legality, writes `$set {estado, estado_updated_at}`, returns updated doc with `_id` as str

State graph:
```
investigando → checkpoint → outreach → handover → nurturing → checkpoint (loop)
investigando → nurturing                                     → archivado (terminal)
checkpoint   → pausado → outreach
outreach     → congelado → outreach (loop)
```

### backend/database.py — init_db() additions

6 new indexes under `# ── Landa Foundation (Phase 12) indexes ──`:
- `leads.estado` — filter by lifecycle state
- `leads.(user_id, estado)` — per-user state queries
- `sector_profiles.(sector, pais_region)` — LANDA-02 cache lookup
- `scheduled_actions.fecha_programada` — time-based job polling
- `scheduled_actions.(estado, fecha_programada)` — compound job status+time filter
- `scheduled_actions.lead_id` — cancel all jobs for a lead

### backend/database.py — save_lead() additions

13 new optional Landa fields (all default to None or []):
`estado`, `decisor`, `canales`, `canal_elegido`, `puntaje`, `criterios`, `senales_intencion`, `recomendacion_agente`, `motivo_nurturing`, `intento_actual`, `fecha_entrada_nurturing`, `ciclo_nurturing`, `historial_conversacion`

### backend/tests/test_landa.py — LANDA-01 stubs un-xfailed

| Test | Result |
|------|--------|
| `test_lead_estado_valid_transition` | PASSED (was xfail) |
| `test_lead_estado_invalid_transition_raises` | PASSED (was xfail) |
| LANDA-02 through LANDA-04 stubs | xfailed (unchanged) |

pytest result: **2 passed, 6 xfailed, 0 errors**

## Verification

```
pytest tests/test_landa.py -k "estado" -v
======================== 2 passed, 6 deselected, 1 warning in 0.15s ==================

pytest tests/test_landa.py -v
=================== 2 passed, 6 xfailed, 1 warning in 1.16s ===================

python -c "import ast; ast.parse(open('database.py').read()); print('syntax OK')"
syntax OK
```

## Deviations from Plan

None — plan executed exactly as written.

## Commits

| Hash | Message |
|------|---------|
| f29eb68 | feat(12-02): add backend/landa package with 8-state lead state machine |
| ba5421c | feat(12-02): extend database.py with Landa Phase 12 indexes and save_lead fields |
| 6d63f39 | test(12-02): un-xfail LANDA-01 stubs — estado tests now pass |

## Self-Check: PASSED

- [x] `backend/landa/__init__.py` exists
- [x] `backend/landa/state_machine.py` exists
- [x] `database.py` syntax OK
- [x] `tests/test_landa.py` — 2 passed, 6 xfailed
- [x] commit f29eb68 exists
- [x] commit ba5421c exists
- [x] commit 6d63f39 exists
