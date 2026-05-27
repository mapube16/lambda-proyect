# Phase 18: Infrastructure Foundation - Research

**Researched:** 2026-05-26
**Domain:** ARQ job queue, Redis pub/sub, Railway multi-service deployment, FastAPI async patterns
**Confidence:** HIGH (ARQ v0.28.0 official docs), HIGH (Railway official docs), HIGH (redis-py 7.4.0 official docs)

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | Developer can deploy API, Worker, and Redis as 3 separate Railway services from one repo | Railway railway.toml config-as-code; each service gets its own toml or startCommand override; Redis is a one-click add-on service |
| INFRA-02 | Worker service processes ARQ jobs from Redis without blocking the API service | ARQ WorkerSettings + `arq backend.worker:WorkerSettings` start command; worker runs in a separate Railway service process |
| INFRA-03 | API service enqueues prospecting campaigns as ARQ jobs and returns run_id immediately | `ArqRedis.enqueue_job()` with pre-generated UUID as `_job_id`; returns in-process without waiting for execution |
</phase_requirements>

---

## Summary

Phase 18 converts the platform from in-process synchronous pipeline execution to a decoupled 3-tier architecture: FastAPI API service, ARQ Worker service, and Redis broker — all deployed as independent Railway services from a single repository.

The current `POST /api/prospect` endpoint calls `state.hive_adapter.start_run()` which creates an `asyncio.Task` in the same process. While this is non-blocking within the event loop, it means the pipeline occupies the API process and cannot scale independently. The new architecture uses ARQ (async Redis queue) to enqueue a job and return a `run_id` immediately. A separate Worker process picks up the job from Redis, executes `HiveAdapter.start_run()`, and publishes progress events to a Redis pub/sub channel `ws:{user_id}:{run_id}`. The API process subscribes to this channel and forwards events to the user's WebSocket connection.

The key challenges are: (1) ARQ WorkerSettings + job function design, (2) Redis pub/sub bridge between Worker and API, (3) Railway multi-service configuration from one Dockerfile-based repo, and (4) job payload design that carries enough context for the Worker to reconstruct the full pipeline inputs without depending on API process state.

**Primary recommendation:** Use ARQ 0.28.0 + redis[asyncio] 7.4.0. Generate `run_id` as a UUID4 string at enqueue time in the API. Pass all pipeline inputs as explicit job kwargs (not references to in-memory state). Worker publishes events to Redis pub/sub; API subscribes per-WebSocket-connection using `asyncio.create_task`. On Railway, use two separate services from the same repo: API uses the existing Dockerfile CMD, Worker overrides startCommand to `arq backend.worker:WorkerSettings`.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| arq | 0.28.0 | Asyncio job queue with Redis backend | Native asyncio, built for FastAPI-style async code; no Celery thread overhead |
| redis | 7.4.0 | Redis client with asyncio pub/sub (`redis.asyncio`) | Ships with `redis.asyncio` module; one package for both ARQ transport and pub/sub bridge |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dotenv | 1.0.0 (already present) | Load `REDIS_URL` from env | Already in requirements.txt |
| certifi | (already present) | TLS cert bundle | Already used for MongoDB; not needed for Redis unless TLS Redis |

**Note:** `aioredis` is a legacy package. Since redis-py v4.2, the `redis.asyncio` module replaces aioredis entirely. Do NOT add `aioredis` as a dependency — use `redis[asyncio]` or just `redis>=4.2` (already ships with async support).

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| arq | TaskIQ | TaskIQ is more actively maintained and feature-rich, but requires more boilerplate; ARQ is simpler for this use case and already decided |
| arq | Celery | Celery requires separate result backend, thread-based, much heavier; ARQ is the locked decision |
| redis pub/sub | Server-Sent Events | SSE is unidirectional and doesn't support cross-process message routing; Redis pub/sub is necessary for Worker→API bridge |

**Installation (add to requirements.txt):**
```bash
arq==0.28.0
redis>=7.0.0
```

