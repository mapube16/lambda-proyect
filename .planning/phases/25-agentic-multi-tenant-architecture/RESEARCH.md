# Phase 25: Agentic Multi-Tenant Architecture - Research

**Researched:** 2026-06-10
**Domain:** Voice AI (Pipecat + Gemini Live), Multi-Tenant MongoDB config, Pinecone RAG, Redis Upstash cache, Telnyx telephony
**Confidence:** HIGH (Pipecat/Telnyx verified in codebase), MEDIUM (Pinecone/Gemini Live API via official docs), LOW (cost estimates)

---

## Summary

Phase 25 replaces three hardcoded systems with MongoDB-driven hot-reload: Twilio with Telnyx, OpenAI Realtime + Assembly AI with Pipecat + Gemini Live, and in-memory cosine-similarity RAG with Pinecone per-tenant namespaces. All config flows through a Redis Upstash cache layer with 5-minute TTL and immediate invalidation for module toggles.

**The key architectural insight:** Pipecat 0.0.108 is already installed and has a native `TelnyxFrameSerializer` in `pipecat.serializers.telnyx`. Telnyx is the correct replacement for Twilio — it has better Pipecat integration than Bandwidth (no native Pipecat serializer for Bandwidth found), and explicit PSTN support for Colombia and Mexico. The existing `voice_pipecat.py` code pattern can be adapted with three changes: serializer swap, LLM swap (`GeminiLiveLLMService`), and loading system_prompt from `tenant_configs` MongoDB instead of hardcoding it.

**Primary recommendation:** Implement in this order — (1) MongoDB `tenant_configs` + Redis cache layer (prerequisite for everything), (2) Telnyx transport swap, (3) Gemini Live LLM swap, (4) CobranzaOrchestrator sub-agents, (5) Pinecone RAG. This ordering ensures the cache-invalidation contract works before any voice calls use it.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Tenant config persistence | Database (MongoDB) | — | Three new collections are the source of truth; hot-reload requires MongoDB as primary |
| Config cache + toggle invalidation | API (Redis Upstash) | — | Cache lives server-side; frontend never touches Redis directly |
| Voice call routing (TwiML/TeXML) | API (webhook endpoint) | — | Provider calls our HTTP endpoint to initiate WebSocket; stays in voice_router.py |
| Audio streaming pipeline | API (WebSocket) | — | Pipecat pipeline runs inside the FastAPI process on WS connection |
| LLM voice decisions | API (Pipecat pipeline) | — | GeminiLiveLLMService runs inside Pipecat; function calling dispatches to sub-agents |
| Sub-agent execution | API (CobranzaOrchestrator) | Worker (ARQ for async) | Identity/escalation are synchronous; bulk WhatsApp is ARQ job |
| RAG ingestion | Worker (ARQ job) | — | Document chunking + embedding is slow; async via ARQ |
| RAG retrieval | API | — | Query during voice call must be synchronous; Pinecone query < 100ms |
| RAG vector storage | External (Pinecone Starter) | — | Tenant namespace isolation; free tier covers MVP scale |
| Call initiation (outbound) | API | — | POST /call/initiate-v2 triggers Telnyx Call Control API |

---

<user_constraints>
## User Constraints (from Phase Description)

### Locked Decisions
1. 3 MongoDB collections: `tenant_configs`, `agent_instances`, `rag_documents`
2. Use existing `user_id` as tenant key (NOT introducing company_id)
3. NO custom template engine — simple string.replace() for brand_name, language variables
4. Prompt versioning: keep only last 5 versions (no infinite arrays)
5. Redis Upstash: TTL 5min for config cache, IMMEDIATE invalidation for module toggles
6. Pinecone Starter ($0 tier) + OpenAI text-embedding-3-small for RAG
7. RecursiveCharacterTextSplitter (chunk_size=1000, overlap=100) for semantic chunking
8. Bandwidth or Telnyx as Twilio replacement (research which is better fit — resolved below: Telnyx)
9. Pipecat + Gemini Live (`GeminiLiveService`) replaces OpenAI Realtime + Assembly AI
10. Sub-agents: debtor_updater, whatsapp_notifier, identity_verifier, escalation_handler
11. Budget-first: MongoDB M0/M2, Redis Upstash free tier, Pinecone Starter $0

### Claude's Discretion
- Implementation order within the phase
- Internal class structure of CobranzaOrchestrator
- Error handling patterns for Redis cache miss
- Pinecone index configuration details (dimensions, metric)

