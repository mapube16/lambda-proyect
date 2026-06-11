"""
test_cobranza_phase25.py — Phase 25: Agentic Multi-Tenant Architecture.
Nyquist xfail scaffold: 8 stubs covering AGENT-CFG-01, AGENT-CFG-02, CACHE-01
and the remaining Phase 25 waves (voice, sub-agents, RAG).

All stubs raise NotImplementedError (Phase 14 convention).
Stubs will be promoted to real tests as each wave lands.
"""
import pytest
import pytest_asyncio
import database
from mongomock_motor import AsyncMongoMockClient


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def reset_db():
    """Fresh in-memory MongoDB per test — mirrors test_cobranza.py pattern."""
    mock_client = AsyncMongoMockClient()
    await database.init_db(client=mock_client)
    yield
    await database.get_db().users.drop()


@pytest_asyncio.fixture
async def async_client():
    """HTTP test client — lazy import avoids startup-time side-effects."""
    from main import app
    from httpx import AsyncClient, ASGITransport
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


# ── xfail stubs — AGENT-CFG-01 / CACHE-01 ────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_config_hot_reload():
    """
    Verify that a config write is immediately visible on the next read
    (hot-reload contract: no stale cache after toggle).
    After upsert_tenant_config + toggle_module, get_tenant_config_doc reflects change.
    """
    from cobranza.tenant_config import upsert_tenant_config, get_tenant_config_doc, toggle_module
    user_id = "user_hot_reload"
    await upsert_tenant_config(user_id, {"business_name": "Acme", "modules": {"voice": True}})
    await toggle_module(user_id, "voice", False)
    doc = await get_tenant_config_doc(user_id)
    assert doc is not None
    assert doc["modules"]["voice"] is False


@pytest.mark.asyncio
async def test_cache_invalidation(monkeypatch):
    """
    After upsert_tenant_config(), Redis key tenant_config:{user_id} must be absent
    (CACHE-01: immediate invalidation on every successful write).
    Uses fakeredis as in-memory Redis substitute (no real Redis needed in CI).
    """
    import fakeredis.aioredis as fakeredis
    import cobranza.config_cache as cc

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cc, "_redis_client", fake)

    from cobranza.tenant_config import upsert_tenant_config
    from cobranza.config_cache import get_tenant_config, invalidate_tenant_config

    user_id = "user_cache_inv_test"
    # Pre-populate the cache with a stale value
    import json
    await fake.setex(f"tenant_config:{user_id}", 300, json.dumps({"stale": True}))

    # Write config — must invalidate cache
    await upsert_tenant_config(user_id, {"business_name": "Fresh"})

    # Key must be absent after write
    cached = await fake.get(f"tenant_config:{user_id}")
    assert cached is None, f"Expected cache key to be deleted, got: {cached}"


# ── Task 2 CRUD tests ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_tenant_config_upsert_and_read():
    """upsert_tenant_config persists fields; get_tenant_config_doc returns them."""
    from cobranza.tenant_config import upsert_tenant_config, get_tenant_config_doc
    user_id = "user_upsert_test"
    await upsert_tenant_config(user_id, {"business_name": "TestCorp", "timezone": "UTC"})
    doc = await get_tenant_config_doc(user_id)
    assert doc is not None
    assert doc["business_name"] == "TestCorp"
    assert doc["user_id"] == user_id
    assert "_id" in doc  # serialized to str


@pytest.mark.asyncio
async def test_agent_instance_upsert_and_read():
    """upsert_agent_instance persists model/temperature; get_agent_instance returns them."""
    from cobranza.tenant_config import upsert_agent_instance, get_agent_instance
    user_id = "user_agent_test"
    await upsert_agent_instance(user_id, {"model": "gemini-2.0-flash-live-001", "temperature": 0.7})
    inst = await get_agent_instance(user_id)
    assert inst is not None
    assert inst["model"] == "gemini-2.0-flash-live-001"
    assert inst["user_id"] == user_id


@pytest.mark.asyncio
async def test_prompt_history_capped_at_5():
    """append_prompt_version keeps at most 5 entries; after 7 calls length == 5."""
    from cobranza.tenant_config import upsert_agent_instance, append_prompt_version, get_agent_instance
    user_id = "user_prompt_cap"
    await upsert_agent_instance(user_id, {"model": "gemini-2.0-flash-live-001", "temperature": 0.5})
    for i in range(7):
        await append_prompt_version(user_id, "cobranza", f"prompt version {i}")
    inst = await get_agent_instance(user_id)
    history = inst.get("prompt_history", [])
    assert len(history) == 5
    # Last 5 in order: versions 2 through 6
    assert history[-1]["prompt"] == "prompt version 6"
    assert history[0]["prompt"] == "prompt version 2"


