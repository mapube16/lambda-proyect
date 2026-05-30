# Phase 19 Specification: Tenant Isolation

**Phase Duration:** 5 days  
**Depends on:** Phase 18 (Railway setup)  
**Blocks:** Phase 24 (Signal Sources)

---

## Executive Summary

**Goal:** Convert single-tenant system to multi-tenant by adding `tenant_id` isolation to all MongoDB collections and queries. Enable multiple insurance brokers to operate independently on same infrastructure without data leakage.

**Success Criteria:**
1. ✅ All MongoDB collections have `tenant_id` field
2. ✅ All queries explicitly filter by `tenant_id` (no leakage possible)
3. ✅ WebSocket channels use `ws:{tenant_id}:{run_id}` (isolated by broker)
4. ✅ E2E test: 2 brokers run simultaneously, no data visible across tenants
5. ✅ Authentication extracts `tenant_id` from JWT (email)

---

## Requirements

| ID | Title | Description | Type |
|---|-------|-------------|------|
| TENANT-01 | tenant_id field | All collections + documents must have tenant_id (indexed) | Data |
| TENANT-02 | Query filtering | No query in backend runs without tenant_id filter | Backend |
| TENANT-03 | WebSocket isolation | Redis channels named ws:{tenant_id}:{run_id} | Realtime |
| AUTH-01 | JWT tenant context | JWT payload includes tenant_id (broker email) | Auth |
| TENANT-04 | Database indexes | Compound indexes on (tenant_id, other_fields) | Data |
| TENANT-05 | Aggregation queries | All aggregations filtered by tenant_id (not just find) | Data |

---

## Architecture Changes

### Before (Single-Tenant):
```python
# Query by user_id only
leads = db.leads.find({"user_id": user_id})  # ❌ May leak across tenants if user_id not unique globally

# WebSocket channel by user
ws_channel = f"ws:{user_id}:{run_id}"  # ❌ If 2 brokers have same user_id format, collision
```

### After (Multi-Tenant):
```python
# Query by tenant + user
leads = db.leads.find({
    "tenant_id": tenant_id,      # ← NEW: Always required
    "user_id": user_id           # Still needed for per-user filtering
})

# WebSocket channel by tenant
ws_channel = f"ws:{tenant_id}:{run_id}"  # ✅ Globally unique
```

---

## Data Model Changes

### MongoDB Collections: Add tenant_id

#### campaigns
```python
{
    _id: ObjectId,
    tenant_id: str,              # ← NEW (indexed)
    user_id: str,                # User within tenant
    campaign_id: str,
    industria_objetivo: str,
    ...
}

# NEW INDEX
db.campaigns.createIndex({ "tenant_id": 1, "user_id": 1 })
db.campaigns.createIndex({ "tenant_id": 1, "is_active": 1 })
```

#### runs
```python
{
    _id: ObjectId,
    tenant_id: str,              # ← NEW
    user_id: str,
    run_id: str,
    campaign_id: str,
    status: str,
    ...
}

# NEW INDEX
db.runs.createIndex({ "tenant_id": 1, "run_id": 1 }, { unique: true })
db.runs.createIndex({ "tenant_id": 1, "user_id": 1, "started_at": -1 })
```

#### leads
```python
{
    _id: ObjectId,
    tenant_id: str,              # ← NEW
    user_id: str,
    run_id: str,
    empresa: str,
    nit: str,
    ...
}

# NEW INDEXES
db.leads.createIndex({ "tenant_id": 1, "run_id": 1, "user_id": 1 })
db.leads.createIndex({ "tenant_id": 1, "user_id": 1, "created_at": -1 })
db.leads.createIndex({ "tenant_id": 1, "estado": 1 })
```

#### All other collections
- `client_knowledge`
- `client_profiles`
- `ideal_leads`
- `rejected_leads`
- `whatsapp_agents`
- `sector_profiles`
- `scheduled_actions`
- `debtors`
- `email_events`
- `cobranza_calls_in_progress`
- `agents`
- `scrape_logs`
- `signal_leads` (new)
- `cost_events` (new)
- `tenant_quotas` (new)

All need: `tenant_id` field + indexed compound keys

---

## Backend Changes

