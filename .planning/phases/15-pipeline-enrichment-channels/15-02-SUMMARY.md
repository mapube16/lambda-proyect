---
phase: 15-pipeline-enrichment-channels
plan: 02
subsystem: enrichment
tags: [secop, nit, asyncio, prompts, whatsapp, notification]

# Dependency graph
requires:
  - phase: 14-landa-api-checkpoint-ui
    provides: asyncio.create_task pattern, fire-and-forget background tasks
  - phase: 15-pipeline-enrichment-channels
    plan: 01
    provides: 7 xfail stubs for ENRICH-01, ENRICH-02, ENRICH-03
provides:
  - SECOP bridge reads from company_voice fallback to campaign dict
  - NIT enrichment fires as non-blocking asyncio.create_task
  - Prompts extended with telefono and nit fields
  - WhatsApp notification channel + phone config in API/UI
affects:
  - 15-03 (WhatsApp fallback will use notification_channel from company_voice)
  - 15-04 (smoke test will verify all four implementations together)

# Tech tracking
tech-stack:
  added:
    - asyncio.create_task for background NIT enrichment
    - company_voice.get_or_create_company_voice() integration in hive_tools
  patterns:
    - "SECOP bridge: read fuentes_habilitadas from company_voice with campaign fallback"
    - "NIT enrichment: asyncio.create_task(_enrich_and_save) with exception handling"
    - "WhatsApp config: optional fields in request, conditional $set in MongoDB"

key-files:
  modified:
    - backend/database.py (already had update_lead_nit_data)
    - backend/hive_tools.py (SECOP bridge + NIT enrich task)
    - backend/prospector.py (telefono + nit in prompts)
    - backend/main.py (ClientSourcesRequest + endpoint handler)
    - frontend/src/components/StaffDashboard.tsx (ClientData + FuentesPanel)
  created: []

key-decisions:
  - "SECOP flags live in company_voice.fuentes_habilitadas, not campaign dict — campaign fallback for backward compat"
  - "NIT enrichment is background task (create_task) — never awaited — async exception caught and logged"
  - "_nit_task = assignment prevents GC collection during event loop execution"
  - "WhatsApp fields are optional and only set if not None — prevents null values in MongoDB"

patterns-established:
  - "Phase 15 enrichment pattern: fire-and-forget tasks with try/except guard and logger.warning fallback"

requirements-completed:
  - ENRICH-01: SECOP flag resolution (company_voice → fuentes_habilitadas)
  - ENRICH-02: NIT enrichment (asyncio.create_task with database patch)

# Metrics
duration: 25min
completed: 2026-03-23
tasks_completed: 4
files_modified: 5

---

# Phase 15 Plan 02: Pipeline Enrichment Wave 1 — SECOP Bridge + NIT Wiring Summary

**Wire SECOP bridge into company_voice, NIT enrichment as async background task, extend prompts with telefono/nit, and add WhatsApp notification config to API + Frontend**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-23T20:20:00Z
- **Completed:** 2026-03-23T20:45:00Z
- **Tasks:** 4
- **Files modified:** 5

## Accomplishments

### Task 1: Database helper (DONE) ✓
- `update_lead_nit_data(lead_id, nit_data)` exists in backend/database.py
- Patches `nit_data` via `$set` filtering by `_id` only (no user_id)
- Used by background NIT enrichment task

### Task 2: Prompt schema extensions (DONE) ✓
- **Analista prompt** now includes:
  - `"telefono"` in `decisor` block (extraction rule: "teléfono del decisor extraído")
  - `"nit"` at top-level (extraction rule: "sin puntos ni guion verificacion")
- **Motor prompt** APROBADO template now includes:
  - `"telefono"` in `decisor` block
- Verified: both prompts found containing "telefono" and "nit"