### Deferred Ideas (OUT OF SCOPE)
- Any prospecting pipeline changes
- Frontend UI changes beyond existing cobranza tab
- Company_id / org hierarchy
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| AGENT-CFG-01 | `tenant_configs` MongoDB collection per user_id; hot-reload on next call | MongoDB upsert pattern already established in database.py; add 3 new collections + indexes |
| AGENT-CFG-02 | `agent_instances` with prompt_history (last 5); Redis cache TTL 5min | `redis.asyncio` (redis-py 4.2+, already at 5.3.1); `await redis.setex(key, 300, json)` + `await redis.delete(key)` for immediate invalidation |
| AGENT-CFG-03 | CobranzaOrchestrator with 4 sub-agents; user_id isolation guaranteed | Framework AgentOrchestrator in backend/framework/runner/orchestrator.py exists but routes via LLM — for cobranza use direct dispatch pattern instead |
| VOICE-01 | Telnyx replaces Twilio in voice_router.py + voice_pipecat.py | `TelnyxFrameSerializer` confirmed in pipecat 0.0.108 at `pipecat.serializers.telnyx`; see migration pattern below |
| VOICE-02 | Pipecat + Gemini Live replaces OpenAI Realtime; TTFB <500ms; function calling | `GeminiLiveLLMService` from `pipecat.services.google.gemini_live.llm`; requires `pip install "pipecat-ai[google]"` + `google-genai`; function calling supported natively |
| RAG-01 | `rag_documents` MongoDB + Pinecone Starter namespace per user_id | Pinecone 9.1.0 on PyPI; `pinecone[asyncio]` for async; namespace isolation is free and zero-overhead |
| RAG-02 | `search_client_knowledge(user_id, query, top_k)` tool for all sub-agents | Existing `rag.py` uses MongoDB cosine similarity — this tool replaces it for cobranza namespace; OpenAI text-embedding-3-small already in use |
| CACHE-01 | Redis Upstash `tenant_config:{user_id}` TTL 5min; immediate invalidation for toggles | `redis.asyncio` already available (redis==5.3.1 installed); Upstash connection via `redis://:<token>@<host>.upstash.io:6379` or REST API |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pipecat-ai[google]` | 0.0.108 (already installed) | Voice pipeline + Gemini Live | Already in requirements.txt; `[google]` extra adds google-genai dep |
| `google-genai` | 2.8.0 (latest on PyPI) | Gemini Live API client | Required by `pipecat-ai[google]`; replaces legacy `google-generativeai` |
| `pinecone` | 9.1.0 (latest on PyPI) | Vector store for RAG | Official SDK; supports async via `pinecone[asyncio]` extra |
| `redis` | 5.3.1 (already installed) | Upstash cache; redis.asyncio module | Already installed; `redis.asyncio` replaces deprecated `aioredis` since redis-py 4.2 |
| `langchain-text-splitters` | 1.1.2 (latest on PyPI) | RecursiveCharacterTextSplitter | Contains ONLY the splitter; no LLM deps; lighter than full langchain |
| `motor` | 3.7.1 (already installed) | Async MongoDB for new collections | Already in use for all other collections |

[VERIFIED: pip registry] — `pipecat-ai`, `google-genai`, `pinecone`, `redis`, `langchain-text-splitters` all confirmed on PyPI.
[VERIFIED: codebase] — `pipecat-ai==0.0.108`, `redis>=4.2.0,<6`, `motor==3.3.2` (upgraded to 3.7.1 per Phase 12 decision) already in requirements.txt.

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `telnyx` (Python SDK) | Latest | Telnyx Call Control API for outbound calls | Replaces `twilio` SDK in initiate_call_v2; for `client.calls.create()` equivalent |
| `certifi` | Already installed | TLS certs for MongoDB | Already used in `database.py init_db` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Telnyx | Bandwidth | Bandwidth has NO native Pipecat serializer found; Telnyx has `TelnyxFrameSerializer` built into pipecat 0.0.108. Telnyx wins for this stack. |
| Pinecone | MongoDB Atlas Vector Search | Atlas Vector Search requires M10+ cluster ($57/mo); Pinecone Starter is $0. Budget constraint eliminates Atlas. |
| `langchain-text-splitters` | Hand-rolled character splitter | `RecursiveCharacterTextSplitter` from langchain-text-splitters is the spec requirement; package is lightweight (no LLM deps) |
| `redis.asyncio` | `aioredis` | `aioredis` is deprecated; `redis.asyncio` is the official async submodule since redis-py 4.2 |

**Installation (new packages only):**
```bash
pip install "pipecat-ai[google]" pinecone "pinecone[asyncio]" langchain-text-splitters telnyx
# google-genai is installed automatically via pipecat-ai[google]
```

---

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| `pipecat-ai` | PyPI | ~2 yrs | High (active) | github.com/pipecat-ai/pipecat | N/A (Python, npm check inapplicable) | Approved — already in requirements.txt |
| `google-genai` | PyPI | ~1 yr | High (Google official) | github.com/google-gemini/python-genai | SLOP on npm (Python-only — not a hallucination) | Approved — official Google SDK, exists on PyPI 2.8.0 [ASSUMED: not verified via Context7] |
| `pinecone` | PyPI + npm | ~5 yrs | Very high | github.com/pinecone-io/pinecone-python-client | [OK] on npm | Approved |
| `redis` | PyPI | ~10 yrs | Very high | github.com/redis/redis-py | [OK] on npm | Approved — already in requirements.txt |
| `langchain-text-splitters` | PyPI | ~2 yrs | High | github.com/langchain-ai/langchain | SLOP on npm (Python-only — not hallucinated) | Approved — exists on PyPI 1.1.2; distinct lightweight package from langchain |
| `telnyx` | PyPI | ~5 yrs | Moderate | github.com/team-telnyx/telnyx-python | N/A (Python, not checked on npm) | [ASSUMED] — must verify on PyPI before install |

**Packages removed due to slopcheck [SLOP] verdict:** none — slopcheck checks npm only; these are PyPI-only packages. False positives for Python packages.

**Packages flagged as suspicious:** `telnyx` Python SDK — [ASSUMED], confirm `pip index versions telnyx` returns results before adding to requirements.txt.

**Note on slopcheck:** Tool checks npm registry. All packages in this phase are Python (PyPI). The `[SLOP]` verdicts for `google-genai` and `langchain-text-splitters` are false positives — both confirmed on PyPI registry by `pip index versions`. The tool is not authoritative for Python packages.

---

## Architecture Patterns

### System Architecture Diagram

```
INBOUND/OUTBOUND CALL FLOW
===========================

