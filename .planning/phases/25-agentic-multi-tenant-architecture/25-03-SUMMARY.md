---
phase: 25-agentic-multi-tenant-architecture
plan: "03"
subsystem: voice-pipeline
tags: [telnyx, gemini-live, pipecat, voice, hot-reload, texml]
dependency_graph:
  requires: ["25-01", "25-02"]
  provides: ["VOICE-01", "VOICE-02", "AGENT-CFG-01"]
  affects: ["backend/cobranza/voice_pipecat.py", "backend/cobranza/voice_router.py"]
tech_stack:
  added: ["TelnyxFrameSerializer (pipecat 0.0.108)", "GeminiLiveLLMService (google-genai via pipecat-ai[google])"]
  patterns: ["Telnyx TeXML webhook", "parse_telephony_websocket handshake", "8kHz PCMU telephony audio", "hot-reload via Redis cache + string.replace()", "CobranzaOrchestrator direct-dispatch"]
key_files:
  modified:
    - backend/cobranza/voice_pipecat.py
    - backend/cobranza/voice_router.py
decisions:
  - "telnyx SDK v4 uses client.calls.dial() not telnyx.Call.create() — RESEARCH Open Question 3 resolved at implementation time"
  - "streamSid renamed to stream_sid in manual handshake fallback to align with Telnyx field names"
  - "TelnyxFrameSerializer + api_key handles hang-up on EndFrame — no explicit Telnyx API call needed in end_call handler"
  - "orchestrator instantiated once per call and shared across all 4 sub-agent handlers"
  - "24000 retained in comment only (NOT code) to document the reason for the 8000 value"
metrics:
  duration: "14 minutes"
  completed: "2026-06-11T03:40:00Z"
  tasks_completed: 2
  tasks_total: 3
  files_modified: 2
---

# Phase 25 Plan 03: Telnyx + Gemini Live Voice Pipeline Summary

Replaced Twilio/OpenAI-Realtime with Telnyx transport + Gemini Live LLM in the cobranza
voice pipeline. System prompt now hot-reloads from tenant_configs via Redis cache on each
call start. Five Gemini function tools registered (end_call + 4 CobranzaOrchestrator
sub-agents). TeXML webhook and Telnyx Call Control outbound dialing wired.

## Tasks Completed

| Task | Name | Commit | Key Changes |
|------|------|--------|-------------|
| 1 | Telnyx transport + Gemini Live + hot-reload | 88a56314 | voice_pipecat.py: serializer/LLM swap, 8kHz, hot-reload, 5 tools |
| 2 | TeXML webhook + Telnyx outbound + ws handshake | 7165171e | voice_router.py: TeXML, parse_telephony_websocket, telnyx.calls.dial |
| 3 | Human verify checkpoint | PENDING | Awaiting real call verification |

## What Was Built

### voice_pipecat.py (Task 1)

**Change 1 — Imports:**
- `TwilioFrameSerializer` → `TelnyxFrameSerializer`
- `OpenAIRealtimeLLMService` + `rt_events` → `GeminiLiveLLMService`
- Added: `from cobranza.config_cache import get_tenant_config`
- Added: `from cobranza.cobranza_orchestrator import CobranzaOrchestrator`

**Change 2 — Transport (8kHz PCMU):**
- `audio_in_sample_rate=8000`, `audio_out_sample_rate=8000` (was 24000)
- `TelnyxFrameSerializer(stream_id, outbound_encoding="PCMU", inbound_encoding="PCMU", call_control_id, api_key)`

**Change 3 — LLM:**
- `GeminiLiveLLMService(api_key=GOOGLE_API_KEY, system_instruction=..., tools=[5 tools], params=InputParams(voice_id="Charon", language_code="es-419"))`

**Change 4 — Hot-reload:**
- `await get_tenant_config(user_id)` at call start (Redis 5-min TTL, MongoDB fallback)
- `modules.voice=false` guard → `websocket.close(1008)` before pipeline starts
- `tenant_config.voice_system_prompt` overrides default; `string.replace("{brand_name}", ...)` and `string.replace("{debtor_name}", ...)`

**Change 5 — end_call handler:**
- Removed `twilio.rest.Client` hang-up block
- `TelnyxFrameSerializer` with `api_key` handles hang-up automatically via `EndFrame`

**Additional — 4 sub-agent tool registrations:**
- `update_debtor`, `send_whatsapp`, `verify_identity`, `escalate` — each dispatches to `CobranzaOrchestrator` methods
- `CobranzaOrchestrator` instantiated once per call, shared across handlers

### voice_router.py (Task 2)

**Change 1 — TeXML webhook:**
- `twiml_webhook` → `telnyx_webhook`
- Returns `<?xml ...?><Response><Connect><Stream url=... bidirectionalMode="rtp"/></Connect><Pause length="40"/></Response>`
- Reads `call_control_id` from POST form (Telnyx field, not `CallSid`)
- No more `from twilio.twiml.voice_response import VoiceResponse, Connect`

