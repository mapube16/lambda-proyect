---
phase: 18-softseguros-sync
verified: 2026-05-12T00:00:00Z
status: passed
score: 10/10 must-haves verified
re_verification: null
gaps: []
human_verification:
  - test: "Conectar credenciales SOFTSEGUROS reales desde la UI de CobranzaTab y observar el loader de onboarding hasta que aparezcan deudores en las 2 vistas"
    expected: "El form valida, dispara onboarding en background, el badge pasa a 'sincronizando' y luego a 'completado'; las pestañas próximos/vencidos se pueblan"
    why_human: "Requiere cuenta SOFTSEGUROS viva y rendering visual; el smoke test live ya confirmó /api/poli/ funciona pero el flujo UI end-to-end no se puede verificar programáticamente"
  - test: "Esperar el cron diario (o forzar la hora) y confirmar que corre el delta sync + soft-delete sweep"
    expected: "Nuevo doc en softseguros_sync_logs con mode=cron_daily; deudores pagados/eliminados marcados is_active=false"
    why_human: "Comportamiento temporal del scheduler APScheduler; no verificable por inspección estática"
---

# Phase 18: SOFTSEGUROS Deudores Sync — Verification Report

**Phase Goal:** El corredor conecta credenciales SOFTSEGUROS y carga automáticamente su cartera de deudores (cuotas pendientes), clasificada en 2 vistas, con sync diario, botón manual rate-limited, y verificación puntual antes de cada llamada del voice agent.
**Verified:** 2026-05-12
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Token auth contra SOFTSEGUROS con header `Authorization: Token <x>` + re-auth en 401 | ✓ VERIFIED | `softseguros/adapter.py:90` POST `/api-token-auth/`; `:118` header `Token`; `:144` re-auth transparente en 401 |
| 2 | Credenciales per-user cifradas con Fernet, validadas al guardar, nunca loggeadas | ✓ VERIFIED | `softseguros/credentials.py:13-46` Fernet `_encrypt/_decrypt`; `database.py:63` unique index `softseguros_credentials.user_id`; `.env` contiene `SOFTSEGUROS_ENCRYPTION_KEY` válida |
| 3 | Paginación del recurso póliza (modelo as-built) con enriquecimiento + cache por sync | ✓ VERIFIED | `softseguros/sync.py` itera páginas (10/page), `adapter.list_polizas/get_poliza`; cache en run_sync; matches 18-CONTEXT.md póliza model |
| 4 | `Semaphore(5)` + tenacity retry exponencial en 429/5xx; sync no crashea, log marca `failed` | ✓ VERIFIED | `sync.py:15,167` `asyncio.Semaphore(MAX_CONCURRENCY=5)`; `adapter.py` tenacity con `Retry-After`; `_safe_run_sync` en routes captura excepciones; sync_log doc por call |
| 5 | Clasificación `ya_vencidos` / `proximos_a_vencer` recalculada cada sync | ✓ VERIFIED | `softseguros/classifier.py:51` `classify_poliza(estado_cartera, fecha_fin, fecha_limite_pago, recaudado, today)`; buckets `ya_vencidos`/`proximos_a_vencer` (today..today+30); shim `classify_pagopoliza` existe; re-clasifica en cada upsert |
| 6 | 3 modos: onboarding one-shot, cron diario APScheduler 3am default, manual rate-limited 1/5min | ✓ VERIFIED | `sync.py:129-138` `run_sync(db, user_id, mode)` con `{onboarding, cron_daily, manual}`; `scheduler.py:52-55` `AsyncIOScheduler` + `CronTrigger(hour=_daily_hour())`; `routes/debtors.py:236` `/sync-now` 429+Retry-After si elapsed < `_RATE_LIMIT_SECONDS` |
| 7 | `/verify-fresh` con 4 ramas (already_paid/not_found/outdated/ok) + fail-open | ✓ VERIFIED | `verify.py:136` `verify_poliza_fresh`; `:175` not_found, `:198` already_paid, `:214` outdated, `:221` ok; `:179,183` fail-open `{should_call:True, warning:"verification_unavailable"}` en timeout/error |
| 8 | REST API filtrada (`?status=`) con JWT + multi-tenant strict; endpoints sync-status/logs/configure | ✓ VERIFIED | `routes/debtors.py` 9 endpoints, todos `Depends(get_current_user)` salvo `/health`; todas las queries filtran `user_id`; integration test cubre aislamiento de tenant |
| 9 | Soft-delete only (`is_active=0`); cuotas ausentes verificadas puntualmente; nunca hard-delete | ✓ VERIFIED | `sync.py:255-276` Phase C soft-delete sweep; `mark_debtor_deleted/paid_by_softseguros_poliza_id` (is_active=false); no hay `delete_one` en sync |
| 10 | Frontend: SoftSegurosSetup (form+validación+loader), DebtorsSoftSegurosTab (2 tabs + badge + botón disabled durante rate-limit), empty/error states | ✓ VERIFIED | `frontend/src/components/SoftSegurosSetup.tsx`, `DebtorsSoftSegurosTab.tsx`, `hooks/useSoftSegurosDebtors.ts`; `CobranzaTab.tsx:51,1472` embebe `<SoftSegurosSection/>`; `npx tsc --noEmit` exit 0 |

