---
phase: 2
slug: hive-adapter-and-tenant-isolation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-18
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| **Config file** | `backend/pytest.ini` (asyncio_mode = auto) |
| **Quick run command** | `cd backend && python -m pytest tests/test_hive_adapter.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_hive_adapter.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest tests/ -q`
- **Before `/gsd:verify-work`:** Full suite must be green (21 existing + new hive tests)
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 2-01-01 | 01 | 0 | HIVE-01 | smoke | `pytest tests/test_hive_adapter.py::test_hive_import_ok -x` | ❌ W0 | ⬜ pending |
| 2-01-02 | 01 | 0 | HIVE-01 | unit | `pytest tests/test_hive_adapter.py::test_agent_runner_instantiates -x` | ❌ W0 | ⬜ pending |
| 2-01-03 | 01 | 0 | HIVE-02 | static | `pytest tests/test_hive_adapter.py::test_hive_adapter_is_only_seam -x` | ❌ W0 | ⬜ pending |
| 2-01-04 | 01 | 0 | HIVE-02 | integration | `pytest tests/test_hive_adapter.py::test_start_run_no_error -x` | ❌ W0 | ⬜ pending |
| 2-01-05 | 01 | 0 | HIVE-03 | integration | `pytest tests/test_hive_adapter.py::test_ws_isolation_user_a_not_b -x` | ❌ W0 | ⬜ pending |
| 2-01-06 | 01 | 0 | HIVE-03 | integration | `pytest tests/test_hive_adapter.py::test_ws_delivery_correct_user -x` | ❌ W0 | ⬜ pending |
| 2-01-07 | 01 | 0 | HIVE-04 | unit | `pytest tests/test_hive_adapter.py::test_shared_memory_per_run_isolation -x` | ❌ W0 | ⬜ pending |
| 2-01-08 | 01 | 0 | HIVE-05 | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_thinking -x` | ❌ W0 | ⬜ pending |
| 2-01-09 | 01 | 0 | HIVE-05 | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_tool_use -x` | ❌ W0 | ⬜ pending |
| 2-01-10 | 01 | 0 | HIVE-05 | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_waiting -x` | ❌ W0 | ⬜ pending |
| 2-01-11 | 01 | 0 | HIVE-05 | unit | `pytest tests/test_hive_adapter.py::test_event_maps_to_waiting_hitl -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_hive_adapter.py` — 11 xfail stubs for HIVE-01 through HIVE-05
- [ ] `backend/hive_adapter.py` — empty file (import target for seam test)
- [ ] `backend/hive_graph.py` — empty file (stub graph placeholder)
- [ ] Framework install: `pip install -e ../vendor/hive/core` or `pip install -e ../vendor/hive/tools && pip install -e ../vendor/hive/core`
- [ ] `vendor/hive/` — git clone of aden-hive/hive into project root

*Wave 0 must complete before any Wave 1 implementation work.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Pixel art office loads and characters animate after HiveAdapter migration | HIVE-05 (visual) | Frontend animation requires browser + WebSocket; no headless test | Start backend, open http://localhost:5173, verify office canvas renders and characters are visible |
| No cross-tenant WS leakage during concurrent real sessions | HIVE-03 (E2E) | Requires two simultaneous browser sessions | Open two browser windows with different users, start a run on user A, verify user B sees no state updates |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