**Version verification (confirmed 2026-05-26):**
- `arq`: 0.28.0 (latest on PyPI, released 2026-04-16) — confirmed via `pip3 index versions arq`
- `redis`: 7.4.0 (latest on PyPI) — confirmed via `pip3 index versions redis`

---

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── worker.py              # WorkerSettings + job functions (new)
├── arq_pool.py            # Shared ArqRedis pool creation helper (new)
├── routers/
│   └── prospect.py        # POST /api/prospect → enqueue_job (modified)
├── routers/
│   └── websocket.py       # WS handler + Redis pub/sub subscriber (modified)
├── services/
│   └── connection_manager.py  # (unchanged)
├── hive_adapter.py        # (unchanged — runs in Worker only)
└── main.py                # API lifespan: init arq_pool (modified)
```

### Pattern 1: ARQ Job Function

The job function receives `ctx` (dict with startup-injected resources) plus all job kwargs explicitly. All pipeline inputs must be passed as serializable values — no references to API process state.

```python
# backend/worker.py

import asyncio
import redis.asyncio as aioredis
from arq import Retry
from hive_adapter import HiveAdapter

REDIS_SETTINGS = None  # set from env at module load

async def run_prospecting_campaign(
    ctx: dict,
    run_id: str,
    user_id: str,
    campaign: dict,
    max_results: int,
    personality_prompt: str,
    runtime_agents: list,
    excluded_domains: list,
    source_priority: str,
) -> dict:
    """ARQ job: run Hive pipeline, publish events to Redis pub/sub."""
    redis_client: aioredis.Redis = ctx["redis"]

    async def publish_event(uid: str, message: dict):
        import json
        channel = f"ws:{uid}:{run_id}"
        await redis_client.publish(channel, json.dumps(message))

    adapter = HiveAdapter(send_to_user_callback=publish_event)
    try:
        await adapter.start_run(
            user_id=user_id,
            inputs={
                "campaign": campaign,
                "max_results": max_results,
                "personality_prompt": personality_prompt,
                "runtime_agents": runtime_agents,
                "excluded_domains": excluded_domains,
                "source_priority": source_priority,
            },
            run_id=run_id,
            save_lead=None,  # Worker uses its own DB connection via ctx
        )
        return {"status": "complete", "run_id": run_id}
    except Exception as exc:
        # Publish error event before re-raising so frontend sees it
        import json
        await redis_client.publish(
            f"ws:{user_id}:{run_id}",
            json.dumps({"type": "error", "message": str(exc)})
        )
        raise  # ARQ will mark job as failed


async def startup(ctx: dict):
    """Called once when worker starts — inject shared resources into ctx."""
    import os
    from arq.connections import RedisSettings
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    ctx["redis"] = await aioredis.from_url(redis_url, decode_responses=False)


async def shutdown(ctx: dict):
    await ctx["redis"].aclose()


class WorkerSettings:
    functions = [run_prospecting_campaign]
    on_startup = startup
    on_shutdown = shutdown
    redis_settings = None   # set at class definition from env (see Pattern 2)
    max_jobs = 5            # cap concurrent pipeline runs
    job_timeout = 3600      # 1 hour max per job (prospecting can be slow)
    keep_result = 86400     # keep result 24h for status checks
    max_tries = 1           # no automatic retry — prospecting is expensive; handle manually
```

**Source:** ARQ v0.28.0 official docs (https://arq-docs.helpmanual.io/)

### Pattern 2: WorkerSettings Redis from Environment

```python
# backend/worker.py (module-level setup)
import os
from arq.connections import RedisSettings

def _redis_settings_from_env() -> RedisSettings:
    url = os.getenv("REDIS_URL", "redis://localhost:6379")
    # RedisSettings can parse redis:// URLs in arq 0.26+
    from urllib.parse import urlparse
    p = urlparse(url)
    return RedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int(p.path.lstrip("/") or 0),
    )

class WorkerSettings:
    redis_settings = _redis_settings_from_env()
    # ... rest of settings
```

**Note:** ARQ `RedisSettings` does not accept a raw `redis://` URL string — parse the URL yourself and pass host/port/password/database individually.

