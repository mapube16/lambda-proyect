---
phase: 16
slug: whatsapp-conversational-advisor-bot
status: planned
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-23
---

# Phase 16 — Validation Strategy

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (asyncio_mode = auto) |
| **Config file** | `backend/pytest.ini` |
| **Quick run command** | `cd backend && python -m pytest tests/test_whatsapp.py -x -q` |
| **Full suite command** | `cd backend && python -m pytest tests/ -x -q` |
| **Estimated runtime** | ~8 seconds |

---

## Sampling Rate

- **After every task commit:** `cd backend && python -m pytest tests/test_whatsapp.py -x -q`
- **After every plan wave:** `cd backend && python -m pytest tests/ -x -q`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** ~8 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Status |
|---------|------|------|-------------|-----------|-------------------|--------|
| 16-01-01 | 01 | 0 | WA-01/02/03/04 | xfail stubs | `pytest tests/test_whatsapp.py -v` | ⬜ pending |
| 16-02-01 | 02 | 1 | WA-01 | integration | `pytest tests/test_whatsapp.py -k "notify_user" -x` | ⬜ pending |
| 16-02-02 | 02 | 1 | WA-01 | integration | `pytest tests/test_whatsapp.py -k "routing" -x` | ⬜ pending |
| 16-03-01 | 03 | 1 | WA-02 | integration | `pytest tests/test_whatsapp.py -k "session" -x` | ⬜ pending |
| 16-03-02 | 03 | 1 | WA-02 | integration | `pytest tests/test_whatsapp.py -k "webhook" -x` | ⬜ pending |
| 16-04-01 | 04 | 2 | WA-03 | integration | `pytest tests/test_whatsapp.py -k "tool_call" -x` | ⬜ pending |
| 16-04-02 | 04 | 2 | WA-03 | integration | `pytest tests/test_whatsapp.py -k "voice_note" -x` | ⬜ pending |
| 16-05-01 | 05 | 4 | WA-04 | integration | `pytest tests/test_whatsapp.py -k "asesor" -x` | ⬜ pending |
| 16-06-01 | 06 | 5 | WA-01/02/03/04 | smoke | `cd backend && python -m pytest tests/ -x -q` | ⬜ pending |

---

## Wave 0 Requirements

- [ ] `twilio>=9.0.0` added to `backend/requirements.txt`
- [ ] `backend/tests/test_whatsapp.py` — xfail stubs for WA-01, WA-02, WA-03, WA-04
- [ ] No other new framework installs needed — existing pytest + mongomock_motor + httpx

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Twilio webhook receives and routes real WA message | WA-02 | Requires live Twilio + ngrok | Configure Twilio sandbox, send WA message, verify response |
| Voice note transcribed and processed | WA-03 | Requires live Whisper API call | Send .ogg voice note to webhook, verify transcription in logs |
| Client receives WA notification when lead reaches checkpoint | WA-01 | Requires notification_channel=whatsapp in DB | Set flag, trigger checkpoint, verify WA message received |
| Asesor tool calling finds SECOP leads via natural language | WA-04 | Requires live LLM call | Send "constructoras Bogotá SECOP" to webhook, verify response |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
