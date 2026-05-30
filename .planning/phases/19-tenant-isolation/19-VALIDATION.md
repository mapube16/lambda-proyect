---
phase: 19
slug: tenant-isolation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-30
---

# Phase 19 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio |
| **Config file** | `tests/conftest.py` |
| **Quick run command** | `pytest tests/test_tenant_isolation.py -x` |
| **Full suite command** | `pytest tests/ -x` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/test_tenant_isolation.py -x`
- **After every plan wave:** Run `pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 19-01-01 | 01 | 1 | TENANT-01 | T-19-01 | All collections have tenant_id field | unit | `pytest tests/test_tenant_isolation.py::test_collections_have_tenant_id -x` | ❌ W0 | ⬜ pending |
| 19-01-02 | 01 | 1 | TENANT-04 | T-19-01 | Compound indexes exist on (tenant_id, fields) | unit | `pytest tests/test_tenant_isolation.py::test_indexes_exist -x` | ❌ W0 | ⬜ pending |
| 19-02-01 | 02 | 1 | TENANT-02 | T-19-02 | find_one_tenant() enforces tenant_id filter | unit | `pytest tests/test_tenant_isolation.py::test_find_one_tenant_enforces_filter -x` | ❌ W0 | ⬜ pending |
| 19-02-02 | 02 | 1 | TENANT-02 | T-19-02 | aggregate_tenant() prepends $match stage | unit | `pytest tests/test_tenant_isolation.py::test_aggregate_tenant_prepends_match -x` | ❌ W0 | ⬜ pending |
| 19-03-01 | 03 | 2 | TENANT-03 | T-19-03 | WebSocket channels use tenant_id namespacing | integration | `pytest tests/e2e_tenant_isolation.py::test_websocket_isolation_2_brokers -x` | ❌ W0 | ⬜ pending |
| 19-04-01 | 04 | 2 | TENANT-01 | — | 2 brokers see only their own data | e2e | `pytest tests/e2e_tenant_isolation.py::test_two_brokers_concurrent_isolation -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_tenant_isolation.py` — unit tests for query helpers (find_one_tenant, aggregate_tenant, count_tenant, update_tenant)
- [ ] `tests/e2e_tenant_isolation.py` — 2-broker E2E isolation test
- [ ] `tests/conftest.py` — shared fixtures (async loop, mongomock DB client, test broker registration helper)

*Existing infrastructure covers framework: pytest + pytest-asyncio already installed.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 24-hour staging soak test | TENANT-01-04 | Requires live environment + monitoring | Deploy to staging, run 2 brokers for 24h, monitor error rate |
| Blue-green deployment cutover | All | Infrastructure action | Verify Railway traffic cutover to new deployment |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
