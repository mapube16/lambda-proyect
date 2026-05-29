# Phase 23: Intelligent Prospecting Chat with NL Input and Company Knowledge Base — Research

**Researched:** 2026-05-28
**Domain:** LLM structured extraction, conversational campaign configuration, MongoDB knowledge base, React chat UI
**Confidence:** HIGH

---

## Summary

Phase 23 replaces the manual campaign configuration form with a natural language chat interface. The user types a free-form description like "busca propietarios arrendando en Bogotá" and an LLM extracts structured prospecting parameters automatically. The phase also adds a company knowledge base that stores tenant-specific context (product, ICP, past campaign signals) and feeds approval/rejection signals back as context for future sessions.

The good news: the codebase already has a working conversational layer. `onboarding.py` implements a multi-turn chat that extracts campaign variables and emits `CAMPAIGN_READY:{...}` when done. `chat_leads.py` does the same for post-run lead feedback with structured `INTENT_JSON` extraction. Both use the same `gpt-5.4-2026-03-05` model with string-marker parsing. The pattern is proven and the planner should extend it, not invent a new one.

The key architectural decision for NL extraction is whether to use OpenAI Structured Outputs (JSON schema response format) or the existing string-marker pattern. Given that the existing codebase uses string-marker parsing universally and the model already knows the `CAMPAIGN_READY:` contract, the lowest-risk approach is to extend the existing `onboarding.py` system prompt to accept a single-turn NL description (not just multi-turn) and emit the same `CAMPAIGN_READY:` JSON. This avoids introducing a new parsing path and keeps worker.py/prospect.py unchanged.

The company knowledge base is the new persistent layer. The `company_voice` collection already exists (introduced in Phase 12) and stores tenant brand/voice data. The knowledge base for Phase 23 is a new concern: it stores the user's product context, ICP, and signal feedback — distinct from `company_voice` which handles outreach tone. The correct collection name is `prospecting_knowledge` (new), with upsert semantics per `user_id`, consistent with how `client_profiles` and `company_voice` are managed in `database.py`.

**Primary recommendation:** Extend the existing `onboarding.py` chat turn to support both multi-turn discovery AND single-turn NL extraction. Add `prospecting_knowledge` collection to MongoDB for tenant knowledge base. Feed approval/rejection signals into that collection (not into `company_voice`). Replace the campaign form in the frontend with the existing chat UI pattern already used in other panels.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| openai | >=1.30.0 | LLM calls for NL extraction and chat | Already installed, model `gpt-5.4-2026-03-05` in use |
| motor | 3.3.2 | MongoDB async driver for knowledge base CRUD | Already the project's DB layer |
| fastapi | 0.109.0 | Backend router for new `/api/chat/prospect` endpoint | Already installed |
| pydantic | >=2.7.0 | Request/response validation for extracted params | Already installed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| mongomock-motor | 0.0.21 | Test isolation for new collection | In conftest.py already — tests use it for reset_db fixture |
| pytest-asyncio | 0.23.5 | Async test runner | Already configured with asyncio_mode=auto in pytest.ini |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| String-marker parsing (`CAMPAIGN_READY:`) | OpenAI `response_format={"type":"json_schema"}` | Structured outputs guarantee JSON but require `gpt-4o-mini-2024-07-18` or newer. The existing model `gpt-5.4-2026-03-05` may or may not support it; string-markers work regardless and are already battle-tested in this codebase |
| New `prospecting_knowledge` collection | Adding fields to `client_profiles` | `client_profiles` is the onboarding RAG memory; mixing knowledge base signals there would conflate two concerns. Separate collection is cleaner and matches `company_voice` pattern |
| Stateful session history in MongoDB | Stateless NL extraction per request | Stateless is simpler and sufficient: each NL message is self-contained. Conversation history adds complexity for minimal gain at this phase |

**Installation:** No new packages required. All dependencies are already in `requirements.txt`.

---

## Architecture Patterns

### Recommended Project Structure
```
backend/
├── routers/
│   └── prospect.py          # Add POST /api/chat/prospect (new NL endpoint)
├── onboarding.py             # Extend with single-turn NL extraction mode
├── database.py               # Add: upsert_prospecting_knowledge(), get_prospecting_knowledge(), append_lead_signal()
└── tests/
    └── test_phase23.py       # New test file for NL extraction + knowledge base

frontend/src/components/
└── AgentPanel.tsx            # Replace CampaignForm with NL chat input section
```