@pytest.mark.asyncio
async def test_rag_document_metadata_save_and_read():
    """save_rag_document_metadata inserts doc; get_rag_documents returns it for correct user."""
    from cobranza.tenant_config import save_rag_document_metadata, get_rag_documents
    user_id = "user_rag_test"
    inserted_id = await save_rag_document_metadata(user_id, "manual.pdf", "pdf", 42)
    assert inserted_id is not None
    docs = await get_rag_documents(user_id)
    assert len(docs) == 1
    assert docs[0]["filename"] == "manual.pdf"
    assert docs[0]["pinecone_namespace"] == user_id
    # Tenant isolation: another user gets empty list
    other_docs = await get_rag_documents("other_user")
    assert other_docs == []


@pytest.mark.asyncio
async def test_toggle_module_persists():
    """toggle_module upserts modules.{module}; subsequent read reflects change."""
    from cobranza.tenant_config import upsert_tenant_config, toggle_module, get_tenant_config_doc
    user_id = "user_toggle_test"
    await upsert_tenant_config(user_id, {"business_name": "Toggle Inc"})
    await toggle_module(user_id, "voice", False)
    doc = await get_tenant_config_doc(user_id)
    assert doc["modules"]["voice"] is False
    await toggle_module(user_id, "voice", True)
    doc2 = await get_tenant_config_doc(user_id)
    assert doc2["modules"]["voice"] is True


# ── Wave 2: sub-agents + CobranzaOrchestrator ────────────────────────────────

@pytest.mark.asyncio
async def test_debtor_updater_cross_tenant_blocked():
    """debtor_updater: updating a debtor with a different user_id returns ok=False."""
    from cobranza.sub_agents.debtor_updater import update_debtor_status
    db = database.get_db()
    owner_user = "user_A"
    attacker_user = "user_B"
    result = await db.debtors.insert_one(
        {"user_id": owner_user, "nombre": "Carlos", "estado": "pendiente", "monto": 100.0}
    )
    debtor_id = str(result.inserted_id)
    # Attacker tries to update owner's debtor
    resp = await update_debtor_status(db, attacker_user, debtor_id, {"estado": "pagado"})
    assert resp["ok"] is False
    assert "not_found" in resp.get("error", "")


@pytest.mark.asyncio
async def test_debtor_updater_valid_update():
    """debtor_updater: updating own debtor returns ok=True with updated doc."""
    from cobranza.sub_agents.debtor_updater import update_debtor_status
    db = database.get_db()
    user_id = "user_valid_update"
    result = await db.debtors.insert_one(
        {"user_id": user_id, "nombre": "Maria", "estado": "pendiente", "monto": 200.0}
    )
    debtor_id = str(result.inserted_id)
    resp = await update_debtor_status(db, user_id, debtor_id, {"estado": "promesa_de_pago"})
    assert resp["ok"] is True
    assert resp["debtor"]["estado"] == "promesa_de_pago"
    assert resp["debtor"]["user_id"] == user_id


@pytest.mark.asyncio
async def test_debtor_updater_invalid_id():
    """debtor_updater: invalid ObjectId returns ok=False with invalid_id error."""
    from cobranza.sub_agents.debtor_updater import update_debtor_status
    db = database.get_db()
    resp = await update_debtor_status(db, "some_user", "not-a-valid-objectid", {"estado": "pagado"})
    assert resp["ok"] is False
    assert "invalid_id" in resp.get("error", "")


@pytest.mark.asyncio
async def test_whatsapp_notifier_enqueues(monkeypatch):
    """whatsapp_notifier: send_whatsapp enqueues ARQ job and returns ok=True immediately."""
    from cobranza.sub_agents import whatsapp_notifier

    enqueued_calls = []

    class FakePool:
        async def enqueue_job(self, task_name, **kwargs):
            enqueued_calls.append((task_name, kwargs))

    async def fake_get_arq_pool():
        return FakePool()

    monkeypatch.setattr(whatsapp_notifier, "get_arq_pool", fake_get_arq_pool)

    resp = await whatsapp_notifier.send_whatsapp("user_1", "+573001234567", "Hola, su pago está pendiente")
    assert resp["ok"] is True
    assert resp.get("queued") is True
    assert len(enqueued_calls) == 1
    assert enqueued_calls[0][0] == "send_whatsapp_job"


@pytest.mark.asyncio
async def test_whatsapp_notifier_missing_phone():
    """whatsapp_notifier: missing phone returns ok=False."""
    from cobranza.sub_agents.whatsapp_notifier import send_whatsapp
    resp = await send_whatsapp("user_1", "", "some message")
    assert resp["ok"] is False
    assert "error" in resp


@pytest.mark.asyncio
async def test_identity_verifier_confirm():
    """identity_verifier: confirms identity when utterance matches confirm pattern."""
    from cobranza.sub_agents.identity_verifier import verify_identity
    resp = await verify_identity("sí, soy yo", "Carlos Perez")
    assert resp["confirmed"] is True
    assert resp["confidence"] == "high"


