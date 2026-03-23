---
phase: 15
slug: pipeline-enrichment-channels
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-23
---

# Phase 15 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode = auto) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_enrichment.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_enrichment.py -x -q`
- **After every plan wave:** `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 15-01-01 | 01 | 0 | ENRICH-01/02/03 | xfail stubs | `pytest tests/test_enrichment.py -v` | ⬜ pending |
| 15-02-01 | 02 | 1 | ENRICH-01 | integration | `pytest tests/test_enrichment.py -k "secop_bridge" -x` | ⬜ pending |
| 15-03-01 | 03 | 1 | ENRICH-02 | integration | `pytest tests/test_enrichment.py -k "nit_enricher" -x` | ⬜ pending |
| 15-03-02 | 03 | 1 | ENRICH-02 | integration | `pytest tests/test_enrichment.py -k "nit_data" -x` | ⬜ pending |
| 15-04-01 | 04 | 1 | ENRICH-03 | integration | `pytest tests/test_enrichment.py -k "whatsapp" -x` | ⬜ pending |
| 15-04-02 | 04 | 1 | ENRICH-03 | integration | `pytest tests/test_enrichment.py -k "fallback" -x` | ⬜ pending |
| 15-04-01 | 04 | 2 | ENRICH-01/02/03 | smoke | `cd backend && python -m pytest tests/ -x -q` | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `backend/tests/test_enrichment.py` — xfail stubs for ENRICH-01, ENRICH-02, ENRICH-03
- [ ] No new framework install needed — existing pytest + mongomock_motor + httpx ASGI transport

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SECOP companies appear in run after toggle activation | ENRICH-01 | Requires live run against real API | Toggle SECOP in StaffDashboard, launch a run, verify server log shows secop results |
| NIT data visible in lead doc in MongoDB | ENRICH-02 | Async task — timing dependent | After approving a SECOP lead, check MongoDB `leads` collection for `nit_data` field |
| WhatsApp fallback logs to historial | ENRICH-03 | Requires outreach run | Approve lead with canal=whatsapp + no phone, verify historial_conversacion entry |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