### Pattern 1: NL Single-Turn Extraction (extend onboarding.py)

**What:** The existing `chat_turn()` in `onboarding.py` is multi-turn by design (4 steps). Add a new function `extract_campaign_from_nl(message, context)` that runs a single-turn prompt: the user message is the full NL description, and the LLM immediately emits `CAMPAIGN_READY:{...}` with inferred values. No conversation history needed.

**When to use:** When the user provides a complete-enough NL description in one message (e.g., "busca propietarios arrendando en Bogotá"). Falls back to multi-turn `chat_turn()` if the message is ambiguous.

**Example:**
```python
# backend/onboarding.py — new function
NL_EXTRACT_SYSTEM = """Eres un extractor de parámetros de campaña B2B.
El usuario describe en una frase a quién quiere prospectar.
Tu tarea: inferir TODOS los parámetros de campaña y emitir inmediatamente:

CAMPAIGN_READY:
{"nombre_remitente": "...", "empresa_remitente": "...", "industria_objetivo": "...", "ciudad_objetivo": "...", "dolor_operativo": "...", "solucion_ofrecida": "...", "software_clave": "...", "jerarquia_decisores": "...", "signal_sources": [...], "max_results": 20}

REGLAS:
- Si la ciudad no se menciona, usa "Bogotá"
- Si signal_sources no aplica, usa ["serper"]
- Responde SOLO con el bloque CAMPAIGN_READY sin texto adicional
"""

async def extract_campaign_from_nl(
    message: str,
    openai_api_key: str,
    context: str = "",
) -> str:
    """Single-turn NL → structured campaign extraction. Returns raw LLM reply."""
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=openai_api_key)
    system = NL_EXTRACT_SYSTEM
    if context.strip():
        system += f"\n\n=== CONTEXTO DEL NEGOCIO ===\n{context.strip()}"
    response = await client.chat.completions.create(
        model="gpt-5.4-2026-03-05",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ],
        temperature=0.2,
        extra_body={"max_completion_tokens": 400},
    )
    return response.choices[0].message.content or ""
```

### Pattern 2: Prospecting Knowledge Base (new MongoDB collection)

**What:** A new `prospecting_knowledge` collection stores per-tenant knowledge: product description, ICP, past campaign signal summaries, and blacklisted domains. Accessed during NL extraction to provide context.

**Schema:**
```python
# Fields per document (user_id is the primary key via upsert)
{
    "user_id": str,                    # tenant key — mandatory
    "product_description": str,         # "vendemos X para Y en Colombia"
    "icp_summary": str,                 # "empresa mediana, sector logística, Bogotá"
    "approved_lead_signals": list[str], # ["empresa de 50+ empleados", "usa SAP"]
    "rejected_lead_signals": list[str], # ["sector residencial", "empresa sin web"]
    "blacklisted_domains": list[str],   # already in excluded_domains, can mirror here
    "last_campaign_params": dict,       # last CAMPAIGN_READY params for context injection
    "updated_at": datetime,
}
```

**database.py functions to add:**
```python
async def upsert_prospecting_knowledge(user_id: str, fields: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.prospecting_knowledge.update_one(
        {"user_id": user_id},
        {"$set": {**fields, "updated_at": now}, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )

async def get_prospecting_knowledge(user_id: str) -> dict:
    db = get_db()
    doc = await db.prospecting_knowledge.find_one({"user_id": user_id})
    return doc or {}

async def append_lead_signal(user_id: str, signal: str, signal_type: str) -> None:
    """Append an approved/rejected lead signal to the knowledge base."""
    db = get_db()
    field = "approved_lead_signals" if signal_type == "approved" else "rejected_lead_signals"
    await db.prospecting_knowledge.update_one(
        {"user_id": user_id},
        {"$addToSet": {field: signal}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
```

### Pattern 3: New API Endpoint (routers/prospect.py)

**What:** Add `POST /api/chat/prospect` — receives a NL message, calls `extract_campaign_from_nl()`, parses the `CAMPAIGN_READY:` block, saves the campaign, and returns structured params to the frontend.

