---
phase: 13-landa-agent-pipeline
plan: "06"
subsystem: landa-pipeline-wiring
tags: [approve-endpoint, reject-endpoint, outreach-wiring, nurturing-wiring, scheduler-dispatch]
dependency_graph:
  requires: [13-04, 13-05, landa-state-machine, landa-scheduler]
  provides: [approve-fires-outreach, reject-transitions-nurturing, scheduler-real-dispatch]
  affects: [full-pipeline-integration]
tech_stack:
  added: []
  patterns: [fire-and-forget-background-task, deferred-import-inside-dispatcher, fallback-user-id-from-lead]
key_files:
  created: []
  modified:
    - backend/main.py
    - backend/landa/scheduler.py
decisions:
  - "approve_lead fetches leads unconditionally (before api_key check) so both learning embed and outreach task share the same result"
  - "reject_lead uses inline 'from bson import ObjectId as _ObjectId' to avoid polluting module namespace; get_db added to file-level import"
  - "_dispatch_scheduled_action reads canal and intento from both top-level action fields and nested contexto dict for backward compatibility with Phase 12 documents"
  - "user_id fallback: if not stored in scheduled_actions doc, resolved by querying the lead document at dispatch time — avoids changing schedule_retry/schedule_nurturing signatures"
metrics:
  duration: "~8 minutes"
  completed: "2026-03-22"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 2
---

# Phase 13 Plan 06: Pipeline Wiring Summary

**One-liner:** Wired approve/reject HITL endpoints to fire run_outreach/transition-to-nurturing, and replaced scheduler _noop_stub with real _dispatch_scheduled_action dispatching to both agents.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Wire outreach and nurturing into approve/reject endpoints | 2d9f4fe | backend/main.py |
| 2 | Replace _noop_stub with _dispatch_scheduled_action in scheduler | 5d81046 | backend/landa/scheduler.py |

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
  18 passed, 2 xfailed in 0.78s
```

Syntax check:
```
all syntax OK
```

Success criteria met:
- approve_lead creates run_outreach background task with canal_elegido from lead document
- reject_lead transitions lead estado from checkpoint to nurturing with motivo_nurturing=rechazado_humano
- scheduler._noop_stub replaced by _dispatch_scheduled_action with real run_outreach/run_nurturing dispatch
- All 18 tests pass, 2 existing xfails unchanged (Phase 12 sector profile stubs)
- Both main.py and landa/scheduler.py parse cleanly

## Changes Made

**backend/main.py — approve_lead:**
- Added `get_db` to file-level database imports
- Moved `leads = await get_leads_by_user(...)` above the `if api_key:` block — shared by both embed and outreach tasks
- Added run_outreach background task after learning embed: `asyncio.create_task(run_outreach(lead_id, user_id, canal, intento=1))`

**backend/main.py — reject_lead:**
- After storing rejection for learning, queries lead doc directly via `db.leads.find_one`
- If lead is in checkpoint estado: sets `motivo_nurturing="rechazado_humano"`, calls `update_lead_estado(lead_id, user_id, "nurturing")`
- ValueError from state machine caught and suppressed gracefully

**backend/landa/scheduler.py — _dispatch_scheduled_action:**
- Replaces `_noop_stub` entirely (function renamed)
- Reads action document from MongoDB to get lead_id, user_id, canal, intento
- Falls back to querying lead doc for user_id if not stored in action (Phase 12 backward compat)
- Reads canal/intento from both top-level and nested contexto fields
- tipo=reintento: imports and awaits `run_outreach(lead_id, user_id, canal, intento=intento)`
- tipo=nurturing: imports and awaits `run_nurturing(lead_id, user_id)`
- Marks estado="ejecutado" on success; estado="error" with error string on exception
- All 3 `add_job` calls in _bootstrap_pending_jobs, schedule_retry, schedule_nurturing updated to use `_dispatch_scheduled_action`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing] Added get_db to file-level import**
- **Found during:** Task 1
- **Issue:** reject_lead needed `get_db()` to query the lead document directly. `get_db` was not in main.py's file-level database import statement.
- **Fix:** Added `get_db` to the `from database import (...)` block.
- **Files modified:** backend/main.py
- **Commit:** 2d9f4fe

**2. [Rule 1 - Bug] canal/intento read from both top-level and contexto in scheduled_actions**
- **Found during:** Task 2 (reviewing Phase 12 document schema)
- **Issue:** Phase 12 schedule_retry stored canal and intento inside a nested `contexto` dict, not at the top level. The plan's dispatch code used `action.get("canal")` which would return None for existing Phase 12 documents.
- **Fix:** `canal = action.get("canal") or action.get("contexto", {}).get("canal", "email")` with same pattern for intento.
- **Files modified:** backend/landa/scheduler.py
- **Commit:** 5d81046

## Self-Check: PASSED

- `backend/main.py` contains `run_outreach`: FOUND
- `backend/landa/scheduler.py` contains `_dispatch_scheduled_action`: FOUND
- `backend/landa/scheduler.py` contains `run_outreach` and `run_nurturing`: FOUND
- No remaining `_noop_stub` references in scheduler.py: CONFIRMED
- Commit 2d9f4fe: FOUND
- Commit 5d81046: FOUND
- pytest 18 passed, 2 xfailed, 0 errors: VERIFIED