[Telnyx PSTN] ──TeXML webhook──> [POST /api/cobranza/voice/webhook]
                                        │
                                  returns TeXML <Stream url="wss://...">
                                        │
[Telnyx] ──WebSocket audio──────> [WS /api/cobranza/voice/ws/{call_sid}]
                                        │
                                  parse_telephony_websocket()
                                        │
                          ┌─────────────▼──────────────────┐
                          │  Redis Cache: get tenant_config │ ← TTL 5min
                          │  MISS → MongoDB tenant_configs  │
                          └─────────────┬──────────────────┘
                                        │ system_prompt, model, tools_enabled
                          ┌─────────────▼──────────────────┐
                          │     Pipecat Pipeline           │
                          │  FastAPIWebsocketTransport      │
                          │  + TelnyxFrameSerializer        │
                          │  + GeminiLiveLLMService         │
                          │    (tools: end_call,            │
                          │     search_knowledge,           │
                          │     update_debtor,              │
                          │     send_whatsapp,              │
                          │     verify_identity,            │
                          │     escalate)                   │
                          └─────────────┬──────────────────┘
                                        │ tool calls
                          ┌─────────────▼──────────────────┐
                          │   CobranzaOrchestrator         │
                          │  ┌──────────────────────────┐  │
                          │  │ debtor_updater           │  │
                          │  │ whatsapp_notifier        │  │
                          │  │ identity_verifier        │  │
                          │  │ escalation_handler       │  │
                          │  └──────────────────────────┘  │
                          └─────────────┬──────────────────┘
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              [MongoDB]           [Pinecone]          [ARQ queue]
          (debtors, calls)    (rag namespace        (bulk_whatsapp
                               per user_id)          log_comm jobs)

CONFIG HOT-RELOAD FLOW
=======================

[Admin API: PATCH /api/cobranza/config/{user_id}]
                │
                ▼
        MongoDB tenant_configs.update_one()
                │
                ▼
        Redis: DEL tenant_config:{user_id}   ← IMMEDIATE invalidation
                │
        Next call picks up fresh config from MongoDB → caches for 5min
```

### Recommended Project Structure
```
backend/cobranza/
├── voice_pipecat.py          # MODIFIED: Telnyx transport + Gemini Live LLM
├── voice_router.py           # MODIFIED: Telnyx webhook + Telnyx SDK for outbound
├── voice_orchestrator.py     # KEEP (legacy fallback, not primary path)
├── cobranza_orchestrator.py  # NEW: CobranzaOrchestrator wrapping sub-agents
├── sub_agents/               # NEW
│   ├── __init__.py
│   ├── debtor_updater.py
│   ├── whatsapp_notifier.py
│   ├── identity_verifier.py
│   └── escalation_handler.py
└── config_cache.py           # NEW: Redis cache helper for tenant_configs

backend/
├── database.py               # MODIFIED: add init_indexes for 3 new collections
├── tenant_config_crud.py     # NEW: CRUD for tenant_configs + agent_instances + rag_documents
└── cobranza_rag.py           # NEW: Pinecone-backed RAG replacing rag.py cosine similarity
```

### Pattern 1: Tenant Config Hot-Reload via Redis Cache

**What:** `tenant_config:{user_id}` key in Redis caches the full config dict. Loaded at the start of each WebSocket call. On module toggle, immediately deleted.

**When to use:** At the start of every `voice_websocket()` handler and every sub-agent initialization.

**Example:**
```python
# Source: redis-py asyncio docs + project patterns
import json
import redis.asyncio as aioredis

_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(
            os.getenv("UPSTASH_REDIS_URL"),  # redis://:<token>@<host>.upstash.io:6379
            encoding="utf-8",
            decode_responses=True,
        )
    return _redis_client

async def get_tenant_config(user_id: str) -> dict:
    """Load tenant config with 5min TTL cache. Falls back to MongoDB on miss."""
    redis = await get_redis()
    key = f"tenant_config:{user_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    # Cache miss: load from MongoDB
    db = get_db()
    doc = await db.tenant_configs.find_one({"user_id": user_id}) or {}
    if doc:
        doc.pop("_id", None)
        await redis.setex(key, 300, json.dumps(doc))  # TTL = 5 minutes
    return doc

async def invalidate_tenant_config(user_id: str) -> None:
    """Immediate invalidation — call after any module toggle update."""
    redis = await get_redis()
    await redis.delete(f"tenant_config:{user_id}")
```

### Pattern 2: Telnyx Transport Swap (replaces TwilioFrameSerializer)

**What:** Replace `TwilioFrameSerializer` + `twilio.rest.Client` with `TelnyxFrameSerializer` + Telnyx Call Control API.

**Key difference from Twilio:** Telnyx WebSocket messages already contain `stream_id`, `call_control_id`, `from`, and `to` fields — no separate webhook state needed. Use `parse_telephony_websocket()` to extract.

**Example:**
```python
# Source: [CITED: docs.pipecat.ai/guides/telephony/telnyx-websockets]
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.transports.websocket.fastapi import FastAPIWebsocketTransport, FastAPIWebsocketParams
from pipecat.runner.utils import parse_telephony_websocket

@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    await websocket.accept()
    transport_type, call_data = await parse_telephony_websocket(websocket)
    
    stream_id = call_data["stream_id"]
    call_control_id = call_data["call_control_id"]
    
    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_in_sample_rate=8000,   # Telnyx uses 8kHz PCMU
            audio_out_sample_rate=8000,
            serializer=TelnyxFrameSerializer(
                stream_id=stream_id,
                outbound_encoding="PCMU",   # Telnyx default
                inbound_encoding="PCMU",
                call_control_id=call_control_id,
                api_key=os.getenv("TELNYX_API_KEY"),
            ),
        ),
    )
