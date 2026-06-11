---
phase: 25
plan: 01
subsystem: backend/cobranza
tags: [mongodb, redis, cache, tenant-config, tdd, phase-25]
dependency_graph:
  requires: []
  provides:
    - cobranza.config_cache (get_redis, get_tenant_config, invalidate_tenant_config)
    - cobranza.tenant_config (upsert_tenant_config, get_tenant_config_doc, toggle_module, upsert_agent_instance, append_prompt_version, save_rag_document_metadata, get_rag_documents)
    - tenant_configs / agent_instances / rag_documents MongoDB collections with indexes
  affects:
    - backend/database.py (4 new indexes in init_db)
    - backend/requirements.txt (fakeredis, pinecone, telnyx, google-genai, langchain-text-splitters)
tech_stack:
  added:
    - redis.asyncio (5-min TTL cache, immediate invalidation)
    - fakeredis (in-memory Redis for CI tests)
    - pinecone>=9.1.0 (per-tenant RAG vector store — consumed in 25-04)
    - telnyx (telephony — consumed in 25-03)
    - google-genai>=2.8.0 (Gemini Live — consumed in 25-03)
    - langchain-text-splitters>=1.1.2 (RAG chunking — consumed in 25-04)
  patterns:
    - Read-through Redis cache with setex(300) TTL
    - Immediate cache invalidation on every write (CACHE-01 contract)
    - Two-op trim for prompt_history (no $slice — mongomock constraint from Phase 16)
    - Lazy fakeredis monkeypatching for CI Redis isolation
key_files:
  created:
    - backend/cobranza/config_cache.py
    - backend/cobranza/tenant_config.py
    - backend/tests/test_cobranza_phase25.py
  modified:
    - backend/database.py (4 new _safe_index calls in init_db)
    - backend/requirements.txt (fakeredis + 5 Phase 25 deps)
    - backend/.env.example (7 new env var keys documented)
decisions:
  - "fakeredis used for CI Redis isolation — no real Redis needed for cache tests (monkeypatch _redis_client sentinel)"
  - "append_prompt_version uses two-op trim (push then read+trim) — $slice not used (mongomock constraint, Phase 16 decision)"
  - "config_cache._invalidate() swallows Redis errors — CRUD must not fail because of cache unavailability"
  - "telnyx pinned (verified via pip index versions: 4.153.0 latest, legitimate package)"
metrics:
  duration: "~35 minutes"
  completed: "2026-06-10"
  tasks_completed: 3
  files_created: 3
  files_modified: 3
requirements_fulfilled: [AGENT-CFG-01, AGENT-CFG-02, CACHE-01]
---

# Phase 25 Plan 01: Multi-Tenant Config Foundation Summary

**One-liner:** MongoDB CRUD + Redis 5-min TTL read-through cache with immediate write invalidation for per-tenant agent config.

## What Was Built

Three new MongoDB collections with unique-user_id indexes, a CRUD module enforcing tenant isolation, and a Redis cache layer providing 300s TTL reads with cache-key deletion on every config write or module toggle.

### Files Created

| File | Purpose |
|------|---------|
| `backend/cobranza/config_cache.py` | Redis helpers: `get_redis` (lazy), `get_tenant_config` (read-through, 300s), `invalidate_tenant_config` (delete key) |
| `backend/cobranza/tenant_config.py` | CRUD: `upsert_tenant_config`, `get_tenant_config_doc`, `toggle_module`, `upsert_agent_instance`, `append_prompt_version` (two-op trim), `save_rag_document_metadata`, `get_rag_documents` |
| `backend/tests/test_cobranza_phase25.py` | 13 tests: 8 pass (6 CRUD + 2 cache) + 5 xfail stubs (Wave 2-4) |

### Files Modified

