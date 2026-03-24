---
phase: 16-whatsapp-conversational-advisor-bot
plan: 04
completed: 2026-03-24
duration: ~20min
tasks_completed: 2
files_modified: 2
---

# Phase 16 Plan 04 — LLM Tool Calling + Whisper Voice Notes

## Deliverables

- `TOOLS_CLIENTE` — 7 OpenAI function-calling definitions
- `dispatch_tool_cliente()` — 7 tools: ver_leads_checkpoint, aprobar_lead, pausar_lead, rechazar_lead, ver_handover, tomar_control, reportar_llamada
- `_transcribe_voice_note()` — httpx download with Twilio Basic Auth + OpenAI Whisper model="whisper-1"
- `_call_llm_with_tools()` — real OpenAI gpt-4o-mini function-calling loop
- `TOOLS_ASESOR: list = []` placeholder for Plan 05

## Test Results
- `pytest -k "tool_call or voice_note"` → 4 passed
- Full `test_whatsapp.py` → 12 passed, 2 xfailed (asesor stubs, done in 05)

## Commits
- `a4eb6f4`: feat(16-04): implement dispatch_tool_cliente, _transcribe_voice_note, _call_llm_with_tools