```

**TeXML webhook (replaces TwiML):**
```xml
<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="wss://yourhost/api/cobranza/voice/ws/{call_control_id}"
            bidirectionalMode="rtp" />
  </Connect>
  <Pause length="40"/>
</Response>
```

### Pattern 3: Gemini Live LLM Service (replaces OpenAIRealtimeLLMService)

**What:** Drop-in LLM replacement in the Pipecat pipeline. Requires `pip install "pipecat-ai[google]"` to install `google-genai`.

**Key difference:** Sample rate changes to 8000Hz (telephony); tools are passed as constructor param (same format as OpenAI function dicts).

**Example:**
```python
# Source: [CITED: docs.pipecat.ai/api-reference/server/services/s2s/gemini-live]
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService

llm = GeminiLiveLLMService(
    api_key=os.getenv("GOOGLE_API_KEY"),
    system_instruction=system_prompt,  # loaded from tenant_configs via Redis
    tools=[end_call_tool, search_knowledge_tool, update_debtor_tool, ...],
    params=GeminiLiveLLMService.InputParams(
        voice_id="Charon",            # or "Aoede", "Fenrir", etc.
        language_code="es-419",       # Colombian Spanish
    ),
)

# Function registration (same pattern as OpenAI Realtime)
llm.register_function("end_call", _handle_end_call, cancel_on_interruption=False)
llm.register_function("update_debtor", _handle_update_debtor)
```

**CRITICAL NOTE:** Pipecat 0.0.108 ships with GeminiLiveLLMService code but `google-genai` is not installed. Adding `pipecat-ai[google]` to requirements.txt installs it. The import `from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService` will fail at startup until `google-genai` is present.

### Pattern 4: Pinecone Namespace Isolation for RAG

**What:** One Pinecone index, one namespace per `user_id`. Queries in namespace `user_abc` never see vectors from `user_xyz`.

**Example:**
```python
# Source: [CITED: docs.pinecone.io/reference/sdks/python/overview]
from pinecone import Pinecone, ServerlessSpec
from pinecone.asyncio import AsyncPinecone   # pinecone[asyncio] extra

async def upsert_to_pinecone(user_id: str, vectors: list[dict]) -> None:
    """vectors = [{"id": "...", "values": [...1536 floats...], "metadata": {...}}]"""
    pc = AsyncPinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "cobranza-rag"))
    await index.upsert(vectors=vectors, namespace=user_id)

async def query_pinecone(user_id: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    pc = AsyncPinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "cobranza-rag"))
    result = await index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=user_id,
        include_metadata=True,
    )
    return result["matches"]
```

**Index creation (one-time setup, not per-tenant):**
```python
# text-embedding-3-small produces 1536-dimensional vectors
pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
if "cobranza-rag" not in [i.name for i in pc.list_indexes().indexes]:
    pc.create_index(
        name="cobranza-rag",
        dimension=1536,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),  # Starter tier
    )
```

### Pattern 5: MongoDB Schema for 3 New Collections

```python
# tenant_configs collection
{
    "user_id": "...",               # indexed unique
    "modules": {
        "voice": True,
        "whatsapp": True,
        "rag": False,
    },
    "language": "es-CO",
    "brand_name": "De Pe Ge Seguros",
    "voice_system_prompt": "Eres Camila...",  # hot-reload on next call
    "updated_at": datetime,
    "created_at": datetime,
}

# agent_instances collection
{
    "user_id": "...",               # indexed unique
    "model": "gemini-2.0-flash-exp",
    "temperature": 0.7,
    "tools_enabled": ["end_call", "update_debtor", "search_knowledge"],
    "prompt_history": [             # $slice to keep last 5
        {"version": 5, "prompt": "...", "updated_at": datetime},
        # ... max 5 entries
    ],
    "updated_at": datetime,
    "created_at": datetime,
}

# rag_documents collection
{
    "user_id": "...",               # indexed, not unique (N docs per user)
    "pinecone_namespace": "...",    # = user_id
    "filename": "...",
    "source_type": "pdf|url|text",
    "chunk_count": 12,
    "created_at": datetime,
}
```

**Indexes needed:**
```python
await _safe_index(db.tenant_configs, "user_id", unique=True)
await _safe_index(db.agent_instances, "user_id", unique=True)
await _safe_index(db.rag_documents, [("user_id", 1), ("filename", 1)])
await _safe_index(db.rag_documents, [("user_id", 1), ("created_at", -1)])
```

### Pattern 6: CobranzaOrchestrator (direct dispatch, NOT framework AgentOrchestrator)

**What:** The existing `framework/runner/orchestrator.py` AgentOrchestrator uses LLM-based routing (checks all agents, routes via LLM when multiple match). For cobranza, the voice agent calls specific tools directly — no routing ambiguity. Use direct function-dispatch pattern instead.

**Why not use AgentOrchestrator:** The framework orchestrator is designed for routing unknown requests to the best agent. CobranzaOrchestrator routes to predetermined handlers based on Gemini's tool call name. LLM-based routing adds latency that would violate the 500ms TTFB target.

```python
class CobranzaOrchestrator:
    """Direct-dispatch orchestrator for cobranza sub-agents.
    Each tool call from GeminiLiveLLMService is routed to its handler synchronously.
    Sub-agents are simple async functions, not full AgentRunner instances.
    """

    def __init__(self, user_id: str, tenant_config: dict):
        self.user_id = user_id
        self.config = tenant_config

    async def update_debtor(self, debtor_id: str, fields: dict) -> dict:
        """debtor_updater sub-agent"""
        ...

    async def send_whatsapp(self, phone: str, message: str) -> dict:
        """whatsapp_notifier sub-agent — enqueues ARQ job for async delivery"""
        ...

    async def verify_identity(self, utterance: str) -> dict:
        """identity_verifier sub-agent — pattern matching + LLM fallback"""
        ...

    async def escalate(self, reason: str) -> dict:
        """escalation_handler sub-agent"""
        ...