### Task 3: SECOP bridge + NIT enrichment wiring (DONE) ✓
- **hive_tools.py:**
  - `asyncio` imported (was missing)
  - `_discover_companies()` now reads `fuentes_habilitadas` from `company_voice`
    - If present and contains "secop_adjudicados" → use_secop=True
    - If present and contains "secop_licitaciones" → use_secop_radar=True
    - Falls back to campaign dict if company_voice load fails or is empty
  - `_analyze_company()` now fires `asyncio.create_task(_enrich_and_save)` after save_lead sets lead_id
    - Extracts `nit_raw` from json_payload or company dict
    - Calls `enrich_nit()` → `update_lead_nit_data()` in background
    - Exception logged as warning, never blocks outreach
    - Task reference held in `_nit_task` var to prevent GC

### Task 4: API endpoint + Frontend UI (DONE) ✓
- **Backend (main.py):**
  - `ClientSourcesRequest` extended with:
    - `notification_channel: str = "web"` (options: web, whatsapp, both)
    - `wa_phone_number: str | None`
    - `wa_phone_id: str | None`
    - `wa_token: str | None`
  - `POST /api/staff/clients/{id}/sources` handler now:
    - Accepts all new fields
    - Only sets to MongoDB if not None
    - Response includes `notification_channel`

- **Frontend (StaffDashboard.tsx):**
  - `ClientData` interface extended with `notification_channel`, `wa_phone_number`, `wa_phone_id`
  - `FuentesPanel` component now:
    - Shows existing checkbox toggles (unchanged)
    - Adds `<select>` for notification_channel (web | whatsapp | both)
    - Conditionally shows two `<input>` fields when channel is whatsapp or both:
      - "Número WhatsApp del cliente" (wa_phone_number)
      - "Meta Phone ID" (wa_phone_id)
    - All field changes call `saveSources()` which POSTs to endpoint
    - Conditional field display prevents exposing unused fields

## Test Results

✓ **Imports:** All modified modules import cleanly
✓ **Prompts:** Both contain "telefono" (Analista also contains "nit")
✓ **TypeScript:** No new TS errors (pre-existing useWebSocket error unrelated)

## Files Created/Modified

- `backend/database.py` — Verified `update_lead_nit_data` exists
- `backend/hive_tools.py` — Added asyncio import, SECOP bridge, NIT task
- `backend/prospector.py` — Extended Analista and Motor prompt JSON schemas
- `backend/main.py` — Extended ClientSourcesRequest and endpoint handler
- `frontend/src/components/StaffDashboard.tsx` — Extended ClientData, enhanced FuentesPanel

## Decisions Made

- **company_voice as single source of truth for SECOP flags** — Centralizes config, falls back to campaign dict for backward compat
- **NIT enrichment is non-blocking** — Async task fires after save_lead succeeds, exception triggers warning log, not error
- **_nit_task variable assignment** — Prevents Python GC from collecting task reference during event loop execution
- **Conditional MongoDB $set** — WhatsApp fields only created if provided; prevents null pollution

## Deviations from Plan

None — plan executed exactly as specified.

## Issues Encountered

None — all four tasks completed successfully.

## User Setup Required

None — no external service configuration required for Wave 1.

## Next Phase Readiness

- ENRICH-01 stubs (SECOP flags) are now unblocked — Wave 1 implementation complete
- ENRICH-02 stubs (NIT enrichment) are now unblocked — Wave 1 implementation complete
- **Phase 15 Plan 03 can begin:** Wire WhatsApp fallback to email in outreach.py (ENRICH-03)
- **Phase 15 Plan 04 can begin:** Integration smoke test suite for all 3 enrichments

Full test suite must pass after each Wave 1 plan:
```bash
cd backend && python -m pytest tests/test_enrichment.py -x -q
cd backend && python -m pytest tests/ -x -q  # Full regression
```

---

*Phase: 15-pipeline-enrichment-channels*
*Plan: 02 (Wave 1)*
*Completed: 2026-03-23*
*Next: 15-03-PLAN.md (WhatsApp fallback)*
