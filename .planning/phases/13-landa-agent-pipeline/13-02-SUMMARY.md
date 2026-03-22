---
phase: 13-landa-agent-pipeline
plan: "02"
subsystem: landa-scoring-routing
tags: [investigador, scoring, routing, sector-profile, canales, state-machine, tdd]
dependency_graph:
  requires: [13-01, 12-03, 12-04]
  provides: [LANDA-05, LANDA-06, investigador-agent, router-agent]
  affects: [13-03, 13-04, 13-05, 13-06]
tech_stack:
  added: []
  patterns: [sector-profile-enrichment, puntaje-threshold-routing, async-mocking-unittest]
key_files:
  created:
    - backend/landa/agents/__init__.py
    - backend/landa/agents/investigador.py
    - backend/landa/agents/router.py
  modified:
    - backend/hive_tools.py
    - backend/tests/test_landa_pipeline.py
decisions:
  - "use_secop_radar handled as closure-level toggle in hive_tools.py rather than parameter to discover_companies — avoids modifying prospector.py signature (out of scope)"
  - "sector_profile load failures are caught and logged with fallback strings to keep scoring non-fatal"
  - "routing ValueError (invalid transition) is caught and logged — leads already processed are not re-transitioned"
  - "TDD: RED commit (52e752c) followed by GREEN commit (704435e) — two separate commits per protocol"
metrics:
  duration: "~18 minutes"
  completed: "2026-03-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 3
  files_modified: 2
---

# Phase 13 Plan 02: Investigador Scoring Enrichment and Post-Scoring Routing — Summary

**One-liner:** Investigador agent calls generate_sector_profile, injects sector intelligence into GPT-4o scoring prompt, returns canales[] with probabilidad, and routes leads by puntaje threshold via update_lead_estado.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 (RED) | Write failing tests for LANDA-05 and LANDA-06 | 52e752c | backend/tests/test_landa_pipeline.py |
| 1 (GREEN) | Implement investigador.py, router.py, hive_tools.py | 704435e | backend/landa/agents/investigador.py, router.py, __init__.py, hive_tools.py |
| 2 | Un-xfail LANDA-05 and LANDA-06 stubs | 52e752c | backend/tests/test_landa_pipeline.py |

## Verification Results

```
python -m pytest tests/test_landa_pipeline.py -k "investigador or routing or scoring" -v
  4 passed, 4 deselected, 1 warning in 0.25s

python -m pytest tests/test_landa_pipeline.py tests/test_landa.py -v
  10 passed, 6 xfailed, 1 warning in 1.02s
```

Success criteria met:
- hive_tools.py scoring produces canales[] with probabilidad per canal: YES
- Post-scoring routing logic present and covered by tests: YES
- LANDA-05 and LANDA-06 stubs flip from xfailed to passed: YES (4 passed)
- No regression in Phase 12 tests: YES (10 passed total, 6 xfailed unchanged)

## Implementation Details

### landa/agents/investigador.py — run_investigador()

1. Calls `generate_sector_profile(sector, pais_region, tamano)` — uses 30-day cache from Phase 12
2. Injects `decisor_primario`, `senales_compra`, `ganchos` into `_SCORING_SYSTEM_TEMPLATE`
3. Calls `call_agent()` at `TEMP_INVESTIGADOR=0.2` with gpt-4o
4. Parses JSON response — normalizes puntaje to int 0-100, ensures canales has >= 1 entry
5. Persists `puntaje`, `criterios`, `senales_intencion`, `recomendacion_agente`, `canales` to lead doc
6. Calls `route_after_scoring(lead_id, user_id, puntaje)` — routing errors caught and logged

### landa/agents/router.py — route_after_scoring()

- puntaje < 40: `db.leads.update_one($set system_state=REJECTED_BY_AI)` — no estado transition
- 40 <= puntaje < 70: `$set motivo_nurturing=score_bajo` then `update_lead_estado(→ nurturing)`
- puntaje >= 70: `update_lead_estado(→ checkpoint)`
- ValueError from invalid transitions caught and logged (idempotent-safe)

### hive_tools.py — use_secop_radar toggle

Added at line ~134, immediately after the `use_secop` read:
```python
use_secop_radar = bool(campaign.get("use_secop_radar", False))
```
When True, calls `secop_radar.fetch_open_processes(sector=industria)` and merges deduplicated radar leads into the companies list. Errors are caught and logged (non-fatal).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] use_secop_radar not passed to discover_companies**

- **Found during:** Task 1 implementation
- **Issue:** The plan said to add `use_secop_radar` following the `use_secop` pattern, but `discover_companies` in prospector.py does not accept a `use_secop_radar` parameter. Passing it would cause a TypeError at runtime.
- **Fix:** `use_secop_radar` is stored as a local variable in the `_discover_companies` closure. When True, `fetch_open_processes()` is called after `discover_companies()` and results merged into the companies list. This is functionally equivalent and avoids modifying prospector.py's signature (which would be a broader change).
- **Files modified:** backend/hive_tools.py
- **Commit:** 704435e

## Self-Check: PASSED

- `backend/landa/agents/__init__.py` exists: FOUND
- `backend/landa/agents/investigador.py` exists: FOUND
- `backend/landa/agents/router.py` exists: FOUND
- Commit 52e752c (RED): FOUND
- Commit 704435e (GREEN): FOUND
- pytest 4 passed (LANDA-05/06): VERIFIED
- pytest 10 passed total, 6 xfailed (no regression): VERIFIED
