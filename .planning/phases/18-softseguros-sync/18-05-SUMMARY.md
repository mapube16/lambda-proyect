---
phase: 18-softseguros-sync
plan: 05
subsystem: softseguros-sync
tags: [frontend, react, hooks, integration-test, respx, multi-tenant]
one-liner: "Frontend SOFTSEGUROS surface — useSoftSegurosDebtors hook (configure/list/sync-status/sync-now with onboarding polling + 429 countdown), SoftSegurosSetup onboarding form, DebtorsSoftSegurosTab (2 tabs + inline DebtorCard + SyncStatusBadge) embedded as a collapsible section atop CobranzaTab — plus a full end-to-end backend integration test (configure→onboarding→list→sync-now 429→verify-fresh→tenant isolation, all SOFTSEGUROS calls mocked via respx)"
requires:
  - 18-03
  - 18-04
provides:
  - "frontend/src/hooks/useSoftSegurosDebtors.ts"
  - "frontend/src/components/SoftSegurosSetup.tsx"
  - "frontend/src/components/DebtorsSoftSegurosTab.tsx (DebtorCard + SyncStatusBadge inline)"
  - "frontend/src/components/CobranzaTab.tsx: SoftSegurosSection collapsible block"
  - "backend/tests/test_softseguros_integration.py"
affects:
  - frontend/src/components/CobranzaTab.tsx
tech-stack:
  added: []
  patterns:
    - "Single hook instance owned by DebtorsSoftSegurosTab — CobranzaTab's SoftSegurosSection only toggles expand/collapse, no second hook (avoids double polling)"
    - "Onboarding progress = poll GET /api/debtors/sync-status every 3s until is_syncing_now=false, then refetch setup + lists"
    - "429 from sync-now → error.code='rate_limited' + retryAfter; the tab tracks first-seen timestamp and renders a live 'Espera Ns' countdown on a 1s interval"
    - "Currency via Intl.NumberFormat('es-CO', COP, 0 fractions); due-date label computed from fecha_fin (fallback vencimiento) → 'Vence en N días' / 'Vencido hace N días' / 'Vence hoy'"
    - "Reuses apiFetch (credentials:'include' cookie auth) — same wrapper as the rest of the frontend; visual tokens copied from CobranzaTab (no new design system)"
    - "Integration test relies on Starlette BackgroundTasks completing within the ASGITransport request cycle (same assumption as the existing test_softseg_06 stubs) so the onboarding sync finishes before assertions"
key-files:
  created:
    - frontend/src/hooks/useSoftSegurosDebtors.ts
    - frontend/src/components/SoftSegurosSetup.tsx
    - frontend/src/components/DebtorsSoftSegurosTab.tsx
    - backend/tests/test_softseguros_integration.py
  modified:
    - frontend/src/components/CobranzaTab.tsx
key-decisions:
  - "Followed 18-CONTEXT.md / corrected_model over the stale 18-05-PLAN.md: /api/poliza/ model, softseguros_poliza_id, embedded cliente_* fields, status_softseguros, total/fecha_fin — no pagopoliza, no separate cliente fetch, no 'comisionada' field surfaced"
  - "Task 6 (turn xfail stubs green) was already fully done by 18-04 — verified 0 xfailed; no change needed to test_softseguros.py"
  - "SoftSegurosSection rendered in BOTH CobranzaTab return branches (cobranza-configured and cobranza-onboarding) so the SOFTSEGUROS surface is visible regardless of Phase-17 cobranza setup state"
  - "Hook lives in DebtorsSoftSegurosTab (not lifted to CobranzaTab) — keeps a single polling source; SoftSegurosSetup receives the hook as a prop"
  - "DebtorCard + SyncStatusBadge kept inline in DebtorsSoftSegurosTab.tsx (no separate files), per plan"
  - "Added a second small integration test (test_softseguros_configure_bad_credentials) — 401 from SOFTSEGUROS → 400, nothing persisted"
metrics:
  duration: "~25 min"
  tasks_completed: 6
  files_created: 4
  files_modified: 1
  completed: "2026-05-12"
---

# Phase 18 Plan 05: Frontend SOFTSEGUROS Tab + Integration Test Summary

## Overview

Ships the user-facing SOFTSEGUROS surface and closes Phase 18:

