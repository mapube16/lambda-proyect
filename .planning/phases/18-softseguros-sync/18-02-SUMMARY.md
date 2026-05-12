---
phase: 18-softseguros-sync
plan: 02
subsystem: softseguros-sync
tags: [adapter, httpx, tenacity, fernet, encryption, mongo]
one-liner: "SoftSegurosAdapter (httpx + tenacity, Token header, 401 re-auth, Retry-After backoff) + Fernet-encrypted per-user credential storage in Mongo"
requires:
  - 18-01
provides:
  - backend/softseguros/adapter.py
  - backend/softseguros/credentials.py
  - softseguros_credentials Mongo collection + unique index on user_id
affects:
  - backend/database.py
  - backend/tests/conftest.py
  - .env.example
  - backend/requirements.txt
tech-stack:
  added:
    - "tenacity>=8.2 (exponential backoff retry decorator)"
    - "cryptography>=42.0 (Fernet symmetric encryption)"
    - "respx>=0.21 (httpx mocking for adapter tests)"
  patterns:
    - "Fail-fast at module import if SOFTSEGUROS_ENCRYPTION_KEY missing"
    - "Async functions accept db as first arg (mirrors cobranza/debtor_crud.py)"
    - "tenacity @retry on httpx.TimeoutException, SoftSegurosRateLimitError, SoftSegurosServerError"
    - "Custom exception hierarchy: SoftSegurosAPIError → Auth / RateLimit / Server"
    - "Transparent single 401 re-auth + retry inside _request"
    - "Retry-After header parsed and awaited via asyncio.sleep before raising retryable"
    - "Authorization: Token <x> (DRF) — explicitly NOT Bearer"
key-files:
  created:
    - backend/softseguros/__init__.py
    - backend/softseguros/credentials.py
    - backend/softseguros/adapter.py
  modified:
    - backend/database.py
    - backend/tests/conftest.py
    - backend/tests/test_softseguros.py
    - backend/requirements.txt
    - .env.example
key-decisions:
  - "Fail-fast RuntimeError in credentials.py at module import if SOFTSEGUROS_ENCRYPTION_KEY is missing/empty — prevents silent misconfig"
  - "Test Fernet key seeded in backend/tests/conftest.py via os.environ.setdefault — must run BEFORE any softseguros.* import"
  - "Adapter __init__ takes explicit username/password/base_url — no env reads inside (testable, multi-tenant safe)"
  - "Custom exceptions (SoftSegurosRateLimitError / SoftSegurosServerError) raised to drive tenacity retry; raw httpx.HTTPStatusError not used because 5xx/429 need special handling (Retry-After)"
  - "401 handled inside _request body (not via tenacity) — exactly one re-auth attempt per logical call, no infinite loops"
  - "respx chosen over pytest-httpx — already pulled in by httpx ecosystem and integrates cleanly with mode=async"
  - "softseguros_credentials index added alongside cobranza indexes in existing init_db (single source of truth for schema setup)"
metrics:
  duration: "~12 min"
  tasks_completed: 3
  files_created: 3
  files_modified: 5
  completed: "2026-05-12"
---

# Phase 18 Plan 02: SOFTSEGUROS Adapter + Encrypted Credentials Summary

## Overview

Lands the foundational SOFTSEGUROS integration layer:

1. **`backend/softseguros/credentials.py`** — Fernet-encrypted password storage in a new
   `softseguros_credentials` Mongo collection (`user_id` unique). All CRUD async,
   `db` is first arg. Plaintext password is never logged.
2. **`backend/softseguros/adapter.py`** — `SoftSegurosAdapter` async HTTP client built on
   `httpx.AsyncClient` with `tenacity` exponential backoff. Authenticates via
   `POST /api-token-auth/`, sends `Authorization: Token <x>` (Django REST Framework,
   never Bearer), retries 429/5xx/timeouts, honors `Retry-After`, and transparently
   re-authenticates once on 401.
3. **Schema/env scaffold** — unique index in `init_db`, 3 new env vars in `.env.example`,
   3 deps in `requirements.txt`.

These unblock Plan 18-03 (sync engine) and 18-04 (REST routes + verify-fresh).

## Tasks Completed

| Task | Description                                                                       | Files                                                                                                | Commit  |
| ---- | --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------- |
| 1    | Add httpx/tenacity/cryptography/respx deps + 3 SOFTSEGUROS env vars               | `backend/requirements.txt`, `.env.example`                                                           | 2345bfb |
| 2    | Create `softseguros/credentials.py` (Fernet + Mongo CRUD) + unique index in init_db | `backend/softseguros/__init__.py`, `credentials.py`, `database.py`, `tests/conftest.py`, `test_softseguros.py` | ee43efb |
| 3    | Implement `SoftSegurosAdapter` (auth, paginated GETs, retry, 401 re-auth)         | `backend/softseguros/adapter.py`, `tests/test_softseguros.py`                                        | 8e2af11 |

