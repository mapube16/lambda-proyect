# 24-CONTEXT.md: Signal Sources Colombianas — Phase Discussion Decisions

**Phase:** 24 — Signal Sources Colombianas (Desempleo v1)  
**Date:** 2026-05-30  
**Status:** Discussion Complete  

---

## Gray Areas Resolved

### 1. RUES API Access Strategy ✅
**Decision:** API Pública (RUES web scraping)
- Scrape https://www.rues.org.co/RM/ daily via scheduled task
- **Cost:** $0 (legal, public data)
- **Latency:** 5-10s per search (acceptable for batch processing)
- **Implementation:** BeautifulSoup XML parser → MongoDB cache
- **Rationale:** Desempleo v1 no justifica costo de CloudCorp ($100-200/mes). Batch daily refresh es suficiente.

### 2. LinkedIn Signal Extraction ✅
**Decision:** Bright Data LinkedIn connector
- Extract: current_job_openings, estimated_employees, recent_hires_30d, tech_mentions
- **Cost:** $300/mes (amortized across all brokers)
- **Frequency:** 2x/week refresh (Monday, Thursday)
- **Reliability:** 99% uptime vs manual scraping (60% success rate)
- **Rationale:** Manual scraping = IP blocks. Bright Data = managed solution, worth $300/mes for desempleo MVP.
- **Data retained:** Job postings history (trending), employee growth trends, tech stack signals

### 3. Decision Maker Extraction ✅
**Decision:** Hybrid approach (Signals Local + Hunter.io)
- **Sources priority:**
  1. RUES: Representante Legal (legal name, guaranteed accurate)
  2. Google Business: Extract from contact info if visible
  3. LinkedIn: Employee profiles with titles matching "Gerente", "Director", "CEO"
  4. Hunter.io: Email verification + enrichment ($0.05/email)
- **Confidence scoring:** RUES=95%, LinkedIn direct=80%, Hunter.io verified=85%, inferred=40%
- **Cost:** Hunter.io @ ~$50-100/mes for desempleo volume
- **Implementation:** Verify all emails via Hunter API before storing (no unverified emails in decisores list)

### 4. Deduplication & Matching ✅
**Decision:** ML-based matching with rule-based fallback
- **Phase 24 Implementation:**
  - Rule 1: Match by NIT (exact) → confidence 100%
  - Rule 2: Fuzzy match Razón Social (Levenshtein >90%) → confidence 90%
  - Rule 3: Lat/Lng proximity (< 100m) + name similarity (>80%) → confidence 75%
  - **Collect training data** during desempleo v1 (manual labels by broker)
- **Phase 25+:** Train ML model (random forest or gradient boosting) with collected labels
- **Why not ML now?** Need ground truth data first. Rules are bulletproof for initial dedup.

### 5. Signal Priority & Ranking ✅
**Decision:** Intent-based ranking (NOT static source priority)

**Hiring Intent Score (0-100) for Desempleo:**
```
score = (
  0.35 × hiring_intensity +        # Job postings + growth rate
  0.25 × company_size_match +      # Min 50 employees
  0.20 × data_recency +            # RUES fresh > 7 days old
  0.15 × tax_compliance +          # Estado = Activo (not suspended)
  0.05 × sector_match              # Optional: match vs campaign sector
)

hiring_intensity = (
  current_job_openings * 0.4 +
  estimated_monthly_hires * 0.3 +
  growth_rate_last_90d * 0.3
) / sector_median_hiring
```

**Threshold logic for desempleo:**
- Score >= 80: High intent (actively hiring, likely to buy desempleo insurance)
- Score 60-79: Medium intent (seasonal hiring or slow growth)
- Score < 60: Skip (not hiring or early stage)

**Why this fixes "bobo" ranking:**
- **Hiring intensity** = aggregates job count + growth + seasonality
- **Sector-relative** = contextual (logistics sector posts 5 jobs = normal; tech post 3 = low)
- **Data recency** = LinkedIn data (2 days old) > RUES data (7 days old)

