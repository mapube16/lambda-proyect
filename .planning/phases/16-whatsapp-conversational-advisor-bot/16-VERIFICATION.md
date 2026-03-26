---
phase: 16-whatsapp-conversational-advisor-bot
verified: 2026-03-25T00:00:00Z
status: human_needed
score: 6/7 must-haves verified
re_verification: false
human_verification:
  - test: "Enviar mensaje WhatsApp real desde número registrado en company_voice"
    expected: "Bot responde en lenguaje natural con herramientas disponibles (ver leads, aprobar, etc.) via Twilio"
    why_human: "Requiere sandbox Twilio activo y número real — no se puede simular el flujo completo end-to-end con mocks"
  - test: "Cliente con notification_channel='whatsapp' recibe notificación WA cuando un lead llega a checkpoint"
    expected: "Mensaje WA llega al número del cliente con el resumen del lead y opciones de acción"
    why_human: "Requiere credenciales Twilio reales y un lead real pasando por el pipeline"
  - test: "Asesor interno escribe 'empresas de construcción en Bogotá en SECOP' por WhatsApp"
    expected: "Bot responde con lista de licitaciones formateada (max 5, plain text, sin markdown rico)"
    why_human: "Requiere número en WA_STAFF_NUMBERS env var y Twilio sandbox activo"
---

# Phase 16: WhatsApp Conversational Advisor Bot — Verification Report

**Phase Goal:** Cualquier cliente de Landa puede elegir operar su flujo completo desde WhatsApp — recibir notificaciones de checkpoint/handover, aprobar/rechazar leads, reportar llamadas y configurar campañas via conversación. Los asesores internos de Landa también pueden buscar prospectos SECOP y gestionar leads desde WhatsApp. La web (pixel art office) y WhatsApp son canales equivalentes — el usuario elige.

**Verified:** 2026-03-25
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Derived Must-Haves (from ROADMAP.md Success Criteria)

The ROADMAP.md defines 4 success criteria for Phase 16. These are mapped to observable truths below:

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | notify_user() routes lead_checkpoint/lead_handover/lead_archived events to WS, WA, or both based on company_voice.notification_channel | VERIFIED | `notify_user()` at lines 193-212 of main.py reads `notification_channel` from `get_or_create_company_voice()`, routes to `manager.send_to_user()` (web) and/or `send_whatsapp_text()` (WA). Called at lines 2270, 2278, 2385 of main.py for the 3 lead lifecycle events. |
| 2 | POST /api/whatsapp/incoming webhook exists, strips whatsapp: prefix, returns TwiML immediately, and fires process_inbound async | VERIFIED | Endpoint at line 2489 of main.py. Strips prefix at line 2511 (`from_raw.replace("whatsapp:", "")`). Always returns `<Response/>`. Calls `asyncio.create_task(wa_handler.process_inbound(...))` at line 2577. |
| 3 | wa_sessions CRUD with 24h TTL index is in database.py | VERIFIED | Lines 45-49 in database.py: unique index on `phone`, TTL index on `updated_at` (expireAfterSeconds=86400). `get_or_create_wa_session()` at line 892, `update_wa_session()` at line 924. Sliding window enforced. |
| 4 | dispatch_tool_cliente() with 7 tools handles all cliente actions via LLM function calling | VERIFIED | `TOOLS_CLIENTE` defined at line 156 (7 tools: ver_leads_checkpoint, aprobar_lead, pausar_lead, rechazar_lead, ver_handover, tomar_control, reportar_llamada). `dispatch_tool_cliente()` at line 360. `_call_llm_with_tools()` at line 507 uses OpenAI gpt-4o-mini with tool_choice="auto". |
| 5 | dispatch_tool_asesor() handles 6+ asesor_interno tools including SECOP and NIT enrichment | VERIFIED | `TOOLS_ASESOR` defined at line 255 (7 tools — 6 spec + 1 additive: crear_reunion). `dispatch_tool_asesor()` at line 647. Calls `secop_radar.fetch_open_processes()` at line 658 and `nit_enricher.enrich_nit()` at line 727. |
| 6 | Voice note transcription via Whisper is implemented and non-fatal | VERIFIED | `_transcribe_voice_note()` at line 457 downloads with httpx+Twilio Basic Auth, calls `openai.audio.transcriptions.create(model="whisper-1")`. All exceptions caught and return None (never propagates). |
| 7 | Client can configure notification_channel ("web", "whatsapp", "both") from StaffDashboard and preference persists | PARTIAL | Frontend `FuentesPanel` in StaffDashboard.tsx (lines 1357-1486) has a `<select>` with 3 options. POSTs to `POST /api/staff/clients/{id}/sources`. Backend at line 2181 of main.py stores `notification_channel` to `company_voice` collection. **Code wiring is verified. Real-time persistence requires human validation.** |

