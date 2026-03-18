---
phase: 01-auth-infrastructure
plan: 02
subsystem: auth
tags: [jwt, bcrypt, passlib, python-jose, aiosqlite, sqlite, fastapi, tdd]

# Dependency graph
requires:
  - phase: 01-auth-infrastructure/01-01
    provides: "Test scaffold with 8 xfail stubs, pytest infrastructure, conftest fixture"
provides:
  - "backend/auth.py: hash_password, verify_password, create_access_token, get_current_user"
  - "backend/database.py: init_db, get_user_by_email, create_user using aiosqlite"
  - "20 passing tests (13 auth unit + 7 database), 8 xfail endpoint stubs unchanged"
affects:
  - "01-auth-infrastructure/01-03 (implements /auth/register, /auth/login using these modules)"
  - "All future phases that use auth middleware or DB CRUD helpers"

# Tech tracking
tech-stack:
  added:
    - "aiosqlite==0.20.0 — async SQLite driver for all DB operations"
    - "python-jose[cryptography]==3.3.0 — HS256 JWT creation and verification"
    - "passlib[bcrypt]==1.7.4 — bcrypt password hashing with timing-safe verify"
    - "bcrypt==4.0.1 — pinned for passlib 1.7.4 compatibility (5.x incompatible)"
  patterns:
    - "All DB operations live exclusively in database.py — no aiosqlite imports elsewhere"
    - "All crypto operations live exclusively in auth.py — no passlib/jose imports in main.py"
    - "OAuth2PasswordBearer with auto_error=False — guarantees 401 never becomes 403"
    - "Every DB function uses async with aiosqlite.connect() — no persistent connection"
    - "get_current_user returns {'user_id': int} — int type enforced by int(payload['sub'])"

key-files:
  created:
    - "backend/auth.py — hash_password, verify_password, create_access_token, get_current_user FastAPI dependency"
    - "backend/database.py — init_db, get_user_by_email, create_user using aiosqlite"
    - "backend/tests/test_auth_unit.py — 13 unit tests for auth.py functions"
    - "backend/tests/test_database.py — 7 unit tests for database.py functions"
  modified:
    - "backend/requirements.txt — added aiosqlite, python-jose, passlib, bcrypt"

key-decisions:
  - "Pin bcrypt==4.0.1: passlib 1.7.4 is incompatible with bcrypt 5.x (wrap-bug detection uses removed attribute)"
  - "oauth2_scheme auto_error=False: prevents FastAPI default 403 on missing Bearer token; auth.py raises 401 explicitly"
  - "create_user() returns {id, email} only — hashed_password never returned to callers"
  - "DATABASE_URL is a module-level constant to enable monkeypatching in tests without env vars"

patterns-established:
  - "Separation of concerns: crypto in auth.py, persistence in database.py, routing in main.py"
  - "TDD with monkeypatching DATABASE_URL for isolated per-test temp DB files"

requirements-completed: [AUTH-01, AUTH-02]

# Metrics
duration: 25min
completed: 2026-03-18
---

# Phase 1 Plan 2: Auth Core Modules Summary

**bcrypt password hashing and HS256 JWT auth module pair (auth.py + database.py) with aiosqlite persistence, TDD-verified with 20 passing unit tests**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-03-18T00:00:00Z
- **Completed:** 2026-03-18T00:25:00Z
- **Tasks:** 2 (4 commits — TDD RED+GREEN for each)
- **Files modified:** 6

## Accomplishments
- database.py delivers async SQLite CRUD (init_db, get_user_by_email, create_user) via aiosqlite with no persistent connection
- auth.py delivers bcrypt hashing, verify, JWT creation, and get_current_user FastAPI dependency that always raises 401 (never 403)
- 20 new passing unit tests; 8 pre-existing xfail endpoint stubs remain unchanged and still xfail

## Task Commits

Each task was committed atomically:

1. **Task 1 RED: database.py failing tests** - `fd0f462` (test)
2. **Task 1 GREEN: database.py implementation** - `8836f42` (feat)
3. **Task 2 RED: auth.py failing unit tests** - `7308c45` (test)
4. **Task 2 GREEN: auth.py implementation** - `7696b9b` (feat)

_Note: TDD tasks have two commits each (test RED then feat GREEN)_

## Files Created/Modified
- `backend/auth.py` — hash_password, verify_password, create_access_token, get_current_user
- `backend/database.py` — init_db, get_user_by_email, create_user; DATABASE_URL constant
- `backend/tests/test_auth_unit.py` — 13 unit tests for auth.py functions
- `backend/tests/test_database.py` — 7 unit tests for database.py functions
- `backend/requirements.txt` — added aiosqlite, python-jose[cryptography], passlib[bcrypt], bcrypt

## Decisions Made
- Pinned bcrypt==4.0.1 because passlib 1.7.4 uses `_bcrypt.__about__.__version__` which was removed in bcrypt 5.x, causing a ValueError during backend detection
- oauth2_scheme uses auto_error=False so FastAPI does not automatically return 403 on missing Bearer; get_current_user explicitly raises 401
- create_user() deliberately omits hashed_password from the return dict to prevent leaking it to callers

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Downgraded bcrypt from 5.0.0 to 4.0.1**
- **Found during:** Task 2 (auth.py GREEN phase)
- **Issue:** bcrypt 5.0.0 removed the `__about__` module attribute that passlib 1.7.4 uses to detect version during backend initialization. This caused a ValueError ("password cannot be longer than 72 bytes") raised inside passlib's own wrap-bug detection test, breaking hash_password for all inputs.
- **Fix:** Ran `pip install bcrypt==4.0.1`; pinned version in requirements.txt
- **Files modified:** backend/requirements.txt
- **Verification:** All 13 auth unit tests pass after downgrade
- **Committed in:** 7696b9b (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (1 blocking dependency version conflict)
**Impact on plan:** Required pin resolves bcrypt/passlib incompatibility. No scope creep.

## Issues Encountered
- bcrypt 5.x incompatibility with passlib 1.7.4 required version pin — documented above under auto-fix.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- auth.py and database.py are fully importable and tested
- Plan 03 can immediately implement /auth/register and /auth/login by importing hash_password, verify_password, create_access_token, get_user_by_email, create_user
- The 8 xfail endpoint tests in test_auth.py will turn green in Plan 03

---
*Phase: 01-auth-infrastructure*
*Completed: 2026-03-18*