```python
class NLProspectRequest(BaseModel):
    message: str

@router.post("/api/chat/prospect")
async def nl_prospect_chat(request: NLProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    # Build context from knowledge base + active campaign
    from database import get_prospecting_knowledge
    from onboarding import extract_campaign_from_nl
    knowledge = await get_prospecting_knowledge(user_id)
    context = _build_nl_context(knowledge)  # format knowledge into prompt context
    reply = await extract_campaign_from_nl(request.message, api_key, context=context)
    # Parse CAMPAIGN_READY: same pattern as existing /api/chat
    if "CAMPAIGN_READY:" in reply:
        try:
            marker = "CAMPAIGN_READY:"
            idx = reply.index(marker) + len(marker)
            raw_json = reply[idx:].strip()
            brace_start = raw_json.index("{")
            brace_end = raw_json.rindex("}") + 1
            campaign_data = json.loads(raw_json[brace_start:brace_end])
            await save_campaign(user_id, campaign_data)
            return {"status": "extracted", "campaign": campaign_data}
        except Exception as e:
            logger.warning("[nl_prospect] parse failed: %s", e)
    # If extraction incomplete, return raw reply so frontend can display it
    return {"status": "needs_clarification", "reply": reply}
```

### Pattern 4: Lead Signal Feedback Hook

**What:** When a user approves or rejects a lead via `POST /api/leads/{id}/decision` (already in `routers/leads.py`), extract a signal summary and append it to `prospecting_knowledge`. This is a fire-and-forget background task — it must not block the HITL response.

**Implementation:** Use `asyncio.create_task()` (consistent with Phase 13/14 pattern: "asyncio.create_task() for fire-and-forget — never await inline"). The signal is a short string extracted from the lead's `expediente_json` (e.g., industry + city + tech stack).

### Pattern 5: Frontend NL Chat UI (AgentPanel.tsx)

**What:** Replace the existing `CampaignForm` section in `AgentPanel.tsx` with a single text input and submit button. The user types a NL description; on submit the frontend calls `POST /api/chat/prospect`. If `status === "extracted"`, the extracted campaign params are shown as a read-only confirmation card; if `status === "needs_clarification"`, the LLM reply is shown as a chat message.

**Design tokens:** Use existing `C.*` design tokens from `ClientDashboard.tsx` for consistent styling. The pixel-art office aesthetic is handled by `OfficeCanvas.tsx` separately — the panel UI uses the modern dark glass style already established.

**Existing chat pattern to reuse:** The `AgentPanel.tsx` already renders a `LeadCard` list and a campaign form with controlled inputs. The NL input replaces the form grid with:
- A `<textarea>` with `onKeyDown` handler (Enter to submit, Shift+Enter for newline)
- A submit button with loading state
- A result card showing extracted params or LLM reply
- "Editar manualmente" toggle to still allow field-by-field editing (progressive enhancement)

### Anti-Patterns to Avoid

- **Introducing RAG vector search for Phase 23:** The knowledge base is a simple document store with string fields. Phase 9 already has a RAG layer (`rag.py`, `client_knowledge` collection). Do not add vector embeddings to `prospecting_knowledge` — that is Phase 9-11 scope. The knowledge base here is a key-value store injected as plain text into the system prompt.
- **Storing conversation history per session:** Stateless extraction is sufficient. Storing multi-turn chat history adds MongoDB I/O per turn and session management complexity with no benefit for single-turn NL extraction.
- **Modifying worker.py for Phase 23:** The NL extraction happens at campaign configuration time (before the run is enqueued). worker.py and the ARQ pipeline do not need to change. The extracted params flow through the existing `campaign` dict that worker.py already receives.
- **Using `response_format={"type": "json_schema"}` without testing:** The codebase uses `extra_body={"max_completion_tokens": N}` syntax indicating a possible custom OpenAI-compatible endpoint. String-marker parsing is safer and already proven.
- **Replacing `onboarding.py`:** The existing multi-turn `chat_turn()` is used by the `/api/chat` endpoint which the WhatsApp bot and other integrations call. Do not remove it. Add `extract_campaign_from_nl()` as a new function in the same file.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON extraction from LLM output | Custom regex parser | `CAMPAIGN_READY:` marker + `json.loads()` | Already working in onboarding.py and chat_leads.py — the LLM reliably emits this format |
| Knowledge base context formatting | Template engine | f-strings / `"\n".join()` | Same pattern used in `_build_campaign_chat_context()` in prospect.py — lightweight, tested |
| Per-tenant document upsert | ORM / custom class | Motor `update_one(upsert=True)` | Established project pattern — see `upsert_client_profile()`, `get_or_create_company_voice()` |
| Fire-and-forget async tasks | Thread pool | `asyncio.create_task()` | Phase 13/14 decision: "asyncio.create_task() for fire-and-forget — never await inline" |
| Chat UI state management | Custom state machine | React `useState` + `useMutation` (@tanstack/react-query) | Already used throughout `ClientDashboard.tsx` |