### 6. Vertical Scope (Phase 24) ✅
**Decision:** Desempleo only (v1)
- **Why:** Focus on depth over breadth. Desempleo is highest ROI for brokers (largest market in Colombia)
- **Arrendamiento + Empresarial:** Planned for Phase 25-26 (template prepared, not implemented)
- **Template structure:** All 3 verticals have identical signal sources. Only filtering + prompt context differs.

### 7. Cost Allocation & Tracking ✅ 🆕 CRITICAL ADDITION
**Decision:** Internal cost tracking (hidden from broker) + Plan-based quota visibility

**INTERNAL COST TRACKING (For Isomorph only):**
- **Signal costs (what YOU pay):**
  - RUES: $0 (public data)
  - Bright Data LinkedIn: $300/mes ÷ N_brokers = amortized cost per lead
  - Hunter.io email verification: $0.05/email verified
  - Google Serper: Already subscribed (shared infra cost)
  
- **Cost event logged per lead (Backend only, not exposed to broker):**
  ```python
  @dataclass
  class CostEvent:  # ← INTERNAL: Never shown to broker
      user_id: str                # Email del broker (ej: dpg.seguros@gmail.com)
      run_id: str                 # Campaign run
      lead_id: str                # Lead found
      source: str                 # 'RUES' | 'Bright-Data' | 'Hunter' | 'Google'
      cost_usd: float             # YOUR cost (Bright Data $0.15/lead)
      tokens_used: Optional[int]  # For LLM stages (GPT-4o)
      timestamp: datetime
      # This collection is Isomorph's internal accounting only
  ```

**BROKER-FACING QUOTA SYSTEM:**
  ```python
  @dataclass
  class TenantQuota:
      user_id: str                # Email del broker (ej: dpg.seguros@gmail.com)
      plan: str                   # 'free' | 'pro' | 'enterprise'
      monthly_leads_limit: int    # 100 | 1000 | unlimited
      monthly_leads_used: int     # ← What broker cares about
      reset_date: datetime        # ← When quota resets (1st of month)
      created_at: datetime
      updated_at: datetime
  ```

- **Query structure (respeta roles):**
  ```python
  # Broker endpoint: GET /api/quota/me
  # Only returns YOUR quota (role-filtered in backend)
  if current_user['role'] != 'client':
      raise 403 Forbidden
  quota = await db.tenant_quotas.find_one({"user_id": current_user['user_id']})
  
  # Staff endpoint: GET /api/admin/quotas
  # Returns all broker quotas (for analytics)
  if current_user['role'] != 'staff':
      raise 403 Forbidden
  quotas = await db.tenant_quotas.find({})
  ```

- **What broker sees on dashboard:**
  - ✅ "You have 234/1000 leads remaining this month"
  - ✅ "Days until quota reset: 12"
  - ❌ NO cost breakdown
  - ❌ NO per-signal pricing
  - ❌ NO "Bright Data cost" or "Hunter cost"

