# Phase 25: Validation Architecture

Extraído de RESEARCH.md — sección "Validation Architecture".

---

## Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | pytest.ini (exists) |
| Quick run command | `pytest backend/tests/test_cobranza_phase25.py -x` |
| Full suite command | `pytest backend/tests/ -x --timeout=30` |

---

## Dimensiones de Validación

### 1. MongoDB Schema Correctness

- `tenant_configs` upsert por `user_id` retorna los mismos campos al leerlo de vuelta.
- `agent_instances.prompt_history` nunca supera 5 entradas (two-op trim, sin `$slice`).
- `rag_documents` registra `pinecone_namespace == user_id` en cada inserción.
- Todos los `find`/`update` en `tenant_config.py` incluyen `"user_id"` en el filtro.

### 2. Redis Cache Invalidation Timing

- `get_tenant_config(user_id)` retorna valor cacheado con TTL 300s en Redis hit.
- Tras `invalidate_tenant_config(user_id)`, la siguiente llamada a `get_tenant_config` recarga desde MongoDB (Redis miss).
- `upsert_tenant_config()` DEBE llamar `invalidate_tenant_config(user_id)` al final de cada write exitoso.
  - Criterio de aceptación: después de `upsert_tenant_config()`, `redis.get(f'tenant_config:{user_id}')` retorna `None`.
- `toggle_module(user_id, module, enabled)` llama `invalidate_tenant_config(user_id)` inmediatamente después del write.

### 3. Pinecone Namespace Isolation

- Upsert y query siempre reciben `namespace=user_id` — nunca `None` ni namespace vacío.
- Un query con `namespace="user_a"` no retorna resultados de `namespace="user_b"`.
- Guard assertion en `cobranza_rag.py`: `assert user_id, "user_id required for Pinecone namespace isolation"`.

### 4. Telnyx / Gemini Live TTFB < 500ms

- TTFB medido desde recepción del primer paquete de audio hasta primer audio de respuesta del bot.
- Objetivo: < 500ms para cumplir VOICE-02.
- Si TTFB > 500ms con Telnyx 8kHz, escalation: conservar OpenAI Realtime como fallback (ver Open Questions Q2).

### 5. Tenant Isolation (no cross-tenant data)

- `log_debtor_communication` ARQ job filtra por `{"_id": oid, "user_id": user_id}` en `db.debtors.update_one` — retorna `{"ok": False}` si no hay match.
- Todos los endpoints `/api/tenant/*` derivan `user_id` de `Depends(get_current_user)`, nunca del request body.
- `get_rag_documents(user_id)` siempre filtra por `user_id`.

---

## Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| AGENT-CFG-01 | tenant_configs upsert + hot-reload | unit | `pytest tests/test_cobranza_phase25.py::test_tenant_config_hot_reload -x` | Wave 0 |
| AGENT-CFG-02 | Redis cache TTL + immediate invalidation | unit | `pytest tests/test_cobranza_phase25.py::test_cache_invalidation -x` | Wave 0 |
| AGENT-CFG-03 | CobranzaOrchestrator sub-agent dispatch | unit | `pytest tests/test_cobranza_phase25.py::test_orchestrator_dispatch -x` | Wave 0 |
| VOICE-01 | TelnyxFrameSerializer import + serializer roundtrip | unit | `pytest tests/test_cobranza_phase25.py::test_telnyx_serializer -x` | Wave 0 |
| VOICE-02 | GeminiLiveLLMService import (requires google-genai) | smoke | `pytest tests/test_cobranza_phase25.py::test_gemini_live_import -x` | Wave 0 |
| RAG-01 | rag_documents collection CRUD + Pinecone namespace isolation | unit | `pytest tests/test_cobranza_phase25.py::test_rag_namespace_isolation -x` | Wave 0 |
| RAG-02 | search_client_knowledge retorna resultados solo del tenant consultante | unit | `pytest tests/test_cobranza_phase25.py::test_search_knowledge_tenant_isolation -x` | Wave 0 |
| CACHE-01 | toggle voice=false → próxima llamada bloqueada en 1 request | integration | `pytest tests/test_cobranza_phase25.py::test_module_toggle_cache -x` | Wave 0 |

---

## Sampling Rate

- **Por task commit:** `pytest backend/tests/test_cobranza_phase25.py -x`
- **Por wave merge:** `pytest backend/tests/ -x --timeout=30`
- **Phase gate:** Suite completa en verde antes de `/gsd-verify-work`

---

## Wave 0 Gaps

- [ ] `backend/tests/test_cobranza_phase25.py` — 8 xfail stubs (2 por req: happy-path + error-path), strict=False, lazy imports per Phase 17/18/23 pattern
- [ ] Nuevas env vars en `.env.example`: `GOOGLE_API_KEY`, `TELNYX_API_KEY`, `PINECONE_API_KEY`, `PINECONE_INDEX_NAME`, `UPSTASH_REDIS_URL`