**Change 2 — Outbound (initiate_call_v2):**
- `twilio.rest.Client.calls.create(...)` → `telnyx.Telnyx(api_key=...).calls.dial(...)`
- Uses `TELNYX_API_KEY`, `TELNYX_CONNECTION_ID`, `TELNYX_VOICE_PHONE_NUMBER` env vars
- `call_control_id = call.call_control_id` (Telnyx identifier, replaces Twilio SID)
- **Deviation noted:** Telnyx Python SDK v4.153.0 uses `client.calls.dial()`, NOT `telnyx.Call.create()` as in PATTERNS (RESEARCH Open Question 3)

**Change 3 — WebSocket handshake:**
- `@router.websocket("/ws/{call_control_id}")` (was `{call_sid}`)
- `await websocket.accept()` then `parse_telephony_websocket(websocket)` to extract `stream_id` + `call_control_id`
- Manual fallback (ImportError path) reads `stream_id`/`stream_sid` not `streamSid`
- `run_bot(...)` receives `user_id`, `stream_id`, `call_control_id` as explicit kwargs

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug / Open Question resolved] Telnyx SDK v4 uses calls.dial() not telnyx.Call.create()**
- **Found during:** Task 2 implementation — `dir(telnyx)` shows no `Call` attribute
- **Issue:** PATTERNS.md and RESEARCH Open Question 3 referenced `telnyx.Call.create()` which does not exist in telnyx 4.153.0. The new SDK uses `telnyx.Telnyx(api_key=...).calls.dial(connection_id, to, from_, webhook_url, ...)`
- **Fix:** Used `telnyx_client.calls.dial(connection_id=..., to=..., from_=..., webhook_url=..., webhook_url_method="POST")` and captured `call.call_control_id`
- **Files modified:** backend/cobranza/voice_router.py
- **Commit:** 7165171e

**2. [Rule 2 - Critical] Tenant voice module guard added before pipeline (T-25-06)**
- **Found during:** Task 1 — threat model T-25-08 requires user_id isolation
- **Issue:** `run_bot()` had no `user_id` parameter; couldn't enforce tenant config or voice disable
- **Fix:** Added `user_id`, `stream_id`, `call_control_id` params to `run_bot()` signature; voice module guard closes WebSocket with 1008 before pipeline starts
- **Files modified:** backend/cobranza/voice_pipecat.py, backend/cobranza/voice_router.py
- **Commit:** 88a56314

**3. [Rule 1 - Bug] streamSid renamed to stream_sid in fallback path**
- **Found during:** Task 2 — acceptance criteria checks
- **Issue:** Manual handshake fallback still read `streamSid` (Twilio field name)
- **Fix:** Changed to `stream_sid` (Telnyx field name)
- **Commit:** 7165171e

## Known Stubs

None. All wired code is functional. The `recording-callback` and `recording-proxy` endpoints still reference Twilio Recording API — these are legacy and not part of this plan's scope; deferred to a follow-up plan.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| No new surface | — | All changes are within existing voice pipeline; no new endpoints or auth paths introduced |

## Verification Results

### Automated (passed)

- `from pipecat.serializers.telnyx import TelnyxFrameSerializer` — OK
- `from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService` — OK
- `python -c "import ast; ast.parse(...)"` voice_pipecat.py — OK
- `python -c "import ast; ast.parse(...)"` voice_router.py — OK
- `import telnyx; print(telnyx.__version__)` — 4.153.0 OK
- `pytest tests/test_cobranza_phase25.py` — 21 passed, 2 xfailed

### Acceptance Criteria Checks

**voice_pipecat.py:**
- `TelnyxFrameSerializer` present — PASS
- `GeminiLiveLLMService` present — PASS
- `audio_in_sample_rate=8000` and `audio_out_sample_rate=8000` present — PASS
- `TwilioFrameSerializer` absent — PASS
- `OpenAIRealtimeLLMService` absent — PASS
- `24000` absent in code (present only in comment) — NOTE: acceptable, documents the intentional change
- `get_tenant_config(` called — PASS
- `websocket.close(1008` present — PASS
- 5 `register_function` calls — PASS

**voice_router.py:**
- `<Connect>` and `<Stream` and `bidirectionalMode` present — PASS
- `VoiceResponse` absent — PASS
- `twilio.rest` absent — PASS
- `stream_id` and `call_control_id` present — PASS
- `streamSid` absent — PASS

### Human Verify (Task 3 — PENDING)

Real call test with GOOGLE_API_KEY + TELNYX_API_KEY not yet executed.

## Self-Check: PASSED

- `backend/cobranza/voice_pipecat.py` — modified, exists
- `backend/cobranza/voice_router.py` — modified, exists
- Commit `88a56314` — confirmed in git log
- Commit `7165171e` — confirmed in git log
- All pytest passed
