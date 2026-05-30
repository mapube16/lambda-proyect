# Phase 19: Tenant Isolation - Research

**Date:** May 30, 2026  
**Domain:** Multi-tenant data isolation (MongoDB, FastAPI, WebSocket, Redis)  
**Confidence:** HIGH  
**Duration Estimate:** 5 days (120 hours)  
**Blocking:** Phase 24 (Signal Sources)

---

## Executive Summary

**Objective:** Convert the single-tenant Lambda Office backend to enforce strict multi-tenant isolation where each broker (user) operates within their own data partition with no possibility of cross-tenant data leakage.

**Current State (Single-Tenant Risk):**
- All queries filter by `user_id` only, assuming it's globally unique
- 17+ MongoDB collections lack `tenant_id` field — data models are tenant-unaware
- ConnectionManager keyed by `user_id` — no tenant separation at WebSocket layer
- ARQ worker publishes to `ws:{user_id}:{run_id}` Redis channel — potential collision if user IDs overlap across tenants
- Zero access control validating a user doesn't access another user's data in the same deployment

**After Phase 19 (Multi-Tenant Safe):**
- All queries enforce `tenant_id` filter first, then `user_id`
- Every collection has indexed `tenant_id` field + compound indexes on `(tenant_id, field)`
- Authentication extracts `tenant_id` from JWT (`tenant_id = user_id` = broker email)
- WebSocket channels namespaced to `ws:{tenant_id}:{run_id}` — globally unique, no collision risk
- Centralized helpers (`find_one_tenant()`, `aggregate_tenant()`) prevent leakage in complex queries
- Soft-delete mechanism for inactive tenants (compliance requirement)

**Key Decision:** `tenant_id = user_id` (email from JWT "sub" claim). No separate tenant table needed for v1.

**Primary Risk:** If migration is incomplete, queries may leak data between tenants. Mitigation: Dry-run on staging, verification step before production rollout.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|----------|-------------|----------------|-----------|
| Tenant identity extraction | Auth (backend) | JWT middleware | JWT "sub" claim parsed in `get_current_user()` |
| Data access control | Database layer | Router handlers | `find_one_tenant()` helper enforces filter; routes call it |
| WebSocket isolation | Real-time layer (Redis) | Connection manager | Redis channel names keyed by tenant_id; ConnectionManager subscribes to tenant-scoped channels |
| Aggregation queries | Database layer | Query layer | `aggregate_tenant()` helper prepends `$match {tenant_id}` stage |
| Soft-delete enforcement | Router handlers | Database layer | Routers pass `active_only=True` to database functions; DB layer applies filter |

---

## Standard Stack

### Core Technologies (Locked)
| Technology | Version | Current in Codebase | Purpose |
|-----------|---------|-------------------|---------|
| MongoDB | 6.x+ | ✅ Motor 3.x async driver | Document store, multi-tenant indexes |
| Motor (pymongo async) | 3.x | ✅ Imported in `database.py` | Non-blocking MongoDB client |
| FastAPI | 0.100+ | ✅ Main app framework | HTTP routing, dependency injection |
| Redis | 7.x+ | ✅ ARQ job queue backend | Message broker for WebSocket channels |

### Supporting Libraries (Confirmed Working)
| Library | Version | Purpose | Location |
|---------|---------|---------|----------|
| `pydantic` | 2.x | Request/response validation | `models.py` |
| `jose` (python-jose) | 3.x | JWT encode/decode | `auth.py` |
| `fastapi.security` | via FastAPI | OAuth2PasswordBearer, Depends | `auth.py` |
| `pymongo` | 4.x | Low-level query builders, ObjectId | `database.py` |

### Not Needed (Already have pattern)
| What? | Why? | Pattern in Code |
|------|------|-----------------|
| Tenant table (separate DB entity) | Decisions lock in: tenant_id = user_id | `19-CONTEXT.md`: "Single-user tenants only" |
| Row-level security library (RLS) | Application-level filtering sufficient | All queries in `database.py` already filter by user_id |
| Multi-database isolation | Not needed for v1 | Single MongoDB database, multiple collections |

**Installation / Verification:**
```bash
# No new packages required — all already in requirements.txt
pip show motor pymongo pydantic jose fastapi
```

---

## Package Legitimacy Audit

**Phase 19 installs: ZERO external packages** ✅

All required libraries are already in `requirements.txt`. This is a refactoring + data migration phase, not a new dependency phase.

| Package | Status |
|---------|--------|
| motor | Already installed (async MongoDB driver) |
| pymongo | Already installed (motor dependency) |
| fastapi | Already installed |
| pydantic | Already installed |
| python-jose | Already installed (auth.py) |

---

## MongoDB Migration Strategy

### Current State (Pre-Migration)

**Collections** (17+):
- `campaigns`, `runs`, `leads` (core)
- `client_profiles`, `client_knowledge` (customer data)
- `ideal_leads`, `rejected_leads` (prospecting)
- `whatsapp_agents`, `wa_sessions` (communication)
- `scheduled_actions`, `debtors`, `cobranza_calls*` (cobranza)
- `email_events`, `agents`, `scrape_logs` (infra)
- `registration_requests`, `users` (auth — already has unique constraint on email)

**Current Indexes** (all single-field or (user_id, field)):
```javascript
campaigns: { user_id: 1, is_active: 1 }
runs: { user_id: 1, started_at: -1 }, { run_id: unique }
leads: { run_id: 1, user_id: 1 }, { user_id: 1, created_at: -1 }
// ... etc, ~30 indexes total
```

**Risk:** No `tenant_id` field on existing docs → queries will fail when `tenant_id` filter added without backfill.

### Recommended 5-Step Migration Path

#### **Step 1: Database Schema Changes (Week 1, Day 1-2)** ⏱️ ~4-6 hours
**Objective:** Add `tenant_id` field to all documents and create new indexes.

**Actions:**
1. **Add `tenant_id` to Pydantic models** ([backend/models.py](backend/models.py))
   - All domain models: `Campaign`, `Lead`, `Run`, `ClientProfile`, etc.
   - Mark `tenant_id: str` as required for new documents
   - Example:
     ```python
     class Campaign(BaseModel):
         tenant_id: str  # ← NEW, required
         user_id: str
         campaign_id: str
         # ... existing fields
     ```

2. **Create MongoDB migration script** (`scripts/migrate_add_tenant_id.py`)
   ```python
   import asyncio
   import os
   from motor.motor_asyncio import AsyncIOMotorClient
   from bson import ObjectId
   
   async def migrate_add_tenant_id():
       client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
       db = client[os.getenv("MONGODB_DB", "hive_office")]
       
       collections = [
           "campaigns", "runs", "leads", "client_profiles", 
           "ideal_leads", "rejected_leads", "whatsapp_agents",
           "scheduled_actions", "debtors", "email_events", 
           "agents", "scrape_logs", "registration_requests",
           "cobranza_calls", "cobranza_calls_in_progress", "wa_sessions"
       ]
       
       for collection_name in collections:
           coll = db[collection_name]
           
           # Strategy: For now, use "legacy-unknown" as placeholder
           # Will be backfilled in Step 2 with actual tenant_id from email
           result = await coll.update_many(
               {"tenant_id": {"$exists": False}},
               {"$set": {"tenant_id": "legacy-unknown"}},
               upsert=False
           )
           print(f"{collection_name}: {result.modified_count} docs updated")
       
       await client.close()
   
   asyncio.run(migrate_add_tenant_id())
   ```

