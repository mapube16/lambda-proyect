---
phase: 18-softseguros-sync
plan: 03
subsystem: softseguros-sync
tags: [sync-engine, apscheduler, classifier, mongo, semaphore, soft-delete]
one-liner: "run_sync engine over /api/poliza/ (onboarding full-scan + cron/manual tail-delta), local cobrable classification, idempotent upsert, GET-verified soft-delete, sync_logs/sync_state checkpointing, and an APScheduler daily cron wired into the FastAPI lifespan"
requires:
  - 18-02
provides:
  - backend/softseguros/sync.py (run_sync, NoCredentialsError)
  - backend/softseguros/scheduler.py (setup_scheduler, run_daily_sync_for_all_users, shutdown_scheduler)
  - "debtor_crud: upsert/mark_paid/mark_deleted_by_softseguros_poliza_id, list_active_softseguros_poliza_ids"
  - "Mongo: debtors sparse unique (user_id, softseguros_poliza_id); softseguros_sync_state; softseguros_sync_logs"
  - "adapter: list_polizas(page), get_poliza(id), parse_next_page(); SoftSegurosNotFoundError"
affects:
  - backend/softseguros/adapter.py
  - backend/cobranza/debtor_crud.py
  - backend/database.py
  - backend/main.py
  - backend/tests/test_softseguros.py
tech-stack:
  added: []
  patterns:
    - "/api/pagopoliza/ is broken upstream (504) — the real model is /api/poliza/ (52K records for DPG, 10/page fixed, no server-side filters)"
    - "All cobrable filtering + classification happens LOCALLY via classifier.classify_poliza (server ignores filters)"
    - "Per-call asyncio.Semaphore(5) wraps every SOFTSEGUROS HTTP request; pages fetched concurrently, per-page upserts gathered"
    - "Idempotency by (user_id, softseguros_poliza_id) upsert query — survives mongomock's lack of sparse-unique enforcement"
    - "Phase 17 cobranza invariants (estado/intentos/historial_llamadas/vapi_call_id/escalado/max_intentos) only set via $setOnInsert — never overwritten on re-sync"
    - "Delta scan: re-fetch tail pages from ceil(last_total_count/10) onward; soft-delete sweep GET-verifies missing pólizas → mark pagado / eliminado, never hard-delete"
    - "404 from adapter raises distinct SoftSegurosNotFoundError to drive soft-delete"
    - "softseguros_sync_logs: one doc per run_sync call (status in_progress→success/failed, counters); softseguros_sync_state: 1 doc/user checkpoint"
key-files:
  created:
    - backend/softseguros/sync.py
    - backend/softseguros/scheduler.py
  modified:
    - backend/softseguros/adapter.py
    - backend/cobranza/debtor_crud.py
    - backend/database.py
    - backend/main.py
    - backend/tests/test_softseguros.py
key-decisions:
  - "Followed 18-CONTEXT.md (smoke-test-corrected) over the stale 18-03-PLAN.md: /api/poliza/ model, softseguros_poliza_id, 4 sync modes, local classification"
  - "classifier.py left untouched — classify_poliza already existed (18-02 era) with the classify_pagopoliza compat shim; SOFTSEG-05 tests already passed"
  - "Per-call semaphore (not global) created inside run_sync — matches CONTEXT; isolates concurrency per tenant/run"
  - "Upsert keyed by (user_id, softseguros_poliza_id); the sparse-unique index is defense-in-depth (mongomock doesn't enforce it, the query does)"
  - "Soft-delete on 404 sets status_softseguros='eliminado'; soft-delete on 'Pagada'/recaudado sets status_softseguros='pagado' — both is_active=false"
  - "Weekly-rescan refinement from CONTEXT left as a last_weekly_rescan_at state field placeholder only (not required to pass tests; optional per the objective)"
  - "Scheduler startup wrapped in try/except in main.py — a scheduler failure must never block app boot"
metrics:
  duration: "~25 min"
  tasks_completed: 4
  files_created: 2
  files_modified: 5
  completed: "2026-05-12"
---

