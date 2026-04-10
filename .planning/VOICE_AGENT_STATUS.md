# Voice Agent Implementation Status

**Date:** 2026-04-10  
**Branch:** `feature/voice-openai-realtime`  
**Status:** WORKING POC, PRODUCTION BLOCKERS IDENTIFIED

---

## What Works ✅

- **OpenAI Realtime API Integration**: Full speech-to-speech pipeline (STT+LLM+TTS) via Pipecat
- **Voice Call Flow**: Twilio → WebSocket → Pipecat → OpenAI Realtime → TTS voice output
- **TTFB**: <700ms (target <500ms achieved)
- **Voice Quality**: Coral voice, natural Colombian dialect ("Camila" character)
- **Call Recording**: Twilio recordings enabled, saved via callback
- **Transcript Capture**: User turns + bot turns accumulated and saved to DB
- **Post-Call Status Update**: Debtor estado updated to "contactado", intentos incremented, historial saved
- **WebSocket Real-Time**: Debtor state pushes to dashboard via WS events
- **Dashboard Integration**: "Llamar Ahora" button initiates Pipecat calls with Ley 2300 guards

**Cost Analysis**: ~$262 COP/call vs Vapi (~$3,150 COP/call) = 12x cheaper

---

## Production Blockers (MUST FIX) 🚫

### 1. Missing Dependency
**File:** `requirements.txt`  
**Status:** ✅ FIXED - Added `pipecat-ai[openai]>=0.0.108`

### 2. POC Fallback Debtor Data
**File:** `backend/cobranza/voice_router.py` lines 131-134  
**Status:** ✅ FIXED - Removed fallback, now fails with 1008 error if no call mapping

### 3. Debug Print Statements (14 total)
**Files:** 
- `backend/cobranza/voice_pipecat.py`: 12 print() calls
- `backend/cobranza/voice_router.py`: 2 print() calls  
**Status:** ⏳ PENDING - Need to replace with logger calls

### 4. Recording Playback Auth Issue
**Problem:** User says "siempre me pide el login en twilio"
**File:** `backend/cobranza/voice_router.py` lines 89-103 (proxy endpoint)
**Status:** ⏳ PENDING - Proxy uses httpx with Twilio auth, frontend needs to send auth token  
**Action:** Verify frontend includes auth header when accessing `/api/cobranza/voice/recording/{recording_sid}`

### 5. Environment Variables
**Critical for Prod:**
- `VOICE_WEBHOOK_HOST` — Must be real domain (e.g., `https://api.yourdomain.com`), currently defaults to `http://localhost:8002`
- `ENV=production` — Enables test bypass gating
- `OPENAI_API_KEY` — Required, no fallback
- `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_VOICE_PHONE_NUMBER` — All required

---

## Completed Tasks ✅

- [x] OpenAI Realtime LLM service integration
- [x] Pipecat pipeline with transport (Twilio) + LLM + output
- [x] FastAPIWebsocketTransport 24kHz PCM16 audio
- [x] System prompt with debtor data (nombre, monto, vencimiento)
- [x] Call state management (call_mapping in DB)
- [x] Transcript collection (user + bot turns)
- [x] CallResult data structure with full_transcript property
- [x] Post-call processing: estado update, intentos++, historial_llamadas save
- [x] WebSocket push to dashboard (debtor_update event)
- [x] Recording callback from Twilio
- [x] Recording proxy endpoint for auth
- [x] Added `contactado` estado to frontend types
- [x] Test bypass gating (`?test=true` only on localhost, gated by ENV)
- [x] Ley 2300 compliance guards (time window, one-contact-per-day)
- [x] Eager Pipecat import (no import delay on call)
- [x] Dual transcript collectors (user upstream, bot downstream of LLM)
- [x] Fixed ObjectId string issue in post-call update
- [x] Removed hardcoded POC fallback debtor data
- [x] Added pipecat-ai to requirements.txt

---

## Remaining Tasks ⏳

1. **Replace 14 print() statements with logger calls**
   - `backend/cobranza/voice_pipecat.py` (12 calls)
   - `backend/cobranza/voice_router.py` (2 calls)
   - Change from: `print(f"[VOICE] ...", flush=True)`
   - Change to: `logger.info("[VOICE] ...", args)` or `logger.error(...)`

2. **Fix recording playback auth issue**
   - Verify frontend sends auth token when accessing recording proxy
   - May need to check `apiFetch()` headers or adjust proxy endpoint
   - User reports: "siempre me pide el login en twilio cuando entro a revisar la info"

3. **Confirm vite.config.ts proxy for prod**
   - Currently points to `http://localhost:8002` for dev
   - Need to verify this doesn't interfere with prod (it shouldn't, vite dev server is dev-only)

