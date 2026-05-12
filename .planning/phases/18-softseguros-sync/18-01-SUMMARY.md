---
phase: 18-softseguros-sync
plan: 01
subsystem: softseguros-sync
tags: [test-scaffold, nyquist, xfail, softseguros]
one-liner: "Nyquist-compliant xfail test scaffold — 20 stubs across SOFTSEG-01..10 importable before backend/softseguros/ exists"
requires: []
provides:
  - backend/tests/test_softseguros.py
affects:
  - backend/tests/
tech-stack:
  added: []
  patterns:
    - "pytest xfail(strict=False) Wave-0 scaffold"
    - "Lazy import inside async_client fixture (mirrors test_cobranza.py)"
    - "Self-contained reset_db autouse fixture per file"
key-files:
  created:
    - backend/tests/test_softseguros.py
  modified: []
key-decisions:
  - "strict=False on all xfail markers — CI never blocks on unimplemented SOFTSEG features"
  - "reset_db autouse fixture duplicated in test_softseguros.py (not imported from conftest) — self-contained per-test Mongo isolation"
  - "Lazy `from main import app` inside async_client fixture body — avoids ImportError at collection time before backend/softseguros/ exists"
  - "raise NotImplementedError stub body (consistent with Phases 16/17) — semantically accurate for unimplemented endpoints"
metrics:
  duration: "~3 min"
  tasks_completed: 1
  files_created: 1
  files_modified: 0
  completed: "2026-05-12"
---

# Phase 18 Plan 01: Test Scaffold (SOFTSEG-01..10 xfail stubs) Summary

## Overview

Nyquist Wave-1 scaffold for Phase 18 (SOFTSEGUROS Deudores Sync). Created `backend/tests/test_softseguros.py` with 20 xfail test stubs — 2 per requirement covering SOFTSEG-01 through SOFTSEG-10. Tests collect cleanly and report XFAILED today; they flip to PASS as implementation lands in subsequent plans (18-02 onwards).

## Tasks Completed

| Task | Description | Files | Commit |
| ---- | ----------- | ----- | ------ |
| 1 | Write 20 xfail stubs for SOFTSEG-01..10 | backend/tests/test_softseguros.py | c08f185 |

## Verification

```
cd backend && python -m pytest tests/test_softseguros.py -v --tb=short
```

Result: **20 collected, 20 xfailed, 0 errors, 0 failures, exit code 0** (1.28s).

All 20 stub names align with PLAN.md Task 1 Action section:

- SOFTSEG-01: `test_softseg_01_authenticate_post`, `test_softseg_01_header_uses_token_not_bearer`
- SOFTSEG-02: `test_softseg_02_save_credentials_encrypts`, `test_softseg_02_get_credentials_decrypts`
- SOFTSEG-03: `test_softseg_03_list_pagopoliza_paginates`, `test_softseg_03_enrich_with_cliente`
- SOFTSEG-04: `test_softseg_04_semaphore_limits_concurrency`, `test_softseg_04_retry_on_429_with_backoff`
- SOFTSEG-05: `test_softseg_05_classify_ya_vencidos`, `test_softseg_05_classify_proximos_a_vencer`
- SOFTSEG-06: `test_softseg_06_configure_triggers_onboarding`, `test_softseg_06_sync_now_rate_limit`
- SOFTSEG-07: `test_softseg_07_verify_fresh_already_paid`, `test_softseg_07_verify_fresh_fail_open`
- SOFTSEG-08: `test_softseg_08_list_filtered_by_status`, `test_softseg_08_tenant_isolation`
- SOFTSEG-09: `test_softseg_09_soft_delete_on_404`, `test_softseg_09_sync_is_idempotent`
- SOFTSEG-10: `test_softseg_10_sync_status_endpoint`, `test_softseg_10_configure_never_returns_password`

## Deviations from Plan

None — plan executed exactly as written.

## Decisions Made

- `strict=False` on all xfail markers — consistent with Phases 16/17 conventions; CI never blocks on unimplemented features.
- `reset_db` autouse fixture duplicated locally (not imported from conftest) — self-contained per-test Mongo isolation.
- Lazy `from main import app` inside `async_client` body — avoids collection-time ImportError before backend/softseguros/ package exists.
- `raise NotImplementedError(...)` for stub bodies — semantically accurate (vs `assert False`).

## Next Steps

Plan 18-02 onwards will land implementation modules (`backend/softseguros/adapter.py`, `credentials.py`, `classifier.py`, `sync.py`, `verify.py`) and REST routes; each implemented requirement flips its 2 stubs from XFAIL to PASS.

## Self-Check: PASSED

- FOUND: backend/tests/test_softseguros.py
- FOUND: commit c08f185
- pytest output verified: 20 xfailed, exit 0