3. **Create new compound indexes** (add to [backend/database.py](backend/database.py) `init_db()`)
   ```python
   # Add to init_db() after existing indexes:
   await _safe_index(db.campaigns, [("tenant_id", 1), ("user_id", 1), ("is_active", 1)])
   await _safe_index(db.campaigns, [("tenant_id", 1), ("created_at", -1)])
   await _safe_index(db.runs, [("tenant_id", 1), ("run_id", 1)], unique=True)
   await _safe_index(db.runs, [("tenant_id", 1), ("user_id", 1), ("started_at", -1)])
   await _safe_index(db.leads, [("tenant_id", 1), ("run_id", 1), ("user_id", 1)])
   await _safe_index(db.leads, [("tenant_id", 1), ("user_id", 1), ("created_at", -1)])
   await _safe_index(db.leads, [("tenant_id", 1), ("estado", 1)])
   # ... repeat for all 17 collections
   ```

**Effort:** ~4-6 hours  
**Risk:** LOW — backward compatible (adds field, doesn't remove)  
**Rollback:** Delete `tenant_id` field (easy, no data loss)

---

#### **Step 2: Backfill Tenant IDs (Week 1, Day 2-3)** ⏱️ ~2-3 hours
**Objective:** Replace "legacy-unknown" with actual tenant_id from user email.

**Prerequisites:**
- All documents have `tenant_id` field (from Step 1)
- User email = tenant_id (decision locked in CONTEXT)

**Actions:**
1. **Create backfill script** (`scripts/backfill_tenant_ids.py`)
   ```python
   async def backfill_tenant_ids():
       client = AsyncIOMotorClient(os.getenv("MONGODB_URI"))
       db = client[os.getenv("MONGODB_DB", "hive_office")]
       
       # For each user, find all their docs and set tenant_id = user_id
       users = await db.users.find({}).to_list(None)
       
       for user in users:
           user_email = user.get("email")  # tenant_id = user_email
           user_id = str(user["_id"])
           
           # Email is tenant_id in this phase (CONTEXT.md locked)
           tenant_id = user_email  
           
           collections = ["campaigns", "runs", "leads", ...]
           for collection_name in collections:
               await db[collection_name].update_many(
                   {"user_id": user_id},
                   {"$set": {"tenant_id": tenant_id}}
               )
       
       # Verify: should be 0 docs with "legacy-unknown"
       for coll_name in collections:
           count = await db[coll_name].count_documents({"tenant_id": "legacy-unknown"})
           if count > 0:
               print(f"❌ WARNING: {coll_name} has {count} legacy-unknown docs")
       
       await client.close()
   ```

2. **Dry-run on staging first**
   - Deploy script to staging environment
   - Verify counts match production
   - Check query performance doesn't degrade

**Effort:** ~2-3 hours (including dry-run)  
**Risk:** MEDIUM — modifies existing data; can be rolled back by re-running script with different value  
**Verification:** Post-script, query each collection: `db.collection.countDocuments({tenant_id: "legacy-unknown"})` should return 0

---

#### **Step 3: Query Layer Refactoring (Week 1, Day 3-4)** ⏱️ ~15-20 hours
**Objective:** Add tenant_id filter to all queries; create helper functions.

**Sub-tasks:**

##### 3a. Extend `auth.py` to Extract tenant_id
**File:** [backend/auth.py](backend/auth.py)

**Change:** Add `tenant_id` to JWT payload at login, return in `get_current_user()`
```python
async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> dict:
    # ... existing JWT decode logic ...
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    user_id: Optional[str] = payload.get("sub")  # Email
    role: str = payload.get("role", "client")
    
    # NEW: Extract tenant_id from JWT
    tenant_id = payload.get("tenant_id", user_id)  # Fallback to user_id if missing
    
    return {
        "user_id": user_id,
        "role": role,
        "tenant_id": tenant_id  # ← NEW: always included
    }
```

**Also update JWT creation in `auth.py`:**
```python
def create_access_token(data: dict, expires_delta=None) -> str:
    to_encode = data.copy()
    # Ensure tenant_id is in the JWT payload
    if "tenant_id" not in to_encode:
        to_encode["tenant_id"] = to_encode.get("sub")  # user_email = tenant_id
    
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
```

**Effort:** ~1 hour  
**Risk:** LOW

##### 3b. Add Centralized Query Helpers to `database.py`
**File:** [backend/database.py](backend/database.py)

**Add helpers to enforce tenant_id filtering:**
```python
async def find_one_tenant(
    collection,
    tenant_id: str,
    query: dict,
    **kwargs
) -> dict:
    """
    Safe find_one that ALWAYS enforces tenant_id filter.
    Prevents accidental queries without tenant isolation.
    
    Example:
        lead = await find_one_tenant(db.leads, tenant_id, 
                                     {"_id": ObjectId(lead_id), "user_id": user_id})
    """
    query = {**query, "tenant_id": tenant_id}  # Add tenant_id, don't override
    return await collection.find_one(query, **kwargs)


async def find_tenant(
    collection,
    tenant_id: str,
    query: dict = None,
    **kwargs
):
    """
    Safe find (cursor) that ALWAYS enforces tenant_id filter.
    Returns Motor cursor for iteration.
    """
    query = query or {}
    query = {**query, "tenant_id": tenant_id}
    return collection.find(query, **kwargs)


async def aggregate_tenant(
    collection,
    tenant_id: str,
    pipeline: list
):
    """
    Safe aggregation that ALWAYS prepends tenant_id $match stage.
    Prevents pipeline bypass of tenant isolation.
    
    Example:
        result = await aggregate_tenant(db.leads, tenant_id, [
            {"$group": {"_id": "$estado", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ])
    """
    # Prepend tenant filter as first stage
    safe_pipeline = [
        {"$match": {"tenant_id": tenant_id}},
        *pipeline
    ]
    return await collection.aggregate(safe_pipeline).to_list(None)


async def count_tenant(collection, tenant_id: str, query: dict = None) -> int:
    """Safe count that enforces tenant_id filter."""
    query = query or {}
    query = {**query, "tenant_id": tenant_id}
    return await collection.count_documents(query)


async def delete_tenant(collection, tenant_id: str, query: dict):
    """Safe delete that enforces tenant_id filter."""
    query = {**query, "tenant_id": tenant_id}
    return await collection.delete_many(query)


async def update_tenant(collection, tenant_id: str, query: dict, update: dict, **kwargs):
    """Safe update that enforces tenant_id filter."""
    query = {**query, "tenant_id": tenant_id}
    return await collection.update_many(query, update, **kwargs)
```

**Effort:** ~2 hours  
**Risk:** LOW (new functions, no changes to existing code yet)

##### 3c. Audit and Update All Queries (Main Effort)
**File:** All router files in [backend/routers/](backend/routers/)

**Scope:** ~40-50 query sites to refactor. Systematic pattern:

**Before:**
```python
# routers/prospect.py
@router.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    campaigns = await db.campaigns.find_one({
        "user_id": current_user["user_id"],
        "is_active": True
    })
    return campaigns
```

**After:**
```python
@router.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    campaigns = await find_one_tenant(
        db.campaigns,
        current_user["tenant_id"],  # ← NEW: always first
        {"user_id": current_user["user_id"], "is_active": True}
    )
    return campaigns
```

**Query Audit Checklist:**
| File | Pattern | Examples | Refactor Method |
|------|---------|----------|-----------------|
| [routers/leads.py](backend/routers/leads.py) | `db.leads.find({user_id})` | find_one, find, insert | find_one_tenant(), find_tenant() |
| [routers/prospect.py](backend/routers/prospect.py) | `db.campaigns.find()`, aggregations | Query + sort | find_tenant(), aggregate_tenant() |
| [routers/knowledge.py](backend/routers/knowledge.py) | `db.client_knowledge.find()` | Multiple queries | find_tenant() |
| [database.py](backend/database.py) | All existing DB functions | get_leads_by_user(), save_lead() | Wrap with tenant_id param |
| [worker.py](backend/worker.py) | ARQ job queries | save_lead(), update_run_status() | Pass tenant_id through job context |

**Effort:** ~12-15 hours (systematic, parallelizable)  
**Risk:** MEDIUM — if any query is missed, tenant leakage possible  
**Verification:** Run grep to find all remaining `db.*.find()` calls without `find_one_tenant()`

---

#### **Step 4: WebSocket Channel Namespacing (Week 1, Day 4)** ⏱️ ~4-6 hours
**Objective:** Change ConnectionManager and ARQ worker to use tenant_id in channel names.

##### 4a. Update ConnectionManager
**File:** [backend/services/connection_manager.py](backend/services/connection_manager.py)

**Current:**
```python
class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}  # Key: user_id

    async def connect(self, websocket: WebSocket, user_id: str):
        self.active_connections[user_id] = websocket
    
    async def send_to_user(self, user_id: str, message: dict):
        ws = self.active_connections.get(user_id)
        if ws:
            await ws.send_json(message)
```

**After:**
```python
class ConnectionManager:
    def __init__(self):
        # Key: tenant_id:{run_id} to isolate broadcasts
        self.active_connections: Dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, tenant_id: str, run_id: str):
        """Register WebSocket for a specific run within a tenant."""
        channel = f"{tenant_id}:{run_id}"
        self.active_connections[channel] = websocket
    
    def disconnect(self, tenant_id: str, run_id: str):
        """Unregister WebSocket from a run."""
        channel = f"{tenant_id}:{run_id}"
        self.active_connections.pop(channel, None)
    
    async def send_to_run(self, tenant_id: str, run_id: str, message: dict):
        """Send message only to WebSocket for this tenant's run."""
        channel = f"{tenant_id}:{run_id}"
        ws = self.active_connections.get(channel)
        if ws:
            try:
                await ws.send_json(message)
            except Exception:
                self.disconnect(tenant_id, run_id)
    
    async def broadcast(self, message: dict):
        """Broadcast to ALL (use sparingly; prefer send_to_run)."""
        disconnected = []
        for channel, connection in self.active_connections.items():
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(channel)
        for channel in disconnected:
            self.active_connections.pop(channel, None)
```

**Effort:** ~2 hours  
**Risk:** LOW (isolated change, clear new behavior)

##### 4b. Update ARQ Worker Redis Channels
**File:** [backend/worker.py](backend/worker.py)

**Current:**
```python
async def run_prospecting_job(ctx: dict, run_id: str, user_id: str, campaign: dict, ...):
    redis_client = ctx["redis"]
    channel = f"ws:{user_id}:{run_id}"  # ← user_id (not tenant_id)
    
    async def publish_event(uid: str, message: dict):
        await redis_client.publish(f"ws:{uid}:{run_id}", json.dumps(message))
```

**After:**
```python
async def run_prospecting_job(
    ctx: dict,
    run_id: str,
    user_id: str,
    tenant_id: str,  # ← NEW: passed from route handler
    campaign: dict,
    ...
):
    redis_client = ctx["redis"]
    channel = f"ws:{tenant_id}:{run_id}"  # ← Now tenant_id-based
    
    async def publish_event(uid: str, message: dict):
        # uid is now tenant_id, not user_id
        await redis_client.publish(f"ws:{uid}:{run_id}", json.dumps(message))
    
    # ... rest of function
```

**Effort:** ~1.5 hours  
**Risk:** LOW (isolated change)

##### 4c. Update Route Handler that Enqueues Job
**File:** [routers/prospect.py](backend/routers/prospect.py) (likely in `@router.post("/api/prospect")`)

**Before:**
```python
@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    # ... create campaign ...
    
    job = await app.state.arq_pool.enqueue_job(
        "run_prospecting_job",
        run_id=run_id,
        user_id=user_id,
        campaign=campaign_dict,
        # ... other args
    )
```

**After:**
```python
@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]  # ← Pass tenant_id to worker
    # ... create campaign ...
    
    job = await app.state.arq_pool.enqueue_job(
        "run_prospecting_job",
        run_id=run_id,
        user_id=user_id,
        tenant_id=tenant_id,  # ← NEW
        campaign=campaign_dict,
        # ... other args
    )
```

**Effort:** ~1-2 hours  
**Risk:** LOW

##### 4d. Update Frontend WebSocket Subscribe Path
**File:** [frontend/src/hooks/useWebSocket.ts](frontend/src/hooks/useWebSocket.ts) (or wherever WS connection happens)

**Assumption:** Frontend has JWT access (already decodes it).

**Before:**
```typescript
// frontend
const tenantId = decodeToken(jwt).sub; // user_email
const runId = "...";
ws = new WebSocket(`wss://api.example.com/ws/${tenantId}/${runId}`);
```

**After:**
```typescript
const token = decodeToken(jwt);
const tenantId = token.sub;  // user_email = tenant_id
const runId = "...";
ws = new WebSocket(`wss://api.example.com/ws/${tenantId}/${runId}`);
// No change needed if frontend already derives tenant_id (which CONTEXT.md says it does)
```

**Effort:** ~0 hours (already designed this way per CONTEXT)

**Effort (4a-4d Total):** ~4-6 hours  
**Risk:** MEDIUM — WebSocket is critical; must verify with 2 concurrent brokers

---

#### **Step 5: Testing, Verification & Rollback Plan (Week 1, Day 4-5)** ⏱️ ~8-10 hours

##### 5a. Unit Tests: Tenant Filtering
**File:** `tests/test_tenant_isolation.py` (new)

```python
import pytest
from backend.database import find_one_tenant, aggregate_tenant

@pytest.mark.asyncio
async def test_find_one_tenant_enforces_filter(db_client):
    """Verify find_one_tenant always adds tenant_id filter."""
    tenant_a = "broker-a@example.com"
    tenant_b = "broker-b@example.com"
    
    # Insert lead for tenant A
    await db_client.leads.insert_one({
        "tenant_id": tenant_a,
        "user_id": "user1",
        "empresa": "Company A"
    })
    
    # Insert lead for tenant B
    await db_client.leads.insert_one({
        "tenant_id": tenant_b,
        "user_id": "user1",  # Same user_id (edge case)
        "empresa": "Company B"
    })
    
    # Query as tenant A
    result = await find_one_tenant(
        db_client.leads,
        tenant_a,
        {"user_id": "user1"}
    )
    
    assert result["empresa"] == "Company A"
    assert result["tenant_id"] == tenant_a
```

**Effort:** ~2 hours (write 5-10 test cases)  
**Risk:** LOW

##### 5b. E2E Test: 2 Brokers, No Data Leakage
**File:** `tests/e2e_tenant_isolation.py` (new)

**Scenario:**
1. Register broker-a@example.com, create campaign, run prospecting
2. Register broker-b@example.com, create campaign, run prospecting
3. Both run simultaneously (or sequential)
4. Verify:
   - Broker A sees only A's leads (not B's)
   - Broker B sees only B's leads (not A's)
   - WebSocket channels isolated (A's updates don't appear in B's feed)

```python
@pytest.mark.asyncio
async def test_two_brokers_concurrent_isolation():
    """E2E: Broker A & B create data, verify no cross-tenant visibility."""
    
    # 1. Setup: Register 2 brokers
    broker_a_token = await register_and_login("broker-a@example.com")
    broker_b_token = await register_and_login("broker-b@example.com")
    
    # 2. Create campaigns
    campaign_a = await create_campaign(broker_a_token, name="Campaign A")
    campaign_b = await create_campaign(broker_b_token, name="Campaign B")
    
    # 3. Broker A: Query their campaign
    campaigns_a = await list_campaigns(broker_a_token)
    assert len(campaigns_a) == 1
    assert campaigns_a[0]["name"] == "Campaign A"
    
    # 4. Broker B: Query their campaign
    campaigns_b = await list_campaigns(broker_b_token)
    assert len(campaigns_b) == 1
    assert campaigns_b[0]["name"] == "Campaign B"
    
    # 5. Broker A: Try to access B's campaign (should fail)
    with pytest.raises(HTTPException) as exc:
        await get_campaign(broker_a_token, campaign_b["_id"])
    assert exc.value.status_code == 404  # Broker A can't see B's data
    
    # 6. WebSocket: 2 concurrent connections
    # Subscribe broker A to their run
    ws_a = await websocket_connect(broker_a_token, campaign_a["_id"])
    # Subscribe broker B to their run
    ws_b = await websocket_connect(broker_b_token, campaign_b["_id"])
    
    # Send message to broker A's run
    await ws_a.send_json({"type": "test_message", "data": "hello from A"})
    
    # Verify broker B does NOT receive broker A's message
    try:
        # Non-blocking receive with timeout
        msg_b = await asyncio.wait_for(ws_b.receive_json(), timeout=0.5)
        assert msg_b["data"] != "hello from A", "Broker B received Broker A's message!"
    except asyncio.TimeoutError:
        pass  # Expected: B should not receive A's messages
```

**Effort:** ~3-4 hours  
**Risk:** LOW

##### 5c. Performance Verification
**File:** `tests/perf_tenant_queries.py` (new)

```python
@pytest.mark.asyncio
async def test_query_performance_100k_docs():
    """Verify query response time < 100ms with compound indexes."""
    
    # Setup: 100k leads, distributed across 10 tenants
    for i in range(100_000):
        await db.leads.insert_one({
            "tenant_id": f"tenant-{i % 10}",
            "user_id": f"user-{i % 100}",
            "lead_id": f"lead-{i}",
            "empresa": f"Company {i}",
            "created_at": datetime.now(timezone.utc)
        })
    
    # Query: Get leads for one tenant
    start = time.time()
    leads = await find_tenant(
        db.leads,
        "tenant-0",
        {"user_id": "user-0"}
    ).to_list(length=100)
    elapsed = time.time() - start
    
    assert elapsed < 0.1, f"Query took {elapsed}s, expected < 100ms"
```

**Effort:** ~2 hours  
**Risk:** LOW

##### 5d. Rollback Plan

**If deployment fails:**

1. **Rollback code**: Git revert to commit before Phase 19
2. **Rollback data**: MongoDB migration is reversible
   ```javascript
   // Option A: Delete tenant_id field from all docs (if no damage)
   db.campaigns.updateMany({}, {$unset: {tenant_id: 1}})
   
   // Option B: Restore from backup (if data was damaged)
   // Use MongoDB backup from pre-deployment snapshot
   ```
3. **Rollback indexes**: Drop new compound indexes
   ```javascript
   db.campaigns.dropIndex("tenant_id_1_user_id_1_is_active_1")
   ```
4. **Revert WebSocket channels**: Revert ConnectionManager to user_id keying
5. **Restart services**: Redeploy previous commit

**Effort:** ~30 minutes (automated via scripts)

**5e. Dry-Run on Staging**

Before production:
1. Deploy Phase 19 code to staging
2. Run E2E test (2 brokers) on staging
3. Run performance test with 100k docs
4. Monitor for 24 hours
5. Get sign-off from product/security
6. Then proceed to production

**Effort:** ~2 hours (monitoring + verification)

---

## Query Layer Refactoring: Implementation Details

### Current Query Patterns (Audit Results)

**Grep Results:** 40+ query sites found in backend. Top files:

| File | Queries Found | Priority | Refactor Method |
|------|---------------|----------|-----------------|
| [database.py](backend/database.py) | 25+ | HIGH | Wrap all with tenant_id param |
| [routers/leads.py](backend/routers/leads.py) | 10 | HIGH | find_tenant() wrapper |
| [routers/prospect.py](backend/routers/prospect.py) | 8 | HIGH | find_tenant(), aggregate_tenant() |
| [routers/staff.py](backend/routers/staff.py) | 5 | MEDIUM | find_tenant() + require_staff() combo |
| [routers/knowledge.py](backend/routers/knowledge.py) | 4 | HIGH | find_tenant() |

### Query Refactoring Template

**Before (Single-Tenant):**
```python
# database.py
async def get_active_campaign(user_id: str):
    return await db.campaigns.find_one({
        "user_id": user_id,
        "is_active": True
    })

# routers/prospect.py
@router.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    campaign = await get_active_campaign(current_user["user_id"])
    return campaign
```

**After (Multi-Tenant):**
```python
# database.py — Signature change
async def get_active_campaign(tenant_id: str, user_id: str):
    return await find_one_tenant(
        db.campaigns,
        tenant_id,
        {"user_id": user_id, "is_active": True}
    )

# routers/prospect.py
@router.get("/api/campaigns/active")
async def get_campaign_endpoint(current_user: dict = Depends(get_current_user)):
    campaign = await get_active_campaign(
        current_user["tenant_id"],  # ← Always first arg
        current_user["user_id"]
    )
    return campaign
```

### Aggregation Pipelines (Complex Queries)

**Current Example** (from database.py search results, line 661):
```python
async def get_leads_facets(user_id: str):
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {"_id": "$estado", "count": {"$sum": 1}}}
    ]
    return await db.leads.aggregate(pipeline).to_list(length=200)