---

## Common Pitfalls

### Pitfall 1: ObjectId in msgpack when enqueuing
**What goes wrong:** If `campaign_data` from NL extraction contains an `_id` field (from a previous `save_campaign` result), msgpack serialization in `arq_pool.enqueue_job()` fails.
**Why it happens:** MongoDB returns `ObjectId` which msgpack cannot serialize.
**How to avoid:** Strip `_id` from campaign before enqueue — already done in `routers/prospect.py`: `safe_campaign = {k: v for k, v in campaign.items() if k != "_id"}`. Apply the same strip in the NL extraction endpoint.
**Warning signs:** `TypeError: can not serialize 'ObjectId' object` in worker logs.

### Pitfall 2: NL message too short / ambiguous — LLM omits required fields
**What goes wrong:** User types "busca empresas en Bogotá" without industry. The LLM fills `industria_objetivo` with a guess or leaves it empty, causing the pipeline to run with no effective filter.
**Why it happens:** The LLM is instructed to infer, not ask. Minimal input yields minimal output.
**How to avoid:** In the extraction prompt, require the LLM to always emit ALL fields (using reasonable defaults). Add a frontend guard: if `industria_objetivo` is empty in the response, show the edit form pre-filled with the extracted data and prompt the user to fill missing fields.
**Warning signs:** Campaigns with `industria_objetivo: ""` in MongoDB.

### Pitfall 3: Knowledge base context window overflow
**What goes wrong:** `approved_lead_signals` grows unbounded over many sessions, eventually overflowing the context window when injected into the NL extraction prompt.
**Why it happens:** `$addToSet` allows unlimited growth.
**How to avoid:** Cap the lists when reading: `signals[:20]` (20 items max). In `_build_nl_context()`, truncate to last 20 signals per type, and the total context block to 1500 chars.
**Warning signs:** LLM `max_tokens` errors or truncated responses.

### Pitfall 4: Signal extraction quality on simple leads
**What goes wrong:** Approved lead has no `expediente_json` (run failed mid-way or lead was rejected before expediente was generated). `append_lead_signal()` gets an empty dict and writes a useless signal like `" — "`.
**Why it happens:** `expediente_json` is nullable in the leads schema.
**How to avoid:** Guard: `if not lead.get("expediente_json"): return` before extracting the signal. Only append if at least industry + city are present.

### Pitfall 5: Frontend double-submit while extracting
**What goes wrong:** User submits NL message twice quickly. Two concurrent `POST /api/chat/prospect` calls both succeed and overwrite the campaign, causing confusing state.
**Why it happens:** No loading guard on the submit button.
**How to avoid:** Disable the submit button while the mutation is in-flight (`isLoading` from `useMutation`). Standard React pattern.

### Pitfall 6: mongomock-motor does not support all MongoDB operators
**What goes wrong:** `$addToSet` with nested document deduplication may behave differently in mongomock vs real Atlas.
**Why it happens:** mongomock is a partial implementation.
**How to avoid:** Signals are plain strings, not nested documents. `$addToSet` on a `list[str]` works correctly in mongomock. Confirmed from Phase 16 decision: "Two-phase sliding window in update_wa_session: push then trim if >10 — mongomock does not support $push with $slice in single op." Use `$addToSet` (not `$push + $slice`) for signal lists.

---

## Code Examples

