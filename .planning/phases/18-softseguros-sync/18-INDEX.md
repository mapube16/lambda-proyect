# Phase 18 — Plan Index

**Phase**: 18 — SOFTSEGUROS Deudores Sync
**Stack**: MongoDB only (extiende colección `debtors` de Phase 17) + Fernet para credenciales
**Wave count**: 4
**Sub-plans**: 5

| # | Plan | Wave | Depends | Files (key) | Reqs |
|---|------|------|---------|-------------|------|
| 01 | [18-01-PLAN.md](./18-01-PLAN.md) — Nyquist xfail scaffold (20 stubs) | 1 | — | `backend/tests/test_softseguros.py` | All SOFTSEG-* |
| 02 | [18-02-PLAN.md](./18-02-PLAN.md) — HTTP adapter + Fernet credentials | 2 | 01 | `backend/softseguros/adapter.py`, `credentials.py`, `.env.example`, `requirements.txt` | SOFTSEG-01,02,04 |
| 03 | [18-03-PLAN.md](./18-03-PLAN.md) — Sync engine + classifier + APScheduler | 2 | 02 | `backend/softseguros/sync.py`, `classifier.py`, `scheduler.py`, `cobranza/debtor_crud.py` ext, `database.py` ext, `main.py` startup | SOFTSEG-03,04,05,06,09 |
| 04 | [18-04-PLAN.md](./18-04-PLAN.md) — REST routes (configure, list, sync-now, verify-fresh) | 3 | 03 | `backend/softseguros/verify.py`, `backend/routes/debtors.py`, `main.py` router | SOFTSEG-06,07,08,10 |
| 05 | [18-05-PLAN.md](./18-05-PLAN.md) — Frontend tab + integration test + green xfails | 4 | 04 | `frontend/src/components/DebtorsSoftSegurosTab.tsx`, `SoftSegurosSetup.tsx`, `CobranzaTab.tsx`, hook, `tests/test_softseguros_integration.py` | SOFTSEG-08,10 |

## Wave Execution

- **Wave 1** (18-01): solo escribe stubs xfail. No depende de implementación.
- **Wave 2** (18-02 → 18-03): cadena secuencial. Adapter + credenciales primero, después el motor de sync.
- **Wave 3** (18-04): REST encima del sync engine.
- **Wave 4** (18-05): frontend + integración E2E + cierre de xfails.

## Reference Documents

- [18-CONTEXT.md](./18-CONTEXT.md) — Decisiones arquitectónicas + hallazgos research API + schema Mongo
- [18-PLAN-DRAFT.md](./18-PLAN-DRAFT.md) — Plan monolítico inicial (preservado como referencia histórica; tiene schema SQLite obsoleto)
- [18-VALIDATION.md](./18-VALIDATION.md) — Estrategia de validación Nyquist

## Out of Scope (v2 backlog)

- Push sync hacia SOFTSEGUROS (marcar pagado desde UI)
- Webhooks de SOFTSEGUROS
- Sync incremental con `modified_since` (cuando SOFTSEGUROS lo soporte)
- Replicación a Supabase para reporting/BI

## Open API Questions (tickets pendientes con SOFTSEGUROS)

1. ¿Existe filtro `modified_since`?
2. ¿Rate limit real y header `Retry-After`?
3. ¿`page_size` ajustable?
4. ¿Webhooks de cobro/recaudo?
5. ¿Expiración de token?
