---
phase: 14-landa-api-checkpoint-ui
plan: "04"
subsystem: backend-api
tags: [staff-endpoint, company-voice, secop, fastapi]
dependency_graph:
  requires: [14-01]
  provides: [POST /api/staff/clients/{user_id}/sources]
  affects: [company_voice collection, investigador agent source config]
tech_stack:
  added: []
  patterns: [require_staff dependency, upsert=True company_voice, VALID_SOURCES set guard]
key_files:
  created: []
  modified:
    - backend/main.py
decisions:
  - "Used Depends(require_staff) consistent with all other /api/staff/* endpoints — no inline role check needed"
  - "upsert=True on db.company_voice.update_one handles both create and update without calling get_or_create_company_voice"
  - "VALID_SOURCES as module-level set — reusable and testable; 400 returned with sorted() list for deterministic error message"
metrics:
  duration: ~5 min
  completed_date: "2026-03-22"
  tasks_completed: 1
  files_modified: 1
requirements: [LANDA-12]
---

# Phase 14 Plan 04: Staff Client Sources Endpoint Summary

Staff-only POST /api/staff/clients/{user_id}/sources that upserts fuentes_habilitadas in company_voice collection, enabling per-client SECOP premium source toggling.

## What Was Built

Added `POST /api/staff/clients/{target_user_id}/sources` to `backend/main.py`:

- `ClientSourcesRequest` Pydantic model with `fuentes_habilitadas: list[str]`
- `VALID_SOURCES` module-level set: `{"google_maps", "secop_adjudicados", "secop_licitaciones"}`
- 400 error on any invalid source value (before touching DB)
- `Depends(require_staff)` guard — consistent with all other `/api/staff/` routes
- `db.company_voice.update_one({"user_id": target_user_id}, {"$set": ...}, upsert=True)` — creates or updates the document

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Implement POST /api/staff/clients/{user_id}/sources | 92ea21d | backend/main.py |

## Deviations from Plan

None — plan executed exactly as written.

## Pre-existing Issues (Out of Scope)

`tests/test_auth_unit.py::test_get_current_user_returns_user_id_for_valid_token` fails because the test asserts `{'user_id': '42'}` but `get_current_user` returns `{'role': 'client', 'user_id': '42'}`. This failure exists before and after this plan's changes (confirmed via git stash). Logged for deferred resolution.

## Self-Check: PASSED

- `backend/main.py` exists and was modified: FOUND
- Commit 92ea21d exists: FOUND
- `python -c "import ast; ast.parse(open('main.py').read())"` returned: `main.py syntax OK`
- Test suite: 15 passed, 1 pre-existing failure (unrelated to this plan)
- Pattern `company_voice.*update_one` present in main.py: FOUND (line 1599)
- Pattern `api/staff/clients` present in main.py: FOUND (line 1580)