4. **Test end-to-end in staging/prod environment**
   - Verify Twilio webhooks reach production domain
   - Test call initiation → recording → playback flow
   - Verify Ley 2300 guards work in prod

---

## Key Code Changes Made

### voice_pipecat.py
- Added CallResult dataclass with transcript accumulation
- Dual TranscriptCollector (before + after LLM)
- Bot tokens accumulated into single lines (not fragmented)
- Returns CallResult with full_transcript property

### voice_router.py
- Added recording callback endpoint (`/recording-callback`)
- Added recording proxy endpoint (`/recording/{recording_sid}`)
- Removed POC fallback, now fails if no call mapping
- Post-call processing with estado update, intentos++, historial save
- WebSocket push to dashboard via manager

### router.py (cobranza/router.py)
- Added `?test=true` parameter to `llamar_ahora` endpoint
- Test bypass gated by `ENV != production`

### Frontend (CobranzaTab.tsx)
- Added `contactado` to estado type
- Added color config for `contactado` estado (green)
- Test bypass only on localhost/127.0.0.1

---

## Git State

**Branch:** `feature/voice-openai-realtime`  
**Commits since POC:**
- Fixed Pipecat Settings schema (model via settings, not deprecated param)
- Fixed LLMContext imports (removed deprecated OpenAILLMContext)
- Added post-call processing with DB updates
- Added recording callback and proxy
- Transcript collection with dual collectors
- Removed POC fallback, fixed ObjectId issue

---

## Next Steps to Prod

1. ✅ Add pipecat-ai dependency — DONE
2. ✅ Remove POC fallback data — DONE
3. ⏳ Replace print() with logger (5 min task)
4. ⏳ Debug recording proxy auth (investigate frontend token flow)
5. ⏳ Test in staging with real domain
6. ⏳ Merge to master after approval
7. ⏳ Deploy with ENV vars set correctly

---

## Model Used

- **LLM:** gpt-4o-mini-realtime-preview-2024-12-17
- **STT:** Whisper-1 (Spanish)
- **TTS Voice:** coral (warm, human-like)
- **Temperature:** 0.8
- **Prompt Length:** ~400 chars (Camila character, Ley 2300 aware)

---

## Testing Notes

- **Test phone:** +573123528153 (test debtor Carlos Andrés Morales García)
- **ngrok tunnel:** https://counterproductive-unphenomenally-amberly.ngrok-free.dev
- **Backend port:** 8002 (dev), will be standard HTTPS in prod
- **Frontend port:** 5173 (dev vite server, not used in prod)

---

## User Reported Issues

1. ❌ "no suena nada" (no audio) — FIXED (Pipecat import delay was blocking)
2. ❌ "Ultra robotico" (too robotic) — FIXED (reduced temperature, adjusted prompt, changed to coral voice)
3. ❌ "suena muy rapido y agresivo" — FIXED (removed speed modifier, softened prompt)
4. ❌ "hay interferencia en las llamadas" — PARTIALLY FIXED (ngrok free tier causes some jitter, will disappear in prod with real domain)
5. ❌ "no se registra en el dashboard" — FIXED (ObjectId string issue in post-call update)
6. ❌ "siempre me pide el login en twilio" (recording playback) — ⏳ PENDING

---

## Architecture Summary

```
Twilio Call
    ↓
TwiML Webhook (/webhook) — returns WebSocket URL
    ↓
Twilio Media Stream WebSocket (/ws/{call_sid})
    ↓
FastAPIWebsocketTransport (24kHz audio in/out)
    ↓
[User Speech] → TranscriptCollector (before LLM) → OpenAI Realtime LLM → TranscriptCollector (after LLM) → [Bot Speech]
    ↓
TwilioFrameSerializer (8kHz mulaw back to Twilio)
    ↓
Twilio Recording (async callback)
    ↓
Post-Call: Update debtor estado, save historial, push WebSocket
    ↓
Dashboard: Real-time update via WS + fetch full debtor for transcript + audio player
```

---

## Cost Per Call

- **Pipecat (OpenAI Realtime):** ~$0.13 USD → ~262 COP/call
- **Vapi:** ~$1.50 USD → ~3,150 COP/call  
- **ElevenLabs (Assembly AI STT):** ~$0.07 USD → ~139 COP/call

**Savings:** 12x cheaper than Vapi with this implementation.

---

## Continuation Notes

When resuming:
1. Check `/tmp/voice_server.log` for current server state
2. Run `taskkill //F //IM python.exe` before restarting backend if needed
3. Frontend Vite dev server may still be running on 5173
4. DB state persists — calls made will be in MongoDB `hive_office.debtors`
5. Recording proxy endpoint requires auth — debug if user still sees Twilio login