### Pattern 3: API Enqueue Job

```python
# backend/routers/prospect.py (modified POST /api/prospect)
import uuid
import state
from arq.connections import ArqRedis

@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    run_id = str(uuid.uuid4())   # Generate at enqueue time — API owns run_id

    # Create DB run record BEFORE enqueuing (so status endpoint works immediately)
    await create_run(user_id=user_id, campaign_id="", max_results=request.max_results, run_id=run_id)

    arq_redis: ArqRedis = state.arq_pool
    job = await arq_redis.enqueue_job(
        "run_prospecting_campaign",
        run_id=run_id,
        user_id=user_id,
        campaign=campaign,
        max_results=min(request.max_results, 50),
        personality_prompt=personality_prompt,
        runtime_agents=runtime_agents,
        excluded_domains=excluded_domains,
        source_priority=request.source_priority,
        _job_id=run_id,       # Use run_id as job_id for deduplication
    )

    return {
        "status": "queued",
        "run_id": run_id,
        "message": "Campaña encolada — los agentes comenzarán pronto"
    }
```

**Source:** ARQ v0.28.0 official docs (https://arq-docs.helpmanual.io/)

### Pattern 4: Redis Pub/Sub Bridge in WebSocket Handler

The WebSocket handler must subscribe to the Redis pub/sub channel for the active run and forward messages. This runs as a background asyncio task per connected user.

```python
# backend/routers/websocket.py (modified)
import asyncio
import json
import redis.asyncio as aioredis
import state

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(...)):
    # ... JWT validation (unchanged) ...
    await manager.connect(websocket, user_id=user_id)

    # Background task: subscribe to Redis pub/sub for this user's runs
    pubsub_task = asyncio.create_task(
        _redis_event_forwarder(user_id, websocket)
    )

    try:
        # ... existing message handling loop (unchanged) ...
    except WebSocketDisconnect:
        manager.disconnect(user_id)
    finally:
        pubsub_task.cancel()
        try:
            await pubsub_task
        except asyncio.CancelledError:
            pass


async def _redis_event_forwarder(user_id: str, websocket: WebSocket):
    """Subscribe to all run channels for this user and forward to WebSocket."""
    redis_client = await aioredis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=True,
    )
    pubsub = redis_client.pubsub()
    # Pattern subscribe: receives events for ALL runs by this user
    pattern = f"ws:{user_id}:*"
    await pubsub.psubscribe(pattern)
    try:
        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                data = message["data"]
                if isinstance(data, str):
                    try:
                        payload = json.loads(data)
                        await websocket.send_json(payload)
                    except Exception:
                        pass
    except asyncio.CancelledError:
        pass
    finally:
        await pubsub.punsubscribe(pattern)
        await redis_client.aclose()
```

**Source:** redis-py async docs (https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html), redis-py pub/sub issue tracker

**Key pitfall:** When the pubsub task is cancelled (WebSocket disconnects), `redis.asyncio` raises `ConnectionError` during the listen loop. Wrap in `try/except asyncio.CancelledError` and always call `pubsub.punsubscribe` + `redis_client.aclose()` in `finally`.

### Pattern 5: API lifespan — init arq pool

```python
# backend/main.py (modified lifespan)
from arq import create_pool
from arq.connections import RedisSettings
import state

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ... existing startup ...
    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    p = urlparse(redis_url)
    state.arq_pool = await create_pool(RedisSettings(
        host=p.hostname or "localhost",
        port=p.port or 6379,
        password=p.password,
        database=int(p.path.lstrip("/") or 0),
    ))
    # ... rest of existing startup ...
    yield
    await state.arq_pool.aclose()
    # ... existing shutdown ...
```

### Pattern 6: Job Status Endpoint

ARQ exposes job status via the `Job` object returned from `enqueue_job`. For status checks after the fact, use the `Job` class reconstructed from the job ID:

```python
# backend/routers/prospect.py (add new endpoint)
from arq.jobs import Job, JobStatus

@router.get("/api/runs/{run_id}/status")
async def get_run_status(run_id: str, current_user: dict = Depends(get_current_user)):
    arq_redis: ArqRedis = state.arq_pool
    job = Job(run_id, arq_redis)
    status = await job.status()
    # JobStatus values: queued, deferred, in_progress, complete, not_found
    return {"run_id": run_id, "job_status": status.value}
```

### Anti-Patterns to Avoid

- **Passing in-memory state to job kwargs:** The Worker runs in a separate process. `state.orchestrator`, `state.hive_adapter`, `manager` are not available in the Worker process. Every input the Worker needs must be serialized into the job kwargs.
- **Using `asyncio.Task` in the API for pipeline execution:** This is what we're replacing. Do not leave `state.hive_adapter.start_run()` calls in the API process.
- **Using aioredis package:** It is abandoned. Use `import redis.asyncio as aioredis` from the `redis` package.
- **Omitting `_job_id` in `enqueue_job`:** Without it, ARQ generates a random UUID. Use `run_id` as `_job_id` for deduplication — prevents duplicate runs if the API retries the enqueue.
- **Not calling `aclose()` on pubsub redis client:** Each WebSocket connection creates its own Redis connection. Failing to close on disconnect leaks connections.
- **max_tries > 1 for pipeline jobs:** Prospecting runs LLM calls and scraping — re-running them on crash doubles cost. Set `max_tries=1` and handle failures via explicit re-run API.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Job queue with Redis | Custom list-based queue with asyncio | `arq` | ARQ handles locking, pessimistic execution, retry, health checks |
| Job deduplication | Custom Redis key checks | `_job_id` in `enqueue_job` | ARQ uses Redis transactions for atomic uniqueness check |
| Worker health check | Custom ping endpoint | `arq --check backend.worker:WorkerSettings` | Built-in, returns exit code 0/1 |
| Pub/sub channel naming | Custom scheme | `ws:{user_id}:{run_id}` pattern (per TENANT-03 spec) | Matches the tenant isolation pattern already specified for Phase 19 |
| Redis URL parsing | Manual string split | `urllib.parse.urlparse` | Railway provides `REDIS_URL` as a full `redis://...` URL |

**Key insight:** ARQ's pessimistic execution means a Worker crash does not lose the job — it re-queues automatically. This is the right behavior for Railway's `restartPolicyType = "ON_FAILURE"`.

---

## Common Pitfalls

### Pitfall 1: Railway Redis URL format
**What goes wrong:** Railway provides `REDIS_URL` in the format `redis://:password@hostname:port`. The `password` field has a leading `:` (empty username). `urlparse` gives `p.password = "actualpassword"` and `p.username = ""` — this is correct Python behavior.
**Why it happens:** RFC 3986 URL format: `redis://:password@host:port`. urllib.parse handles this correctly.
**How to avoid:** Use `urlparse(url).password` — will correctly extract the password even with the leading colon in the URL.
**Warning signs:** `WRONGPASS invalid username-password pair` in ARQ logs.

### Pitfall 2: Worker cannot import from main.py state
**What goes wrong:** Worker imports `from main import app` or `import state` expecting `state.orchestrator` to be populated — but in the Worker process, `lifespan` never ran.
**Why it happens:** Railway Worker service runs `arq backend.worker:WorkerSettings`, not uvicorn. The FastAPI lifespan never executes.
**How to avoid:** Worker must initialize its own MongoDB client and any other resources in `WorkerSettings.on_startup`. Never reference `state.*` from worker code.
**Warning signs:** `AttributeError: 'NoneType' object has no attribute 'start_run'` in Worker logs.

### Pitfall 3: Redis pub/sub messages lost during WebSocket reconnect
**What goes wrong:** User's frontend disconnects and reconnects. The pub/sub task was cancelled on disconnect. During reconnect, some Worker events fire before the new subscription is established — those messages are lost permanently.
**Why it happens:** Redis pub/sub is fire-and-forget with no persistence. There is no replay on subscribe.
**How to avoid:** For Phase 18, accept this limitation. The run_id status endpoint (`GET /api/runs/{run_id}/status`) lets the frontend poll for final status. Phase 19 can add event buffering in MongoDB if needed.
**Warning signs:** Frontend shows spinner forever after reconnect during an active run.

### Pitfall 4: ARQ `_job_id` re-use after completion
**What goes wrong:** User triggers a second run with the same `run_id` (e.g., if the API retries). ARQ prevents re-enqueue while the job is in-flight but allows it after `keep_result` seconds.
**Why it happens:** ARQ's deduplication is time-bounded by `keep_result`.
**How to avoid:** Always generate a new UUID4 for each `run_id`. Never reuse run IDs.

### Pitfall 5: Railway Worker service vs Cron service
**What goes wrong:** Configuring the Worker as a `cronSchedule` service instead of a persistent long-running service.
**Why it happens:** Railway has cron-type deploys. ARQ workers must run continuously, not on a schedule.
**How to avoid:** Set `restartPolicyType = "ON_FAILURE"` in worker's railway.toml. No `cronSchedule`. The worker process runs `arq backend.worker:WorkerSettings` indefinitely.

### Pitfall 6: `database.py` `init_db()` not called in Worker
**What goes wrong:** Worker calls `save_lead()` or other database functions but `_client` is None — `init_db()` was never called in the Worker process.
**Why it happens:** `init_db()` is called in `main.py` lifespan; the Worker doesn't run `main.py`.
**How to avoid:** Call `await database.init_db()` in `WorkerSettings.on_startup`. Also requires `MONGODB_URI` env var to be set on the Worker service in Railway (shared variable).

### Pitfall 7: Serialization of campaign data
**What goes wrong:** `campaign` dict contains MongoDB `ObjectId` fields (e.g., `_id`). ARQ serializes job kwargs with msgpack by default — `ObjectId` is not serializable.
**Why it happens:** MongoDB documents have `_id` as ObjectId. If the campaign dict is passed directly from a `find_one()` result, it includes `_id`.
**How to avoid:** Strip `_id` and all ObjectId fields from campaign dict before passing to `enqueue_job`. Convert to plain string if needed: `{k: v for k, v in campaign.items() if k != "_id"}`.

---

## Code Examples

Verified patterns from official sources:

### Running the ARQ Worker locally

```bash
# From backend/ directory
arq worker:WorkerSettings

# Or with auto-reload during development
arq worker:WorkerSettings --watch .
```

### Job status check from Job object

```python
# Source: https://arq-docs.helpmanual.io/
from arq.jobs import Job, JobStatus

job = Job(job_id=run_id, redis=arq_redis)
status = await job.status()
# Returns: JobStatus.queued | .in_progress | .complete | .not_found | .deferred
info = await job.info()  # Full metadata including score, enqueue_time, etc.
```

### Pessimistic execution — job survives Worker crash

```
# From ARQ docs: "Jobs aren't removed from the queue until they've succeeded or failed."
# If Worker restarts, the in-progress job re-queues and runs again.
# Design jobs to be idempotent (MongoDB upsert instead of insert).
```

### Redis pub/sub publish from Worker

```python
# Source: redis-py asyncio docs
import json
import redis.asyncio as aioredis

redis_client: aioredis.Redis = ctx["redis"]
await redis_client.publish(
    f"ws:{user_id}:{run_id}",
    json.dumps({"type": "agent_update", "agent_id": "...", "state": "THINKING"})
)
```

---

## Railway Multi-Service Configuration

### Strategy: Two railway.toml files + shared Dockerfile

Railway allows each service in the same repo to have its own `railway.toml`. The recommended approach is to keep the existing root `railway.toml` for the API service and create `railway-worker.toml` for the Worker service (configurable in Railway dashboard per service).

However, the simplest approach for this repo (which uses a single Dockerfile) is to use **separate railway.toml files with different startCommands** while sharing the same Dockerfile. The Worker service overrides the start command.

#### API service (`railway.toml` — existing, modify):

```toml
[build]
builder = "dockerfile"

[deploy]
startCommand = "uvicorn main:app --host 0.0.0.0 --port $PORT"
healthcheckPath = "/api/health"
healthcheckTimeout = 60
restartPolicyType = "on_failure"
```

#### Worker service (`railway-worker.toml` — new):

```toml
[build]
builder = "dockerfile"
# Same Dockerfile as API — Worker shares the image

[deploy]
startCommand = "arq backend.worker:WorkerSettings"
restartPolicyType = "on_failure"
restartPolicyMaxRetries = 10
# No healthcheckPath — Worker is not HTTP
```

**In Railway dashboard:** Create a new service pointing at the same repo. In Service Settings → "Config file path", set `/railway-worker.toml`. This tells Railway to use the worker config instead of the default `railway.toml`.

#### Redis service:

Redis is a one-click add-on in Railway — no `railway.toml` needed. After creating it, Railway provides:
- `REDIS_URL` — full connection URL (`redis://:password@hostname:port`)
- `REDISHOST`, `REDISPORT`, `REDISPASSWORD` — individual components

#### Environment variable sharing between services:

In Railway dashboard, use **variable references** to share `REDIS_URL` across services:

```
# In API service variables:
REDIS_URL = ${{Redis.REDIS_URL}}

# In Worker service variables:
REDIS_URL = ${{Redis.REDIS_URL}}
MONGODB_URI = ${{API.MONGODB_URI}}   # or set independently
OPENAI_API_KEY = ${{API.OPENAI_API_KEY}}
```

**Source:** Railway docs (https://docs.railway.com/variables), (https://docs.railway.com/guides/redis)

### Private networking between services

Railway services in the same project communicate via `railway.internal` private DNS. The Worker should connect to Redis using the private URL to avoid egress fees:

```
REDIS_PRIVATE_URL = ${{Redis.REDIS_PRIVATE_URL}}
```

Use `REDIS_PRIVATE_URL` for Worker→Redis and API→Redis communication. Only the API needs a public domain.

---

## Job Payload Design

### Recommended job function kwargs

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| `run_id` | `str` (UUID4) | Generated in API at enqueue time | Used as ARQ `_job_id` and pub/sub channel suffix |
| `user_id` | `str` | JWT `sub` claim | Used for pub/sub channel prefix and tenant isolation |
| `campaign` | `dict` | MongoDB document (strip `_id`) | All 10 campaign variables |
| `max_results` | `int` | Request parameter | Capped at 50 |
| `personality_prompt` | `str` | client_profiles document | Fetched by API before enqueue |
| `runtime_agents` | `list[dict]` | Built by API | Serializable dicts (id, name, role, state, palette) |
| `excluded_domains` | `list[str]` | Fetched from DB by API | List of domain strings |
| `source_priority` | `str` | Request parameter | "serper" or "google_maps" |

### run_id generation

**Use UUID4 generated in the API process at enqueue time.** This is correct because:
1. The API needs `run_id` to create the MongoDB run record BEFORE enqueuing (so status polling works immediately)
2. The frontend needs `run_id` in the HTTP response to establish the WebSocket subscription
3. Using `_job_id=run_id` in `enqueue_job` deduplicates if the API retries

Do NOT use MongoDB ObjectId for `run_id` — ObjectId is not JSON-serializable by default and ARQ uses JSON/msgpack for job kwargs. Use `str(uuid.uuid4())`.

**However:** The existing `database.create_run()` may generate its own `_id` as ObjectId. You need to either: (a) pass `run_id` as a separate field in `create_run()` and use it as the run identifier, or (b) convert the ObjectId to string after creation. Option (a) is cleaner.

---

## Backward Compatibility

### Existing `/api/prospect` endpoint

The endpoint currently calls `state.hive_adapter.start_run()` synchronously (via asyncio.Task). For Phase 18, this endpoint should be modified in-place to call `arq_redis.enqueue_job()` instead. The response shape stays the same: `{"status": ..., "run_id": ..., "message": ...}`.

The endpoint at `POST /api/campaigns` currently saves campaign config and returns `campaign_id`. This is a DIFFERENT endpoint from the run-triggering endpoint. Keep both:
- `POST /api/campaigns` — saves campaign config (unchanged)
- `POST /api/prospect` — triggers a run (change to ARQ enqueue)

The roadmap mentions adding `POST /api/campaigns` as the new run-trigger endpoint (Phase 18 success criteria says "POST /api/campaigns returns run_id immediately"). However, `POST /api/campaigns` already exists and does something different (saves campaign config). **Resolution:** Keep the existing endpoint names. Modify `POST /api/prospect` to enqueue via ARQ. Do not repurpose `POST /api/campaigns`.

---

## Dev Local Setup

### Running API + Worker + Redis locally

```bash
# Terminal 1: Redis (Docker)
docker run -p 6379:6379 redis:7-alpine

# Terminal 2: API
cd backend
REDIS_URL=redis://localhost:6379 uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Terminal 3: Worker
cd backend
REDIS_URL=redis://localhost:6379 arq worker:WorkerSettings --watch .
```

Or use `dev.ps1` / `dev.sh` to orchestrate all three.

**REDIS_URL not set:** Both API and Worker must have `REDIS_URL` in their environment. In development, set `REDIS_URL=redis://localhost:6379` in `.env` (already loaded via `python-dotenv`).

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `aioredis` standalone package | `redis.asyncio` (in `redis` package) | redis-py v4.2 (2022) | Remove `aioredis` dependency; use `import redis.asyncio as aioredis` |
| ARQ uses msgpack for job serialization | ARQ uses msgpack by default; custom serializers possible | ARQ v0.23+ | Job kwargs must be msgpack-serializable; ObjectId is not |
| ARQ `functions = [func]` used bare functions | Same pattern still current in v0.28.0 | — | No change needed |

**Deprecated/outdated:**
- `aioredis` package: Abandoned. Replaced by `redis.asyncio` which ships with `redis>=4.2`.
- ARQ < 0.16: Did not have pessimistic execution. Jobs were removed from queue before completion. Use 0.28.0.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Redis server | ARQ queue + pub/sub | Needs installation | — | Use Railway Redis service; locally use Docker |
| arq (pip) | Worker + API enqueue | Not installed | — | Add to requirements.txt |
| redis (pip) | pub/sub + ARQ transport | Not installed | — | Add to requirements.txt |
| Python 3.11 | Worker process | ✓ (Dockerfile uses python:3.11-slim) | 3.11 | — |
| Docker | Local dev Redis | ✓ (assumed on dev machine) | Any | Use Railway Redis with public URL |

**Missing dependencies with no fallback:**
- Redis server: must exist (Railway one-click add-on for prod; Docker for local dev)
- `arq` and `redis` pip packages: must be added to `requirements.txt`

**Missing dependencies with fallback:**
- Docker locally: use Railway Redis public TCP proxy URL with `REDIS_URL` env var pointed at it

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| Config file | `backend/pytest.ini` (asyncio_mode = auto) |
| Quick run command | `cd backend && pytest tests/test_infra.py -x` |
| Full suite command | `cd backend && pytest tests/ -x` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01 | Railway services config files exist and are valid TOML | smoke | manual check + `python -c "import tomllib; tomllib.load(open('railway.toml','rb'))"` | ❌ Wave 0 |
| INFRA-02 | Worker processes ARQ job from Redis | unit/integration | `pytest tests/test_infra.py::test_worker_processes_job -x` | ❌ Wave 0 |
| INFRA-03 | POST /api/prospect returns run_id immediately without waiting | unit | `pytest tests/test_infra.py::test_prospect_enqueues_returns_run_id -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `cd backend && pytest tests/test_infra.py -x`
- **Per wave merge:** `cd backend && pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_infra.py` — covers INFRA-02, INFRA-03 with xfail stubs
- [ ] Mock ArqRedis in tests — use `unittest.mock.AsyncMock` for `enqueue_job`; no real Redis needed for unit tests

*(Existing conftest.py uses mongomock-motor for MongoDB isolation — same pattern applies: mock ArqRedis in tests)*

---

## Open Questions

1. **`create_run()` run_id vs MongoDB _id**
   - What we know: `create_run()` in `database.py` likely creates a MongoDB document and returns the `_id` as a string (ObjectId → str). The existing `run_id` returned by `POST /api/prospect` is a MongoDB ObjectId string.
   - What's unclear: Whether the Worker can store results back to MongoDB using this same run_id, or needs its own UUID.
   - Recommendation: Check `database.create_run()` implementation. If it generates ObjectId, add a `run_id` (UUID4) parameter to `create_run()` so it stores both. The ARQ job uses the UUID4. The MongoDB document links both.

2. **Worker Dockerfile: single image vs separate**
   - What we know: The current Dockerfile builds frontend + backend in a multi-stage build. The Worker only needs the backend stage.
   - What's unclear: Whether Railway allows overriding just the CMD in a `railway-worker.toml` pointing at the same `Dockerfile`, or if a separate `Dockerfile.worker` is cleaner.
   - Recommendation: Use the same Dockerfile, override `startCommand` in `railway-worker.toml`. The Worker image will include the unused frontend dist — slight size overhead, but avoids maintaining two Dockerfiles.

3. **save_lead callback in Worker**
   - What we know: `HiveAdapter.start_run()` accepts a `save_lead` callback. The current `POST /api/prospect` passes `save_lead=save_lead` from `database.py`.
   - What's unclear: Whether the Worker should pass `save_lead` directly (Worker has its own DB connection) or if `save_lead=None` causes issues in HiveAdapter.
   - Recommendation: In Worker's `on_startup`, call `await database.init_db()`. Pass `save_lead=database.save_lead` to `adapter.start_run()` in the job function.

---

## Sources

### Primary (HIGH confidence)
- [arq v0.28.0 official docs](https://arq-docs.helpmanual.io/) — WorkerSettings, job function signature, enqueue_job, JobStatus, retry
- [redis-py asyncio docs](https://redis.readthedocs.io/en/stable/examples/asyncio_examples.html) — pub/sub subscribe, get_message, psubscribe, cleanup
- [Railway Config as Code](https://docs.railway.com/reference/config-as-code) — railway.toml structure, startCommand, restartPolicyType
- [Railway Variables](https://docs.railway.com/variables) — variable references between services, shared variables
- [Railway Redis docs](https://docs.railway.com/guides/redis) — REDIS_URL, one-click provisioning

### Secondary (MEDIUM confidence)
- [Railway multi-agent guide](https://docs.railway.com/guides/multi-agent-system) — verified: API vs Worker start commands, shared REDIS_URL pattern
- [chanx ARQ+FastAPI tutorial](https://chanx.readthedocs.io/en/stable/tutorial-fastapi/cp3-background-jobs.html) — verified against arq official docs: job function ctx pattern, WorkerSettings
- [Nanda Gopal Pattanayak — Scaling WebSockets with pub/sub](https://medium.com/@nandagopal05/scaling-websockets-with-pub-sub-using-python-redis-fastapi-b16392ffe291) — verified against redis-py docs: subscribe, unsubscribe cleanup pattern

### Tertiary (LOW confidence)
- ARQ issue #343 "Tasks get stuck if worker crash and restart" — known issue: worker must be running for jobs to re-queue; short job_timeout recommended for fast re-pickup after restart
- redis-py issue #2717 "Redis pubsub task cancellation raises ConnectionError" — confirmed: CancelledError on pubsub listen; wrap in try/except

---

## Metadata

**Confidence breakdown:**
- Standard stack (arq 0.28.0, redis 7.4.0): HIGH — confirmed current PyPI versions, official docs match
- Architecture patterns: HIGH — direct code examples from official arq and redis-py docs
- Railway config: MEDIUM — official docs confirm structure but multi-Dockerfile approach needs validation in dashboard
- Pitfalls: HIGH for Python pitfalls (confirmed via issue trackers); MEDIUM for Railway-specific (confirmed via official docs)

**Research date:** 2026-05-26
**Valid until:** 2026-08-26 (ARQ is "maintenance only mode" — no breaking changes expected; Railway config is stable)