```

### Anti-Patterns to Avoid

- **Don't poll Redis to detect config changes:** Use immediate `redis.delete(key)` on every write to `tenant_configs`. The next request auto-loads from MongoDB and re-caches.
- **Don't use pipecat 0.0.108's GeminiLiveLLMService at 24kHz:** Telnyx uses 8kHz PCM (PCMU). Set `audio_in_sample_rate=8000` and `audio_out_sample_rate=8000`.
- **Don't upsert to Pinecone without namespace:** Default namespace is `""` — all tenants share it. Always pass `namespace=user_id`.
- **Don't use `$push` with `$slice` in mongomock:** Phase 16 decision. For prompt_history rotation: push first, then trim if len > 5 (separate update_one). Follows existing wa_sessions pattern.
- **Don't use `twilio.rest.Client` for hang-up in Gemini Live path:** The `end_call` function handler must use Telnyx Call Control API. The `TelnyxFrameSerializer` handles hang-up automatically when `api_key` is provided.
- **Don't import `google.genai` before `pipecat-ai[google]` is in requirements:** The module will fail at app startup with `Exception: Missing module: No module named 'google.genai'`. Confirm install in requirements.txt BEFORE the Wave 0 scaffold.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| RecursiveCharacterTextSplitter | Custom sentence-boundary splitter | `langchain-text-splitters` `RecursiveCharacterTextSplitter` | The recursive split with configurable separators handles edge cases (code, lists, bare text) correctly; hand-rolled character slice misses paragraph breaks |
| Audio serialization for Telnyx | Custom PCMU encoder | `TelnyxFrameSerializer` in pipecat 0.0.108 | Already handles PCMU encode/decode, resampling, and base64 framing |
| Gemini function call dispatch | Custom JSON parser | `llm.register_function()` in GeminiLiveLLMService | Handles tool call lifecycle (arguments parsing, result_callback, NON_BLOCKING semantics for Gemini 2.x) |
| Vector similarity search | Cosine similarity in Python (existing rag.py approach) | Pinecone query() | At scale, Python cosine over 1000+ chunks in MongoDB is O(N); Pinecone is O(1) approximate nearest neighbor |
| Cache invalidation strategy | Custom TTL tracking | `redis.setex(key, 300, val)` + `redis.delete(key)` | Two-operation pattern is the industry standard; no custom middleware needed |

**Key insight:** The existing `rag.py` cosine similarity approach works for prospecting (tens of chunks per user) but breaks for cobranza (hundreds of documents per debtor portfolio). Pinecone is the correct tool at cobranza scale.

---

## Common Pitfalls

### Pitfall 1: GeminiLiveLLMService NOT in pipecat-ai base install

**What goes wrong:** `from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService` raises `Exception: Missing module: No module named 'google.genai'` at app startup.

**Why it happens:** pipecat 0.0.108 ships the service code but `google-genai` is an optional dependency gated behind `pipecat-ai[google]`.

**How to avoid:** Add `"pipecat-ai[google]"` AND `google-genai` explicitly to requirements.txt (explicit version pin avoids future SDK breaking changes). Wave 0 must include this install step.

**Warning signs:** `ImportError` or `Exception: Missing module` in server startup logs.

---

### Pitfall 2: Telnyx audio sample rate mismatch

**What goes wrong:** Voice sounds distorted or silent. Bot receives garbled audio.

**Why it happens:** Telnyx PSTN telephony streams use 8kHz PCMU. The current `voice_pipecat.py` uses 24kHz (OpenAI Realtime native rate). Setting 24kHz with TelnyxFrameSerializer causes the resampler to produce corrupted audio.

**How to avoid:** Always configure `audio_in_sample_rate=8000` and `audio_out_sample_rate=8000` in `FastAPIWebsocketParams` when using TelnyxFrameSerializer. Also set `TelnyxFrameSerializer(outbound_encoding="PCMU", inbound_encoding="PCMU")`.

**Warning signs:** Call connects but only silence or noise; `[VOICE] ERROR in pipeline` logs.

---

### Pitfall 3: Long-running Gemini tools break tool response processing

**What goes wrong:** After a function call that takes >6-7 seconds, Gemini Live cannot process the tool result — user transcription finishes first and becomes the last message.

**Why it happens:** GitHub issue #1564 in pipecat repo. Gemini 2.x lacks NON_BLOCKING support for async tools.

**How to avoid:** Keep all sub-agent tool handlers under 3 seconds. For slow operations (bulk WhatsApp, complex DB writes): dispatch as ARQ job and return immediately. The tool response should acknowledge receipt, not wait for completion.

**Warning signs:** Bot goes silent after a tool call; no follow-up utterance after long tool execution.

---

### Pitfall 4: Pinecone namespace=None sends vectors to default namespace

**What goes wrong:** Tenant A's documents visible to Tenant B's queries.

**Why it happens:** Pinecone SDK v8+ changed namespace default behavior: when `namespace=None`, the parameter is omitted, which means the default (empty) namespace. All tenants without explicit namespace share the same vector space.

**How to avoid:** ALWAYS pass `namespace=user_id` in both `upsert()` and `query()`. Add a guard assertion in `cobranza_rag.py`: `assert user_id, "user_id required for Pinecone namespace isolation"`.

**Warning signs:** RAG retrieval returns results from other tenants' documents.

---

### Pitfall 5: Redis connection for Upstash requires SSL

**What goes wrong:** `redis.asyncio.from_url("redis://...")` fails or hangs when pointing to Upstash.

**Why it happens:** Upstash requires SSL (`rediss://` not `redis://`). The standard Railway Redis uses plain `redis://`, but Upstash always requires TLS.