## Verification

```
cd backend && python -m pytest tests/test_softseguros.py -v
```

Result: **5 passed, 15 xfailed, 0 errors, 0 failures** (exit code 0, ~4s).

Tests flipped XFAIL → PASS in this plan (exactly 5):

| Test                                              | Requirement | Validates                                              |
| ------------------------------------------------- | ----------- | ------------------------------------------------------ |
| `test_softseg_01_authenticate_post`               | SOFTSEG-01  | POST /api-token-auth/ with correct body + token store  |
| `test_softseg_01_header_uses_token_not_bearer`    | SOFTSEG-01  | Outbound `Authorization: Token <x>`, never Bearer      |
| `test_softseg_02_save_credentials_encrypts`       | SOFTSEG-02  | Fernet ciphertext (gAAAAA…) persisted, not plaintext   |
| `test_softseg_02_get_credentials_decrypts`        | SOFTSEG-02  | Round-trip decrypts to original plaintext              |
| `test_softseg_04_retry_on_429_with_backoff`       | SOFTSEG-04  | 2× 429 with Retry-After honored, then success on 3rd   |

The remaining 15 stubs (SOFTSEG-03, 05, 06, 07, 08, 09, 10 + SOFTSEG-04 semaphore) stay XFAIL — those land in Plans 18-03 / 18-04 / 18-05. **REQUIREMENTS.md traceability is NOT flipped to Complete here** — that happens at phase verification.

## Deviations from Plan

**None blocking.** Minor additive choices:

- Added `respx>=0.21` to requirements.txt (not in plan's deps list) — needed for adapter tests; this is a test-only dep that follows the Phase 16/17 pattern of pinning HTTP-mock tooling.
- Test-only Fernet key planted in `backend/tests/conftest.py` (autoenv setdefault). Plan did not specify where the key would come from at test time; setting it before any `softseguros.*` import is the only way to satisfy the fail-fast contract without mutating production code paths.

## Decisions Made

- **Fail-fast at import** — `credentials.py` raises `RuntimeError` if `SOFTSEGUROS_ENCRYPTION_KEY` is missing/empty. Prevents silent misconfig in prod.
- **Adapter constructor takes explicit creds** — no env reads inside the class. Trivially testable, multi-tenant safe (one adapter per user).
- **401 re-auth inside `_request`, not via tenacity** — exactly one attempt, no infinite loop risk.
- **429 handling raises a custom exception after awaiting Retry-After** — tenacity drives the actual retry loop; the sleep happens inside `_request` so backoff sums (Retry-After + tenacity exponential) compose cleanly.
- **`respx` over `pytest-httpx`** — minimal dep surface and idiomatic for httpx.
- **Test conftest sets Fernet key via `os.environ.setdefault`** before any `database`/`softseguros` import.

## Next Steps

- **Plan 18-03** — Build `sync.py` engine (onboarding/cron/manual modes), `classifier.py`, and concurrency semaphore. Will flip SOFTSEG-03 (2 stubs), SOFTSEG-04 semaphore stub, SOFTSEG-05 (2 stubs), SOFTSEG-06 (2 stubs), SOFTSEG-09 (2 stubs).
- **Plan 18-04** — REST routes (`/api/debtors/configure-softseguros`, `sync-now`, `verify-fresh`, `sync-status`), tenant filtering. Flips SOFTSEG-07/08/10.
- **Plan 18-05** — Frontend (SoftSegurosSetupPage, DebtorsPage 2-tab).

## Self-Check: PASSED

- FOUND: backend/softseguros/__init__.py
- FOUND: backend/softseguros/credentials.py
- FOUND: backend/softseguros/adapter.py
- FOUND: backend/database.py (softseguros_credentials index added)
- FOUND: backend/tests/conftest.py (Fernet test-key seed)
- FOUND: backend/tests/test_softseguros.py (5 stubs flipped to assertion-bearing tests)
- FOUND: backend/requirements.txt (tenacity, cryptography, respx added)
- FOUND: .env.example (3 SOFTSEGUROS_* vars added)
- FOUND: commit 2345bfb
- FOUND: commit ee43efb
- FOUND: commit 8e2af11
- pytest verified: 5 passed, 15 xfailed, exit 0
