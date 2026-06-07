---
phase: 18-softseguros-sync
type: validation
created: "2026-05-12"
---

# Phase 18 — Validation Strategy (Nyquist)

## Premise

Every requirement (SOFTSEG-01..10) has at least 2 automated tests that turn green when the implementation lands. Plan 18-01 creates 20 xfail stubs as scaffolding; subsequent plans implement the modules; Plan 18-05 confirms all stubs go green and adds an integration test.

## Test → Requirement Map

| Test | Requirement | Scope | Lives in |
|------|-------------|-------|----------|
| test_softseg_01_authenticate_post | SOFTSEG-01 | Unit (adapter, mocked httpx) | `tests/test_softseguros.py` |
| test_softseg_01_header_uses_token_not_bearer | SOFTSEG-01 | Unit | same |
| test_softseg_02_save_credentials_encrypts | SOFTSEG-02 | Unit + mongomock | same |
| test_softseg_02_get_credentials_decrypts | SOFTSEG-02 | Unit + mongomock | same |
| test_softseg_03_list_pagopoliza_paginates | SOFTSEG-03 | Unit (adapter) | same |
| test_softseg_03_enrich_with_cliente | SOFTSEG-03 | Unit (sync engine) | same |
| test_softseg_04_semaphore_limits_concurrency | SOFTSEG-04 | Unit (instrumented mock) | same |
| test_softseg_04_retry_on_429_with_backoff | SOFTSEG-04 | Unit (mocked 429 + Retry-After) | same |
| test_softseg_05_classify_ya_vencidos | SOFTSEG-05 | Pure unit (classifier) | same |
| test_softseg_05_classify_proximos_a_vencer | SOFTSEG-05 | Pure unit | same |
| test_softseg_06_configure_triggers_onboarding | SOFTSEG-06 | API + BackgroundTask | same |
| test_softseg_06_sync_now_rate_limit | SOFTSEG-06 | API (2 calls + assert 429) | same |
| test_softseg_07_verify_fresh_already_paid | SOFTSEG-07 | API + Mongo assertion | same |
| test_softseg_07_verify_fresh_fail_open | SOFTSEG-07 | API + mocked timeout | same |
| test_softseg_08_list_filtered_by_status | SOFTSEG-08 | API | same |
| test_softseg_08_tenant_isolation | SOFTSEG-08 | API w/ 2 JWTs | same |
| test_softseg_09_soft_delete_on_404 | SOFTSEG-09 | Sync engine + mocked 404 | same |
| test_softseg_09_sync_is_idempotent | SOFTSEG-09 | Sync engine (run twice) | same |
| test_softseg_10_sync_status_endpoint | SOFTSEG-10 | API | same |
| test_softseg_10_configure_never_returns_password | SOFTSEG-10 | API (assert no password in response) | same |
| `test_softseguros_integration.py::test_full_flow` | SOFTSEG-01..10 (cross) | E2E with mocked SOFTSEGUROS | `tests/test_softseguros_integration.py` |

**Coverage**: 10 requirements × 2 stubs = 20 unit-level + 1 E2E = 21 automated assertions.

## Mocking Strategy

- **HTTP layer**: `respx` or `pytest-httpx` to intercept SOFTSEGUROS calls. No network traffic during tests.
- **Mongo**: `mongomock_motor` (already used by Phase 17 cobranza tests — see `tests/test_cobranza.py` for pattern).
- **Time**: `freezegun` to control "today" for classifier and rate-limit tests.
- **JWT**: existing test fixtures from Phase 1 (`get_current_user` mocked via dependency override).

## Validation Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Plan 18-01 (Wave 1)                                     │
│  → Creates 20 xfail stubs with NotImplementedError       │
│  → pytest collects them, reports all XFAILED             │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Plans 18-02, 18-03, 18-04                               │
│  → Implement modules (adapter, sync, verify, routes)     │
│  → Each plan's <verify> runs the specific stubs related  │
│    to its SOFTSEG-* IDs, asserting they pass             │
└──────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────┐
│  Plan 18-05 (Wave 4)                                     │
│  → Task 5: integration test with full E2E mock           │
│  → Task 6: remove @xfail decorators; assert 20 PASSED    │
└──────────────────────────────────────────────────────────┘
```

## Non-Automated Checks (manual verification at phase close)

1. **Real SOFTSEGUROS smoke test**: with valid customer credentials, run onboarding from staging UI → confirm < 2 min for a real cartera.
2. **Visual confirmation**: 2 tabs render with real data, manual sync button works.
3. **Voice agent integration handoff**: document the contract (`GET /api/debtors?status=ya_vencidos` + `GET /{id}/verify-fresh`) for Phase 17 consumer.

## Acceptance for Phase Complete

- [ ] All 20 xfail stubs converted to PASSED
- [ ] Integration test passes
- [ ] Frontend compiles, manually verified once
- [ ] Backend starts cleanly, scheduler registers without errors
- [ ] No plaintext credentials in any log output
- [ ] OpenAPI docs include all new endpoints with correct request/response schemas