**How to avoid:** Use `rediss://` (double-s) for Upstash. Or use `redis.asyncio.from_url(url, ssl_cert_reqs=None)` for local dev where URL is plain redis://.

**Warning signs:** `ConnectionError` or timeout when first trying to hit Redis cache.

---

### Pitfall 6: Framework AgentOrchestrator LLM routing adds 200-500ms overhead

**What goes wrong:** CobranzaOrchestrator using `AgentOrchestrator.dispatch()` fails TTFB <500ms target because routing decision itself requires an LLM call.

**Why it happens:** `AgentOrchestrator._check_all_capabilities()` calls all registered agents in parallel, then routes via LLM. This is designed for unknown request routing, not predetermined tool dispatch.

**How to avoid:** Implement `CobranzaOrchestrator` as a direct-dispatch class (Pattern 6 above). Sub-agents are plain async functions, not AgentRunner instances. Reserve `AgentOrchestrator` for the prospecting pipeline where it was designed.

---

## Code Examples

### Loading system_prompt from tenant_configs (hot-reload pattern)

```python
# Source: [ASSUMED] — based on project patterns in database.py + voice_pipecat.py
async def run_bot(websocket, call_sid: str, debtor: dict) -> CallResult:
    user_id = debtor["user_id"]
    
    # Hot-reload: fetch from Redis cache (5min TTL), fall back to MongoDB
    tenant_config = await get_tenant_config(user_id)
    
    # Check module enabled — immediate Redis invalidation means this is always fresh
    if not tenant_config.get("modules", {}).get("voice", True):
        await websocket.close(1008, "Voice module disabled")
        return CallResult()
    
    system_prompt = tenant_config.get("voice_system_prompt") or DEFAULT_SYSTEM_PROMPT
    brand_name = tenant_config.get("brand_name", "nuestra empresa")
    
    # Simple string.replace() per locked decision (no template engine)
    system_prompt = system_prompt.replace("{brand_name}", brand_name)
    system_prompt = system_prompt.replace("{debtor_name}", debtor.get("nombre", ""))
```

### Prompt history rotation (last 5 versions, no $push $slice in mongomock)

```python
# Source: [ASSUMED] — follows Phase 16 pattern for wa_sessions history trimming
async def update_agent_prompt(user_id: str, new_prompt: str) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    new_entry = {"version": now.timestamp(), "prompt": new_prompt, "updated_at": now}
    # Push new entry
    await db.agent_instances.update_one(
        {"user_id": user_id},
        {"$push": {"prompt_history": new_entry}, "$set": {"updated_at": now}},
        upsert=True,
    )
    # Trim to last 5 (separate op — mongomock does not support $push $slice in single op)
    doc = await db.agent_instances.find_one({"user_id": user_id})
    if doc and len(doc.get("prompt_history", [])) > 5:
        trimmed = doc["prompt_history"][-5:]
        await db.agent_instances.update_one(
            {"user_id": user_id},
            {"$set": {"prompt_history": trimmed}},
        )
    # Invalidate Redis cache
    await invalidate_tenant_config(user_id)
```

### RecursiveCharacterTextSplitter for RAG ingestion

```python
# Source: [CITED: PyPI langchain-text-splitters]
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_text_for_rag(text: str) -> list[str]:
    """Semantic chunking per RESEARCH locked decision: chunk_size=1000, overlap=100."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    return splitter.split_text(text)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Twilio TwilioFrameSerializer | TelnyxFrameSerializer (pipecat) | pipecat 0.0.108 (already installed) | Native serializer; no custom adapter needed |
| OpenAIRealtimeLLMService | GeminiLiveLLMService | pipecat 0.0.108+ | Requires `pipecat-ai[google]` extra; same `register_function()` API |
| Assembly AI STT (separate) | Gemini Live built-in STT | Gemini 2.0 Flash | Eliminates Assembly AI client; single API handles STT+LLM+TTS |
| aioredis (deprecated) | redis.asyncio (redis-py 4.2+) | redis-py 4.2 | No separate install; same async API |
| pinecone-client (old name) | pinecone (v5.1.0+) | 2024 | Package rename; uninstall old before installing new |
| Custom cosine similarity (rag.py) | Pinecone query() | Phase 25 | Scales to millions of vectors; namespace isolation built-in |

**Deprecated/outdated:**
- `aioredis` package: Deprecated. Use `redis.asyncio` submodule from `redis-py` (already installed at 5.3.1)
- `google-generativeai` package: Deprecated in favor of `google-genai` (new unified SDK)
- `pinecone-client` package: Renamed to `pinecone` since v5.1.0. Never install `pinecone-client`.
- `TwilioFrameSerializer` + `twilio.rest.Client`: Replaced by `TelnyxFrameSerializer` + Telnyx SDK

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pipecat-ai[google]` extra installs `google-genai` as dependency | Standard Stack | Planner adds wrong install command; blocked until confirmed |
| A2 | Telnyx Python SDK package name is `telnyx` on PyPI | Standard Stack | Wrong pip install; must verify `pip index versions telnyx` |
| A3 | Gemini Live voice_id `"Charon"` supports `language_code="es-419"` (Colombian Spanish) | Code Examples | Bot speaks English; must test voice+language combo before production |
| A4 | Pinecone Starter tier supports 10,000 namespaces (one per tenant) | Standard Stack | Hitting namespace limit with >10k tenants (not a concern for MVP scale) |
| A5 | `GeminiLiveLLMService.InputParams` is the correct params class name in 0.0.108 | Code Examples | ImportError at startup; verify against pipecat source at install time |
| A6 | Telnyx `parse_telephony_websocket()` is available in pipecat 0.0.108 | Pattern 2 | Not found at import; check if `from pipecat.runner.utils import parse_telephony_websocket` works in installed version |