- **`useSoftSegurosDebtors`** — the data hook: `{ setup, debtors:{proximosAVencer,yaVencidos}, syncStatus, loading, error, configure, triggerSync, refetch }`. `configure(u,p)` POSTs `/api/debtors/configure-softseguros` (400 → `bad_credentials`, 502 → `provider_down`), then polls `GET /sync-status` every 3 s until the onboarding sync finishes and refetches everything. `triggerSync()` POSTs `/sync-now` and maps 429 → `error.code='rate_limited'` + `retryAfter`. Polling intervals are cleared on unmount.
- **`SoftSegurosSetup`** — credential form (usuario + contraseña + "Conectar SOFTSEGUROS"); "Validando…" while in-flight; inline "Credenciales inválidas" on 400; on success swaps to an indeterminate "Importando pólizas…" progress (shows running `debtors_created` when available) and fires `onComplete` once the sync settles.
- **`DebtorsSoftSegurosTab`** — if not configured renders `<SoftSegurosSetup/>`; otherwise a header (`SOFTSEGUROS` label + `SyncStatusBadge` "Última sync: hace N…" / "Sincronizando…" + "Actualizar ahora" button, disabled with a live "Espera Ns" countdown while rate-limited or while a sync runs) + two tabs **"Próximos a vencer (N)"** / **"Ya vencidos (N)"**, each listing an inline `DebtorCard` (nombre bold, tel/email links, `total` as COP, due-date + "Vence en/Vencido hace N días", `numero_poliza`/`ramo`/`estado_poliza` as faint metadata) with a per-tab empty state. Refetches on window focus.
- **`CobranzaTab`** — new `SoftSegurosSection` collapsible block (default expanded) rendered at the top of the scrollable content (and above the cobranza onboarding screen), so the SOFTSEGUROS deudores view is always reachable from the cobranza tab.
- **`backend/tests/test_softseguros_integration.py`** — end-to-end with respx mocking the upstream API: 25 mixed pólizas across 3 pages → configure → onboarding sync → 15 cobrable debtors persisted (8 `ya_vencidos` + 7 `proximos_a_vencer`, 10 paid/far skipped) → `GET /api/debtors?status=…` returns the right buckets with embedded cliente fields → two quick `/sync-now` calls → second is 429 + `Retry-After` → `verify-fresh` on a now-"Pagada" póliza → `should_call=false`, `reason='already_paid'`, doc becomes `is_active=false`/`status_softseguros='pagado'` → second JWT user sees no debtors and 404s on the first user's debtor id. Plus a `configure-bad-credentials` → 400 case. Zero network calls leak (all mocked).

## Tasks Completed

| Task | Description | Files | Commit |
| ---- | ----------- | ----- | ------ |
| 1 | `useSoftSegurosDebtors` hook (setup/list/sync-status/sync-now + 3 s onboarding polling, 429 → rate_limited) | `frontend/src/hooks/useSoftSegurosDebtors.ts` | `feat(18-05): useSoftSegurosDebtors hook (...)` |
| 2 | `SoftSegurosSetup` onboarding form + import progress UI | `frontend/src/components/SoftSegurosSetup.tsx` | `feat(18-05): SoftSegurosSetup onboarding form + import progress UI` |
| 3 | `DebtorsSoftSegurosTab` — 2-tab debtor view + sync badge + rate-limit countdown (inline `DebtorCard`) | `frontend/src/components/DebtorsSoftSegurosTab.tsx` | `feat(18-05): DebtorsSoftSegurosTab (...)` |
| 4 | Embed collapsible `SoftSegurosSection` atop `CobranzaTab` (both return branches) | `frontend/src/components/CobranzaTab.tsx` | `feat(18-05): embed collapsible SOFTSEGUROS deudores section at top of CobranzaTab` |
| 5 | End-to-end SOFTSEGUROS integration test (respx-mocked) + bad-creds case | `backend/tests/test_softseguros_integration.py` | `test(18-05): end-to-end SOFTSEGUROS integration test (...)` |
| 6 | Turn xfail stubs green — **already done by 18-04**; verified `tests/test_softseguros.py` → 21 passed / 0 xfailed, no change required | — | — |

## Verification