### Verified: Existing campaign CAMPAIGN_READY parsing (from routers/prospect.py, line 144)
```python
if "CAMPAIGN_READY:" in reply:
    try:
        marker = "CAMPAIGN_READY:"
        idx = reply.index(marker) + len(marker)
        raw_json = reply[idx:].strip()
        brace_start = raw_json.index("{")
        brace_end = raw_json.rindex("}") + 1
        campaign_data = json.loads(raw_json[brace_start:brace_end])
        await save_campaign(user_id, campaign_data)
    except Exception as e:
        logger.warning("[chat] Failed to auto-save campaign: %s", e)
```

### Verified: upsert pattern (from database.py, upsert_client_profile)
```python
await db.client_profiles.update_one(
    {"user_id": user_id},
    {
        "$set": set_payload,
        "$setOnInsert": {"created_at": now},
    },
    upsert=True,
)
```

### Verified: fire-and-forget asyncio pattern (established in Phase 13-14)
```python
# Do NOT await inline — use create_task for non-blocking dispatch
asyncio.create_task(append_lead_signal(user_id, signal_text, "approved"))
```

### Verified: context builder pattern (from routers/prospect.py, _build_campaign_chat_context)
```python
sections = []
if campaign_lines:
    sections.append("=== CAMPAÑA ACTIVA ===\n" + "\n".join(campaign_lines))
if profile_lines:
    sections.append("=== PERFIL DEL NEGOCIO ===\n" + "\n".join(profile_lines))
return "\n\n".join(sections)
```

---

## What to Reuse vs. Replace

| Component | Action | Reason |
|-----------|--------|--------|
| `onboarding.py` `chat_turn()` | Keep as-is | Used by `/api/chat` and WhatsApp bot — do not remove |
| `onboarding.py` SYSTEM_PROMPT | Add new NL prompt, do not modify existing | Backwards compatibility |
| `routers/prospect.py` `/api/chat` endpoint | Keep as-is | Multi-turn campaign chat still used by some flows |
| `database.py` `save_campaign()` | Keep as-is — call from new endpoint | Campaign schema unchanged |
| `AgentPanel.tsx` campaign form | Replace form grid with NL input + confirmation card | Phase 23 goal |
| `AgentPanel.tsx` form-based campaign fields | Keep as hidden "edit manually" toggle | Progressive enhancement |
| `landa/company_voice.py` | No change | Different concern (outreach tone, not prospecting params) |
| `client_profiles` collection | No change | RAG memory is out of scope for Phase 23 |
| `worker.py` | No change | Campaign params flow through existing `campaign` dict |

---

## Validation Architecture

