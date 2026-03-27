---
gsd_state_version: 1.0
milestone: v0.6
milestone_name: milestone
status: planning
stopped_at: Completed 17-07-PLAN.md
last_updated: "2026-03-27T19:49:00Z"
last_activity: "2026-03-27 — Phase 17 Plan 07 complete: Frontend CobranzaTab + ClientDashboard section switcher"
progress:
  total_phases: 17
  completed_phases: 5
  total_plans: 43
  completed_plans: 37
  percent: 43
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-17)

**Core value:** Un cliente piloto puede configurar su agente prospector, ver los agentes trabajar en la oficina pixel art en tiempo real, y recibir expedientes con correos listos para enviar.
**Current focus:** Phase 2 — Hive Adapter and Tenant Isolation

## Current Position

Phase: 2 of 8 (Hive Adapter and Tenant Isolation)
Plan: —
Status: Planning (not started)
Last activity: 2026-03-22 — Phase 14 Plan 01 complete: 8 xfail stubs for LANDA-09/10/11

Progress: [████░░░░░░] 40%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: ~10 min
- Total execution time: ~0.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-auth-infrastructure | 3/3 ✓ | ~30 min | 10 min |
| Phase 12-landa-foundation P01 | 5 | 1 tasks | 1 files |
| Phase 12-landa-foundation P02 | ~8 min | 2 tasks | 4 files |
| Phase 12 P03 | 5 | 2 tasks | 2 files |
| Phase 12 P04 | 10 | 4 tasks | 6 files |
| Phase 13 P02 | 18m | 2 tasks | 5 files |
| Phase 13 P04 | 5m | 2 tasks | 4 files |
| Phase 13 P05 | 5m | 2 tasks | 3 files |
| Phase 14-landa-api-checkpoint-ui P04 | 5m | 1 tasks | 1 files |
| Phase 14-landa-api-checkpoint-ui P03 | 12m | 2 tasks | 2 files |
| Phase 14-landa-api-checkpoint-ui P02 | 5m | 2 tasks | 2 files |
| Phase 16-whatsapp-conversational-advisor-bot P01 | 5 | 1 tasks | 2 files |
| Phase 16-whatsapp-conversational-advisor-bot P02 | 4m | 2 tasks | 2 files |
| Phase 16-whatsapp-conversational-advisor-bot P03 | 8m | 2 tasks | 3 files |
| Phase 16-whatsapp-conversational-advisor-bot P04 | 20m | 2 tasks | 2 files |
| Phase 16-whatsapp-conversational-advisor-bot P05 | 10m | 1 tasks | 2 files |
| Phase 16-whatsapp-conversational-advisor-bot P06 | 5m | smoke test | all green |
| Phase 16-whatsapp-conversational-advisor-bot P06 | 5m | 2 tasks | 0 files |
| Phase 17-voice-cobranza-agent P01 | 2 | 1 tasks | 1 files |
| Phase 17-voice-cobranza-agent P03 | 5min | 2 tasks | 3 files |
| Phase 17-voice-cobranza-agent P02 | 8 | 2 tasks | 5 files |
| Phase 17-voice-cobranza-agent P05 | 7min | 1 tasks | 3 files |
| Phase 17-voice-cobranza-agent P06 | 5min | 1 tasks | 1 files |
| Phase 17-voice-cobranza-agent P04 | 9min | 2 tasks | 3 files |
| Phase 17-voice-cobranza-agent P07 | 9min | 2 tasks | 3 files |

## Accumulated Context

### Roadmap Evolution