### Authentication Layer
```python
# auth.py
async def get_current_user(token: str) -> dict:
    payload = jwt.decode(token, SECRET_KEY, algorithm=ALGORITHM)
    user_id = payload.get("sub")  # Email: "dpg.seguros@gmail.com"
    role = payload.get("role", "client")
    
    # ← NEW: Extract tenant_id from user_id (email)
    # Tenant = user's domain or explicit field
    # Assumption: user_id IS the tenant identifier (broker email)
    tenant_id = user_id
    
    return {
        "user_id": user_id,
        "role": role,
        "tenant_id": tenant_id  # ← NEW: passed to all endpoints
    }
```

### Router Layer
```python
# routers/prospect.py
@router.post("/api/prospect")
async def prospect(
    request: ProspectRequest,
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user["user_id"]
    tenant_id = current_user["tenant_id"]  # ← NEW: always use this
    
    # Before: campaigns = await get_active_campaign(user_id)
    # After:
    campaigns = await db.campaigns.find_one({
        "tenant_id": tenant_id,  # ← Filter by tenant
        "user_id": user_id,
        "is_active": True
    })
```

### Database Layer
```python
# database.py - New helper
async def find_one_tenant(collection, tenant_id: str, query: dict):
    """
    Safe find that enforces tenant_id filter.
    Prevents accidental queries without tenant isolation.
    """
    query["tenant_id"] = tenant_id  # Always add tenant_id
    return await collection.find_one(query)

async def find_tenant(collection, tenant_id: str, query: dict):
    """Safe find_many that enforces tenant_id filter."""
    query["tenant_id"] = tenant_id
    return await collection.find(query)

# Usage in all endpoints:
lead = await find_one_tenant(db.leads, tenant_id, {"_id": lead_id, "user_id": user_id})
```

---

## WebSocket Changes

### Before:
```python
# main.py
connection_manager.active_connections[f"ws:{user_id}:{run_id}"] = websocket

# Worker publishes to:
redis_channel = f"ws:{user_id}:{run_id}"
```

### After:
```python
# main.py
connection_manager.active_connections[f"ws:{tenant_id}:{run_id}"] = websocket

# Worker publishes to:
redis_channel = f"ws:{tenant_id}:{run_id}"

# Redis: Subscribe frontend to correct channel
# @app.websocket("/ws/{tenant_id}/{run_id}")
```

---

## Migration Strategy

### Step 1: Add tenant_id field (no queries change yet)
- Add `tenant_id` to all inserts
- No query changes (backward compatible)

### Step 2: Add tenant_id to existing documents
```javascript
// MongoDB: Batch migration
db.campaigns.updateMany(
    { tenant_id: { $exists: false } },
    { $set: { tenant_id: "legacy-unknown" } }
)
// Later: backfill from user_id email domain or explicit mapping
```

### Step 3: Create new indexes
- Add compound indexes (tenant_id, other fields)
- Old indexes remain (don't break queries)

### Step 4: Update all queries
- Systematic: search codebase for `db.*.find(` patterns
- Add `tenant_id` filter to each
- No order changes (can parallelize)

### Step 5: Test + Verify
- E2E: 2 brokers, 1 campaign each
- Verify no cross-tenant data leak
- Performance: Check index hit rates

---

## Risk Mitigation

| Risk | Probability | Mitigation |
|------|-------------|-----------|
| Data leak (query missing tenant_id) | Medium | Code review + lint rule |
| Aggregation pipeline bypass | Medium | Centralize aggregation helper |
| WebSocket channel collision | Low | Use tenant_id (globally unique) |
| Migration failure (mid-flight) | Low | Dry-run on staging, backups |
| Query performance regression | Low | Indexes added, not removed |

---

## Testing Strategy

### Unit Tests
- Mock db queries, verify tenant_id always present
- Test get_current_user() extracts tenant_id

### Integration Tests
- Create 2 test brokers
- Broker A creates campaign, broker B queries → no results (expected)
- Broker A queries own campaign → found (expected)

### Load Tests
- 10 concurrent brokers, each running campaign
- Verify no cross-tenant data access
- Monitor memory + latency

### UAT
- Staff manually tests with 2 demo broker accounts
- Confirm isolation is bulletproof

---

## Success Metrics

- ✅ 0 data leaks across tenants (security audit)
- ✅ All queries explicitly filter tenant_id (code review)
- ✅ E2E test passes (2 brokers isolated)
- ✅ Query latency: p50 < 50ms, p99 < 200ms
- ✅ Zero regression in existing endpoints