**Score:** 10/10 truths verified

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `backend/softseguros/{__init__,adapter,credentials,classifier,sync,scheduler,verify}.py` | ✓ VERIFIED | All 7 present, substantive |
| `backend/routes/debtors.py` | ✓ VERIFIED | 9 endpoints, JWT, multi-tenant |
| `backend/cobranza/debtor_crud.py` | ✓ VERIFIED | softseguros upsert/soft-delete helpers used by sync |
| `backend/database.py` | ✓ VERIFIED | sparse unique index `(user_id, softseguros_poliza_id)`, new collection indexes (`:63-72`) |
| `backend/main.py` | ✓ VERIFIED | `:3436` router included; `:345` scheduler wired in lifespan |
| `backend/tests/test_softseguros.py` + `test_softseguros_integration.py` | ✓ VERIFIED | 23 passed, 0 xfailed |
| `frontend/src/hooks/useSoftSegurosDebtors.ts` + `SoftSegurosSetup.tsx` + `DebtorsSoftSegurosTab.tsx` | ✓ VERIFIED | present; tsc clean |
| `frontend/src/components/CobranzaTab.tsx` | ✓ VERIFIED | embeds SOFTSEGUROS section |
| `backend/.env` SOFTSEGUROS_* vars | ✓ VERIFIED | 6 vars incl. Fernet key (not printed) |
| `backend/requirements.txt` | ✓ VERIFIED | httpx, tenacity, cryptography, respx, apscheduler all present |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| `main.py` lifespan | `softseguros.scheduler.setup_scheduler` | import + await in startup | ✓ WIRED |
| `main.py` | `routes.debtors.router` | `app.include_router` | ✓ WIRED |
| `routes/debtors.py` `/sync-now` | `softseguros.sync.run_sync` | `_safe_run_sync` background task | ✓ WIRED |
| `routes/debtors.py` `/verify-fresh` | `softseguros.verify.verify_poliza_fresh` | direct call | ✓ WIRED |
| `sync.py` | `cobranza.debtor_crud` upsert/soft-delete helpers | direct calls | ✓ WIRED |
| `CobranzaTab.tsx` | `DebtorsSoftSegurosTab` | import + render | ✓ WIRED |
| `useSoftSegurosDebtors.ts` | `/api/debtors/*` endpoints | fetch | ✓ WIRED |

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| SOFTSEG-01 (token auth, Token header, re-auth 401) | ✓ SATISFIED | adapter.py |
| SOFTSEG-02 (Fernet per-user creds, validate, no log) | ✓ SATISFIED | credentials.py, database.py |
| SOFTSEG-03 (paginate + enrich + cache) | ✓ SATISFIED | sync.py — adapted to póliza model per 18-CONTEXT |
| SOFTSEG-04 (Semaphore(5) + tenacity + no crash + failed log) | ✓ SATISFIED | sync.py, adapter.py |
| SOFTSEG-05 (clasificación recalculada) | ✓ SATISFIED | classifier.py |
| SOFTSEG-06 (3 modos: onboarding/cron 3am/manual 1/5min) | ✓ SATISFIED | sync.py, scheduler.py, routes/debtors.py |
| SOFTSEG-07 (verify-fresh 4 ramas + fail-open) | ✓ SATISFIED | verify.py |
| SOFTSEG-08 (REST filtrada JWT + multi-tenant + sync endpoints) | ✓ SATISFIED | routes/debtors.py, integration test |
| SOFTSEG-09 (soft-delete only, verificación puntual, no hard-delete) | ✓ SATISFIED | sync.py Phase C, debtor_crud |
| SOFTSEG-10 (frontend setup + 2 tabs + badge + botón rate-limit + empty/error) | ✓ SATISFIED | frontend components, tsc clean |

All 10 requirement IDs accounted for. No orphaned requirements.

### Anti-Patterns Found

None blocking. Known/accepted:
- ℹ️ Plans 18-02..05 PLAN.md retain stale `pagopoliza` references — known doc-debt; SUMMARYs reflect as-built póliza model (per execution context).
- ℹ️ `backend/tests/test_cobranza.py` has 8 pre-existing failures (`KeyError: 'access_token'` in Phase 17) — predate Phase 18, not counted.
- ℹ️ "deudor cobrable" filter includes old `Sin pagos Asignados` pólizas (2016-2017) — refinement intentionally deferred to Phase 17 consumer.

### Human Verification Required

See `human_verification` in frontmatter. Two items: live onboarding UI flow with real SOFTSEGUROS account, and observing the daily cron sweep. Both require runtime/external state, not static verification.

### Gaps Summary

None. All 10 observable truths verified, all artifacts present and substantive, all key links wired, 23 tests pass with 0 xfailed, frontend typechecks clean, 22 atomic commits with 18-0N prefixes across all 5 plans. The mid-execution pivot from `pagopoliza` to `poliza` model is documented in 18-CONTEXT.md and reflected in the implementation — not a defect.

---

_Verified: 2026-05-12_
_Verifier: Claude (gsd-verifier)_
