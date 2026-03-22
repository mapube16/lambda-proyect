---
phase: 12-landa-foundation
plan: "01"
subsystem: landa-tests
tags: [tdd, xfail, landa, wave-0]
dependency_graph:
  requires: []
  provides: [LANDA-01-stub, LANDA-02-stub, LANDA-03-stub, LANDA-04-stub]
  affects: [backend/tests/test_landa.py]
tech_stack:
  added: []
  patterns: [xfail-strict, async-pytest, wave-0-scaffold]
key_files:
  created:
    - backend/tests/test_landa.py
  modified: []
decisions:
  - "8 stubs (2 per requirement) chosen over 4 to document both happy-path and error-path contracts from the start"
  - "motor upgraded 3.3.2 → 3.7.1 (Rule 3 auto-fix: pymongo 4.16 incompatibility blocked conftest)"
  - "python-multipart installed (Rule 3 auto-fix: missing FastAPI form-data dep blocked conftest)"
metrics:
  duration: "~5 min"
  completed_date: "2026-03-22"
  tasks_completed: 1
  files_created: 1
---

# Phase 12 Plan 01: Landa Foundation — Wave 0 xfail Stubs Summary

**One-liner:** 8 async xfail stubs with strict=True documenting the observable contracts for LANDA-01 (state machine), LANDA-02 (sector profiles), LANDA-03 (scheduler), and LANDA-04 (prompt template builder).

## What Was Built

`backend/tests/test_landa.py` — 8 xfail async test stubs, two per LANDA requirement:

| Requirement | Test 1 | Test 2 |
|-------------|--------|--------|
| LANDA-01 | `test_lead_estado_valid_transition` | `test_lead_estado_invalid_transition_raises` |
| LANDA-02 | `test_generate_sector_profile_returns_schema` | `test_generate_sector_profile_uses_cache` |
| LANDA-03 | `test_schedule_retry_creates_job` | `test_cancel_lead_actions_removes_jobs` |
| LANDA-04 | `test_build_system_prompt_replaces_all_vars` | `test_build_system_prompt_marks_missing_vars` |

pytest result: **8 xfailed, 0 errors, 0 failures** — Nyquist compliance satisfied.

## Verification

```
pytest tests/test_landa.py -v
======================== 8 xfailed, 1 warning in 0.67s ========================
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] motor/pymongo version incompatibility**
- **Found during:** Task 1 verification
- **Issue:** motor 3.3.2 imported `_QUERY_OPTIONS` from `pymongo.cursor`, removed in pymongo 4.16.0
- **Fix:** Upgraded motor 3.3.2 → 3.7.1 (latest, supports pymongo 4.x)
- **Files modified:** .venv (dependency only)
- **Commit:** (dependency install, not a source file change)

**2. [Rule 3 - Blocking] Missing python-multipart dependency**
- **Found during:** Task 1 verification (after motor fix)
- **Issue:** FastAPI's file upload route in main.py requires python-multipart; conftest imports main.app at collection time
- **Fix:** Installed python-multipart 0.0.22
- **Files modified:** .venv (dependency only)
- **Commit:** (dependency install, not a source file change)

## Commits

| Hash | Message |
|------|---------|
| 13d393e | test(12-01): add Wave 0 xfail stubs for LANDA-01 through LANDA-04 |

## Self-Check: PASSED

- [x] `backend/tests/test_landa.py` exists
- [x] commit 13d393e exists
- [x] pytest reports 8 xfailed, 0 errors