```

**After:**
```python
async def get_leads_facets(tenant_id: str, user_id: str):
    pipeline = [
        {"$match": {"user_id": user_id}},  # ← Keep user filter
        {"$group": {"_id": "$estado", "count": {"$sum": 1}}}
    ]
    return await aggregate_tenant(db.leads, tenant_id, pipeline)
    # aggregate_tenant prepends: {"$match": {"tenant_id": tenant_id}}
```

---

## WebSocket Channel Namespacing

### Current Architecture
```
Frontend: ws://api.example.com/ws/{user_id}/{run_id}
           ↓
Backend ConnectionManager: active_connections[f"{user_id}:{run_id}"] = WebSocket
           ↓
ARQ Worker: Publishes to Redis channel: ws:{user_id}:{run_id}
           ↓
Frontend Redis subscriber: Listens to ws:{user_id}:{run_id}
```

**Risk:** If two brokers have same `user_id` format, collision. Example:
- Broker A: user_id = "user123@example.com"
- Broker B: user_id = "user123" (no domain)
- Both users create run with run_id = "run-001"
- Channel collision: `ws:user123:run-001` ← ambiguous!

### After Phase 19 (Tenant-Isolated)
```
Frontend: ws://api.example.com/ws/{tenant_id}/{run_id}
          (tenant_id = broker email, unique globally)
           ↓
