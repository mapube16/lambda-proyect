# Phase 19 Context: Tenant Isolation Design Decisions

**Status:** Discussion Phase Complete  
**Date:** May 30, 2026

---

## Gray Areas Resolved

### Gray Area 1: How is tenant_id derived?
**Question:** Each broker is a "tenant". But what identifier uniquely identifies a tenant?

**Options:**
- A) user_id (email) IS the tenant_id (simplest)
- B) Separate tenant entity in DB (complex, not needed yet)
- C) Tenant ID in JWT issued at registration (requires changes to auth flow)

**DECISION: A (user_id = tenant_id)**
- Reasoning: Email is globally unique, already in JWT as "sub"
- Implementation: In get_current_user(), set tenant_id = user_id
- Advantage: No schema changes to users collection
- Risk: Email conflicts (very low probability)

---

### Gray Area 2: Multi-user tenants (teams)?
**Question:** Can a tenant have multiple users? (E.g., DPG Seguros has 3 staff members)

**Options:**
- A) Single-user tenants only (dpg.seguros@gmail.com is one broker, one person)
- B) Support team members within a tenant (requires tenant table + user-to-tenant mapping)

**DECISION: A (Single-user for v1)**
- Reasoning: MVP only needs per-broker isolation, not team collaboration
- Deferral: Phase 28 can add team members + role-based access
- Current: Each broker is email + password, no team structure

---

### Gray Area 3: Tenant data ownership
**Question:** If Broker A stops paying, do we delete their data? Or keep it (compliant)?

**Options:**
- A) Soft delete: Mark tenant_id inactive, keep data
- B) Hard delete: Remove all documents with tenant_id
- C) Archive: Move to separate "archived_tenants" collection

**DECISION: A (Soft delete)**
- Reasoning: Compliance (legal discovery, audit trails)
- Implementation: Add tenant_status: "active" | "suspended" | "archived"
- Data queries: Filter by tenant_status = "active"

---

### Gray Area 4: WebSocket tenant routing
**Question:** How does frontend know which WebSocket channel to subscribe to?

**Options:**
- A) Frontend hardcodes ws:{user_id}:{run_id} (current, works)
- B) Backend returns channel name in response
- C) Frontend derives tenant_id from JWT, constructs ws:{tenant_id}:{run_id}

**DECISION: C (Frontend derives)**
- Reasoning: Simplest, no extra API call
- Implementation: JWT decode on frontend, extract tenant_id
- Assumption: Frontend can do JWT decode (client-side safe, it's in local storage anyway)

---

### Gray Area 5: Aggregation pipelines
**Question:** Complex queries (aggregation, faceting) need tenant_id. How to enforce?

**Options:**
- A) Centralized aggregation helper: db.aggregate_tenant(tenant_id, pipeline)
- B) Linting rule: Flag aggregations without tenant_id stage
- C) Manual code review: Check each aggregation

**DECISION: A + B (Helper + Linting)**
- Reasoning: Defense in depth
- Implementation:
  ```python
  async def aggregate_tenant(collection, tenant_id: str, pipeline: list):
      """Adds $match { tenant_id } as first stage."""
      return await collection.aggregate([
          {"$match": {"tenant_id": tenant_id}},
          *pipeline
      ]).to_list(None)
  ```

---

### Gray Area 6: Backward compatibility
**Question:** Existing (non-migrated) documents don't have tenant_id. What happens?

**Options:**
- A) Fail on read (no backward compat)
- B) Default to "legacy" tenant (breaks isolation)
- C) Migration + hotfix before rollout

**DECISION: C (Migration required)**
- Reasoning: Cannot launch multi-tenant with data leakage risk
- Plan:
  1. Run migration script: Add tenant_id to all docs
  2. Verify: Query returns 0 docs without tenant_id
  3. Deploy: Only then enable multi-tenant checks

---

## Design Decisions Locked In

### ✅ Tenant Identifier: user_id (email)
- Broker email = tenant ID
- Example: "dpg.seguros@gmail.com" = tenant identifier
- JWT sub field contains it

### ✅ Tenant Scope: Broker level (not team)
- One broker = one tenant
- Team collaboration deferred to Phase 28

### ✅ Data Lifecycle: Soft delete (inactive status)
- Inactive tenants keep data (compliance)
- Active-only filtering on queries

### ✅ WebSocket Channels: tenant_id-based
- Channel format: `ws:{tenant_id}:{run_id}`
- Frontend derives tenant_id from JWT

### ✅ Query Pattern: Centralized helper for aggregations
- All queries: explicit tenant_id filter
- Aggregations: use aggregate_tenant() helper

### ✅ Migration: Bulk update + verification
- Update all docs before deploying
- Verify 0 docs without tenant_id
- Then enable multi-tenant auth

---

## Implementation Dependencies

**Blocks Phase 24** until complete:
- ❌ Cannot add multi-tenant Signal Sources without tenant isolation
- ❌ Cannot track per-tenant quotas without tenant_id
- ❌ Cannot isolate costs without tenant filtering

---

## Success Criteria (Acceptance)

- ✅ All MongoDB collections have tenant_id field + index
- ✅ All queries filter by tenant_id explicitly
- ✅ E2E test: 2 brokers, 0 data leakage
- ✅ WebSocket channels use tenant_id (no collision)
- ✅ Performance: No regression vs single-tenant

