---
phase: 14
slug: landa-api-checkpoint-ui
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-22
---

# Phase 14 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode = auto) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_landa_api.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_landa_api.py -x -q`
- **After every plan wave:** `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~5 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 14-01-01 | 01 | 0 | LANDA-09/10/11 | xfail stubs | `pytest tests/test_landa_api.py -v` | ❌ W0 | ⬜ pending |
| 14-02-01 | 02 | 1 | LANDA-09 | integration | `pytest tests/test_landa_api.py -k "checkpoint" -x` | ✅ W0 | ⬜ pending |
| 14-02-02 | 02 | 1 | LANDA-09 | integration | `pytest tests/test_landa_api.py -k "decision" -x` | ✅ W0 | ⬜ pending |
| 14-03-01 | 03 | 1 | LANDA-10 | integration | `pytest tests/test_landa_api.py -k "handover" -x` | ✅ W0 | ⬜ pending |
| 14-03-02 | 03 | 1 | LANDA-11 | integration | `pytest tests/test_landa_api.py -k "reporte" -x` | ✅ W0 | ⬜ pending |
| 14-04-01 | 04 | 1 | LANDA-12 | smoke | `python -m pytest tests/ -x -q` | ✅ | ⬜ pending |
| 14-05-01 | 05 | 2 | LANDA-12 | unit | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 14-05-02 | 05 | 2 | LANDA-12 | unit | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 14-06-01 | 06 | 2 | LANDA-12 | unit | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 14-06-02 | 06 | 2 | LANDA-12 | unit | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 14-07-01 | 07 | 3 | LANDA-12 | manual | Visual check in browser | N/A | ⬜ pending |
| 14-07-02 | 07 | 3 | LANDA-12 | unit | `cd frontend && npx tsc --noEmit` | ✅ | ⬜ pending |
| 14-07-03 | 07 | 3 | LANDA-12 | manual | Visual check staff dashboard | N/A | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `backend/tests/test_landa_api.py` — 8 xfail stubs for LANDA-09, LANDA-10, LANDA-11
- [ ] No new framework install needed — existing pytest + mongomock_motor + httpx ASGI transport

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Checkpoint modal renders on WS lead_checkpoint event | LANDA-12 | React UI — no headless browser | Open app, trigger checkpoint, verify overlay appears on agent click |
| HandoverPanel shows hilo de conversación | LANDA-12 | React UI | Create lead with historial_conversacion, trigger handover WS event |
| Staff dashboard SECOP toggles save and reload | LANDA-12 | React UI | Toggle SECOP in staff dashboard, reload page, verify persisted |
| AgentPanel shows semantic waiting message | LANDA-12 | React UI | Trigger lead_checkpoint WS event, verify "Tengo N candidatos" text |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