Backend ConnectionManager: active_connections[f"{tenant_id}:{run_id}"] = WebSocket
                          (e.g., "dpg.seguros@gmail.com:run-123")
           ↓
ARQ Worker: Publishes to Redis channel: ws:{tenant_id}:{run_id}
           ↓
Redis: Channel names GLOBALLY UNIQUE → no collision risk
```

### Testing WebSocket Isolation

**Test Scenario:**
```python
async def test_websocket_isolation_2_brokers():
    """Verify WebSocket messages don't leak across tenants."""
    
    # 1. Broker A connects
    ws_a = await connect_websocket(
        tenant_id="broker-a@example.com",
        run_id="run-001"
    )
    # ConnectionManager stores: active_connections["broker-a@example.com:run-001"] = ws_a
    
    # 2. Broker B connects
    ws_b = await connect_websocket(
        tenant_id="broker-b@example.com",
        run_id="run-001"  # Same run_id, different tenant
    )
    # ConnectionManager stores: active_connections["broker-b@example.com:run-001"] = ws_b
    
    # 3. Worker publishes message for Broker A
    await worker.publish_event(
        tenant_id="broker-a@example.com",
        run_id="run-001",
        message={"type": "lead_found", "empresa": "Secret Company"}
    )
    
    # 4. Broker A receives it
    msg_a = await ws_a.receive_json(timeout=1.0)
    assert msg_a["empresa"] == "Secret Company"
    
    # 5. Broker B does NOT receive it
    with pytest.raises(asyncio.TimeoutError):
        msg_b = await ws_b.receive_json(timeout=0.5)
    
    # ✅ PASS: Messages properly isolated
