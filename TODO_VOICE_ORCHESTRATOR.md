# Voice Orchestrator — Checklist de Implementación

## Phase A: Setup & Configuration

### A1: Credenciales de Google Cloud TTS
- [ ] Create Google Cloud project
- [ ] Enable Cloud Text-to-Speech API
- [ ] Create service account (JSON key)
- [ ] Download JSON key
- [ ] Encode to base64: `cat key.json | base64 -w 0`
- [ ] Add to `.env`: `GOOGLE_CLOUD_TTS_CREDENTIALS_JSON=...`
- [ ] Test: `python -c "import google.cloud; print('✓')"`

### A2: Assembly AI Setup
- [ ] Sign up at [assemblyai.com](https://assemblyai.com)
- [ ] Get API key
- [ ] Add to `.env`: `ASSEMBLY_AI_API_KEY=...`
- [ ] Test streaming connection

### A3: Twilio Setup
- [ ] Have Twilio account?
- [ ] Get Account SID, Auth Token
- [ ] Get a phone number (or use existing)
- [ ] Add to `.env`: `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`
- [ ] Set webhook URL in Twilio dashboard: `https://your-domain.com/api/cobranza/voice/webhook`

### A4: Environment Variables
- [ ] Copy `.env.example` to `.env`
- [ ] Fill in all `VOICE_ORCHESTRATOR_*` variables
- [ ] Set `VOICE_ORCHESTRATOR_ENABLED=true`
- [ ] Choose `TTS_PROVIDER` (default: google-cloud)

---

## Phase B: Implementation

### B1: WebSocket Handler (Critical)
**File:** `backend/cobranza/voice_router.py`

Current state: Skeleton with `TODO` comments

Needs:
- [ ] Parse Twilio media stream format
- [ ] Initialize Assembly AI WebSocket
- [ ] Main loop: receive → transcribe → decide → respond → send
- [ ] Handle timeouts (silence after 60s = hang up)
- [ ] Error handling & reconnection logic
- [ ] Call state tracking (call_sid ↔ debtor_id mapping)

**Estimated effort:** 3-4 hours

**Why it's here:** This is where the magic happens. Audio flows through this function.

### B2: Call State Management
**File:** `backend/cobranza/database.py` (new collection)

Needs:
- [ ] `cobranza_calls_in_progress` collection (temp, for active calls)
- [ ] Schema: `{call_sid: str, user_id: str, debtor_id: str, started_at: datetime}`
- [ ] Index on call_sid (for fast lookup)
- [ ] Cleanup: remove entries older than 2 hours

**Estimated effort:** 1 hour

### B3: Outbound Call Initiation
**File:** `backend/cobranza/router.py` (modify existing `/llamar-ahora`)

Currently: Calls Vapi with `initiate_call()`

Needs:
- [ ] Add `initiate_orchestrator_call()` function (Twilio outbound)
- [ ] Map call_sid → debtor_id in database
- [ ] Switch `/debtors/{id}/llamar-ahora` to use orchestrator
- [ ] Keep Vapi as fallback (optional)

**Estimated effort:** 2 hours

### B4: Debtor Lookup in WebSocket
**File:** `backend/cobranza/voice_router.py`

Needs:
- [ ] Extract debtor_id from call_sid
- [ ] Fetch debtor document from MongoDB
- [ ] Fetch cobranza_config (estrategia) from MongoDB
- [ ] Handle missing data gracefully

**Estimated effort:** 1 hour

---

## Phase C: Testing

### C1: Unit Tests
**File:** Create `backend/tests/test_voice_orchestrator.py`

Test:
- [ ] `claude_decision.get_next_action()` with mock responses
- [ ] `voice_orchestrator.VoiceOrchestrator.run_conversation_turn()`
- [ ] `tts_adapter.get_tts_provider()` (all providers)

**Estimated effort:** 2 hours

### C2: Integration Tests
**File:** Create `backend/tests/test_voice_e2e.py`

Test:
- [ ] WebSocket connection (mock Twilio)
- [ ] Full call flow (speech → decision → TTS → response)
- [ ] Error handling (Assembly AI timeout, Claude error, etc.)

**Estimated effort:** 3 hours

### C3: Manual E2E Testing
- [ ] Deploy to staging
- [ ] Call test phone number
- [ ] Listen for quality (audio, timing, naturalness)
- [ ] Check MongoDB logs for issues
- [ ] Tweak Claude prompt if needed

**Estimated effort:** 2-3 hours (plus iteration)

---

## Phase D: Optimization & Monitoring

### D1: Latency Optimization
- [ ] Profile WebSocket handler (where are the bottlenecks?)
- [ ] Consider async Assembly AI batching (if latency is high)
- [ ] Cache TTS results (if same text asked multiple times)
- [ ] Monitor `turn_latency` metric

### D2: Fallback Strategy (Optional)
- [ ] If orchestrator fails, fall back to Vapi
- [ ] Log fallback events
- [ ] Monitor fallback rate

### D3: Monitoring & Alerts
- [ ] Dashboard: call success rate, avg turns, escalation rate
- [ ] Alert on: Assembly AI errors, Claude API errors, TTS failures
- [ ] Log: call quality metrics (transcript clarity, decision confidence)

---

## Phase E: Rollout

### E1: Feature Branch Testing
- [ ] Deploy to staging
- [ ] Run E2E tests
- [ ] Internal calls (staff → test number)
- [ ] Validate quality

### E2: Beta (10% of Calls)
- [ ] Route 10% of `/llamar-ahora` calls to orchestrator
- [ ] Rest still use Vapi
- [ ] Monitor success rate, escalation rate
- [ ] Collect feedback

### E3: Full Rollout
- [ ] If metrics look good (>95% success), switch 100%
- [ ] Keep Vapi as fallback for 2 weeks
- [ ] Monitor closely

### E4: Deprecate Vapi (Optional)
- [ ] Once orchestrator is stable, remove Vapi calls
- [ ] Clean up `vapi_client.py`
- [ ] Save costs

---

## Estimated Timeline

| Phase | Hours | Notes |
|-------|-------|-------|
| A: Setup | 4-6 | Credentials, env vars |
| B: Implementation | 7-8 | Core WebSocket handler |
| C: Testing | 7-8 | Unit + E2E tests |
| D: Optimization | 3-4 | Latency, fallback |
| E: Rollout | 3-4 | Staging → beta → prod |
| **Total** | **24-30h** | ~1 week full-time |

---

## Immediate Next Steps

### TODAY
- [ ] Pick what to work on first (A1, A2, A3, or B1?)
- [ ] Get credentials (Google, Assembly AI, Twilio)
- [ ] Fill `.env`

### THIS WEEK
- [ ] Implement B1 (WebSocket handler)
- [ ] Run C1 + C2 tests
- [ ] Manual test with real call

### NEXT WEEK
- [ ] D (monitoring), E1 (staging)
- [ ] Beta rollout

---

## Questions / Blockers

If stuck:
1. **TTS provider** — Want to switch? Change 1 line in `.env`
2. **Claude prompt** — Not natural enough? Tweak `_build_decision_prompt()` in `claude_decision.py`
3. **Assembly AI timeout** — Adjust timeout in `voice_router.py`
4. **Latency** — Profile and optimize the WebSocket loop

I'm here to help unblock. Just ask. 🚀
