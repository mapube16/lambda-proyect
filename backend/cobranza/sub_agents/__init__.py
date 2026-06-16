"""
sub_agents — CobranzaOrchestrator sub-agent handlers (Phase 25).

Each sub-agent is a standalone async function that:
- Enforces tenant isolation via user_id MongoDB filters.
- Returns {"ok": bool, ...} dicts matching GeminiLiveLLMService result_callback semantics.
- Stays under 3s to comply with Gemini Live tool-response limit (RESEARCH Pitfall 3).
"""