```

---

## Authentication Layer Integration

### Tenant ID Extraction

**Decision:** `tenant_id = user_id` = broker email (from JWT "sub" claim)

**Flow:**
```
1. Broker logs in: POST /auth/login {email, password}
2. Backend validates credentials
3. Backend creates JWT with:
   - "sub": "dpg.seguros@gmail.com"
   - "role": "client"
   - "tenant_id": "dpg.seguros@gmail.com"  ← NEW
4. Frontend stores JWT
5. Frontend sends JWT in Authorization header or httpOnly cookie
6. get_current_user() decodes JWT, extracts tenant_id
7. Returns: {"user_id": "dpg.seguros@gmail.com", "role": "client", "tenant_id": "dpg.seguros@gmail.com"}
8. All route handlers receive tenant_id, pass to queries
```

**Implementation:** Already described in Step 3a above (update auth.py)

### Dependency Injection Pattern

**Existing in codebase:**
```python
from fastapi import Depends, HTTPException

async def get_current_user(...) -> dict:
    # Returns user context
    pass

async def require_staff(current_user: dict = Depends(get_current_user)) -> dict:
    # Requires user.role == "staff"
    pass
```

**Phase 19 Usage:**
```python
@router.get("/api/leads")
async def get_leads(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]  # ← Extracted automatically
    user_id = current_user["user_id"]
    
    leads = await find_tenant(db.leads, tenant_id, {"user_id": user_id})
    return leads