| File | Change |
|------|--------|
| `backend/database.py` | Added 4 Phase 25 `_safe_index` calls in `init_db`: `tenant_configs.user_id unique`, `agent_instances.user_id unique`, `rag_documents (user_id+filename)`, `rag_documents (user_id+created_at desc)` |
| `backend/requirements.txt` | Added `fakeredis`, `pinecone>=9.1.0`, `pinecone[asyncio]`, `langchain-text-splitters>=1.1.2`, `telnyx`, `google-genai>=2.8.0`, `pipecat-ai[google]` |
| `backend/.env.example` | Documented 7 new env vars: `GOOGLE_API_KEY`, `TELNYX_API_KEY`, `TELNYX_CONNECTION_ID`, `TELNYX_VOICE_PHONE_NUMBER`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `UPSTASH_REDIS_URL` |

## Commits

| Hash | Message |
|------|---------|
| `3addaae1` | feat(25-01): add Phase 25 deps, env vars, and xfail test scaffold |
| `c56513cd` | test(25-01): RED — add failing CRUD + hot-reload tests for tenant_config |
| `3d37c10c` | feat(25-01): implement tenant_config CRUD + 4 new MongoDB indexes |
| `4644d5b8` | test(25-01): RED — add failing cache invalidation tests + fakeredis dep |
| `511d8bb0` | feat(25-01): implement Redis config cache with 5min TTL + immediate invalidation |

## Test Results

```
8 passed, 5 xfailed, 4 warnings
```

- `test_tenant_config_upsert_and_read` — PASSED
- `test_agent_instance_upsert_and_read` — PASSED
- `test_prompt_history_capped_at_5` — PASSED
- `test_rag_document_metadata_save_and_read` — PASSED
- `test_toggle_module_persists` — PASSED
- `test_tenant_config_hot_reload` — PASSED
- `test_cache_invalidation` — PASSED (fakeredis monkeypatch)
- `test_module_toggle_cache` — PASSED (fakeredis monkeypatch)
- `test_orchestrator_dispatch` — XFAIL (Wave 2 stub)
- `test_telnyx_serializer` — XFAIL (Wave 3 stub)
- `test_gemini_live_import` — XFAIL (Wave 3 stub)
- `test_rag_namespace_isolation` — XFAIL (Wave 4 stub)
- `test_search_knowledge_tenant_isolation` — XFAIL (Wave 4 stub)

## TDD Gate Compliance

Plan type is `execute` (not `tdd`), but tasks 2 and 3 have `tdd="true"`. Both followed RED/GREEN cycle:

- Task 2: RED commit `c56513cd` → GREEN commit `3d37c10c`
- Task 3: RED commit `4644d5b8` → GREEN commit `511d8bb0`

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Test Dependency] Added fakeredis to requirements.txt**
- **Found during:** Task 3 (cache tests needed in-memory Redis)
- **Issue:** Test plan required Redis mocking but no fake Redis package was present
- **Fix:** Installed `fakeredis>=2.20.0` and added to requirements.txt; monkeypatched `_redis_client` module sentinel for CI isolation
- **Files modified:** `backend/requirements.txt`
- **Commit:** `4644d5b8`

**2. [Rule 2 - Missing Critical Guard] invalidate_tenant_config swallows errors**
- **Found during:** Task 3 implementation review
- **Issue:** If Redis is unavailable, a cache invalidation failure would propagate up and break CRUD writes — CRUD must not depend on Redis availability
- **Fix:** `_invalidate()` helper wraps the call in try/except, logs warning, does not raise
- **Files modified:** `backend/cobranza/tenant_config.py`
- **Commit:** `3d37c10c`

## Threat Surface Scan

No new network endpoints, auth paths, or schema changes at external trust boundaries introduced in this plan. All new collections are internal MongoDB writes. Redis key namespace (`tenant_config:{user_id}`) uses MongoDB ObjectId strings — no collision risk (T-25-01 accepted).

## Known Stubs

None — all implemented functions are fully wired. The 5 xfail stubs in the test file are Wave 2-4 placeholders (not stubs in the UI-rendering sense; they have no data rendered to users).

## Self-Check: PASSED
