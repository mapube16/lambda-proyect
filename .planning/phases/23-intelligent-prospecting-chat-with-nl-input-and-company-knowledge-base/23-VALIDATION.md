---
phase: 23
slug: intelligent-prospecting-chat-with-nl-input-and-company-knowledge-base
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 23 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | backend/pytest.ini |
| **Quick run command** | `cd backend && python -m pytest tests/test_prospect_chat.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest -x -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `cd backend && python -m pytest tests/test_prospect_chat.py -x -q`
- **After every plan wave:** Run `cd backend && python -m pytest -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 23-01-01 | 01 | 0 | NL-01 | unit stub | `pytest tests/test_prospect_chat.py -x -q` | ❌ W0 | ⬜ pending |
| 23-02-01 | 02 | 1 | NL-01 | unit | `pytest tests/test_prospect_chat.py::test_extract_campaign_from_nl -x -q` | ✅ | ⬜ pending |
| 23-02-02 | 02 | 1 | NL-02 | unit | `pytest tests/test_prospect_chat.py::test_knowledge_base_upsert -x -q` | ✅ | ⬜ pending |
| 23-03-01 | 03 | 2 | NL-03 | unit | `pytest tests/test_prospect_chat.py::test_lead_signal_feedback -x -q` | ✅ | ⬜ pending |
| 23-04-01 | 04 | 2 | NL-04 | manual | n/a | n/a | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `backend/tests/test_prospect_chat.py` — stubs for NL-01 through NL-04 (2 stubs per req, strict=False xfail pattern)
- [ ] `backend/tests/conftest.py` — existing, covers reset_db autouse fixture

*If none: "Existing infrastructure covers all phase requirements."*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Chat UI renders in pixel-art office, NL input box visible | NL-04 | Frontend visual verification | Open app, navigate to prospecting section, verify chat input replaces campaign form |
| NL message produces visible pipeline run | NL-04 | End-to-end WebSocket flow | Type "busca propietarios en Bogotá", verify agents appear in office, leads appear in dashboard |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