```

**New Dependency (Optional, for stricter control):**
```python
async def get_current_tenant(current_user: dict = Depends(get_current_user)) -> str:
    """Returns tenant_id, fails if not present (safety check)."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Tenant context missing")
    return tenant_id

# Usage:
@router.get("/api/leads")
async def get_leads(tenant_id: str = Depends(get_current_tenant)):
    leads = await find_tenant(db.leads, tenant_id, {})
    return leads
```

---

## Testing & Validation Strategy

### Test Scope

| Test Type | Scope | Effort | Risk if Missing |
|-----------|-------|--------|-----------------|
| **Unit: Query Filtering** | Each helper function (find_one_tenant, aggregate_tenant) | ~2h | HIGH — core logic untested |
| **Unit: Auth** | JWT tenant_id extraction, get_current_user() | ~1h | HIGH — auth bypass |
| **Integration: E2E 2 Brokers** | 2 brokers, simultaneous operations, data isolation | ~4h | CRITICAL — main requirement |
| **Performance** | Query time with 100k docs, compound indexes | ~2h | MEDIUM — SLA risk |
| **WebSocket Isolation** | 2 concurrent WS connections, message routing | ~2h | HIGH — real-time leakage |
| **Regression: Existing Endpoints** | 20 critical endpoints, post-migration | ~3h | MEDIUM — feature breakage |

### Test Execution Plan

**Phase 1 (Week 1, Day 4):**
- Run unit tests in CI/CD
- Run E2E test on staging
- Dry-run performance test

**Phase 2 (Week 1, Day 5):**
- 24-hour staging soak test (monitor for leaks)
- Manual testing: 2 brokers in staging
- Sign-off from product/security

**Phase 3 (Week 2, Day 1):**
- Production canary: 10% users
- Monitor error rates, latency, tenant leakage alerts
- Full rollout if green

---

## Common Pitfalls & Mitigations

### Pitfall 1: Aggregation Pipeline Bypass
**Risk:** Developer writes aggregation without using `aggregate_tenant()`, leading to cross-tenant data leakage.

**Example:**
```python
# ❌ WRONG: Leaks data
pipeline = [{"$group": {"_id": "$sector", "count": {"$sum": 1}}}]
result = await db.leads.aggregate(pipeline).to_list(None)  # No tenant filter!
```

**Mitigation:**
- Use `aggregate_tenant()` helper (always prepends tenant filter)
- Linting rule: Flag all `db.*.aggregate()` calls not wrapped by helper
- Code review checklist item

**Effort to Prevent:** ~1 hour (lint rule setup)

---

### Pitfall 2: Worker Job Doesn't Receive tenant_id
**Risk:** ARQ worker publishes to `ws:{user_id}:{run_id}` instead of `ws:{tenant_id}:{run_id}`, causing WebSocket messages to route incorrectly.

**Example:**
```python
# ❌ WRONG: Worker doesn't know tenant_id
await enqueue_job("run_prospecting_job", run_id=run_id, user_id=user_id)
# Worker has no tenant_id, publishes to ws:user_id:run_id ← Ignores tenant isolation
```

**Mitigation:**
- Route handler MUST pass `tenant_id` when enqueueing job
- Type hint in ARQ job signature: `tenant_id: str` (catches missing param)
- Test: Verify job receives tenant_id

**Effort to Prevent:** ~1 hour (code review + testing)

---

### Pitfall 3: Soft-Delete Not Enforced on Queries
**Risk:** After marking tenant as inactive, queries still return data for inactive tenants.

**Example:**
```python
# ❌ WRONG: Returns data for all tenants, including inactive
leads = await find_tenant(db.leads, tenant_id, {"estado": "checkpoint"})
```

**Mitigation:**
- Add `tenant_status` to queries: `{"tenant_id": tenant_id, "tenant_status": "active"}`
- Or: Wrap all queries with filter function that adds status check
- Update test: Verify inactive tenant data not returned

**Effort to Prevent:** ~2 hours (implement + test)

---

### Pitfall 4: Index Order Matters (Performance Regression)
**Risk:** Without proper compound indexes, queries slow down 10-100x when tenant_id is added.

**Example:**
```javascript
// ❌ WRONG: Index order
db.leads.createIndex({ "user_id": 1, "tenant_id": 1 })
// Query: {tenant_id, user_id} uses this inefficiently (ESR rule violation)

// ✅ CORRECT: Tenant first (Equality-Sort-Range rule)
db.leads.createIndex({ "tenant_id": 1, "user_id": 1, "created_at": -1 })
```

**Mitigation:**
- Follow ESR (Equality-Sort-Range) indexing rule
- Performance test: Verify < 100ms for 100k docs
- Index analysis: Use MongoDB explain() plan to verify index usage

**Effort to Prevent:** ~1 hour (index design review)

---

### Pitfall 5: Frontend Still Uses Old WebSocket URL
**Risk:** Frontend connects to `ws://.../ws/{user_id}/{run_id}`, but backend now expects `{tenant_id}/{run_id}`.

**Example:**
```typescript
// ❌ WRONG: Frontend doesn't know about tenant_id namespacing
const url = `wss://api.example.com/ws/${userId}/${runId}`;
ws = new WebSocket(url);
```

**Mitigation:**
- CONTEXT.md already says: Frontend derives tenant_id from JWT
- No backend URL change needed (if frontend already does this)
- If frontend hasn't been updated: Coordinate with frontend team, update WebSocket endpoint

**Effort to Prevent:** ~0 hours (already designed in CONTEXT)

---

### Pitfall 6: Batch Queries (updateMany, deleteMany) Bypass tenant_id
**Risk:** `db.leads.updateMany({user_id}, {$set: {...}})` updates leads for ALL tenants with that user_id.

**Example:**
```python
# ❌ WRONG: Batch update without tenant filter
result = await db.leads.update_many(
    {"user_id": user_id},
    {"$set": {"estado": "processed"}}
)
# Updates leads for user_id across ALL tenants!
```

**Mitigation:**
- Use `update_tenant()` helper (enforces tenant filter)
- Never call `updateMany`, `deleteMany` directly
- Code review: All batch operations must use centralized helper

**Effort to Prevent:** ~1 hour (enforce via helper)

---

## Deployment & Rollback Strategy

### Deployment Approach: Staged Rollout

**Option A: Blue-Green (Recommended)**
- Deploy Phase 19 code to "green" environment (new, separate)
- Run E2E tests in green (2 brokers, no leakage)
- Run 24h soak test in green
- Cut traffic from blue → green (instant, atomic)
- Keep blue running for quick rollback

**Advantages:**
- Zero downtime
- Quick rollback (revert to blue)
- Staging mirrors production exactly

**Disadvantages:**
- 2x infrastructure cost temporarily

**Effort:** ~2 hours (deploy + verify)

---

**Option B: Canary (If no blue-green capacity)**
- Deploy Phase 19 to 10% of users
- Monitor: error rate, latency, cross-tenant query alerts
- If 2 hours green, expand to 50%, then 100%

**Advantages:**
- Lower infrastructure cost
- Gradual rollout, safer

**Disadvantages:**
- Slower rollout (if issues, affects more users)
- More complex monitoring setup

**Effort:** ~3 hours (deploy + monitor)

---

### Rollback Procedure (If Issues Detected)

**Time to Rollback:** < 30 minutes

1. **Immediate:** Git revert to commit before Phase 19
   ```bash
   git revert --no-edit <phase-19-commit>
   git push
   # Redeploy previous commit
   ```

2. **Data:** MongoDB rollback (do NOT delete tenant_id field; just stop using it)
   ```javascript
   // Option 1: Ignore tenant_id (it's inert, doesn't break queries)
   // All queries add tenant_id filter naturally, data still correct
   
   // Option 2: Restore from backup (if data was corrupted)
   // Use pre-migration snapshot from MongoDB backup
   ```

3. **Services:**
   - Restart backend (old code, new data with tenant_id)
   - Restart worker (old code)
   - Restart frontend (if WebSocket changes were deployed)

4. **Verify:**
   - Queries return data (even with unused tenant_id field)
   - WebSocket connections work
   - E2E test: 1 broker, full workflow

**Alert Triggers for Rollback:**
- Error rate spike > 2%
- Cross-tenant query detected (monitoring alert)
- Latency p99 > 1s (index missing)
- WebSocket connection failures

---

## Monitoring & Alerting (Post-Deployment)

### Critical Alerts

| Alert | Query | Threshold | Action |
|-------|-------|-----------|--------|
| **Cross-tenant query** | `db.audit.count({type: "tenant_leak"})` | > 0 | Page on-call, investigate |
| **Error rate** | `errors / requests` | > 2% | Evaluate rollback |
| **Query latency p99** | MongoDB query time | > 1s | Check indexes, evaluate rollback |
| **WebSocket disconnects** | Connection drop rate | > 5% | Check ConnectionManager, evaluate rollback |

### Cross-Tenant Query Detection

**Recommendation:** Add logging to `find_one_tenant()`, `find_tenant()` helpers.

```python
async def find_one_tenant(collection, tenant_id: str, query: dict):
    if "tenant_id" in query:
        # Warn: duplicate tenant_id in query (may indicate developer error)
        logger.warning("[AUDIT] Duplicate tenant_id in query: %s", query)
    
    query = {**query, "tenant_id": tenant_id}
    result = await collection.find_one(query)
    
    # If result is None, log (useful for debugging)
    if result is None:
        logger.debug("[AUDIT] find_one_tenant miss: %s", query)
    
    return result
```

---

## Architecture Patterns

### Recommended Project Structure (No Changes)
```
backend/
├── main.py                 # FastAPI app, lifespan
├── auth.py                 # ← MODIFIED: Extract tenant_id from JWT
├── database.py             # ← MODIFIED: Add find_one_tenant(), aggregate_tenant(), etc.
├── models.py               # ← MODIFIED: Add tenant_id to domain models
├── routers/                # ← MODIFIED: All routes use tenant_id parameter
│   ├── prospect.py         #   Update queries, pass tenant_id to worker
│   ├── leads.py            #   Update queries
│   ├── knowledge.py        #   Update queries
│   └── ...
├── services/
│   └── connection_manager.py  # ← MODIFIED: Key by tenant_id:run_id
├── worker.py               # ← MODIFIED: Accept tenant_id, publish to tenant-scoped channels
└── scripts/
    ├── migrate_add_tenant_id.py      # ← NEW: Add field to all docs
    ├── backfill_tenant_ids.py        # ← NEW: Backfill from user email
    └── verify_tenant_isolation.py    # ← NEW: Pre-deployment audit
```

### Query Pattern (Centralized Helper)

All queries follow this pattern:
```python
# Old (single-tenant)
result = await db.collection.find_one({"user_id": user_id})

# New (multi-tenant)
result = await find_one_tenant(
    db.collection,
    current_user["tenant_id"],  # Always from auth
    {"user_id": user_id}        # Business-logic filter
)
```

**Why:**
- `tenant_id` is ALWAYS first (enforced by helper, not developer choice)
- Prevents accidental queries without tenant filter
- Auditable: search for `find_one_tenant` finds all queries

---

## Don't Hand-Roll (Multi-Tenant Is Hard)

| Problem | Don't Build | Use Instead | Why |
|---------|------------|------------|-----|
| Tenant data isolation | Custom WHERE clause injection | `find_one_tenant()` helper (enforced) | Prevents logic errors; single source of truth |
| Aggregation safety | Manual `$match` prepending | `aggregate_tenant()` helper | One place to test; easy to audit |
| Auth context | Manual tenant extraction | `get_current_user()` dep injection | Centralized, tested, reusable |
| WebSocket channel naming | Ad-hoc string formats | `f"{tenant_id}:{run_id}"` constant | Prevents typos; globally unique |
| Multi-tenant indexing | Default indexes | Compound `(tenant_id, ...)` indexes | ESR rule; prevents query performance degradation |

**Key Insight:** Multi-tenancy is a **systemic change**, not a feature. Every layer must enforce it. Helpers prevent developers from accidentally opting out of isolation.

---

## Code Examples (Verified Patterns)

### Pattern 1: Route Handler with Tenant Context
```python
# Source: Phase 19 spec + existing routers/prospect.py
@router.get("/api/leads")
async def get_leads(current_user: dict = Depends(get_current_user)):
    tenant_id = current_user["tenant_id"]
    user_id = current_user["user_id"]
    
    leads = await find_tenant(
        db.leads,
        tenant_id,
        {"user_id": user_id}
    ).sort("created_at", -1).to_list(length=100)
    
    return leads
```

### Pattern 2: Aggregation with Tenant Filter
```python
# Source: Phase 19 spec + database.py line 661 aggregation example
async def get_leads_by_estado(tenant_id: str, user_id: str):
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$group": {
            "_id": "$estado",
            "count": {"$sum": 1},
            "sample": {"$first": "$empresa"}
        }},
        {"$sort": {"count": -1}}
    ]
    
    return await aggregate_tenant(db.leads, tenant_id, pipeline)
    # aggregate_tenant prepends: {"$match": {"tenant_id": tenant_id}}
```

### Pattern 3: WebSocket Broadcast (Tenant-Scoped)
```python
# Source: Phase 19 spec + ConnectionManager refactor
async def publish_prospect_event(tenant_id: str, run_id: str, event: dict):
    """Publish event to specific tenant's run."""
    await connection_manager.send_to_run(tenant_id, run_id, event)
    
    # Also publish to Redis (for worker-to-frontend flow)
    redis_channel = f"ws:{tenant_id}:{run_id}"
    await redis_client.publish(redis_channel, json.dumps(event))
