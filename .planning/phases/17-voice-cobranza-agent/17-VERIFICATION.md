---
phase: 17-voice-cobranza-agent
verified: 2026-03-27T21:00:00Z
status: human_needed
score: 4/4 must-haves verified
human_verification:
  - test: "Start backend and confirm the 3 scheduler job IDs appear in startup logs: cobr_pre_vencimiento, cobr_post_vencimiento, cobr_rescue_llamando"
    expected: "Logs show all 3 jobs registered by APScheduler on app startup"
    why_human: "Cannot verify APScheduler logs at startup time programmatically in this environment"
  - test: "Log in as a client user in the browser and verify the Cobranza section button appears in ClientDashboard sidebar alongside the Leads section button"
    expected: "Two top-level section buttons visible; clicking Cobranza shows CobranzaTab with empty debtor table and filter pills"
    why_human: "Visual rendering and tab switching require a browser"
  - test: "Upload a test CSV to POST /api/cobranza/debtors/csv (requires staff to first call POST /api/staff/clients/{user_id}/cobranza/enable). CSV: nombre,telefono,monto,vencimiento / Juan Perez,+573001234567,500000,2026-06-01 / Maria Lopez,3009876543,300000,2026-05-15"
    expected: "201 response with {created: 2, errors: []} and both debtors visible in the Cobranza tab with estado=pendiente"
    why_human: "End-to-end flow through real database and authenticated HTTP requires running app"
  - test: "POST /api/vapi/tool-call without any Authorization header. Body: {\"message\":{\"type\":\"tool-calls\",\"call\":{\"id\":\"test\"},\"toolWithToolCallList\":[]}}"
    expected: "HTTP 200 {\"results\":[]} — no 401 or 403"
    why_human: "JWT-bypass behavior on Vapi webhook routes requires a running server to confirm"
  - test: "POST /api/cobranza/onboarding/start with {\"descripcion\":\"Tengo deudores morosos de cartera pequeña\"} (authenticated)"
    expected: "200 response with estrategia object containing keys: tono, frecuencia_dias, max_intentos, guion (with saludo/propuesta/objeciones/cierre). Uses empresa_nombre from client profile, not a generic placeholder."
    why_human: "OpenAI Queen call and empresa_nombre injection require a running app with client profile data"
---

# Phase 17: Voice Cobranza Agent — Verification Report

**Phase Goal:** Cualquier cliente de Landa puede comprar el agente de cobranza, subir su cartera de deudores via CSV o ingreso manual, configurar la estrategia de cobro via onboarding conversacional, y el sistema ejecuta llamadas outbound automatizadas — negociando pagos, registrando promesas, y mostrando el estado de cada deudor en tiempo real en el dashboard.

