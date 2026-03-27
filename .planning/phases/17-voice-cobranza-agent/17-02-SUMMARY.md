---
phase: 17-voice-cobranza-agent
plan: "02"
subsystem: api
tags: [fastapi, mongodb, motor, phonenumbers, cobranza, csv-upload, e164, tenant-isolation]

# Dependency graph
requires:
  - phase: 17-voice-cobranza-agent
    plan: "01"
    provides: xfail test scaffold — 8 stubs that verify imports resolve without error
provides:
  - cobranza/ package with debtor_crud.py, csv_parser.py, router.py
  - 9 REST endpoints for debtor CRUD under /api/cobranza
  - E164 phone normalization for Colombian numbers via phonenumbers library
  - Tenant-isolated MongoDB CRUD with debtors collection + 4 indexes
affects:
  - 17-03-PLAN (onboarding + campaign setup — shares cobranza/ package)
  - 17-04-PLAN (Vapi integration — uses debtor_crud update_debtor, get_debtor_by_id)
  - 17-05-PLAN (dashboard + reporting — uses get_debtors with estado filter)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - cobranza-router-pattern: APIRouter prefix=/api/cobranza, all endpoints Depends(get_current_user), user_id=current_user["user_id"]
    - bulk-insert-skip-duplicates: insert_many ordered=False + BulkWriteError catch — silently skips duplicate telefono per user_id
    - e164-normalization: normalize_phone() via phonenumbers.parse + is_valid_number + format_number(E164) — returns None on invalid

key-files:
  created:
    - backend/cobranza/__init__.py
    - backend/cobranza/csv_parser.py
    - backend/cobranza/debtor_crud.py
    - backend/cobranza/router.py
  modified:
    - backend/database.py

key-decisions:
  - "router.py not included in main.py yet — Plan 17-08 registers the router (as specified in plan)"
  - "reactivar endpoint guards on estado=='pausado' — prevents unintentional state resets from non-pausado states"
  - "DebtorPatch uses Optional fields; only non-None fields are included in $set — avoids nulling existing data"
  - "normalize_phone called again on PATCH /debtors/{id} telefono field — re-validates before storing, prevents invalid E164 creeping in via PATCH"

patterns-established:
  - "Cobranza CRUD pattern: all functions async, db as first arg, user_id for tenant isolation, _serialize converts ObjectId to str"
  - "CSV upload returns partial success: {created: N, errors: [...]} — invalid rows skipped with row-level error messages"

requirements-completed: [COBR-01]

# Metrics
duration: 8min
completed: 2026-03-27
---

# Phase 17 Plan 02: Voice Cobranza Agent — Debtor Ingestion Summary

**MongoDB debtor CRUD layer with E164 phone normalization, CSV bulk upload parser, and 9 REST endpoints under /api/cobranza with tenant isolation**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-27T18:10:09Z
- **Completed:** 2026-03-27T18:18:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Created `cobranza/` package with `__init__.py`, `csv_parser.py`, `debtor_crud.py`, and `router.py`
- `normalize_phone()` handles Colombian numbers in multiple formats (+57, national, with spaces) via `phonenumbers` library
- `parse_debtor_csv()` decodes utf-8-sig (Excel BOM), validates all 4 required columns, returns partial success with row-level errors
- `router.py` exposes 9 REST endpoints covering full debtor lifecycle including pagar/pausar/reactivar state transitions
- 4 MongoDB debtors indexes added to `init_db()` (estado filter, created_at sort, vapi_call_id sparse, unique telefono per user)
- All 8 xfail test stubs remain xfail (not error) — imports fully resolve

## Task Commits

Each task was committed atomically:

1. **Task 1: debtor_crud.py + csv_parser.py + database indexes** - `505c2ad` (feat)
2. **Task 2: REST endpoints for debtor CRUD** - `e264bbb` (feat)

**Plan metadata:** (docs commit follows)

## Files Created/Modified

- `backend/cobranza/__init__.py` — Package marker with comment
- `backend/cobranza/csv_parser.py` — normalize_phone() (E164 via phonenumbers), parse_debtor_csv() (utf-8-sig, DictReader, row-level validation)
- `backend/cobranza/debtor_crud.py` — async CRUD: create_debtor, bulk_create_debtors, get_debtors, get_debtor_by_id, update_debtor, delete_debtor
- `backend/cobranza/router.py` — FastAPI APIRouter prefix=/api/cobranza; 9 endpoints with DebtorCreate/DebtorPatch Pydantic models
- `backend/database.py` — 4 debtors collection indexes appended to init_db()

## Decisions Made

- `router.py` not included in `main.py` yet — Plan 17-08 registers the router (as stated in plan spec)
- `reactivar` endpoint guards on `estado == "pausado"` — prevents unintentional state resets; returns 400 with explanation if current estado is not pausado
- `DebtorPatch` builds patch dict from only non-None fields — avoids nulling existing data via partial updates
- `normalize_phone` re-called on PATCH telefono field — ensures E164 validity on every write path, not just creation

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- `cobranza/` package fully importable; all subsequent Phase 17 plans can import from it
- 17-03 (onboarding + campaign setup) can add campaign CRUD to cobranza/ and extend router
- 17-04 (Vapi integration) can import `update_debtor`, `get_debtor_by_id` directly
- 17-05 (dashboard) can call `get_debtors(db, user_id, estado=...)` for filtered reporting
- COBR-01 xfail stubs ready to be replaced with real assertions in 17-08 integration plan

---
*Phase: 17-voice-cobranza-agent*
*Completed: 2026-03-27*
