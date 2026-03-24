---
phase: 16-whatsapp-conversational-advisor-bot
plan: 05
completed: 2026-03-24
duration: ~10min
tasks_completed: 1
files_modified: 2
---

# Phase 16 Plan 05 — Asesor Interno Tools

## Deliverables

- `TOOLS_ASESOR` — 6 OpenAI function-calling definitions: buscar_licitaciones, buscar_adjudicados, enriquecer_empresa, ver_clientes, ver_leads_cliente, iniciar_outreach
- `dispatch_tool_asesor()` — calls secop_radar.fetch_open_processes(), nit_enricher.enrich_nit(), asyncio.create_task(run_outreach)
- `_call_llm_with_tools()` routes to dispatch_tool_asesor when profile="asesor_interno"

## Test Results
- `pytest -k "asesor"` → 2 passed
- Full `test_whatsapp.py` → 14 passed, 0 xfailed
- Full suite → 79 passed, 2 xfailed, 0 failed

## Commits
- `9bcc092`: feat(16-05): implement dispatch_tool_asesor with 6 tools + TOOLS_ASESOR