---

## Open Questions

1. **`parse_telephony_websocket` in pipecat 0.0.108**
   - What we know: Documented in Telnyx guide
   - What's unclear: Whether this utility exists in the currently-installed 0.0.108 or was added in a later version
   - Recommendation: Wave 0 task must import and verify `from pipecat.runner.utils import parse_telephony_websocket` before building the Telnyx endpoint

2. **Gemini Live latency on Telnyx audio (8kHz PCMU vs 24kHz)**
   - What we know: OpenAI Realtime runs at 24kHz; Gemini Live architecture not fully documented for telephony sample rates
   - What's unclear: Whether 8kHz input significantly degrades Gemini Live speech recognition quality
   - Recommendation: Include a latency measurement task in Wave 1 — if TTFB >500ms on Telnyx, fallback is keeping OpenAI Realtime for voice and only swapping the transport

3. **Telnyx Python SDK for outbound calls**
   - What we know: Telnyx Call Control API uses REST; Python SDK likely mirrors Twilio SDK structure
   - What's unclear: Exact method signature for `client.calls.create()` equivalent in Telnyx SDK
   - Recommendation: Check Telnyx Python SDK docs before writing `initiate_call_v2`; the pattern is `telnyx.Call.create(connection_id=..., to=..., from_=..., webhook_url=...)`

4. **Pinecone Starter index region for Colombia/Mexico latency**
   - What we know: Starter tier available on AWS us-east-1
   - What's unclear: Whether Pinecone Starter supports region selection or only us-east-1
   - Recommendation: Start with us-east-1; measure query latency from Railway (likely US region); acceptable for RAG which is pre-call, not during-call

---

## Open Questions (RESOLVED)

| # | Question | Status | Resolution |
|---|----------|--------|------------|
| Q1 |  in pipecat 0.0.108 | **RESOLVED** | Plan 25-03 includes a Wave 0 verification task:  is imported and tested before building the endpoint. If the import fails, fallback is calling  directly without the utility (no blocking dependency). |
| Q2 | Gemini Live latency on Telnyx 8kHz audio | OPEN | Latency measurement deferred to post-Wave-1 testing. Fallback documented: keep OpenAI Realtime if TTFB >500ms. |
| Q3 | Telnyx Python SDK outbound call signature | **RESOLVED-DEFERRED** | Plan 25-03 Wave 0 task verifies the SDK signature () before writing . If the SDK signature differs, the task documents the correct form in 25-03-SUMMARY.md before implementation. |
| Q4 | Pinecone Starter region for LATAM latency | OPEN | Accepted: start with us-east-1; measure in production. |

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pipecat-ai | Voice pipeline | ✓ | 0.0.108 | — |
| pipecat-ai[google] | GeminiLiveLLMService | ✗ (google extra not installed) | — | Add to requirements.txt; pip install |
| google-genai | GeminiLiveLLMService | ✗ | — | Installed by pipecat-ai[google] |
| redis (redis.asyncio) | Cache layer | ✓ | 5.3.1 | — |
| pinecone | RAG vector store | ✗ | — | Add `pinecone` to requirements.txt |
| langchain-text-splitters | RecursiveCharacterTextSplitter | ✗ | — | Add to requirements.txt |
| telnyx Python SDK | Outbound call initiation | ✗ | — | Add to requirements.txt (verify name first) |
| GOOGLE_API_KEY env var | GeminiLiveLLMService | ✗ (not in codebase) | — | New env var required |
| TELNYX_API_KEY env var | TelnyxFrameSerializer + outbound | ✗ | — | New env var; replaces TWILIO_* |
| PINECONE_API_KEY env var | Pinecone client | ✗ | — | New env var required |
| UPSTASH_REDIS_URL env var | Cache layer | ✗ (REDIS_URL exists) | — | REDIS_URL for local dev; UPSTASH_REDIS_URL for production |

**Missing dependencies with no fallback (block execution):**
- `pipecat-ai[google]` + `google-genai` — required for VOICE-02; must be in requirements.txt before any voice testing
- `GOOGLE_API_KEY` — must be provisioned in Railway environment