```

---

## Decision Points for Planner

**Checkpoint 1: Migration Strategy**
- **Decision:** Use 5-step approach (schema → backfill → queries → WebSocket → test)?
- **Alternative:** Single-step migration (riskier, but faster if fully tested)

**Checkpoint 2: Zero-Downtime Deployment**
- **Decision:** Blue-green deployment (2x infra temporarily)?
- **Alternative:** Canary rollout (slower, lower cost)

**Checkpoint 3: Soft-Delete Enforcement**
- **Decision:** All queries include `tenant_status = "active"`?
- **Alternative:** Skip for v1, add in Phase 28

**Checkpoint 4: Index Strategy**
- **Decision:** Create all 30+ new compound indexes upfront?
- **Alternative:** Lazy create (create when query observably slow)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|-----------|-----------|-----------|---------|----------|
| MongoDB | Data layer | ✅ | 6.x (Railway) | — |
| Redis | WebSocket pub/sub | ✅ | 7.x (Railway) | — |
| Motor (async MongoDB) | Database layer | ✅ | 3.x | — |
| Python | Backend | ✅ | 3.10+ | — |
| FastAPI | HTTP server | ✅ | 0.100+ | — |
| ARQ | Job queue | ✅ | 0.25+ | — |

**Missing dependencies:** None — all available on Railway infrastructure.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio |
| Config file | `tests/conftest.py` (shared fixtures) |
| Quick run command | `pytest tests/test_tenant_isolation.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| TENANT-01 | All collections have tenant_id field + index | Unit | `pytest tests/test_tenant_isolation.py::test_collections_have_tenant_id -x` | ❌ Wave 0 |
| TENANT-02 | All queries filter by tenant_id explicitly | Unit | `pytest tests/test_tenant_isolation.py::test_find_one_tenant_enforces_filter -x` | ❌ Wave 0 |
| TENANT-03 | WebSocket channels use tenant_id namespacing | Integration | `pytest tests/e2e_tenant_isolation.py::test_websocket_isolation_2_brokers -x` | ❌ Wave 0 |
| TENANT-04 | Compound indexes exist on (tenant_id, fields) | Unit | `pytest tests/test_tenant_isolation.py::test_indexes_exist -x` | ❌ Wave 0 |
| TENANT-05 | Aggregations filter by tenant_id (first stage) | Unit | `pytest tests/test_tenant_isolation.py::test_aggregate_tenant_prepends_match -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_tenant_isolation.py -x` (quick unit tests)
- **Per wave merge:** `pytest tests/ -x` (full suite including E2E)
- **Phase gate:** Full suite green + 24h staging soak test before production

