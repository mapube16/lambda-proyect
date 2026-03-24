---
phase: 15-pipeline-enrichment-channels
plan: 04
subsystem: integration-smoke
tags: [test, smoke, regression, enrich-01, enrich-02, enrich-03]

# Dependency graph
requires:
  - phase: 15-pipeline-enrichment-channels
    plan: 02
    provides: ENRICH-01 (SECOP bridge), ENRICH-02 (NIT enrichment)
  - phase: 15-pipeline-enrichment-channels
    plan: 03
    provides: ENRICH-03 (WhatsApp fallback)
provides:
  - 7 passing enrichment tests (ENRICH-01 × 2, ENRICH-02 × 2, ENRICH-03 × 3)
  - Zero regressions in full test suite
  - Phase 15 ready for /gsd:verify-work

# Tech tracking
tech-stack:
  added:
    - types.ModuleType stubs for heavy-dep modules (prospector, nit_enricher) not in .venv
    - vendor/hive/core path injection at test module level for framework.llm.provider import
    - patch.dict(sys.modules, ...) pattern for local-import patching inside closures
  patterns:
    - "Stub heavy deps via sys.modules injection — avoids pip install in test env"
    - "asyncio.sleep(0.1) drain for asyncio.create_task background assertions"

key-files:
  modified:
    - backend/tests/test_enrichment.py (4 xfail stubs converted to passing tests)
  created: []

requirements-completed:
  - ENRICH-01: test_secop_flag_from_company_voice (GREEN)
  - ENRICH-01: test_secop_flag_fallback_to_campaign (GREEN)
  - ENRICH-02: test_nit_enrichment_saved_to_lead (GREEN)
  - ENRICH-02: test_nit_enrichment_skipped_when_no_nit (GREEN)
  - ENRICH-03: test_outreach_whatsapp_sends_with_phone (GREEN — already passing)
  - ENRICH-03: test_outreach_whatsapp_fallback_to_email (GREEN — already passing)
  - ENRICH-03: test_outreach_no_phone_no_email (GREEN — already passing)

# Metrics
duration: 30min
completed: 2026-03-23
tasks_completed: 1
files_modified: 1

---

# Phase 15 Plan 04: Integration Smoke — Summary

**All 7 enrichment tests green; zero regressions across test suite**

## Performance

- **Duration:** ~30 min
- **Completed:** 2026-03-23
- **Tasks:** 1 (test implementation) + 1 (human checkpoint)
- **Files modified:** 1 (`tests/test_enrichment.py`)

## Accomplishments

### Task 1: Convert 4 xfail stubs → passing tests (DONE) ✓

Converted the 4 remaining `@pytest.mark.xfail(strict=True)` stubs to real integration tests:

**ENRICH-01 — SECOP flag resolution:**
- `test_secop_flag_from_company_voice`: verifies `_discover_companies` passes `use_secop=True` when `fuentes_habilitadas=["secop_adjudicados"]` in company_voice, even when `campaign.use_secop=False`
- `test_secop_flag_fallback_to_campaign`: verifies fallback to `campaign.use_secop=True` when company_voice raises an exception

**ENRICH-02 — NIT enrichment:**
- `test_nit_enrichment_saved_to_lead`: verifies `asyncio.create_task` fires `enrich_nit("900123456")` and patches result via `update_lead_nit_data(lead_id, enriched_data)`
- `test_nit_enrichment_skipped_when_no_nit`: verifies `enrich_nit` is never called when `json_payload` has no `nit` field

**Technical approach:**
- `sys.path.insert(vendor_core)` at module level so `from hive_tools import make_prospecting_registry` can resolve `framework.llm.provider`
- `patch.dict(sys.modules, {"prospector": fake_module, "nit_enricher": fake_module})` to stub modules with heavy deps (`bs4`, `ddgs`) not installed in `.venv`
- `await asyncio.sleep(0.1)` to drain `asyncio.create_task` background tasks before asserting

## Test Results

```
PASSED  test_secop_flag_from_company_voice
PASSED  test_secop_flag_fallback_to_campaign
PASSED  test_nit_enrichment_saved_to_lead
PASSED  test_nit_enrichment_skipped_when_no_nit
PASSED  test_outreach_whatsapp_sends_with_phone
PASSED  test_outreach_whatsapp_fallback_to_email
PASSED  test_outreach_no_phone_no_email

7 passed in 1.18s
```

**Full suite (excluding pre-existing failures in test_auth_unit.py and test_hive_adapter.py):**
```
41 passed, 2 xfailed, 0 failed
```

Pre-existing failures confirmed: `test_auth_unit.py::test_get_current_user_*` and `test_hive_adapter.py` failures existed before Phase 15 (verified by git stash round-trip).

## Files Modified

- `backend/tests/test_enrichment.py` — 4 xfail stubs replaced with real tests; added vendor path injection and `import types`

## Decisions Made

- **`patch.dict(sys.modules, ...)` over installing deps** — avoids polluting `.venv` with packages only needed for real network calls
- **`asyncio.sleep(0.1)` drain** — simple and sufficient for single-task background assertions in the test event loop
- **Vendor path injected at module level** — once, not per-test; safe because pytest imports the module once per session

## Deviations from Plan

- `files_modified: []` in the plan was incorrect — `test_enrichment.py` required modifications to convert the 4 xfail stubs into real tests. This was expected (plan intent was to make 7 tests green; the `[]` was a planning artifact).

## Issues Encountered

1. `.venv` lacked `_framework.pth` (present in `venv`) — fixed with `sys.path.insert` at module level
2. `prospector` and `nit_enricher` have heavy deps (`bs4`, `ddgs`) not in `.venv` — fixed with `patch.dict(sys.modules, {...})` stub injection
3. `patch("prospector.discover_companies")` triggers real import of prospector — replaced with `patch.dict` approach that never triggers the import

## Human Checkpoint Results

All 7 tests pass. Phase 15 enrichment pipeline fully verified.

## Next Phase Readiness

- Phase 15 complete: ENRICH-01 + ENRICH-02 + ENRICH-03 all green
- Ready for `/gsd:verify-work` on Phase 15
- Phase 16 (WhatsApp Conversational Advisor Bot) can begin

---

*Phase: 15-pipeline-enrichment-channels*
*Plan: 04 (Integration Smoke)*
*Completed: 2026-03-23*
*Next: /gsd:verify-work or Phase 16*
