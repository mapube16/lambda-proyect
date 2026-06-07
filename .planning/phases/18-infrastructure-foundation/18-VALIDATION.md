---
phase: 18
slug: infrastructure-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-26
---

# Phase 18 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/pytest.ini |
| **Quick run command** | `cd backend && python -m pytest tests/test_infra.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_infra.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 18-01-01 | 01 | 0 | INFRA-01/02/03 | xfail stub | `python -m pytest tests/test_infra.py -x -q` | ❌ W0 | ⬜ pending |
| 18-02-01 | 02 | 1 | INFRA-03 | unit | `python -m pytest tests/test_infra.py::test_enqueue_returns_run_id -x -q` | ✅ | ⬜ pending |
| 18-02-02 | 02 | 1 | INFRA-02 | unit | `python -m pytest tests/test_infra.py::test_worker_processes_job -x -q` | ✅ | ⬜ pending |
| 18-03-01 | 03 | 1 | INFRA-01 | manual | See Manual-Only Verifications | N/A | ⬜ pending |
| 18-03-02 | 03 | 2 | INFRA-02 | integration | `python -m pytest tests/test_infra.py::test_pubsub_event_routing -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_infra.py` — xfail stubs for INFRA-01, INFRA-02, INFRA-03
- [ ] `backend/tests/conftest.py` — verify reset_db fixture exists and covers new collections

*Existing pytest infrastructure covers test runner; Wave 0 only adds new stubs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Railway 3-service deploy from one repo | INFRA-01 | Requires Railway dashboard, remote deploy, live service logs | Deploy to Railway staging: create API service (startCommand: uvicorn), Worker service (startCommand: arq backend.worker:WorkerSettings), Redis service (image: redis:7). Verify all 3 start without errors in Railway logs. |
| Worker restart resilience | INFRA-02 | Requires killing a running process mid-job | Start a campaign run, restart the Worker process, verify job re-queues and completes. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