Nyquist validation is enabled (`workflow.nyquist_validation: true`).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| Config file | `backend/pytest.ini` (asyncio_mode = auto) |
| Quick run command | `pytest backend/tests/test_phase23.py -x` |
| Full suite command | `pytest backend/tests/ -x --timeout=30` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NL-01 | `extract_campaign_from_nl()` returns CAMPAIGN_READY with all required fields for a complete NL description | unit | `pytest backend/tests/test_phase23.py::test_extract_campaign_from_nl_complete -x` | Wave 0 |
| NL-02 | `POST /api/chat/prospect` returns `{"status":"extracted", "campaign":{...}}` for a well-formed NL message | integration | `pytest backend/tests/test_phase23.py::test_nl_prospect_endpoint -x` | Wave 0 |
| KB-01 | `upsert_prospecting_knowledge()` creates document with user_id; second call updates without duplicate | unit | `pytest backend/tests/test_phase23.py::test_upsert_knowledge -x` | Wave 0 |
| KB-02 | `append_lead_signal()` appends to approved/rejected lists without duplicates ($addToSet) | unit | `pytest backend/tests/test_phase23.py::test_append_lead_signal -x` | Wave 0 |
| KB-03 | Knowledge base context is injected into NL extraction prompt (context param non-empty when knowledge exists) | unit | `pytest backend/tests/test_phase23.py::test_nl_context_injection -x` | Wave 0 |
| SIGNAL-FB-01 | Lead decision endpoint fires fire-and-forget signal append (create_task called) | integration | `pytest backend/tests/test_phase23.py::test_lead_decision_fires_signal -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest backend/tests/test_phase23.py -x`
- **Per wave merge:** `pytest backend/tests/ -x --timeout=30`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_phase23.py` — covers NL-01, NL-02, KB-01, KB-02, KB-03, SIGNAL-FB-01 (6 xfail stubs, strict=False, 2 per logical req)
- [ ] No framework install needed — pytest already configured

---

## Environment Availability

Step 2.6: All dependencies are already available.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| OpenAI API | NL extraction | Checked at runtime via `OPENAI_API_KEY` env | gpt-5.4-2026-03-05 | Returns 503 if not configured (existing guard) |
| MongoDB / Motor | prospecting_knowledge CRUD | Available | 3.3.2 | — |
| Redis | Not needed (NL extraction is synchronous request) | Available | — | — |
| mongomock-motor | Tests | Available | 0.0.21 | — |

**Missing dependencies with no fallback:** None.

---

## Open Questions

1. **Should `signal_sources` and `max_results` be extractable from NL?**
   - What we know: The existing `ProspectRequest` accepts `max_results` and `source_priority`. These are not part of the current `CAMPAIGN_READY` JSON schema (which has 8 campaign fields).
   - What's unclear: Whether Phase 23 extends the CAMPAIGN_READY schema to include these, or whether they remain defaults.
   - Recommendation: Add `signal_sources` (maps to `source_priority`) and `max_results` as optional fields in the NL extraction schema. If the user says "busca 10 empresas", `max_results=10` should be extracted. Default to 20 and "serper" if not mentioned. This is additive to existing schema.

2. **Should the company knowledge base be populated from existing data at first run?**
   - What we know: `client_profiles.business_summary` and `client_profiles.personality_prompt` contain relevant ICP context from the Phase 9 RAG onboarding.
   - What's unclear: Whether to auto-seed `prospecting_knowledge` from `client_profiles` on first access (like `get_or_create_company_voice()` does from `client_profiles`).
   - Recommendation: Yes — add a `get_or_create_prospecting_knowledge()` that seeds from `client_profiles.business_summary` if the document doesn't exist yet. Consistent with `company_voice.py` pattern.

3. **Does the frontend campaign form still need to exist?**
   - What we know: CONF-01/02/03 (campaign configuration requirements) are listed as Pending in REQUIREMENTS.md. Phase 23 description says "replace the campaign configuration form".
   - What's unclear: Whether CONF-01/02/03 are superseded by Phase 23 or still required as a fallback.
   - Recommendation: Keep the form fields as an "edit manually" expansion panel (hidden by default). The NL chat is the primary UX; the form is the escape hatch. Both can coexist in `AgentPanel.tsx` with a toggle.

---

## Sources

### Primary (HIGH confidence)
- Codebase: `backend/onboarding.py` — existing `chat_turn()`, `CAMPAIGN_READY:` parsing pattern
- Codebase: `backend/chat_leads.py` — `INTENT_JSON:` structured extraction pattern
- Codebase: `backend/routers/prospect.py` — campaign save flow, NL context builder
- Codebase: `backend/landa/company_voice.py` — `get_or_create_company_voice()` upsert pattern
- Codebase: `backend/database.py` — `upsert_client_profile()`, `save_campaign()` upsert patterns
- Codebase: `backend/worker.py` — pipeline job inputs schema (campaign, max_results, etc.)
- Project STATE.md decisions — `asyncio.create_task()` fire-and-forget pattern (Phase 13-14)

### Secondary (MEDIUM confidence)
- `.planning/ROADMAP.md` Phase 23 description — confirmed "replace campaign form, company knowledge base, signal feedback"
- `.planning/REQUIREMENTS.md` CONF-01/02/03 — campaign configuration requirements still pending

### Tertiary (LOW confidence)
- OpenAI `response_format={"type":"json_schema"}` — not researched via Context7 for this specific model (`gpt-5.4-2026-03-05`). String-marker parsing is the safe path given existing codebase evidence.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new packages needed; all existing
- Architecture: HIGH — patterns verified directly in codebase
- Pitfalls: HIGH — most derived from existing STATE.md decisions and known codebase behavior
- Frontend pattern: MEDIUM — AgentPanel.tsx structure verified; specific NL chat sub-component is new work

**Research date:** 2026-05-28
**Valid until:** 2026-07-01 (30 days — stable patterns)