# Phase 18 Plan 03: SOFTSEGUROS Sync Engine + APScheduler Summary

## Overview

The heart of Phase 18. Builds `run_sync(db, user_id, mode)` — the engine that pulls
pólizas from SOFTSEGUROS `/api/poliza/` (the `/api/pagopoliza/` endpoint the original
plan assumed turned out to be broken: 504 in the live DPG smoke test), filters the
**cobrable** ones locally (the API ignores every server-side filter), classifies each
via `classifier.classify_poliza`, and upserts the `ya_vencidos` / `proximos_a_vencer`
ones into the Mongo `debtors` collection — preserving all Phase 17 cobranza state.

Three implemented modes:
- **onboarding** — full scan of every page (slow by design; tests use a small mocked `count`). No soft-delete (no prior state). Writes `last_full_scan_at`.
- **cron_daily / manual** — delta scan: re-fetch the tail pages where new ids live + a soft-delete sweep that GET-verifies pólizas that fell out of the listing (→ mark `pagado` or `eliminado`, never hard-delete). (`pre_call_check` is Plan 18-04.)

Plus an `AsyncIOScheduler` cron job (daily at `SOFTSEGUROS_SYNC_DAILY_HOUR_UTC`:00 UTC,
default 3) that iterates every user with credentials and runs a `cron_daily` sync,
wired into the FastAPI lifespan after `init_db` and torn down on shutdown.

## Tasks Completed

| Task | Description | Files | Commit |
| ---- | ----------- | ----- | ------ |
| 1 | classifier (pre-existing `classify_poliza` + compat shim — no change needed) + adapter `list_polizas`/`get_poliza`/`parse_next_page` + `SoftSegurosNotFoundError` | `backend/softseguros/adapter.py` | (adapter) `feat(18-03): add list_polizas/get_poliza adapter methods + SoftSegurosNotFoundError` |
| 2 | `debtor_crud` SOFTSEGUROS helpers (upsert/mark_paid/mark_deleted/list_active) + sparse unique index + sync_state/sync_logs indexes | `backend/cobranza/debtor_crud.py`, `backend/database.py` | `feat(18-03): SOFTSEGUROS upsert/soft-delete helpers + sparse unique index` |
| 3 | `run_sync` orchestrator — onboarding full-scan, cron/manual delta, Semaphore(5), local cobrable filter, classify-driven upsert, soft-delete sweep, sync_logs + sync_state | `backend/softseguros/sync.py` | `feat(18-03): run_sync engine — onboarding full-scan + cron/manual delta + soft-delete` |
| 4 | `scheduler.py` (AsyncIOScheduler daily cron + run_daily_sync_for_all_users) + `main.py` lifespan wiring (startup/shutdown) | `backend/softseguros/scheduler.py`, `backend/main.py` | `feat(18-03): APScheduler daily SOFTSEGUROS sync wired into FastAPI lifespan` |
| — | flip 5 test stubs to PASS for the póliza model | `backend/tests/test_softseguros.py` | `test(18-03): flip 5 stubs to PASS for the póliza sync model (SOFTSEG-03/04/09)` |

(`apscheduler>=3.10.4` was already present in `requirements.txt` — no change.)

## Verification

```
cd backend && python -m pytest tests/test_softseguros.py -v
```
Result: **12 passed, 8 xfailed, 0 errors** (~5s). 7 prior PASS + 5 flipped this plan
(`test_softseg_03_list_polizas_paginates`, `test_softseg_03_enrich_with_cliente`,
`test_softseg_04_semaphore_limits_concurrency`, `test_softseg_09_soft_delete_on_404`,
`test_softseg_09_sync_is_idempotent`). Remaining 8 XFAIL = SOFTSEG-06/07/08/10 (Plans 18-04/18-05).

```
cd backend && python -m pytest tests/test_cobranza.py -q
```
Result: 8 failed, 0 new failures — **identical before and after this plan** (verified via `git stash`). These are pre-existing `KeyError: 'access_token'` / assertion failures in the Phase 17 auth/test setup, unrelated to Plan 18.