**Score:** 6/7 truths fully verified automatically (Truth 7 needs human to confirm round-trip persistence)

---

## Required Artifacts

| Artifact | Provided | Status | Details |
|----------|----------|--------|---------|
| `backend/requirements.txt` | twilio>=9.0.0 | VERIFIED | Line 16: `twilio>=9.0.0` present |
| `backend/tests/test_whatsapp.py` | 14 test functions, 0 xfail stubs remaining | VERIFIED | 344 lines, 14 `async def test_*` functions found, no `@pytest.mark.xfail` remaining |
| `backend/main.py` | notify_user() + POST /api/whatsapp/incoming | VERIFIED | `async def notify_user` at line 193, webhook at line 2489, 3 notify_user calls at lines 2270/2278/2385 |
| `backend/database.py` | wa_sessions CRUD + TTL index | VERIFIED | TTL index at lines 45-49, `get_or_create_wa_session` at line 892, `update_wa_session` at line 924 |
| `backend/wa_handler.py` | All WA-01/02/03/04 exports | VERIFIED | 804 lines. All required functions present: `validate_twilio_signature` (line 31), `get_profile` (line 53), `process_inbound` (line 98), `TOOLS_CLIENTE` (line 156), `TOOLS_ASESOR` (line 255), `dispatch_tool_cliente` (line 360), `_transcribe_voice_note` (line 457), `_call_llm_with_tools` (line 507), `dispatch_tool_asesor` (line 647) |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| main.py notify_user() | landa/company_voice.get_or_create_company_voice() | notification_channel lookup | WIRED | `from landa.company_voice import get_or_create_company_voice` at line 104; called at line 202 inside notify_user() |
| main.py notify_user() | main.py send_whatsapp_text() | channel in ('whatsapp','both') check | WIRED | Lines 208-212: `if channel in ("whatsapp", "both"): ... await send_whatsapp_text(wa_number, message)` |
| main.py notify_user() | main.py manager.send_to_user() | channel in ('web','both') check | WIRED | Lines 205-206: `if channel in ("web", "both"): await manager.send_to_user(user_id, event)` |
| main.py /api/whatsapp/incoming | wa_handler.process_inbound() | asyncio.create_task() | WIRED | Line 2577: `asyncio.create_task(wa_handler.process_inbound(...))` in the default "landa" bot_mode branch |
| wa_handler.dispatch_tool_cliente() | landa/state_machine.update_lead_estado() | aprobar/rechazar/pausar tools | WIRED | `from landa.state_machine import update_lead_estado` at line 25; called at lines 384, 394, 404, 423 |
| wa_handler.dispatch_tool_asesor('buscar_licitaciones') | secop_radar.fetch_open_processes() | direct async call | WIRED | Lines 655, 658: `import secop_radar; ... secop_radar.fetch_open_processes(sector, ciudad, max_results=20)` |
| wa_handler.dispatch_tool_asesor('enriquecer_empresa') | nit_enricher.enrich_nit() | direct async call | WIRED | Lines 726-727: `import nit_enricher; data = await nit_enricher.enrich_nit(nit)` |
| wa_handler.dispatch_tool_asesor('iniciar_outreach') | landa/agents/outreach.run_outreach() | asyncio.create_task() | WIRED | Line 780: `asyncio.create_task(_run_outreach_asesor(...))` → line 801: `await run_outreach(lead_id, user_id, canal, intento=1)` |
| wa_handler._transcribe_voice_note() | openai.audio.transcriptions.create() | model='whisper-1' | WIRED | Lines 495-496: `await openai_client.audio.transcriptions.create(model="whisper-1", ...)` |
| frontend StaffDashboard | backend /api/staff/clients/{id}/sources | fetch POST | WIRED | Frontend line 1390 POSTs to `/api/staff/clients/${client.id}/sources` with `notification_channel`. Backend at line 2181 persists to company_voice collection. |

---

## Requirements Coverage

The WA-01 through WA-04 requirement IDs are defined in ROADMAP.md (not in REQUIREMENTS.md, which was created before Phase 16 and only covers phases 1-8). REQUIREMENTS.md has no WA-* entries — this is an orphan in the requirements document, not a gap in implementation.