- Phase 15 added: Pipeline Enrichment + Real Channel Activation (SECOP bridge, NIT enricher, WhatsApp fallback)
- Phase 16 added: WhatsApp Conversational Advisor Bot (LLM tool-calling bot para asesores via Twilio)

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Roadmap: `HiveAdapter` is the single seam between FastAPI and Hive — nothing in `main.py` imports Hive directly
- Roadmap: Auth must exist before any other feature — tenant isolation is a Phase 1 blocker, not a Phase 4 polish item
- [Phase 01]: pytest asyncio_mode = auto; Wave-0 xfail scaffold pattern established for Nyquist compliance
- [Phase 01]: Pin bcrypt==4.0.1 — passlib 1.7.4 incompatible with bcrypt 5.x
- [Phase 01]: oauth2_scheme auto_error=False — get_current_user explicitly raises 401, never 403
- [Phase 01]: MongoDB Atlas via Motor (not aiosqlite) — per-test isolation via mongomock-motor
- [Phase 01]: ConnectionManager keyed by user_id (Dict[str, WebSocket]) — tenant isolation at WS layer
- [Phase 12-landa-foundation]: 8 xfail stubs (2 per req) chosen over 4 to document both happy-path and error-path contracts from the start
- [Phase 12-landa-foundation]: motor upgraded 3.3.2 to 3.7.1 and python-multipart installed to fix pre-existing env incompatibilities blocking conftest
- [Phase 12-02]: VALID_TRANSITIONS is hardcoded dict[str,set[str]] — not DB-driven — per Documento B Sección 5.5; archivado is terminal by empty set construction
- [Phase 12]: APScheduler uses MemoryJobStore only — MongoDB jobstore conflicts with Motor async stack; durable state in db.scheduled_actions
- [Phase 12]: build_system_prompt uses [inferida — KEY] marker for missing variables
- [Phase 13-01]: 8 strict xfail stubs (2 per req) for LANDA-05 through LANDA-08; import-inside-body pattern ensures collection with missing modules
- [Phase 13-03]: smtplib STARTTLS wrapped in asyncio.to_thread; httpx AsyncClient for Meta Graph API v18.0; both return False on missing creds without raising
- [Phase 13]: use_secop_radar handled at closure level in hive_tools.py — avoids modifying prospector.py signature
- [Phase 13]: sector_profile failures are non-fatal — fallback strings used so scoring continues
- [Phase 13-04]: outreach.py placed in landa/agents/ to match test import path; backend/outreach_agent.py is a re-export shim
- [Phase 13-04]: module-level imports in agent files required for unittest.mock patch() targets to work
- [Phase 13-landa-agent-pipeline]: nurturing.py placed at backend/landa/agents/nurturing.py with backend/nurturing_agent.py as re-export shim to satisfy test imports and plan artifact spec simultaneously
- [Phase 13-landa-agent-pipeline]: Module-level imports in nurturing.py required for unittest.mock.patch patchability — send_email and call_agent promoted from lazy to module-level
- [Phase 13-landa-agent-pipeline]: approve_lead fetches leads once before api_key check, shared between embed and outreach tasks
- [Phase 13-landa-agent-pipeline]: _dispatch_scheduled_action reads canal/intento from both top-level and nested contexto for Phase 12 backward compat
- [Phase 13-landa-agent-pipeline]: scheduler user_id fallback: query lead document at dispatch time if not in action doc — avoids changing schedule_retry/schedule_nurturing signatures
- [Phase 14-01]: raise NotImplementedError used as xfail stub body (vs assert False in test_landa.py) — both trigger strict xfail; NotImplementedError is more semantically accurate for unimplemented endpoints
- [Phase 14-04]: Used Depends(require_staff) consistent with all other /api/staff/* endpoints
- [Phase 14-04]: upsert=True on db.company_voice.update_one handles both create and update without get_or_create_company_voice
- [Phase 14-landa-api-checkpoint-ui]: call_agent adapted to actual signature (system_prompt, user_message); wrapped in try/except since it raises RuntimeError on missing creds
- [Phase 14-landa-api-checkpoint-ui]: no_pude/incorrecto sets buscar_numero_alternativo=True without state transition (RESEARCH pitfall 4)
- [Phase 14-02]: DECISION_MAP maps human decision vocabulary ('aprobar'/'pausar'/'rechazar') to machine estados ('outreach'/'pausado'/'nurturing')
- [Phase 14-02]: asyncio.create_task() for fire-and-forget outreach — never await inline to avoid blocking HTTP response
- [Phase 14]: CheckpointModal fetches GET /api/leads/checkpoint to resolve full lead data by leadId
- [Phase 14-landa-api-checkpoint-ui]: LandaCheckpointLead/LandaHandoverLead Omit<T> intersection casts in useWebSocket make imports load-bearing and avoid TS6196 unused-import errors
- [Phase 14-landa-api-checkpoint-ui]: lead_archived uses useOfficeStore.getState().clearCheckpointLead() directly to avoid adding clearCheckpointLead to useCallback dep array
- [Phase 16-01]: strict=False on all xfail markers — stubs show as xfail not failures, CI never blocks on unimplemented WA features
- [Phase 16-01]: reset_db autouse fixture duplicated in test_whatsapp.py (not imported from conftest) — self-contained per-test MongoDB isolation
- [Phase 16-01]: async_client uses lazy import inside fixture body to prevent collection-time app-import errors before wa_handler.py exists
- [Phase 16-02]: send_whatsapp_text() placed in main.py not wa_handler.py to avoid circular import at module init
- [Phase 16-02]: Only 3 lead lifecycle events replaced with notify_user(): lead_checkpoint, lead_archived, lead_handover — agent_state UI signals left as direct send_to_user()
- [Phase 16-03]: Two-phase sliding window in update_wa_session: push then trim if >10 — mongomock does not support $push with $slice in single op
- [Phase 16-03]: validate_twilio_signature returns True when creds not set — permissive fallback for local dev and test environments
- [Phase 16-03]: get_profile uses lazy import of database inside function body — avoids circular import with main.py
- [Phase 16-whatsapp-conversational-advisor-bot]: No new code changes in 16-06 — pure smoke-test plan; all fixes already in place from 16-01..16-05
- [Phase 16-whatsapp-conversational-advisor-bot]: TOOLS_ASESOR ended up 7 tools (crear_reunion added beyond spec in 16-05) — accepted as additive, not regression
- [Phase 16-whatsapp-conversational-advisor-bot]: 2 xfailed tests are legitimate manual-only verification stubs; CI should not block on them
- [Phase 17-voice-cobranza-agent]: strict=False on all xfail markers — stubs show as xfail not failures, CI never blocks on unimplemented cobranza features
- [Phase 17-voice-cobranza-agent]: reset_db autouse fixture duplicated in test_cobranza.py (not imported from conftest) — self-contained per-test MongoDB isolation
- [Phase 17-voice-cobranza-agent]: async_client uses lazy import inside fixture body to prevent collection-time ImportError before cobranza/ package exists
- [Phase 17-voice-cobranza-agent]: Lazy import of AsyncVapi inside function body — SDK optional at startup; consistent with Phase 16 WhatsApp lazy import pattern
- [Phase 17-voice-cobranza-agent]: initiate_call() falls back to VAPI_API_KEY/ASSISTANT_ID/PHONE_NUMBER_ID env vars if config keys absent — dual-path config
- [Phase 17-voice-cobranza-agent]: router.py not included in main.py yet — Plan 17-08 registers the router
- [Phase 17-voice-cobranza-agent]: reactivar endpoint guards on estado=='pausado' — prevents unintentional state resets, returns 400 on non-pausado
- [Phase 17-voice-cobranza-agent]: DebtorPatch uses Optional fields — only non-None fields included in $set to avoid nulling existing data
- [Phase 17-04]: empresa_nombre fetched live from get_client_profile at onboarding/start — avoids stale data in Queen module
- [Phase 17-04]: generate_cobranza_proposal fallback triggers on ANY exception — OpenAI errors never surface as 500 to user
- [Phase 17-04]: llamar-ahora returns 202 immediately; Vapi call result updates debtor estado async via asyncio.create_task
- [Phase 17-04]: cobranza_config uses user_id as upsert key — one campaign config per tenant, overwrites on re-approval
- [Phase 17-voice-cobranza-agent]: register_cobranza_jobs() accepts scheduler as parameter — no circular import with landa.scheduler; called in main.py lifespan
- [Phase 17-voice-cobranza-agent]: asyncio.create_task() for fire-and-forget Vapi call dispatch from campaign_scheduler jobs — avoids blocking the job loop
- [Phase 17-voice-cobranza-agent]: rescue_stuck_llamando_job resets to sin_contacto (not pendiente) — debtor needs re-contact, not initial contact
- [Phase 17-05]: Both Vapi endpoints always return HTTP 200 — outer try/except catches everything; Vapi aborts call on non-200 response
- [Phase 17-05]: Lazy import of manager from main inside handle_call_ended() prevents circular import at module load time
- [Phase 17-05]: Terminal estados (promesa_de_pago, escalado, pagado) are never overwritten by endedReason mapping — tool calls set state mid-call
- [Phase 17-07]: CustomEvent bridge (cobr:debtor_update) preferred over store coupling — CobranzaTab is self-contained with no store mutations
- [Phase 17-07]: Section switcher uses display:none for leads panel when cobranza active — avoids remount and preserves leads scroll position

### Pending Todos

None.

### Blockers/Concerns

- **Phase 2 research flag:** Hive v0.6.0 callback API signatures (`on_node_event`, `ctx.runtime` dict, `AgentRunner.run()` parameter shape) are inferred from `negocio.md` — not verified against installed framework source. Must verify after `pip install` before committing to architecture patterns.
- **Phase 3 research flag:** `web_scrape_tool` anti-bot capability against Cloudflare-protected sites is unknown. Test against 5 real Colombian B2B URLs before building the scoring node. Have Firecrawl API ($20/month) as fallback plan.

## Session Continuity

Last session: 2026-03-27T19:49:00Z
Stopped at: Completed 17-07-PLAN.md
Resume file: None