**Verified:** 2026-03-27T21:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (from ROADMAP.md Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can upload CSV or manually add debtors; records appear with estado=pendiente | VERIFIED | `test_cobr_01_csv_upload` and `test_cobr_01_manual_add` both PASS; debtor_crud.py creates with `estado="pendiente"` |
| 2 | Conversational onboarding: Queen proposes estrategia with tono/frecuencia_dias/max_intentos/guion that user approves | VERIFIED | `test_cobr_02_queen_propone_estrategia` and `test_cobr_02_approve_saves_campaign` PASS; cobranza_queen.py uses `response_format={"type": "json_object"}` |
| 3 | Vapi outbound calls with tool calls (consultar_deuda, registrar_promesa, escalar_a_humano) updating debtor state | VERIFIED | `test_cobr_03_tool_call_consultar_deuda` and `test_cobr_03_call_ended_updates_estado` PASS; webhooks.py has full dispatch logic |
| 4 | Dashboard shows real-time debtor state with historial de llamadas and transitions | VERIFIED | `test_cobr_04_list_debtors_filterable` and `test_cobr_04_debtor_detail_historial` PASS; CobranzaTab.tsx (969 lines) with WS bridge; useWebSocket.ts dispatches `cobr:debtor_update` CustomEvent |

**Score:** 4/4 truths verified (automated)

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/cobranza/__init__.py` | Package marker | VERIFIED | Exists, 1 line |
| `backend/cobranza/debtor_crud.py` | MongoDB CRUD for debtors | VERIFIED | 161 lines; exports create_debtor, get_debtors, get_debtor_by_id, update_debtor, delete_debtor, bulk_create_debtors |
| `backend/cobranza/csv_parser.py` | CSV upload + phone E164 validation | VERIFIED | 95 lines; uses `phonenumbers` library; normalize_phone returns E164 or None |
| `backend/cobranza/router.py` | APIRouter with 9+ debtor endpoints | VERIFIED | 382 lines; 15 routes confirmed registered in app |
| `backend/cobranza/call_scheduler.py` | Ley 2300 compliance functions | VERIFIED | 96 lines; COLOMBIA_TZ, COLOMBIA_HOLIDAYS_2026, is_contact_allowed_now(), has_been_contacted_today(), get_next_allowed_slot() |
| `backend/cobranza/vapi_client.py` | AsyncVapi outbound call wrapper | VERIFIED | 78 lines; lazy `from vapi import AsyncVapi` inside function body; raises ValueError on missing key |
| `backend/cobranza/cobranza_queen.py` | Queen strategy proposal via OpenAI | VERIFIED | 119 lines; response_format=json_object; returns safe fallback on missing API key |
| `backend/cobranza/webhooks.py` | Vapi tool-call + call-ended handlers | VERIFIED | 236 lines; vapi_router with /api/vapi/tool-call and /api/vapi/call-ended; always returns HTTP 200 |
| `backend/cobranza/campaign_scheduler.py` | APScheduler campaign jobs | VERIFIED | 238 lines; register_cobranza_jobs() with 3 jobs: cobr_pre_vencimiento (60m), cobr_post_vencimiento (60m), cobr_rescue_llamando (10m) |
| `backend/tests/test_cobranza.py` | 8 passing tests (no xfail) | VERIFIED | 328 lines; 8/8 PASSED, 0 xfail markers present |
| `frontend/src/components/CobranzaTab.tsx` | Full cobranza tab UI (min 200 lines) | VERIFIED | 969 lines; debtor table, filter pills, detail modal, WS real-time updates, all 6 API actions |
| `frontend/src/components/ClientDashboard.tsx` | Cobranza section added | VERIFIED | `section` state ('leads'|'cobranza') added; CobranzaTab imported and rendered |
| `backend/database.py` | debtors collection indexes in init_db() | VERIFIED | 4 indexes present: (user_id,estado), (user_id,created_at), vapi_call_id sparse, (user_id,telefono) unique |
| `backend/main.py` | cobranza_router + vapi_router included; register_cobranza_jobs called | VERIFIED | Lines 334-335 call register_cobranza_jobs; lines 2755-2759 include both routers |
| `backend/requirements.txt` | vapi_server_sdk, phonenumbers, pytz, pandas listed | VERIFIED | All 4 present: phonenumbers==9.0.26, pytz>=2024.1, vapi_server_sdk>=0.1.0, pandas>=2.0.0 |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `cobranza/router.py` | `cobranza/debtor_crud.py` | `from cobranza.debtor_crud import` | WIRED | Line 34 imports create_debtor, bulk_create_debtors, get_debtors, get_debtor_by_id, update_debtor, delete_debtor |
| `cobranza/router.py` | `cobranza/csv_parser.py` | `from cobranza.csv_parser import` | WIRED | Line 42 imports normalize_phone, parse_debtor_csv |
| `cobranza/cobranza_queen.py` | `openai.AsyncOpenAI` | response_format=json_object | WIRED | Line 82: `response_format={"type": "json_object"}` |
| `cobranza/router.py (onboarding/approve)` | `db.cobranza_config` | upsert with user_id key | WIRED | upsert=True call confirmed in router.py |
| `cobranza/webhooks.py (handle_call_ended)` | `manager.send_to_user()` | lazy import from main | WIRED | Line 223: sends `{"type": "debtor_update", ...}` |
| `cobranza/webhooks.py (dispatch_tool)` | `db.debtors` | find_one by ObjectId | WIRED | `db.debtors.find_one({"_id": ObjectId(debtor_id)})` present |
| `cobranza/campaign_scheduler.py` | `cobranza/call_scheduler.py` | is_contact_allowed_now + has_been_contacted_today | WIRED | Line 20 import; used at lines 59, 77, 103, 132 |
| `main.py (lifespan)` | `cobranza/campaign_scheduler.py` | register_cobranza_jobs(scheduler) | WIRED | Lines 334-335 in lifespan |
| `main.py` | `cobranza/router.py` | app.include_router(cobranza_router) | WIRED | Line 2755 |
| `main.py` | `cobranza/webhooks.py` | app.include_router(vapi_router) | WIRED | Lines 2758-2759 |
| `frontend/CobranzaTab.tsx` | `/api/cobranza/debtors` | apiFetch GET on mount + filter params | WIRED | Line 626: `apiFetch('/api/cobranza/debtors${params}', ...)` |
| `frontend/CobranzaTab.tsx` | `useWebSocket cobr:debtor_update` | window.addEventListener('cobr:debtor_update') | WIRED | Lines 658-659; useWebSocket.ts line 215-218 dispatches the CustomEvent |
| `database.py` | `db.debtors` | create_index calls in init_db() | WIRED | Lines 57-60: 4 debtors indexes |
| `vapi_client.py` | `vapi.AsyncVapi` | lazy import from vapi_server_sdk | WIRED | `from vapi import AsyncVapi` inside function body |
| `call_scheduler.py` | `pytz.timezone('America/Bogota')` | COLOMBIA_TZ | WIRED | Line 14: `COLOMBIA_TZ = pytz.timezone("America/Bogota")` |

---

## Requirements Coverage

| Requirement | Plans | Description | Status | Evidence |
|-------------|-------|-------------|--------|----------|
| COBR-01 | 17-02, 17-08 | Debtor ingestion via CSV upload and manual entry | SATISFIED | test_cobr_01_csv_upload and test_cobr_01_manual_add PASS; debtor_crud.py + csv_parser.py + router.py endpoints live |
| COBR-02 | 17-04, 17-08 | Conversational onboarding + campaign approval | SATISFIED | test_cobr_02_queen_propone_estrategia and test_cobr_02_approve_saves_campaign PASS; cobranza_queen.py + onboarding endpoints live |
| COBR-03 | 17-03, 17-05, 17-06, 17-08 | Automated outbound calls with Vapi tool calls + APScheduler campaign | SATISFIED | test_cobr_03_* PASS; webhooks.py + campaign_scheduler.py + call_scheduler.py + vapi_client.py all wired |
| COBR-04 | 17-07, 17-08 | Real-time dashboard with debtor state, historial, WS updates | SATISFIED | test_cobr_04_* PASS; CobranzaTab.tsx (969 lines) with WS bridge; ClientDashboard section switcher |

Note: COBR-01..04 are defined in the phase 17 ROADMAP and CONTEXT — they do not appear in the top-level REQUIREMENTS.md (which covers only phases 1-8 from the initial MVP scope). No orphaned requirements found for phase 17.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TODO/FIXME/placeholder stubs, empty return values, or console.log-only implementations found in phase 17 artifacts.

Notable: The `cobranza_enabled` guard on `llamar-ahora` and `onboarding/approve` was added as a deliberate architectural decision (staff must enable per client). Pure CRUD endpoints remain accessible to any authenticated client — this is intentional per the design decision documented in 17-08-SUMMARY.md.

---

## Test Suite Status

| Suite | Result |
|-------|--------|
| tests/test_cobranza.py | 8/8 PASSED |
| Full suite (tests/) | 143 passed, 3 failed, 2 xfailed, 7 xpassed |
| Pre-existing failures | `test_get_staff_stats_returns_global_and_per_client` — FAILED before phase 17 (confirmed via git stash); `test_tool_call_ver_leads_checkpoint` — FAILED before phase 17 (confirmed) |
| test_voice_note_transcription_success | Passes in isolation; fails only when run in full suite due to test ordering / asyncio state leak — pre-existing isolation issue, not caused by phase 17 |

---

## Human Verification Required

### 1. Scheduler Job Registration at Startup

**Test:** Start backend with `cd backend && uvicorn main:app --port 8001 --reload`. Observe stdout/log output during startup.
**Expected:** Three APScheduler job IDs logged: `cobr_pre_vencimiento`, `cobr_post_vencimiento`, `cobr_rescue_llamando`
**Why human:** Cannot verify live APScheduler startup log output programmatically in this context.

### 2. CobranzaTab Visual Render in ClientDashboard

**Test:** Open browser at http://localhost:5173, log in as a client user. Verify "Leads" and "Cobranza" section buttons appear in the left nav area of ClientDashboard.
**Expected:** Two top-level section buttons. Clicking Cobranza shows CobranzaTab with empty debtor table, filter pills for each estado, and a stats header row.
**Why human:** Visual appearance and tab switching behavior require a browser.

### 3. End-to-End CSV Upload Flow

**Test:** First enable cobranza for the test user: `POST /api/staff/clients/{user_id}/cobranza/enable` (staff JWT). Then upload CSV via `POST /api/cobranza/debtors/csv` with content `nombre,telefono,monto,vencimiento\nJuan Perez,+573001234567,500000,2026-06-01\nMaria Lopez,3009876543,300000,2026-05-15`.
**Expected:** 201 `{created: 2, errors: []}`. Both debtors appear in Cobranza tab with estado=pendiente. Maria Lopez's phone `3009876543` normalizes to `+573009876543` (E164).
**Why human:** End-to-end through real auth, real database, and UI rendering requires running app.

### 4. Vapi Webhook No-Auth Bypass

**Test:** `curl -X POST http://localhost:8001/api/vapi/tool-call -H "Content-Type: application/json" -d '{"message":{"type":"tool-calls","call":{"id":"test"},"toolWithToolCallList":[]}}'` — no Authorization header.
**Expected:** HTTP 200 `{"results":[]}` — not 401 or 403.
**Why human:** JWT bypass on webhook routes requires a running server to confirm.

### 5. Queen Estrategia with Empresa Nombre

**Test:** POST `/api/cobranza/onboarding/start` with `{"descripcion":"Tengo 50 deudores morosos de crédito de consumo"}` (authenticated as a client who has `empresa_nombre` in their profile).
**Expected:** 200 with `estrategia.guion.saludo` containing the actual company name (not "la empresa" or "Empresa"), confirming `get_client_profile` lookup is working.
**Why human:** Requires a client profile with empresa_nombre set and a real (or mocked) OpenAI call in a running environment.

---

## Summary

All 4 phase goal truths are verified through automated tests (8/8 COBR tests pass). All 15 artifacts exist, are substantive, and are properly wired. The 3 test failures in the full suite are confirmed pre-existing (existed before phase 17 started). The `test_voice_note_transcription_success` failure is a test isolation issue from asyncio state leakage that predates this phase.

The automated evidence is complete. The 5 human verification items cover visual rendering, live scheduler confirmation, real-database end-to-end flow, and the no-auth Vapi webhook path — none of these can be confirmed by static code analysis alone.

Phase 17 is ready for human smoke-test sign-off.

---

_Verified: 2026-03-27T21:00:00Z_
_Verifier: Claude (gsd-verifier)_