| Requirement | Source Plan(s) | Description | Status | Evidence |
|-------------|----------------|-------------|--------|----------|
| WA-01 | 16-01, 16-02, 16-03 | Webhook entrante + router notify_user() web/WA/both | SATISFIED | POST /api/whatsapp/incoming at line 2489 main.py; notify_user() at line 193; 5 tests green (notify_user x3, routing x2) |
| WA-02 | 16-01, 16-03 | wa_sessions CRUD en MongoDB con TTL 24h | SATISFIED | get_or_create_wa_session + update_wa_session in database.py; TTL index in init_db(); 3 tests green (session x2, webhook x1) |
| WA-03 | 16-01, 16-04 | LLM tool calling (cliente profile) + transcripción Whisper | SATISFIED | dispatch_tool_cliente() 7 tools; _transcribe_voice_note() with Whisper; _call_llm_with_tools() with gpt-4o-mini; 4 tests green (tool_call x2, voice_note x2) |
| WA-04 | 16-01, 16-05 | dispatch_tool_asesor() — SECOP, NIT enrichment, gestión clientes | SATISFIED | dispatch_tool_asesor() 7 tools (6 spec + 1 additive crear_reunion); secop_radar + nit_enricher wired; 2 tests green (asesor x2) |

**Orphaned requirement note:** WA-01 through WA-04 do not appear in `.planning/REQUIREMENTS.md`. That document was frozen at v1 (phases 1-8 only). These requirements live entirely in ROADMAP.md. No implementation gap — purely a documentation coverage gap in the REQUIREMENTS.md file.

---

## Anti-Patterns Found

| File | Pattern | Severity | Impact |
|------|---------|----------|--------|
| backend/wa_handler.py (line ~464-466 originally) | `_transcribe_voice_note` was a stub returning `None` in Plan 03 | RESOLVED | Plan 04 replaced the stub with real Whisper implementation |
| backend/wa_handler.py (line ~470-475 originally) | `_call_llm_with_tools` was a placeholder returning a static string in Plan 03 | RESOLVED | Plan 04 replaced with real OpenAI function-calling loop |
| backend/wa_handler.py (line 255, TOOLS_ASESOR) | Originally `TOOLS_ASESOR: list = []` placeholder from Plan 04 | RESOLVED | Plan 05 replaced with 7 real tool definitions |

No remaining stubs or anti-patterns found in the current codebase state. No `TODO`, `FIXME`, `pytest.fail`, or placeholder returns remaining in Phase 16 code paths.

**Notable deviation:** TOOLS_ASESOR has 7 entries (spec was 6). `crear_reunion` was added beyond spec in Plan 05. This is additive and accepted — it does not break any requirement.

**Notable architecture note:** The `/api/whatsapp/incoming` endpoint has a `bot_mode` routing layer (lines 2537-2585) that routes to `legacy` (SECOP prospector bot from whatsapp_agent.py), `calendar` (Phase 17 agent), or `landa` (Phase 16 LLM tool calling bot — the default). This is correct architecture but means Phase 16's `wa_handler.process_inbound()` is only invoked when `bot_mode == "landa"` (the default for unknown phones) or as a fallback when calendar_agent import fails. For Maximiliano's personal number (`+573123528153`), `bot_mode` is hardcoded to `"legacy"`. This is a design decision, not a gap.

---

## Human Verification Required

### 1. End-to-end WhatsApp conversation — cliente profile

**Test:** Configure a test user with `notification_channel="whatsapp"` and `wa_phone_number="+57XXXXXXXXXX"`. Send "ver mis leads" from that WhatsApp number to the Twilio sandbox.
**Expected:** Bot responds in Spanish with a list of leads in checkpoint state (or "No tienes leads en este momento" if none). Response arrives as a WhatsApp message, not just in the web panel.
**Why human:** Requires live Twilio sandbox credentials (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_WHATSAPP_FROM) and a phone number registered in company_voice.

### 2. Lead checkpoint notification via WhatsApp

**Test:** Run the prospecting pipeline with a client whose `notification_channel` is "whatsapp" or "both". Wait for a lead to reach checkpoint state.
**Expected:** Client receives a WhatsApp message: "Lead listo para revision: {empresa} (puntaje: {N}). Escribe 'ver leads' para revisarlos." — in addition to (or instead of) the web panel notification.
**Why human:** Requires a full pipeline run reaching checkpoint, live Twilio creds, and real WA delivery.

### 3. notification_channel persistence via StaffDashboard

**Test:** Log into StaffDashboard as a staff user, open a client panel, change "Canal de notificacion" from "Web (panel)" to "WhatsApp", enter a phone number, and reload the page.
**Expected:** The selected channel and phone number persist after page reload. The company_voice document in MongoDB reflects the change.
**Why human:** Frontend state/backend persistence round-trip requires a browser session — cannot verify programmatically.

---

## Gaps Summary

No structural gaps found. All code is substantive (not stubs). All key links are wired. All 4 requirements are satisfied by verifiable implementation.

The `human_needed` status reflects 3 behaviors that cannot be verified without a live Twilio sandbox and real WhatsApp messages — this is expected for a messaging integration phase, not a code quality gap.

The one documentation gap: REQUIREMENTS.md does not contain WA-01 through WA-04 (it predates Phase 16). This is a documentation debt, not an implementation gap.

---

_Verified: 2026-03-25_
_Verifier: Claude (gsd-verifier)_
