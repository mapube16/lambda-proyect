---
phase: 12-landa-foundation
plan: "04"
subsystem: landa-scheduler-context
tags: [apscheduler, scheduler, context, build_system_prompt, mongodb, landa, wave-2]
dependency_graph:
  requires: [landa.state_machine, database.get_db, scheduled_actions indexes (Phase 12-02)]
  provides: [landa.scheduler, landa.core.context, lifespan scheduler wiring]
  affects: [backend/landa/scheduler.py, backend/landa/core/context.py, backend/main.py, backend/tests/test_landa.py]
tech_stack:
  added: [apscheduler>=3.10.4 (AsyncIOScheduler + MemoryJobStore)]
  patterns: [MemoryJobStore-dispatch + Motor-async-durable-storage, defer-openai-import, bootstrap-pending-jobs-on-startup]
key_files:
  created:
    - backend/landa/scheduler.py
    - backend/landa/core/__init__.py
    - backend/landa/core/context.py
  modified:
    - backend/main.py
    - backend/requirements.txt
    - backend/tests/test_landa.py
decisions:
  - "APScheduler uses MemoryJobStore only — MongoDB jobstore requires pymongo sync which conflicts with Motor async stack; durable state lives in db.scheduled_actions via Motor"
  - "bootstrap_pending_jobs marks past-due pendiente actions as vencido on startup (Phase 13 will handle recovery)"
  - "build_system_prompt uses [inferida — KEY] marker for missing variables, not silent empty string"
  - "call_agent defers openai import to function body to avoid import-time failure when OPENAI_API_KEY is unset"
  - "LANDA-04 tests are sync (def not async def) since build_system_prompt is a pure sync function"
metrics:
  duration: "~10 min"
  completed_date: "2026-03-22"
  tasks_completed: 4
  files_created: 3
  files_modified: 3
---

# Phase 12 Plan 04: Landa Foundation — Scheduler and Context Summary

**One-liner:** APScheduler AsyncIOScheduler with Motor-backed scheduled_actions persistence, variable template builder with [inferida — KEY] fallback, and lifespan wiring — completing all LANDA-03 and LANDA-04 tests.

## What Was Built

### backend/landa/scheduler.py

- `AsyncIOScheduler` instance (MemoryJobStore) — separate from durable MongoDB storage
- `start_scheduler()` / `shutdown_scheduler()` — lifecycle functions called from lifespan
- `_bootstrap_pending_jobs()` — on startup, queries `scheduled_actions {estado: pendiente}`, re-registers future jobs with APScheduler, marks past-due as `vencido`
- `_noop_stub(action_id, tipo)` — Phase 12 placeholder; Phase 13 replaces with real agent dispatch; marks action as `ejecutado` when triggered
- `schedule_retry(lead_id, canal, days, mensaje)` — inserts reintento doc + registers APScheduler job; returns action `_id` as str
- `schedule_nurturing(lead_id, mes, motivo)` — inserts nurturing doc + registers APScheduler job; returns action `_id` as str
- `cancel_lead_actions(lead_id)` — bulk-cancels all pendiente actions for a lead in MongoDB and removes from in-memory scheduler; returns count

### backend/landa/core/__init__.py

Empty package init — makes `landa.core` importable.

### backend/landa/core/context.py

- `build_system_prompt(template, variables)` — regex replaces `[KEY]` placeholders; missing/blank keys become `[inferida — KEY]`; pattern: `[A-Z][A-Z0-9_]*`
- `call_agent(system_prompt, user_message, temperature, model)` — async OpenAI wrapper; raises `RuntimeError` if `OPENAI_API_KEY` unset; deferred import
- Temperature constants: `TEMP_INVESTIGADOR=0.2`, `TEMP_OUTREACH=0.7`, `TEMP_NURTURING=0.6`

### backend/main.py — lifespan wiring

Added import `from landa.scheduler import start_scheduler, shutdown_scheduler` and wired `await start_scheduler()` before `yield`, `shutdown_scheduler()` after `yield`.

### backend/tests/test_landa.py — LANDA-03 and LANDA-04 un-xfailed

| Test | Result |
|------|--------|
| `test_schedule_retry_creates_job` | PASSED (was xfail) |
| `test_cancel_lead_actions_removes_jobs` | PASSED (was xfail) |
| `test_build_system_prompt_replaces_all_vars` | PASSED (was xfail) |
| `test_build_system_prompt_marks_missing_vars` | PASSED (was xfail) |
| LANDA-02 stubs | xfailed (unchanged — not in scope) |

pytest result: **6 passed, 2 xfailed, 0 errors**

## Verification

```
pytest tests/test_landa.py -v
tests/test_landa.py::test_lead_estado_valid_transition PASSED
tests/test_landa.py::test_lead_estado_invalid_transition_raises PASSED
tests/test_landa.py::test_schedule_retry_creates_job PASSED
tests/test_landa.py::test_cancel_lead_actions_removes_jobs PASSED
tests/test_landa.py::test_build_system_prompt_replaces_all_vars PASSED
tests/test_landa.py::test_build_system_prompt_marks_missing_vars PASSED
=================== 6 passed, 2 xfailed, 1 warning in 1.18s ===================

python -c "import ast; ast.parse(open('main.py').read()); print('main.py OK')"
main.py OK

python -c "from landa.core.context import TEMP_INVESTIGADOR, TEMP_OUTREACH, TEMP_NURTURING; ..."
constants OK
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] apscheduler not installed in venv**
- **Found during:** Task 4 (test run)
- **Issue:** `apscheduler` was added to `requirements.txt` but not installed in the active `.venv`; conftest import of main.py failed with `ModuleNotFoundError: No module named 'apscheduler'`
- **Fix:** Ran `.venv/Scripts/pip install "apscheduler>=3.10.4"` — installed apscheduler 3.11.2
- **Files modified:** None (runtime install only)
- **Commit:** N/A (dependency install, not a code change)

## Commits

| Hash | Message |
|------|---------|
| b3dadd3 | feat(12-04): add APScheduler-backed scheduler.py with schedule_retry/nurturing/cancel |
| f4b727a | feat(12-04): add landa/core package with build_system_prompt and call_agent |
| 8b992c8 | feat(12-04): wire Landa scheduler into main.py lifespan |
| 02bcff0 | test(12-04): un-xfail LANDA-03 and LANDA-04 stubs — all 6 tests now pass |

## Self-Check: PASSED

- [x] `backend/landa/scheduler.py` — FOUND
- [x] `backend/landa/core/__init__.py` — FOUND
- [x] `backend/landa/core/context.py` — FOUND
- [x] `backend/main.py` syntax OK
- [x] temperature constants OK (0.2, 0.7, 0.6)
- [x] pytest: 6 passed, 2 xfailed, 0 errors
- [x] commit b3dadd3 — FOUND
- [x] commit f4b727a — FOUND
- [x] commit 8b992c8 — FOUND
- [x] commit 02bcff0 — FOUND