**Missing dependencies with fallback:**
- `UPSTASH_REDIS_URL` — can use existing `REDIS_URL` (Railway Redis) for development; Upstash for production toggle-invalidation testing

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pytest.ini (exists) |
| Quick run command | `pytest backend/tests/test_cobranza_phase25.py -x` |
| Full suite command | `pytest backend/tests/ -x --timeout=30` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-CFG-01 | tenant_configs upsert + hot-reload | unit | `pytest tests/test_cobranza_phase25.py::test_tenant_config_hot_reload -x` | Wave 0 |
| AGENT-CFG-02 | Redis cache TTL + immediate invalidation | unit | `pytest tests/test_cobranza_phase25.py::test_cache_invalidation -x` | Wave 0 |
| AGENT-CFG-03 | CobranzaOrchestrator sub-agent dispatch | unit | `pytest tests/test_cobranza_phase25.py::test_orchestrator_dispatch -x` | Wave 0 |
| VOICE-01 | TelnyxFrameSerializer import + serializer roundtrip | unit | `pytest tests/test_cobranza_phase25.py::test_telnyx_serializer -x` | Wave 0 |
| VOICE-02 | GeminiLiveLLMService import (requires google-genai) | smoke | `pytest tests/test_cobranza_phase25.py::test_gemini_live_import -x` | Wave 0 |
| RAG-01 | rag_documents collection CRUD + Pinecone namespace isolation | unit | `pytest tests/test_cobranza_phase25.py::test_rag_namespace_isolation -x` | Wave 0 |
| RAG-02 | search_client_knowledge returns results only for querying tenant | unit | `pytest tests/test_cobranza_phase25.py::test_search_knowledge_tenant_isolation -x` | Wave 0 |
| CACHE-01 | toggle voice=false → next call blocked within 1 request | integration | `pytest tests/test_cobranza_phase25.py::test_module_toggle_cache -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest backend/tests/test_cobranza_phase25.py -x`
- **Per wave merge:** `pytest backend/tests/ -x --timeout=30`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `backend/tests/test_cobranza_phase25.py` — 8 xfail stubs (2 per req: happy-path + error-path), strict=False, lazy imports per Phase 17/18/23 pattern
- [ ] New env vars in `.env.example`: `GOOGLE_API_KEY`, `TELNYX_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `UPSTASH_REDIS_URL`

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Existing JWT (Auth-03) guards all endpoints |
| V3 Session Management | no | Voice session tied to call_sid; no session tokens issued |
| V4 Access Control | yes | `tenant_config:{user_id}` MUST only be writable by the authenticated user; POST /config endpoint must use `Depends(get_current_user)` |
| V5 Input Validation | yes | system_prompt input must be sanitized (max length, no injection); Pydantic model for config PATCH |
| V6 Cryptography | no | API keys stored as env vars (not in DB); no new crypto needed |

### Known Threat Patterns for this Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Cross-tenant config write | Elevation of Privilege | Enforce `user_id == current_user["user_id"]` in all PATCH config endpoints |
| Prompt injection via voice_system_prompt | Tampering | Max length validation (2000 chars); disallow `<|` or `[INST]` style markers |
| Pinecone namespace bypass | Elevation of Privilege | Assert `namespace == user_id` in RAG helpers; never accept namespace from HTTP request |
| Redis key collision | Spoofing | Key format `tenant_config:{user_id}` — user_id is MongoDB ObjectId string, no collision possible |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: codebase] `backend/requirements.txt` — pipecat-ai==0.0.108, redis>=4.2.0, motor, confirmed installed
- [VERIFIED: codebase] `pipecat.serializers.*` module list — confirmed via Python import: `['base_serializer', 'exotel', 'genesys', 'plivo', 'protobuf', 'telnyx', 'twilio', 'vonage']`
- [VERIFIED: codebase] `TelnyxFrameSerializer.__init__` signature — `(stream_id, outbound_encoding, inbound_encoding, call_control_id=None, api_key=None, params=None)`
- [CITED: docs.pipecat.ai/guides/telephony/telnyx-websockets] — Telnyx TeXML + WebSocket integration guide
- [CITED: docs.pipecat.ai/api-reference/server/services/s2s/gemini-live] — GeminiLiveLLMService constructor signature and tools support
- [CITED: docs.pinecone.io] — Pinecone namespace isolation; max 10,000 namespaces on Starter; upsert/query API
- [VERIFIED: pip registry] — `pinecone==9.1.0`, `google-genai==2.8.0`, `langchain-text-splitters==1.1.2` confirmed on PyPI

### Secondary (MEDIUM confidence)
- [CITED: github.com/pipecat-ai/pipecat issue #1564] — Long-running Gemini tools break tool response processing (>6-7 seconds)
- [CITED: telnyx.com/release-notes/pstn-replacement-latam] — Telnyx PSTN support for Colombia and Mexico
- [CITED: redis-py docs] — `redis.asyncio` available since redis-py 4.2; `setex()` + `delete()` for cache invalidation

### Tertiary (LOW confidence)
- [ASSUMED] Telnyx outbound calling costs 40-60% less than Twilio (from phase description; not independently verified)
- [ASSUMED] Gemini Live TTFB <500ms on Telnyx 8kHz telephony (plausible but not benchmarked in this environment)

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all packages confirmed on PyPI; pipecat serializer confirmed in codebase
- Telnyx transport: HIGH — TelnyxFrameSerializer confirmed in pipecat 0.0.108; integration pattern from official docs
- Gemini Live: MEDIUM — constructor signature from official docs; pipecat 0.0.108 has the code but requires `[google]` extra
- Pinecone RAG: MEDIUM — SDK confirmed on PyPI; async client from official docs (404 on direct asyncio page)
- Redis cache: HIGH — redis-py 5.3.1 already installed; `redis.asyncio` confirmed standard
- Sub-agent pattern: HIGH — direct dispatch pattern confirmed better than AgentOrchestrator for this use case

**Research date:** 2026-06-10
**Valid until:** 2026-07-10 (pipecat releases rapidly; verify GeminiLiveLLMService API before coding)
