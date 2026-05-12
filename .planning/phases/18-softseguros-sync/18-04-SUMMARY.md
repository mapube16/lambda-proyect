---
phase: 18-softseguros-sync
plan: 04
subsystem: softseguros-sync
tags: [rest-api, fastapi, multi-tenant, rate-limit, pre-call-check, fail-open]
one-liner: "REST router /api/debtors (configure-softseguros with real-auth validation + background onboarding, tenant-scoped paginated list, sync-status/sync-logs, 5-min rate-limited sync-now, single-debtor 404-on-cross-user) plus verify_poliza_fresh — the fail-open pre-call freshness check Phase 17 consumes"
requires:
  - 18-02
  - 18-03
provides:
  - "backend/softseguros/verify.py (verify_poliza_fresh + VerifyNotFoundError/VerifyNoCredentialsError; verify_pagopoliza_fresh alias)"
  - "backend/routes/debtors.py (FastAPI router, prefix /api/debtors)"
  - "backend/routes/__init__.py"
  - "main.py: app.include_router(debtors_router)"
affects:
  - backend/main.py
  - backend/tests/test_softseguros.py
tech-stack:
  added: []
  patterns:
    - "Stale 18-04-PLAN.md (pagopoliza / softseguros_pagopoliza_id / comisionada+fecha_recibo_comision) superseded by 18-CONTEXT.md: /api/poliza/ model, softseguros_poliza_id, estado_cartera/recaudado/classify_poliza"
    - "verify_poliza_fresh branches: already_paid (paid OR no longer cobrable→ mark pagado+inactive) / not_found (404→ mark eliminado+inactive) / outdated (fecha_fin|total|estado_poliza_nombre changed→ upsert + last_verified) / ok (last_verified only)"
    - "Fail-open: httpx.TimeoutException / SoftSegurosRateLimitError / SoftSegurosServerError / any unexpected → should_call=true + warning='verification_unavailable', NO local mutation, sync_log status='partial'"
    - "All /debtors queries tenant-scoped by user_id; source='softseguros' + is_active=true filter on list; ?status validated against {proximos_a_vencer, ya_vencidos}"
    - "Literal-path routes (sync-status, sync-logs, configure-softseguros, health) declared before /{debtor_id} so they win the match"
    - "BackgroundTasks for onboarding & manual sync wrapped in _safe_run_sync (catches+logs all exceptions; lazy-imports run_sync to keep router import cheap)"
    - "sync-now rate-limit: latest mode='manual' sync_log started_at within 5 min → HTTP 429 + Retry-After header (seconds remaining); naive datetimes coerced to UTC"
    - "configure-softseguros validates by SoftSegurosAdapter.authenticate(): 401/API error → 400 'credenciales inválidas'; network error → 502"
    - "GET configure-softseguros projects only configured_at — never returns password/password_encrypted"
    - "Test JWT minted via auth.create_access_token (login only sets an httpOnly Secure cookie which httpx won't persist over http://test)"
key-files:
  created:
    - backend/softseguros/verify.py
    - backend/routes/__init__.py
    - backend/routes/debtors.py
  modified:
    - backend/main.py
    - backend/tests/test_softseguros.py
key-decisions:
  - "Followed 18-CONTEXT.md over the stale 18-04-PLAN.md (poliza model, not pagopoliza) — same call 18-03 made"
  - "verify_poliza_fresh treats 'futuro'/'pagado' classification the same as paid → not callable now → mark pagado+inactive (per corrected_model)"
  - "Reused debtor_crud.{upsert,mark_paid,mark_deleted}_by_softseguros_poliza_id and a local _poliza_to_debtor_doc copy (kept verify.py self-contained rather than importing sync.py internals)"
  - "Flipped ALL 8 remaining stubs (incl. SOFTSEG-10 sync-status & no-password) since this plan fully covers them → 21 passed / 0 xfailed; 18-05 just adds the frontend integration test"
  - "Added one extra test (test_softseg_health_no_auth) — /api/debtors/health 200 without auth"
  - "configure endpoint returns 502 (not 500) on SOFTSEGUROS network failure — distinguishes 'bad creds' (400) from 'provider down' (502)"
metrics:
  duration: "~20 min"
  tasks_completed: 2
  files_created: 3
  files_modified: 2
  completed: "2026-05-12"
---

# Phase 18 Plan 04: REST Routes + Pre-Call Verify-Fresh Summary

## Overview

Exposes Phase 18 over HTTP and delivers the pre-call hook Phase 17 will call before
every outbound voice call.

- **`backend/softseguros/verify.py`** — `verify_poliza_fresh(db, user_id, debtor_id)`:
  one `GET /api/poliza/{softseguros_poliza_id}` against SOFTSEGUROS, then the
  centralized mutation decision (4 branches + fail-open) and a `pre_call_check`
  entry in `softseguros_sync_logs`. Raises `VerifyNotFoundError` / `VerifyNoCredentialsError`
  for the route to translate to 404 / 400. Backwards-compat alias `verify_pagopoliza_fresh`.
