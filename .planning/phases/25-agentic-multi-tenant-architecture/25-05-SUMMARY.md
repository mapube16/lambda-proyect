---
phase: 25-agentic-multi-tenant-architecture
plan: 05
wave: 4
status: complete
date: 2026-06-11
files_modified:
  - backend/routers/tenant_admin.py
  - backend/main.py
  - backend/worker.py
  - backend/cobranza/rag_service.py
---

# 25-05 Summary — Tenant Admin API + ARQ Communication Log + Wiring

## What was built

Wave 4 closes Phase 25: a self-service multi-tenant admin API, an async
communication-log ARQ job, and full wiring into the app.

### Task 1 — `backend/routers/tenant_admin.py` (NEW, 7 endpoints)

All endpoints derive `user_id` from `Depends(get_current_user)` — never from
the request body or path (T-25-12..15). Prefix `/api/tenant`.

| Method | Path | Behavior |
|--------|------|----------|
| GET | `/config` | Read-through Redis cache of tenant_configs |
| PATCH | `/config` | `upsert_tenant_config` → invalidates Redis (CACHE-01) |
| POST | `/modules/{module}/toggle` | `toggle_module` → invalidates Redis |
| GET | `/agents` | Lists agent_instances filtered by user_id |
| PATCH | `/agents/{agent_type}` | `upsert_agent_instance` + `append_prompt_version` when `new_prompt` present |
| POST | `/rag/upload` (multipart) | `ingest_document(user_id, ...)` per file; per-file error capture |
| GET | `/rag/documents` | `get_rag_documents(user_id)` — tenant-scoped |

Pydantic models enforce `max_length=2000` on `voice_system_prompt` and
`new_prompt` (ASVS V5, T-25-13).

### Task 2 — Wiring + ARQ job

- **main.py**: included `tenant_admin_router` alongside cobranza routers. No
  existing router touched or reordered.
- **worker.py**: added `log_debtor_communication` ARQ job (channel/direction/
  content) that pushes to `debtors.historial_llamadas` with a
  `{"_id": oid, "user_id": user_id}` filter for tenant isolation (T-25-15).
  Registered in `WorkerSettings.functions`.

## Deviations from plan

- **`config_cache` export name**: plan referenced `invalidate_config`; actual
  export is `invalidate_tenant_config`. The router relies on
  `upsert_tenant_config` / `toggle_module` calling invalidation internally, so
  no direct import of the invalidator was needed.
- **`upsert_agent_instance(user_id, fields)`** takes only 2 args (one
  agent_instances doc per tenant). `agent_type` is written inside `fields`,
  not passed as a separate positional arg as the plan sketch implied.
- **rag_service.py import fix**: `from pinecone.asyncio import AsyncPinecone`
  was wrong for pinecone 9.1.0. Corrected to
  `from pinecone import AsyncPinecone, ServerlessSpec`. This unblocked
  `/rag/upload`; it now reaches Pinecone and fails only on the placeholder
  `PINECONE_API_KEY` (expected — needs a real key for live ingestion).

## Verification

- All plan assertions PASS (`tenant_admin` in main, `log_debtor_communication`
  in worker + WorkerSettings.functions, 7× `Depends(get_current_user)`,
  `max_length=2000`).
- `worker.py` and `main.py` import cleanly.
- `pytest tests/test_cobranza_phase25.py` → **21 passed, 2 xfailed**.
- Live endpoint tests against running backend:
  - 401 without JWT ✅
  - GET/PATCH `/config` round-trip persists `brand_name` + `voice_system_prompt` ✅
  - `/modules/voice/toggle` off/on ✅
  - PATCH `/agents/cobranza` writes model/temperature + prompt_history version ✅
  - `/rag/upload` reaches Pinecone (401 on placeholder key — code path correct) ✅

## Wave 3 voice checkpoint — RESOLVED during this session

The Telnyx path was abandoned (free-tier connection_id 422 errors) in favor of
**Twilio + Gemini Live**. End-to-end outbound voice now works. Root cause of
"caller hears nothing" was a chain of three bugs, fixed in order:

1. **Self-interruption**: Gemini's native VAD fired ~2s in on phone-line noise,
   cancelling bot audio. Fixed: `GeminiVADParams(disabled=True)` + Silero VAD in
   transport + `allow_interruptions=False`.
2. **No audio modality**: Gemini returned text only. Fixed:
   `modalities=GeminiModalities.AUDIO`.
3. **Wrong streamSid** (the real culprit): `run_bot` was called with
   `stream_id=call_sid` (CA…) instead of the parsed Twilio `stream_id` (MZ…).
   Twilio silently drops media whose `streamSid` doesn't match the session.
   Fixed in `voice_router.py` to pass the real `stream_id`.

Audio config that works: pipeline output 24kHz, `TwilioFrameSerializer`
downsamples to 8kHz µ-law (`twilio_sample_rate=8000, sample_rate=24000`).

User confirmed: **"Eureka / ya respondió"** — agent (Camila, voice Charon,
es-US) speaks and is heard on the phone.
