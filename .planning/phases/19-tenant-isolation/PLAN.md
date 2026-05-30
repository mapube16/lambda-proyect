# Phase 19 Plan: Tenant Isolation

**Phase Duration:** 5 days
**Depends on:** Phase 18
**Blocks:** Phase 24
**Mode:** Standard (sequential execution)
**Research:** Skipped per request

---

## Goal

Add `tenant_id` isolation to all MongoDB collections and queries, namespace WebSocket channels by tenant, and verify zero cross-tenant leakage with end-to-end tests.

## Success Criteria

- [ ] All collections include `tenant_id` and have compound indexes with `tenant_id`
- [ ] All queries (find, update, aggregate) enforce `tenant_id`
- [ ] WebSocket channels use `ws:{tenant_id}:{run_id}` across API + Worker
- [ ] E2E test: 2 brokers running simultaneously see only their own data
- [ ] No performance regression (p50 < 50ms, p99 < 200ms on core endpoints)

## Assumptions (Locked by CONTEXT)

- `tenant_id = user_id` (email)
- Single-user tenants (teams deferred)
- Soft delete (tenant_status) for compliance
- Aggregations must be guarded via helper
- Migration required before rollout (no backwards-compat mode)

---

## Wave 0 (Day 1): Inventory + Tenant Scaffolding

**Goal:** Prepare tenant primitives and create the migration + index plan.

- [ ] Inventory all MongoDB collections and current indexes in [backend/database.py](backend/database.py)
- [ ] Add `tenant_id` field to all relevant Pydantic models in [backend/models.py](backend/models.py)
- [ ] Add `tenant_id` extraction in [backend/auth.py](backend/auth.py) via `get_current_user()`
- [ ] Add `tenant_status` enforcement approach (active-only filter) in data helpers
- [ ] Define centralized helpers in [backend/database.py](backend/database.py):
  - `find_one_tenant()`
  - `find_tenant()`
  - `update_one_tenant()`
  - `aggregate_tenant()`
- [ ] Draft migration script plan (collections, backfill source, verification)

**Deliverables:**
- Tenant helper signatures + scaffolding in database layer
- Pydantic models updated with `tenant_id`
- Auth extraction confirmed in JWT flow

---

## Wave 1 (Day 2): Data Model + Indexes

**Goal:** Add tenant_id to all write paths and indexes.

- [ ] Update all insert/create flows to include `tenant_id`
  - Prospector pipeline (runs, leads, campaigns)
  - Onboarding flows
  - Staff flows
  - WhatsApp + cobranzas flows
- [ ] Add compound indexes with `tenant_id` for every collection
  - Example: `tenant_id + user_id`, `tenant_id + run_id`, `tenant_id + created_at`
- [ ] Ensure unique constraints are tenant-scoped (e.g., run_id)

**Deliverables:**
- All collection indexes updated and tenant-scoped
- All writes include tenant_id in payloads

---

## Wave 2 (Day 3): Query Layer Refactor

**Goal:** Enforce tenant_id in every query path.

- [ ] Replace direct `db.<collection>.find` calls with tenant helpers
- [ ] Add `tenant_id` to all filter dicts (including updates and deletes)
- [ ] Enforce tenant_id as first `$match` in all aggregation pipelines
- [ ] Update router dependencies to pass `tenant_id` from auth to database calls

**Deliverables:**
- No query path bypasses tenant_id
- All aggregations guarded via `aggregate_tenant()`

---

## Wave 3 (Day 4): WebSocket Isolation + Migration

**Goal:** Isolate realtime events and backfill existing data.

- [ ] Change WS channel format to `ws:{tenant_id}:{run_id}`
  - API: [backend/main.py](backend/main.py)
  - Worker: [backend/worker.py](backend/worker.py)
  - Connection Manager: [backend/services/connection_manager.py](backend/services/connection_manager.py)
- [ ] Update frontend subscription logic (derive tenant_id from JWT)
- [ ] Run migration script on staging
  - Backfill `tenant_id` for all docs
  - Verify zero docs missing tenant_id

**Deliverables:**
- WebSocket channels namespaced by tenant
- Migration run on staging with verification report

---

## Wave 4 (Day 5): Verification + Rollout

**Goal:** Prove isolation and ship.

- [ ] E2E test with 2 brokers (A/B) across campaigns, runs, leads
- [ ] Verify no data leak across tenants (API + WebSocket)
- [ ] Load test key endpoints for regression (p50/p99)
- [ ] Deploy to production
- [ ] Update [ROADMAP.md](.planning/ROADMAP.md) to mark Phase 19 complete

**Deliverables:**
- E2E isolation test results
- Performance baseline check
- Production deployment completed

---

## Verification Checklist (Required)

- [ ] Query audit: no direct `db.<collection>` calls without tenant_id filter
- [ ] Aggregation audit: all use `aggregate_tenant()`
- [ ] Migration audit: 0 documents missing tenant_id
- [ ] WebSocket audit: correct channel names
- [ ] E2E test: broker A/B isolation

---

## Risks + Mitigations

- **Risk:** Missing tenant_id in a single endpoint -> data leak
  - **Mitigation:** Central helpers + code review + grep audit
- **Risk:** Aggregation pipeline bypasses tenant filter
  - **Mitigation:** `aggregate_tenant()` required, add review gate
- **Risk:** Migration failure or partial backfill
  - **Mitigation:** Dry-run on staging, verify counts before prod

---

## Open Questions

- None. Decisions locked in 19-CONTEXT.md.

---

## Rollback Plan

- Revert to previous release tag if isolation bug detected
- Disable multi-tenant enforcement in auth dependency (temporary emergency mode)
- Restore from pre-migration backup if data integrity is compromised