```
cd backend && python -m pytest tests/test_softseguros.py tests/test_softseguros_integration.py -q
```
Result: **23 passed, 0 xfailed, 0 errors** (~11 s) — 21 prior SOFTSEG tests + 2 new integration tests.

```
cd backend && python -m pytest tests/test_cobranza.py -q
```
Result: **8 failed** — identical to before this plan (pre-existing `KeyError: 'access_token'` / assertion failures in the Phase 17 test setup, confirmed unrelated). No new failures.

```
cd frontend && npx tsc --noEmit
```
Result: exit 0 — no TS errors (whole project).

## Deviations from Plan

The written `18-05-PLAN.md` was **stale** in the same way 18-03/18-04's were — it referenced `valor_a_pagar` / `fecha_pago` / `numero_factura` / `softseguros_pagopoliza_id`, a separate `/api/cliente/` fetch, and a `comisionada` field. Per the objective, `18-CONTEXT.md` (smoke-test-corrected) and the actual `backend/routes/debtors.py` surface are the source of truth. Concretely the frontend consumes:

- `GET /api/debtors/configure-softseguros` → `{configured, configured_at}`; `POST` → `{sync_started:true}` | 400 | 502.
- `GET /api/debtors?status=proximos_a_vencer|ya_vencidos&page&page_size` → `{items, page, page_size, total}`; items are the full debtor docs with embedded `cliente_*`, `numero_poliza`, `total`, `fecha_fin`, `status_softseguros`, `source`.
- `GET /api/debtors/sync-status` → `{last_sync_at, last_sync_mode, last_sync_status, debtors_created, debtors_updated, next_sync_at, is_syncing_now, …}`.
- `POST /api/debtors/sync-now` → `{sync_started:true}` | 429 + `Retry-After`.
- `GET /api/debtors/{id}` → `{debtor}` | 404; `GET /api/debtors/{id}/verify-fresh` → `{should_call, reason, …}` (frontend doesn't call verify-fresh — it's the voice agent's).

Additive: a second integration test for the bad-creds → 400 path. Task 6 reduced to a no-op (18-04 already flipped all 20 stubs + added one). No architectural (Rule 4) changes. No authentication gates.

REQUIREMENTS.md traceability NOT touched (phase verifier's job). ROADMAP.md Phases 3–8 NOT touched. The 21 existing `test_softseguros.py` tests still PASS.

## Decisions Made

- Followed `18-CONTEXT.md` + the real REST surface over the stale plan (poliza model, embedded cliente fields, status_softseguros).
- Single hook instance in `DebtorsSoftSegurosTab`; `CobranzaTab`'s `SoftSegurosSection` only handles collapse — no second polling loop.
- SOFTSEGUROS section rendered in both `CobranzaTab` return branches so it's visible whether or not Phase-17 cobranza is configured.
- `DebtorCard` / `SyncStatusBadge` kept inline (no extra component files).
- Rate-limit countdown tracked client-side from the first-seen `429` timestamp + `Retry-After`.

## Next Steps

- Phase 18 PHASE VERIFIER: confirm SOFTSEG-08 / SOFTSEG-10 observable truths and flip the REQUIREMENTS.md traceability rows.
- (Out of scope here) Phase 17 voice agent can consume `GET /api/debtors?status=ya_vencidos` for its call queue and `GET /api/debtors/{id}/verify-fresh` as its pre-call check — contract is stable.

## Self-Check: PASSED

- FOUND: frontend/src/hooks/useSoftSegurosDebtors.ts
- FOUND: frontend/src/components/SoftSegurosSetup.tsx
- FOUND: frontend/src/components/DebtorsSoftSegurosTab.tsx
- FOUND: frontend/src/components/CobranzaTab.tsx (SoftSegurosSection + DebtorsSoftSegurosTab import)
- FOUND: backend/tests/test_softseguros_integration.py
- pytest verified: tests/test_softseguros.py tests/test_softseguros_integration.py → 23 passed, 0 xfailed
- pytest verified: tests/test_cobranza.py → 8 pre-existing failures, no regression
- tsc verified: cd frontend && npx tsc --noEmit → exit 0, no errors
- commits: useSoftSegurosDebtors hook · SoftSegurosSetup · DebtorsSoftSegurosTab · embed in CobranzaTab · integration test