Scheduler boot smoke:
```
python -c "import asyncio; from softseguros.scheduler import setup_scheduler; from fastapi import FastAPI; app=FastAPI(); asyncio.run(setup_scheduler(app)); print([j.id for j in app.state.softseguros_scheduler.get_jobs()])"
→ ['softseguros_daily_sync']
```

## Deviations from Plan

The written `18-03-PLAN.md` was **stale** — it assumed `/api/pagopoliza/`, `softseguros_pagopoliza_id`, `classify_pagopoliza(fecha_pago, comisionada, today)`, and 3 sync modes. Per the objective, `18-CONTEXT.md` (updated with live smoke-test findings) was the source of truth. Concretely:

- **Endpoint:** `/api/poliza/` (not `/api/pagopoliza/` → 504). Adapter got `list_polizas(page)` / `get_poliza(id)` / `parse_next_page()`. The old `list_pagopoliza`/`get_pagopoliza` methods were left in place (still referenced by two passing SOFTSEG-01 tests that mock `/api/pagopoliza/`) but new code never calls them.
- **Idempotency key:** `softseguros_poliza_id` (the póliza `id`), not `softseguros_pagopoliza_id`. Index, helpers, and doc fields all use the póliza naming from CONTEXT.
- **No separate cliente fetch:** the póliza already embeds `cliente_*` fields (`/api/cliente/` → 401). `test_softseg_03_enrich_with_cliente` was rewritten to assert the embedded fields land on the debtor doc.
- **Classifier:** `classify_poliza(estado_cartera, fecha_fin, fecha_limite_pago, recaudado, today)` already existed (with a `classify_pagopoliza` backwards-compat shim that the SOFTSEG-05 tests still use). `classifier.py` was **not modified** — Task 1's "create classifier" was already satisfied.
- **4 sync modes** acknowledged; `pre_call_check` is out of scope here (Plan 18-04). The optional weekly-rescan refinement is left as a `last_weekly_rescan_at` placeholder field only.
- **Test fixtures:** póliza fixtures use per-id phone numbers because the Phase 17 `(user_id, telefono)` unique index is real and would otherwise collide on shared dummy phones.

No architectural (Rule 4) changes. No authentication gates.

## Decisions Made

- Followed `18-CONTEXT.md` over the stale plan (per objective).
- Per-call (not global) `asyncio.Semaphore(5)` inside `run_sync`.
- Upsert keyed by `(user_id, softseguros_poliza_id)` query; sparse-unique index is defense-in-depth (mongomock doesn't enforce it).
- Phase 17 invariants only via `$setOnInsert`; SOFTSEGUROS-owned fields always `$set`.
- 404 → `SoftSegurosNotFoundError` → soft-delete `status_softseguros='eliminado'`; paid → `status_softseguros='pagado'`; both `is_active=false`; never hard-delete.
- Scheduler startup in `main.py` wrapped in `try/except` so it can never block app boot.

## Next Steps

- **Plan 18-04** — REST routes: `configure-softseguros` (validate creds + kick off background onboarding), `sync-now` (5-min rate limit), `verify-fresh` (pre-call check, fail-open), `sync-status`, filtered `GET /api/debtors`. Flips SOFTSEG-06/07/08/10.
- **Plan 18-05** — Frontend SOFTSEGUROS setup + 2-tab debtors view; flip remaining stubs.

## Self-Check: PASSED

- FOUND: backend/softseguros/sync.py
- FOUND: backend/softseguros/scheduler.py
- FOUND: backend/softseguros/adapter.py (list_polizas/get_poliza/parse_next_page + SoftSegurosNotFoundError)
- FOUND: backend/cobranza/debtor_crud.py (upsert/mark_paid/mark_deleted/list_active helpers)
- FOUND: backend/database.py (sparse unique index + sync_state/sync_logs indexes)
- FOUND: backend/main.py (lifespan setup/shutdown of softseguros scheduler)
- pytest verified: tests/test_softseguros.py → 12 passed, 8 xfailed
- pytest verified: tests/test_cobranza.py → no regression (8 pre-existing failures, identical with/without this plan)
