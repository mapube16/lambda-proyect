---
phase: 1
slug: auth-infrastructure
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-17
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x + httpx AsyncClient |
| **Config file** | `backend/tests/conftest.py` — Wave 0 installs |
| **Quick run command** | `cd backend && pytest tests/test_auth.py -x -q` |
| **Full suite command** | `cd backend && pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && pytest tests/test_auth.py -x -q`
- **After every plan wave:** Run `cd backend && pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | AUTH-01 | unit | `pytest tests/test_auth.py::test_register_201 -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 1 | AUTH-01 | integration | `pytest tests/test_auth.py::test_register_no_raw_password -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 01 | 1 | AUTH-02 | integration | `pytest tests/test_auth.py::test_login_returns_jwt -x` | ❌ W0 | ⬜ pending |
| 1-02-02 | 01 | 1 | AUTH-02 | unit | `pytest tests/test_auth.py::test_jwt_decode -x` | ❌ W0 | ⬜ pending |
| 1-03-01 | 02 | 2 | AUTH-03 | integration | `pytest tests/test_auth.py::test_unauth_rest_returns_401 -x` | ❌ W0 | ⬜ pending |
| 1-03-02 | 02 | 2 | AUTH-03 | integration | `pytest tests/test_auth.py::test_unauth_websocket_rejected -x` | ❌ W0 | ⬜ pending |
| 1-03-03 | 02 | 2 | AUTH-03 | integration | `pytest tests/test_auth.py::test_two_users_isolated -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/__init__.py` — empty init
- [ ] `backend/tests/conftest.py` — async test client fixtures, test DB setup/teardown
- [ ] `backend/tests/test_auth.py` — stubs for AUTH-01, AUTH-02, AUTH-03 (all xfail initially)
- [ ] `pytest pytest-asyncio httpx` — install if not present

*Wave 0 must be committed before any implementation tasks run.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Password not stored in plaintext | AUTH-01 | DB inspection required | Open SQLite DB, verify `password_hash` column contains bcrypt hash string starting with `$2b$` |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