@pytest.mark.asyncio
async def test_identity_verifier_deny():
    """identity_verifier: denies identity when utterance matches deny pattern."""
    from cobranza.sub_agents.identity_verifier import verify_identity
    resp = await verify_identity("no, se equivocó", "Carlos Perez")
    assert resp["confirmed"] is False
    assert resp["confidence"] == "high"


@pytest.mark.asyncio
async def test_escalation_handler_sets_estado(monkeypatch):
    """escalation_handler: escalate sets estado=escalado in DB and returns ok=True."""
    from cobranza.sub_agents import escalation_handler

    # Patch WS push to avoid importing main
    async def fake_ws_push(*args, **kwargs):
        pass
    monkeypatch.setattr(escalation_handler, "_push_ws_event", fake_ws_push)

    db = database.get_db()
    user_id = "user_esc"
    result = await db.debtors.insert_one(
        {"user_id": user_id, "nombre": "Pedro", "estado": "pendiente", "monto": 500.0, "intentos": 0}
    )
    debtor_id = str(result.inserted_id)
    resp = await escalation_handler.escalate(db, user_id, debtor_id, "no_pago_reiterado")
    assert resp["ok"] is True
    assert resp["estado"] == "escalado"
    # Verify DB was updated
    doc = await db.debtors.find_one({"_id": result.inserted_id})
    assert doc["estado"] == "escalado"


@pytest.mark.asyncio
async def test_orchestrator_dispatch():
    """
    CobranzaOrchestrator.update_debtor dispatches to debtor_updater with user_id.
    """
    from cobranza.cobranza_orchestrator import CobranzaOrchestrator
    db = database.get_db()
    user_id = "user_orch"
    result = await db.debtors.insert_one(
        {"user_id": user_id, "nombre": "Luis", "estado": "pendiente", "monto": 300.0}
    )
    debtor_id = str(result.inserted_id)
    orch = CobranzaOrchestrator(user_id=user_id, tenant_config={}, db=db)
    resp = await orch.update_debtor(debtor_id, {"estado": "promesa_de_pago"})
    assert resp["ok"] is True
    assert resp["debtor"]["estado"] == "promesa_de_pago"


@pytest.mark.xfail(strict=False, reason="Phase 25 WIP — Wave 3 Telnyx serializer")
@pytest.mark.asyncio
async def test_telnyx_serializer():
    """
    Telnyx webhook payload serializes to the internal CallEvent model
    without data loss.
    """
    raise NotImplementedError


# ── xfail stubs — Wave 3 (Gemini Live voice) ─────────────────────────────────

@pytest.mark.xfail(strict=False, reason="Phase 25 WIP — Wave 3 Gemini Live import")
@pytest.mark.asyncio
async def test_gemini_live_import():
    """
    google.genai and pipecat_ai[google] are importable and the
    GeminiLiveAdapter initialises without credentials at module level.
    """
    raise NotImplementedError


# ── xfail stubs — Wave 4 (RAG) ───────────────────────────────────────────────

@pytest.mark.xfail(strict=False, reason="Phase 25 WIP — Wave 4 RAG namespace isolation")
@pytest.mark.asyncio
async def test_rag_namespace_isolation():
    """
    Documents ingested under tenant A are NOT returned by a query
    executed under tenant B (Pinecone namespace isolation).
    """
    raise NotImplementedError


@pytest.mark.xfail(strict=False, reason="Phase 25 WIP — Wave 4 search knowledge")
@pytest.mark.asyncio
async def test_search_knowledge_tenant_isolation():
    """
    search_knowledge(user_id=A, query) returns only chunks whose
    pinecone_namespace == A.
    """
    raise NotImplementedError


# ── CACHE-01 / module toggle ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_module_toggle_cache(monkeypatch):
    """
    toggle_module(user_id, 'voice', False) upserts modules.voice=False
    AND calls invalidate_tenant_config(user_id) so the next
    get_tenant_config returns voice=False from MongoDB (hot-reload through cache).
    Uses fakeredis — no real Redis needed in CI.
    """
    import fakeredis.aioredis as fakeredis
    import cobranza.config_cache as cc

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(cc, "_redis_client", fake)

    from cobranza.tenant_config import upsert_tenant_config, toggle_module
    from cobranza.config_cache import get_tenant_config

    user_id = "user_toggle_cache_test"
    await upsert_tenant_config(user_id, {"business_name": "Toggle Cache Inc", "modules": {"voice": True}})

    # First read populates cache
    cfg1 = await get_tenant_config(user_id)
    assert cfg1["modules"]["voice"] is True

    # Toggle off — must invalidate cache
    await toggle_module(user_id, "voice", False)

    # Next read should reload from MongoDB and reflect new value
    cfg2 = await get_tenant_config(user_id)
    assert cfg2["modules"]["voice"] is False, f"Expected voice=False, got: {cfg2.get('modules')}"