- **`backend/routes/debtors.py`** — `APIRouter(prefix="/api/debtors")`, all endpoints
  `Depends(get_current_user)` except `/health`. Endpoints: `POST/GET /configure-softseguros`,
  `GET /` (+ `GET ""`), `GET /sync-status`, `GET /sync-logs`, `POST /sync-now`,
  `GET /{id}`, `GET /{id}/verify-fresh`, `GET /health`. Every `debtors` query is
  tenant-scoped. `sync-now` rate-limited to 1 / 5 min per user (429 + `Retry-After`).
- **`backend/main.py`** — `app.include_router(debtors_router)` after the Phase 17 routers.

## Tasks Completed

| Task | Description | Files | Commit |
| ---- | ----------- | ----- | ------ |
| 1 | `verify_poliza_fresh` — 4 branches (already_paid / not_found / outdated / ok) + fail-open + `pre_call_check` sync log | `backend/softseguros/verify.py` | 8f5b7af `feat(18-04): add verify_poliza_fresh pre-call freshness check` |
| 2 | `/api/debtors` router (8 endpoints, JWT, multi-tenant, rate-limit, real-auth validation, background sync) + `main.py` wiring + 8 stubs flipped + `/health` test | `backend/routes/__init__.py`, `backend/routes/debtors.py`, `backend/main.py`, `backend/tests/test_softseguros.py` | e13925e `feat(18-04): SOFTSEGUROS debtors REST router + verify-fresh endpoint` |

## Verification

```
cd backend && python -m pytest tests/test_softseguros.py -q
```
Result: **21 passed, 0 xfailed, 0 errors** (~12s). 12 prior PASS + 8 flipped this plan
(`test_softseg_06_configure_triggers_onboarding`, `test_softseg_06_sync_now_rate_limit`,
`test_softseg_07_verify_fresh_already_paid`, `test_softseg_07_verify_fresh_fail_open`,
`test_softseg_08_list_filtered_by_status`, `test_softseg_08_tenant_isolation`,
`test_softseg_10_sync_status_endpoint`, `test_softseg_10_configure_never_returns_password`)
+ 1 new (`test_softseg_health_no_auth`).

```
cd backend && python -m pytest tests/test_cobranza.py -q
```
Result: **8 failed** — identical to before this plan (pre-existing `KeyError: 'access_token'`
/ assertion failures in the Phase 17 auth/test setup; confirmed unrelated). No new failures.

OpenAPI / health: `GET /api/debtors/health` → `200 {"status":"ok"}` without an auth header
(covered by `test_softseg_health_no_auth`).

## Deviations from Plan

The written `18-04-PLAN.md` was **stale** in the same way 18-03's was — it assumed
`/api/pagopoliza/`, `softseguros_pagopoliza_id`, `adapter.get_pagopoliza`,
`comisionada=true OR fecha_recibo_comision`, `fecha_pago` / `valor_a_pagar`. Per the
objective, `18-CONTEXT.md` is the source of truth. Concretely the implementation uses:

- `GET /api/poliza/{softseguros_poliza_id}` via `adapter.get_poliza` (the `/api/pagopoliza/`
  endpoint is broken upstream — 504).
- The "paid" test is `estado_cartera in {Pagada,Comisionada} OR recaudado=true`, plus a
  re-classification check (`classify_poliza` → `futuro`/`pagado` ⇒ also not callable now).
- The "outdated" test is `fecha_fin | total | estado_poliza_nombre` changed (not `fecha_pago`/`valor_a_pagar`).
- Function named `verify_poliza_fresh` (alias `verify_pagopoliza_fresh` retained for the stale plan's artifact name).

Additive: `test_softseg_health_no_auth`; `configure-softseguros` returns 502 (not 500) on
provider network failure. `sync-status` also surfaces `last_sync_status` /
`debtors_marked_paid` / `debtors_marked_deleted` / `next_sync_at` beyond the plan's listed fields.

No architectural (Rule 4) changes. No authentication gates.

## Decisions Made

- Followed `18-CONTEXT.md` over the stale plan.
- `'futuro'`/`'pagado'` classification treated as "not callable now" → mark pagado+inactive.
- `verify.py` kept self-contained (local `_poliza_to_debtor_doc`) rather than importing `sync.py` internals.
- Flipped all 8 remaining stubs (this plan fully covers SOFTSEG-06/07/08/10) → 21 passed / 0 xfailed.
- Test JWT minted directly via `auth.create_access_token` (login returns the token only as an httpOnly Secure cookie).
- `configure-softseguros`: 400 on bad creds, 502 on provider unreachable.

## Self-Check: PASSED

- FOUND: backend/softseguros/verify.py
- FOUND: backend/routes/__init__.py
- FOUND: backend/routes/debtors.py
- FOUND: backend/main.py (app.include_router(debtors_router))
- FOUND: backend/tests/test_softseguros.py (8 stubs flipped + 1 new test)
- FOUND: commit 8f5b7af
- FOUND: commit e13925e
- pytest verified: tests/test_softseguros.py → 21 passed, 0 xfailed
- pytest verified: tests/test_cobranza.py → 8 pre-existing failures, no regression
