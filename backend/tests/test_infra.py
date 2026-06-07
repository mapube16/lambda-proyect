"""
test_infra.py — Phase 18: Infrastructure Foundation.

Requirement areas:
  INFRA-01: Developer can deploy API, Worker, and Redis as 3 separate Railway services
  INFRA-02: Worker service processes ARQ jobs from Redis without blocking the API service
  INFRA-03: API service enqueues prospecting campaigns as ARQ jobs and returns run_id immediately

All stubs use strict=False so CI never blocks on unimplemented features.
Heavy imports (worker, arq) are placed INSIDE test bodies (lazy) so collection
succeeds before those modules exist.
"""
import pytest


# ── INFRA-01: Railway config files ───────────────────────────────────────────

@pytest.mark.xfail(reason="INFRA-01: railway-worker.toml not created yet", strict=False)
def test_railway_config_files_valid():
    import tomllib, pathlib
    root = pathlib.Path(__file__).resolve().parents[2]
    api_cfg = tomllib.loads((root / "railway.toml").read_text())
    worker_cfg = tomllib.loads((root / "railway-worker.toml").read_text())
    assert "build" in api_cfg and "deploy" in api_cfg
    start = worker_cfg["deploy"]["startCommand"]
    assert "arq" in start and "worker:WorkerSettings" in start


# ── INFRA-03: POST /api/prospect enqueues and returns run_id ─────────────────

@pytest.mark.xfail(reason="INFRA-03: /api/prospect not yet wired to ARQ enqueue", strict=False)
async def test_enqueue_returns_run_id(async_client):
    import state
    from unittest.mock import AsyncMock
    from auth import create_access_token
    import database
    user = await database.create_user("infra@test.com", "hashed", role="client")
    uid = user["id"]
    token = create_access_token({"sub": str(uid)})
    state.arq_pool = AsyncMock()
    state.arq_pool.enqueue_job = AsyncMock(return_value=None)
    resp = await async_client.post(
        "/api/prospect",
        json={"campaign": {"industria_objetivo": "logistica"}, "max_results": 5},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "run_id" in body and body["run_id"]
    state.arq_pool.enqueue_job.assert_awaited_once()


# ── INFRA-02 / INFRA-03 boundary: API must not run pipeline in-process ────────

@pytest.mark.xfail(reason="INFRA-02: API must not run pipeline in-process", strict=False)
async def test_prospect_does_not_run_pipeline_inprocess(async_client):
    import state, database
    from unittest.mock import AsyncMock
    from auth import create_access_token
    user = await database.create_user("infra2@test.com", "hashed", role="client")
    uid = user["id"]
    token = create_access_token({"sub": str(uid)})
    state.arq_pool = AsyncMock()
    state.arq_pool.enqueue_job = AsyncMock(return_value=None)
    state.hive_adapter = AsyncMock()
    state.hive_adapter.start_run = AsyncMock()
    await async_client.post("/api/prospect", json={"campaign": {}, "max_results": 3},
                            headers={"Authorization": f"Bearer {token}"})
    state.hive_adapter.start_run.assert_not_awaited()


# ── INFRA-02: Worker job function exists and is registered ───────────────────

@pytest.mark.xfail(reason="INFRA-02: backend/worker.py not created yet", strict=False)
def test_worker_job_function_signature():
    import worker
    assert hasattr(worker, "run_prospecting_job")
    assert callable(worker.run_prospecting_job)
    fns = worker.WorkerSettings.functions
    assert worker.run_prospecting_job in fns


# ── INFRA-02 bridge: pub/sub forwarder routes Worker events to WebSocket ──────

async def test_pubsub_event_routing():
    import routers.websocket as ws
    from unittest.mock import AsyncMock, MagicMock, patch

    sent = []
    fake_websocket = AsyncMock()
    fake_websocket.send_json = AsyncMock(side_effect=lambda payload: sent.append(payload))

    async def fake_listen():
        yield {"type": "pmessage", "data": '{"type": "agent_update", "state": "THINKING"}'}
        raise __import__("asyncio").CancelledError()

    fake_pubsub = MagicMock()
    fake_pubsub.psubscribe = AsyncMock()
    fake_pubsub.punsubscribe = AsyncMock()
    fake_pubsub.listen = fake_listen
    fake_redis = AsyncMock()
    fake_redis.pubsub = MagicMock(return_value=fake_pubsub)
    fake_redis.aclose = AsyncMock()

    with patch("routers.websocket.aioredis.from_url", new=AsyncMock(return_value=fake_redis)):
        await ws._redis_event_forwarder("user1", fake_websocket)

    assert any(p.get("state") == "THINKING" for p in sent)
    fake_pubsub.psubscribe.assert_awaited_once()
    fake_redis.aclose.assert_awaited_once()


# ── INFRA-02: Worker job function invokes HiveAdapter and publishes events ────

@pytest.mark.xfail(reason="INFRA-02: run_prospecting_job not implemented yet", strict=False)
async def test_worker_processes_job():
    import worker
    from unittest.mock import AsyncMock, patch
    mock_redis = AsyncMock()
    ctx = {"redis": mock_redis}
    with patch("worker.HiveAdapter") as MockAdapter:
        instance = MockAdapter.return_value
        instance.start_run = AsyncMock(return_value="user1")
        result = await worker.run_prospecting_job(
            ctx, run_id="run-123", user_id="user1",
            campaign={"industria_objetivo": "x"}, max_results=5,
            personality_prompt="", runtime_agents=[],
            excluded_domains=[], source_priority="serper",
        )
        instance.start_run.assert_awaited_once()
    assert result["run_id"] == "run-123"