- **Pricing model (broker perspective):**
  - Free Plan: 100 leads/month
  - Pro Plan: 1000 leads/month @ $500/month (broker's fixed cost)
  - Enterprise: Unlimited leads @ custom pricing
  
- **Margin calculation (YOUR dashboard):**
  ```python
  # Isomorph financial dashboard (not in broker UI)
  monthly_revenue_pro = $500/broker × 20_brokers = $10,000
  monthly_costs = (
    $300 (Bright Data) +
    $200 (Hunter.io at $0.05 × 4000 emails) +
    $100 (Serper amortized)
  ) = $600
  monthly_gross_margin = $10,000 - $600 = $9,400 (94%)
  ```

### 8. Data Freshness Strategy ✅
**Decision:** Scheduled refreshes + smart caching
- **RUES data:**
  - Frequency: Daily cron 9 PM UTC-5 (low-traffic window)
  - Scope: Full refresh (small dataset ~5k active companies in desempleo target)
  - TTL: 7 days (if company not refreshed in 7 days, flag as stale)
  
- **Bright Data LinkedIn:**
  - Frequency: 2x/week (Monday 10 AM, Thursday 3 PM UTC-5)
  - Scope: Incremental (only refresh companies touched in last 14 days)
  - TTL: 14 days (hiring plans don't change weekly)
  
- **Hunter.io verification:**
  - Frequency: On-demand per lead (when decisores extracted)
  - Cost: Only pay for emails we verify (smart batching)
  
- **Google Business (via Serper):**
  - Frequency: Weekly (reuse existing Serper calls)
  - TTL: 7 days

- **Staleness alerts:**
  - Backend flags leads with data > 7 days old in search results
  - UI shows badge "Data refreshed 3 days ago" per lead
  - Broker can request manual refresh (triggers immediate crawl)

---

## Key Unknowns → Deferred to Planning

❓ **ML Training Data Collection:** When/where do we label dedup decisions to train Phase 25 model?  
→ *Answer in planning:* Broker feedback loop + manual labels from HITL checkpoint

❓ **Hunter.io batching strategy:** How many emails per day without hitting rate limits?  
→ *Answer in planning:* Analyze Hunter API docs + set conservative batch size

❓ **Bright Data LinkedIn blocklist:** What companies should we skip (e.g., very small, startups)?  
→ *Answer in planning:* Implement size_min filter (default 50 employees)

---

## Dependencies & Prerequisites

### Must complete BEFORE Phase 24:
- ✅ Phase 19: Multi-tenant isolation (tenant_id in all collections)
  - Required for: `TenantQuota` collection + cost per tenant
  - Status: Must be done first

### Can execute in parallel:
- [ ] API keys procurement (Bright Data, Hunter.io)
- [ ] RUES documentation review (URL patterns, XML schema)
- [ ] Caching infrastructure (Redis for signal_leads TTL)

---

## Success Criteria for Phase 24 Discussion

✅ **RUES integration strategy locked** (daily scrape + XML parsing)  
✅ **LinkedIn signals source locked** (Bright Data 2x/week)  
✅ **Decision maker extraction locked** (RUES + Hunter.io)  
✅ **Deduplication approach locked** (rule-based in v1, ML in v2)  
✅ **Ranking algorithm locked** (intent-based, sector-relative)  
✅ **Vertical scope locked** (desempleo only, template for v2)  
✅ **Cost tracking locked** (per-signal logging + tenant quota)  
✅ **Data freshness locked** (scheduled + smart cache)  
✅ **Broker visibility locked** (quota dashboard shows remaining leads + budget)

---

## 🆕 New Requirements Discovered

### USAGE.md (Broker-facing requirements)
- **USAGE-01:** Broker can view remaining leads quota for current month (e.g., "234/1000 remaining")
- **USAGE-02:** Dashboard shows "days until quota reset"
- **USAGE-03:** Alert when broker hits 80% quota (proactive warning before running out)
- **USAGE-04:** Annual usage report (how many leads consumed per month)
- **USAGE-05:** Current usage per campaign (not just monthly total)

### Broker Dashboard Extension
- Add sidebar widget: "Plan Status"
  - Progress bar: X / Y leads used this month
  - Text: "Reset in 12 days"
  - Text: "Your plan: Pro (1000 leads/month)"
  - Link: "Upgrade plan" (if at 90% quota)
- **API endpoints (role-protected):**
  ```python
  # Broker: Can only see their OWN quota
  GET /api/quota/me
  @require_client  # Dependency: role must be 'client'
  Returns: TenantQuota for current_user.user_id
  
  # Staff: Can see ALL broker quotas (for analytics dashboard)
  GET /api/admin/quotas
  @require_staff  # Dependency: role must be 'staff'
  Returns: List[TenantQuota]
  ```
### Cost Events Collection (MongoDB - Internal Only)
```javascript
// INTERNAL accounting (never shown to broker)
db.tenant_quotas.createIndex({ "user_id": 1 }, { unique: true })
db.tenant_quotas.createIndex({ "reset_date": 1 })

db.cost_events.createIndex({ "user_id": 1, "timestamp": -1 })
db.cost_events.createIndex({ "source": 1, "timestamp": -1 })
```
This is for YOUR accounting. Used to:
- Calculate profit per broker (revenue $500/mo - costs $X)
- Optimize signal sources (if Bright Data gets too expensive, switch strategy)
- Track margin by plan type (Pro vs Enterprise)

---

## Backend Optimizations (Parallel to Signal Sources)

### Quick Wins (~30 min each):
1. **Truncamiento Inteligente:** `scraped[:6000]` → `truncate_intelligently(3000)`
   - Saves 60% of GPT-4o tokens (still enough context)
   - Preserve paragraphs (don't cut mid-sentence)
   
2. **Increase Concurrency:** `_CONCURRENCY = 3` → `8`
   - 20 companies: 6.6 cycles → 2.5 cycles
   - Risk: Monitor rate limiting on Serper
   
3. **Decisor Caching:** If NIT already scraped, reuse decisor extraction
   - Saves 30-40% GPT-4o calls per run
   
4. **Batch Serper Queries:** Parallelize 5 queries simultaneously (was 3)
   - Already has `asyncio.gather()`, just increase batch size

### Critical Backend Fixes (MUST DO BEFORE SIGNALS):
1. **Add asyncio.timeout() on external APIs** (15 min)
   - OpenAI calls (now: unlimited)
   - Mailgun calls (now: unlimited)
   - Vapi calls (now: unlimited)
   - URL fetch (now: unlimited)
   
2. **Reduce job_timeout** (5 min)
   - `worker.py: job_timeout = 600` (10 min instead of 1 hour)
   
3. **Error Handler Middleware** (30 min)
   - Global @app.exception_handler(Exception)
   - Log + return 500 instead of internal error
   
4. **Dead-Letter Queue** (45 min)
   - Store failed webhook messages in MongoDB
   - Retry logic with exponential backoff

---

## Next Steps: Planning Phase

### Phase 24 Planning will break down into:

**Wave 1: Infrastructure (3 days)**
- RUES scraper module + daily cron
- LinkedIn connector setup (Bright Data account + auth)
- Hunter.io integration
- signal_leads + cost_events MongoDB collections

**Wave 2: Core Pipeline (4 days)**
- SignalSourceRegistry class (pluggable interface)
- Deduplication engine (rule-based)
- Intent-based ranking engine
- Decision maker extraction pipeline

**Wave 3: API + Testing (2 days)**
- GET /api/signals/search endpoint
- POST /api/signals/{empresa_id}/verify-contact endpoint
- Unit tests + integration tests

**Wave 4: Quota + Dashboard (2 days)**
- TenantQuota model + collection (indexed by user_id, not tenant_id)
- Quota enforcement in enqueue_job():
  ```python
  # Before running signal search, check quota
  quota = await db.tenant_quotas.find_one({"user_id": current_user['user_id']})
  if quota.monthly_leads_used >= quota.monthly_leads_limit:
      raise HTTPException(status_code=429, detail="Monthly leads quota exceeded")
  ```
- Dashboard widget (frontend) showing "X/Y leads remaining, reset in N days"
- Quota endpoints:
  - GET /api/quota/me (broker-facing, role-protected)
  - GET /api/admin/quotas (staff-facing, for analytics)

**Wave 5: Validation (2 days)**
- End-to-end test: campaign → signal search → leads populated → quota reduced
- Demo to broker (DPG Seguros)

---

## Effort Estimate (Revised with Quota + Usage Tracking)

| Wave | Component | Days |
|------|-----------|------|
| 1 | Infrastructure (RUES + LinkedIn + Hunter) | 3 |
| 2 | Core pipeline + ranking | 4 |
| 3 | API endpoints | 2 |
| 4 | **Quota + Usage Dashboard** | **2** |
| 5 | Testing + validation | 2 |
| **Total** | **Phase 24 Complete** | **13 days** |

---

## Broker Value Prop (Correct SaaS Model)

Before: "Find 100 qualified leads/month for desempleo insurance"  
After: **"Pro plan: 1000 leads/month for $500. Know exactly how many you've used and when your quota resets."**

Simple, transparent to broker, profitable for you.
- Broker pays: $500/month fixed (knows exactly what they pay)
- Broker sees: "850 leads used, 150 remaining, resets in 18 days"
- You pocket: Margin from Bright Data ($300) vs broker payment ($500) = $200 profit per broker