### Wave 0 Gaps
- [ ] `tests/test_tenant_isolation.py` — unit tests for query helpers (find_one_tenant, aggregate_tenant)
- [ ] `tests/e2e_tenant_isolation.py` — 2-broker E2E test
- [ ] `tests/perf_tenant_queries.py` — performance test (100k docs, < 100ms)
- [ ] `tests/conftest.py` — shared fixtures (db client, async loop, test brokers)
- [ ] Framework install: `pip install pytest pytest-asyncio` (likely already installed)

---

## Security Domain

### Applicable ASVS (Application Security Verification Standard) Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | ✅ Yes | JWT tenant_id extraction (auth.py) |
| V3 Session Management | ✅ Yes | Tenant context in session (current_user dict) |
| V4 Access Control | ✅ YES ⭐ | Mandatory: find_one_tenant() enforces tenant_id filter |
| V5 Input Validation | ✅ Yes | Pydantic validates tenant_id present |
| V6 Cryptography | ✅ Yes | JWT signed with SECRET_KEY (existing) |

### V4 Access Control: Critical for This Phase
**Threat:** Cross-tenant data access (CWE-639: Authorization Bypass)

**Mitigation:**
- All queries MUST enforce tenant_id filter
- `find_one_tenant()` helper prevents developer bypass
- Linting rule: Flag direct `db.*.find()` calls (should use helper)
- Code review: Mandatory for every query change

**Testing:**
- E2E: 2 brokers, verify neither sees other's data
- Unit: Query helpers, verify tenant_id always applied

---

## Known Threat Patterns for FastAPI + MongoDB

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| **SQL Injection** | Tampering | N/A (MongoDB uses JSON, not SQL) |
| **NoSQL Injection** | Tampering | Pydantic validates all inputs; never concat user strings into queries |
| **Cross-tenant access** | Spoofing | JWT tenant_id extraction + find_one_tenant() helper (THIS PHASE) |
| **Privilege escalation** | Elevation | Role checks (require_staff) + tenant validation |
| **Information disclosure** | Disclosure | Tenant isolation (THIS PHASE); soft-delete (CONTEXT) |

---

## Sources

### Primary (HIGH Confidence)
- **Phase 19 SPEC.md** — Requirements, data model changes, architecture
- **Phase 19 CONTEXT.md** — Design decisions (tenant_id = user_id, soft delete, etc.)
- **BACKEND_ARCHITECTURE_ANALYSIS.md** — Current system structure, query patterns
- **Existing codebase** — database.py (Motor patterns), auth.py (JWT extraction), routers (query sites)

### Secondary (MEDIUM Confidence)
- **MongoDB Best Practices** — Compound indexing, multi-tenant patterns
- **FastAPI Documentation** — Dependency injection, request validation
- **ARQ Documentation** — Job queueing, context passing

### Tertiary (LOW Confidence)
- None — this is a straightforward refactoring phase, not research-heavy

---

## Assumptions Log

| # | Assumption | Section | Risk if Wrong | Mitigation |
|---|-----------|---------|--------------|-----------|
| A1 | tenant_id = user_id (email) | Auth Layer | If tenants need separate identity, schema changes required | Locked in CONTEXT.md; no action |
| A2 | Single-user tenants (no teams) | Auth Layer | If teams added later, user-tenant mapping table needed | Deferred to Phase 28 |
| A3 | Email is globally unique | Auth Layer | Email conflicts could cause data leak | LOW risk; email already has unique index |
| A4 | Soft-delete via tenant_status field | Data Model | If hard-delete required, migration script differs | Locked in CONTEXT.md |
| A5 | MongoDB queries skip tenant filter if developer forgets | Query Layer | Some queries may leak if developer doesn't use helper | Mitigated by code review + helper enforcement |

**All assumptions are locked in CONTEXT.md or mitigated by implementation strategy.**

---

## Metadata

**Research Date:** May 30, 2026  
**Valid Until:** June 5, 2026 (5 days; after phase execution begins, may need re-assessment)  
**Confidence Breakdown:**
- **MongoDB Migration:** HIGH — straightforward backfill, no novel patterns
- **Query Layer Refactoring:** HIGH — systematic, grep-auditable
- **WebSocket Namespacing:** HIGH — clear pattern change
- **Auth Layer Integration:** HIGH — JWT already extracted, just add tenant_id field
- **Testing Strategy:** MEDIUM — E2E requires coordinated 2-broker setup (not yet prototyped)
- **Deployment:** MEDIUM — blue-green assumes Railway supports, needs verification
- **Rollback:** MEDIUM — data rollback is reversible but requires coordination

---

## Open Questions

1. **Blue-Green Infrastructure:** Does Railway support instant traffic cutover between environments?
   - **Action:** Infrastructure team to confirm capacity, cutover mechanism
   - **Impact:** Determines zero-downtime feasibility

2. **Monitoring Alert Setup:** What observability tools are available for cross-tenant query detection?
   - **Action:** DevOps to provide logging, alerting infrastructure
   - **Impact:** Determines real-time leak detection capability

3. **Frontend WebSocket Update:** Has frontend already been coded to derive tenant_id from JWT?
   - **Action:** Confirm with frontend team
   - **Impact:** If not done, adds 1-2 days to Phase 19

4. **Existing Data Corruption:** Are there docs missing user_id or with duplicate emails?
   - **Action:** Run audit on production MongoDB before migration
   - **Impact:** May require manual data cleanup before backfill script runs

---

## Effort Breakdown

| Area | Days | Notes |
|------|------|-------|
| Step 1: Schema Changes + Indexes | 1 | MongoDB, Pydantic models |
| Step 2: Backfill tenant_ids | 0.5 | Script + dry-run on staging |
| Step 3: Query Layer Refactor | 3 | Systematic, parallelizable |
| Step 4: WebSocket Namespacing | 1 | ConnectionManager + worker changes |
| Step 5: Testing & Verification | 1 | Unit + E2E + 24h soak |
| **Total** | **6.5 days** | Target: 5 days (compress via parallelization) |

**Compression Strategy:**
- Parallelize Step 1 + 3 (schema while planning queries)
- Parallelize query audit + refactoring (grep audit while writing helpers)
- Run staging tests in parallel (soak test doesn't block planner)
- **Realistic:** 5-6 days with 2 engineers

---

**Ready for planning. Planner can now create PLAN.md with task breakdown.**
