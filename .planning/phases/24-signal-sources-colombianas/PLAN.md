# Phase 24 Plan: Colombian Signal Sources + Backend Hardening

**Duration:** 18 days (vs 13 estimated in SPEC)  
**Reason:** Added Wave 0 (Backend Fixes) + Optimizations  
**Wave Parallelization:** Yes (code review + tests run parallel to implementation)

---

## Wave 0: Backend Fixes (Days 1-2)
**Goal:** Harden production readiness before adding Signal Sources  
**Effort:** 2 days  
**Blocker for:** All other waves (cannot add new APIs without timeout protection)

### Task 0.1: Add asyncio.timeout() on External API Calls
**Effort:** 6 hours  
**Files:** prospector.py, mailer.py, knowledge.py, onboarding.py, cobranza/voice_router.py

```python
# Pattern to apply everywhere:
async with asyncio.timeout(30):  # Python 3.11+
    result = await external_api_call()

# Specific endpoints:
- prospector.py: chat_turn() → OpenAI (timeout 30s)
- prospector.py: scrape_url() → curl_cffi (timeout 12s, already done)
- mailer.py: send_lead_outreach() → Mailgun (timeout 10s)
- cobranza/voice_router.py: initiate_vapi_call() → Vapi (timeout 15s)
- knowledge.py: fetch_url_text() → HTTP (timeout 10s)
- orchestrator.py: HiveAdapter calls → OpenAI (timeout 30s)
```

**Testing:**
- Unit: Mock timeouts, verify exception raised
- Integration: Test each endpoint with intentional 40s delay

**Acceptance Criteria:**
- ✅ No external call can hang > timeout threshold
- ✅ TimeoutError caught and converted to 503 (Service Unavailable)
- ✅ User gets feedback within timeout (no spinner forever)

---

### Task 0.2: Reduce Job Timeout + Add User Feedback
**Effort:** 4 hours  
**Files:** worker.py, routers/prospect.py, frontend (if exists)

```python
# worker.py
class WorkerSettings:
    job_timeout = 600  # was 3600 (1 hour) → 10 minutes

# Add timeout warning to user at 8 minutes
# routers/prospect.py
if elapsed_time > 480:  # 8 minutes
    await publish_event({
        "type": "job_timeout_warning",
        "run_id": run_id,
        "message": "Búsqueda tardando más de lo esperado. Si no termina en 2 min, será cancelada."
    })
```

**Acceptance Criteria:**
- ✅ Job kills at 600s (not 3600s)
- ✅ User notified at 480s
- ✅ Graceful shutdown (no corrupted state)

---

### Task 0.3: Global Error Handler Middleware
**Effort:** 4 hours  
**Files:** main.py

```python
import logging
from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    # Log with full traceback
    logger.error(
        "[ERROR] %s %s | %s",
        request.method, 
        request.url.path,
        str(exc),
        exc_info=True
    )
    
    # Return user-friendly response
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error. Support team notified."}
    )

@app.exception_handler(asyncio.TimeoutError)
async def timeout_handler(request: Request, exc: Exception):
    logger.warning("[TIMEOUT] %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=504,
        content={"detail": "Request timeout. Please try again."}
    )
```

**Testing:**
- Unit: Mock exception scenarios
- Integration: Trigger unhandled exception, verify 500 response + logging

**Acceptance Criteria:**
- ✅ All unhandled exceptions return 500 (not 500 with traceback in response)
- ✅ TimeoutError → 504 (not 500)
- ✅ Errors logged to console + file
- ✅ User never sees Python traceback

---

### Task 0.4: Dead-Letter Queue for Webhooks
**Effort:** 5 hours  
**Files:** routers/whatsapp.py, database.py, new webhook_dlq.py

**Schema:**
```python
# MongoDB collection: webhook_dlq
{
    _id: ObjectId,
    webhook_type: "whatsapp" | "vapi" | "email_event",
    payload: {...},  # Original webhook data
    error: "exception message",
    attempt_count: 1,
    next_retry: datetime,
    created_at: datetime,
    processed_at: Optional[datetime],
}

# Indexes
db.webhook_dlq.createIndex({ "processed_at": 1, "next_retry": 1 })
db.webhook_dlq.createIndex({ "webhook_type": 1 })
```

**Retry Logic:**
```python
# exponential backoff: 1min, 5min, 15min, 1hour, give up
RETRY_DELAYS = [60, 300, 900, 3600]

async def process_with_dlq(webhook_data, processor_fn):
    for attempt in range(len(RETRY_DELAYS) + 1):
        try:
            await processor_fn(webhook_data)
            return  # success
        except Exception as e:
            if attempt < len(RETRY_DELAYS):
                # Store in DLQ for later retry
                next_retry = datetime.now() + timedelta(seconds=RETRY_DELAYS[attempt])
                await db.webhook_dlq.insert_one({
                    "webhook_type": "...",
                    "payload": webhook_data,
                    "error": str(e),
                    "attempt_count": attempt + 1,
                    "next_retry": next_retry,
                    "created_at": datetime.now(),
                })
                logger.warning(f"[DLQ] Webhook stored, retry at {next_retry}")
                return  # non-blocking
            else:
                logger.error(f"[DLQ] Webhook failed after {attempt} attempts")
                # Alert team (Slack/email)
```

**Background Job:**
```python
# ARQ job: run every 5 minutes
async def retry_webhook_dlq():
    pending = await db.webhook_dlq.find_one({
        "processed_at": None,
        "next_retry": {"$lte": datetime.now()}
    })
    for item in pending:
        try:
            await process_with_dlq(item["payload"], processor)
            await db.webhook_dlq.update_one(
                {"_id": item["_id"]},
                {"$set": {"processed_at": datetime.now()}}
            )
        except Exception as e:
            # Re-queue if retry failed
            pass
```

**Testing:**
- Unit: Mock processor failure, verify DLQ insert
- Integration: Trigger webhook, simulate crash, verify retry works

**Acceptance Criteria:**
- ✅ Failed webhook stored in DLQ
- ✅ Automatic retry with exponential backoff
- ✅ After 4 attempts, alert team
- ✅ DLQ can be queried via admin endpoint

---

## Wave 1: Signal Sources Infrastructure (Days 3-5)
**Goal:** Build pluggable signal source modules  
**Dependencies:** Wave 0 complete  
**Effort:** 3 days

### Task 1.1: RUES Integration
**Effort:** 8 hours  
**Files:** backend/signal_sources.py, backend/rues_scraper.py, database.py

**RUES Public API:**
- Endpoint: `https://www.rues.org.co/api/search` (estimated, may need web scraping as fallback)
- Authentication: None (public)
- Rate limit: TBD (assume 100/day conservative)
- Returns: [`{nit, razón_social, actividad_económica, fecha_registro, estado}`]

**Implementation:**
```python
# signal_sources.py
class SignalSourceRegistry:
    def __init__(self):
        self.sources = {}
    
    def register(self, name: str, source):
        self.sources[name] = source
    
    async def search(self, source_name: str, **kwargs):
        return await self.sources[source_name].search(**kwargs)

# rues_scraper.py
class RUESSource:
    async def search(self, sector: str, ciudad: str, max_results: int = 50):
        """
        Search RUES for recently registered companies.
        Returns: [{"nit": "...", "razón_social": "...", "fecha_registro": "..."}]
        """
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://www.rues.org.co/api/search",
                params={"sector": sector, "ciudad": ciudad, "limit": max_results}
            )
            return response.json()["results"]
```

**Schema:**
```python
# MongoDB collection: signal_leads
{
    _id: ObjectId,
    user_id: str,
    source: "rues" | "bright_data" | "google_maps" | "hunter",
    empresa: str,
    nit: str,  # unique per source
    sector: str,
    ciudad: str,
    fecha_señal: datetime,  # when signal discovered
    confianza: float (0-1),
    metadatos: {
        "url": Optional[str],
        "telefono": Optional[str],
        "email": Optional[str],
        "tamaño_estimado": Optional[str],
    },
    processed: bool,  # Has it entered prospecting pipeline?
    created_at: datetime,
}

# Index
db.signal_leads.createIndex({ "user_id": 1, "source": 1, "nit": 1 }, { unique: true })
db.signal_leads.createIndex({ "user_id": 1, "processed": 1 })
```

**Testing:**
- Mock: Fake RUES response, verify parsing
- Integration: Real RUES call, verify schema

**Acceptance Criteria:**
- ✅ RUES can search by sector + ciudad
- ✅ Returns valid NITs
- ✅ Deduped by (user_id, source, nit)
- ✅ Can be scheduled daily

---

### Task 1.2: Bright Data LinkedIn Integration
**Effort:** 8 hours  
**Files:** backend/bright_data_linkedin.py, database.py

**Bright Data API:**
- Endpoint: `https://api.brightdata.com/datasets/{dataset_id}/download` (POST)
- Authentication: API key in header
- Rate limit: Depends on plan (assume 500 results/day)
- Returns: Hiring signals + company growth

**Implementation:**
```python
# bright_data_linkedin.py
class BrightDataSource:
    def __init__(self, api_key: str, dataset_id: str):
        self.api_key = api_key
        self.dataset_id = dataset_id
    
    async def search(self, sector: str, ciudad: str = None):
        """
        Fetch LinkedIn hiring signals from Bright Data.
        Returns: [{"company": "...", "new_hires": 5, "growth_rate": 0.12, "url": "..."}]
        """
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                f"https://api.brightdata.com/datasets/{self.dataset_id}/download",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={"query": {"sector": sector, "country": "CO"}}
            )
            return response.json()["data"]
```

**Signal Interpretation:**
```python
signal_strength = {
    "new_hires": lambda n: min(1.0, n / 10),      # 10+ hires = max strength
    "growth_rate": lambda r: min(1.0, r / 0.5),   # 50% YoY growth = max
    "funding_round": lambda f: 0.8 if f else 0,   # Recent funding = high
}
```

**Testing:**
- Mock: Fake LinkedIn data, verify hiring signal extraction
- Integration: Real Bright Data call (if credentials available)

**Acceptance Criteria:**
- ✅ Bright Data credentials work
- ✅ Returns hiring intent signals
- ✅ Integrates with SignalSourceRegistry

---

### Task 1.3: Hunter.io Integration
**Effort:** 6 hours  
**Files:** backend/hunter_enricher.py, database.py

**Hunter.io API:**
- Endpoint: `https://api.hunter.io/v2/email-finder` or `domain-search`
- Authentication: API key as query param
- Cost: $0.05 per email verified, $0.01 per domain search
- Returns: Decision maker email + confidence score

**Implementation:**
```python
# hunter_enricher.py
class HunterSource:
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    async def find_email(self, domain: str, first_name: str, last_name: str):
        """
        Find decision maker email for a person at a domain.
        Cost: $0.05 per successful find
        """
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                "https://api.hunter.io/v2/email-finder",
                params={
                    "domain": domain,
                    "first_name": first_name,
                    "last_name": last_name,
                    "api_key": self.api_key
                }
            )
            result = response.json()
            return {
                "email": result.get("data", {}).get("email"),
                "confidence": result.get("data", {}).get("confidence"),
                "cost_usd": 0.05 if result["meta"]["result_found"] else 0.00
            }
    
    async def domain_search(self, domain: str):
        """
        Get all emails found for a domain.
        Cost: $0.01 per domain
        """
        # Similar implementation
```

**Quota Awareness:**
```python
# Before calling Hunter.io, check budget
if cost_so_far + 0.05 > monthly_budget:
    log("Hunter.io: Monthly budget exceeded, skipping enrichment")
    return None

# Track costs
cost_events.insert_one({
    "user_id": user_id,
    "source": "hunter",
    "cost_usd": 0.05,
    "timestamp": datetime.now()
})
```

**Testing:**
- Mock: Fake Hunter response, verify parsing
- Unit: Cost tracking logic

**Acceptance Criteria:**
- ✅ Can find emails by domain + name
- ✅ Cost tracked accurately
- ✅ Budget respected (no over-spend)

---

## Wave 2: Core Pipeline Integration (Days 6-9)
**Goal:** Connect signal sources to existing 4-stage pipeline  
**Dependencies:** Wave 1 complete  
**Effort:** 4 days

### Task 2.1: Deduplication Engine
**Effort:** 10 hours  
**Files:** backend/deduplication.py, database.py

**Fuzzy Matching Strategy:**
```python
# deduplication.py
class DeduplicationEngine:
    
    async def find_duplicate(self, new_nit: str, new_empresa: str):
        """
        Check if this lead already exists in database.
        Match by NIT (exact) or empresa name (fuzzy).
        """
        # Exact match by NIT
        existing = await db.leads.find_one({
            "$or": [
                {"nit": new_nit},
                {"nit_desplegado": new_nit},  # With format
            ]
        })
        if existing:
            return existing
        
        # Fuzzy match by name (Levenshtein)
        from difflib import SequenceMatcher
        similar_leads = await db.leads.find({"empresa": {"$exists": True}}).to_list(None)
        
        for lead in similar_leads:
            ratio = SequenceMatcher(None, new_empresa, lead["empresa"]).ratio()
            if ratio > 0.92:  # 92% match = probable duplicate
                return lead
        
        return None
```

**Dedup Rules:**
```
1. Exact NIT match → SKIP (already processed)
2. Empresa name 92%+ similar → MERGE (update existing)
3. Same ciudad + sector + date within 7 days → INVESTIGATE
4. No match → CREATE new
```

**Testing:**
- Unit: Test fuzzy matching with known duplicates
- Integration: Run dedup on 100 mixed (new + dups) leads

**Acceptance Criteria:**
- ✅ Exact NIT dedup works
- ✅ Fuzzy name dedup catches 90%+ of duplicates
- ✅ False positive rate < 5%

---

### Task 2.2: Intent-Based Ranking
**Effort:** 8 hours  
**Files:** backend/ranking.py, database.py

**Scoring Model (for Desempleo vertical):**
```python
# ranking.py
def calculate_intent_score(lead: dict) -> float:
    """
    Score 0-100. Higher = more likely to buy.
    Components:
    - Hiring intensity (40%)
    - Company size (25%)
    - Recency (20%)
    - Tax compliance (15%)
    """
    hiring_intensity = 0
    if "new_hires" in lead.get("signals", {}):
        hiring_intensity = min(100, lead["signals"]["new_hires"] * 8)
    elif "licitacion_abierta" in lead.get("señales", []):
        hiring_intensity = 60  # Contracting = hiring phase
    
    company_size = 0
    tam = lead.get("tamano_estimado", "desconocido")
    if tam == "micro":
        company_size = 10
    elif tam == "pequeña":
        company_size = 40
    elif tam == "mediana":
        company_size = 80
    elif tam == "grande":
        company_size = 100
    
    # Recency: 0-20 points
    days_old = (datetime.now() - lead["fecha_señal"]).days
    recency = max(0, 20 - (days_old * 2))  # -2 points per day, min 0
    
    # Tax compliance: 0-15 points
    tax_compliance = 15 if lead.get("tax_compliant") else 0
    
    total = (
        hiring_intensity * 0.40 +
        company_size * 0.25 +
        recency * 1.0 +
        tax_compliance * 1.0
    )
    
    return min(100, total)

# Sort by score
leads_sorted = sorted(leads, key=calculate_intent_score, reverse=True)
```

**Testing:**
- Unit: Known companies with known scores
- A/B test: Compare old ranking vs intent ranking (conversion rate)

**Acceptance Criteria:**
- ✅ Score correlates with actual conversion rate
- ✅ Top 10 leads have > 70% conversion (vs 40% baseline)

---

### Task 2.3: Signal Enrichment in Analyzer
**Effort:** 10 hours  
**Files:** prospector.py (modify _analista_prompt), models.py

**New Analyzer Prompt Section:**
```python
def _analista_prompt_with_signals(url: str, scraped: str, signals: list, c: dict) -> str:
    """
    Augment analyst prompt with signal data (hiring, compliance, growth).
    Help GPT-4o infer pain points from signals.
    """
    
    signal_context = ""
    if signals:
        signal_context = f"""
        
═══════════════════════════════════════
SEÑALES DETECTADAS (datos externo):
═══════════════════════════════════════
"""
        for sig in signals:
            if sig["type"] == "new_hires":
                signal_context += f"- Contratan activamente: {sig['value']} personas en últimos 3 meses\n"
            elif sig["type"] == "licitacion_abierta":
                signal_context += f"- Licitación abierta: {sig['value']} (monto: {sig.get('monto', 'N/A')})\n"
            elif sig["type"] == "adjudicacion_reciente":
                signal_context += f"- Ganaron adjudicación: {sig['value']} hace {sig['dias']} días\n"
    
    # Modify prompt to include signals
    return base_prompt + signal_context
```

**Testing:**
- Unit: Mock signals, verify prompt construction
- Integration: Compare analysis with/without signals

**Acceptance Criteria:**
- ✅ Signals improve pain point detection accuracy
- ✅ No false positives (signals don't mislead analyzer)

---

### Task 2.4: Compliance Scoring
**Effort:** 8 hours  
**Files:** backend/compliance.py, database.py

**Compliance Checks (Colombia):**
```python
# compliance.py
async def calculate_compliance_score(nit: str, empresa: str) -> float:
    """
    Score 0-1. Check tax registry, legal status, etc.
    High score = lower risk of default.
    """
    
    # 1. DIAN tax compliance (via Rues or DIAN API)
    tax_compliant = await check_dian_compliance(nit)
    
    # 2. Bancolombia fraud check (if available)
    fraud_risk = await check_fraud_registry(nit)
    
    # 3. Public lawsuit registry
    has_lawsuits = await check_lawsuit_registry(nit)
    
    # Score calculation
    score = 0.5  # baseline
    if tax_compliant:
        score += 0.3
    if not fraud_risk:
        score += 0.2
    if not has_lawsuits:
        score += 0.0  # (already in tax compliance)
    
    return min(1.0, score)

# Use in lead scoring
lead_score = calculate_intent_score(lead) * compliance_score
```

**Testing:**
- Mock: Fake DIAN response
- Integration: Real DIAN call (if API available)

**Acceptance Criteria:**
- ✅ Can determine tax compliance
- ✅ Compliance score used in final ranking

---

## Wave 3: API Endpoints (Days 10-11)
**Goal:** Expose signal sources to frontend  
**Dependencies:** Wave 2 complete  
**Effort:** 2 days

### Task 3.1: Signal Configuration Endpoints
**Effort:** 6 hours  
**Files:** routers/prospect.py (new endpoint), database.py

```python
@router.post("/api/prospect/signal-sources/config")
async def configure_signal_sources(
    current_user: dict = Depends(get_current_user),
    enabled_sources: list[str] = ["rues", "bright_data"],
    weights: dict = {"rues": 1.0, "bright_data": 1.5}
):
    """
    User configures which signal sources to use for this campaign.
    Weights affect ranking (bright_data signals worth 1.5x vs RUES).
    """
    user_id = current_user["user_id"]
    
    # Validate sources
    valid_sources = ["rues", "bright_data", "google_maps", "hunter"]
    enabled_sources = [s for s in enabled_sources if s in valid_sources]
    
    # Save config
    await db.signal_source_configs.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "enabled_sources": enabled_sources,
                "weights": weights,
                "updated_at": datetime.now()
            }
        },
        upsert=True
    )
    
    return {"status": "updated", "config": {...}}

@router.get("/api/prospect/signal-sources/usage")
async def get_signal_usage(current_user: dict = Depends(get_current_user)):
    """
    Show user their signal source quota usage (internal cost tracking).
    Note: Broker only sees lead count quota, not cost breakdown.
    """
    user_id = current_user["user_id"]
    
    # Get cost events this month
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    costs = await db.cost_events.aggregate([
        {"$match": {"user_id": user_id, "timestamp": {"$gte": month_start}}},
        {"$group": {"_id": "$source", "count": {"$sum": 1}, "total_cost": {"$sum": "$cost_usd"}}}
    ]).to_list(None)
    
    return {
        "month": month_start.strftime("%Y-%m"),
        "costs_by_source": {c["_id"]: {"count": c["count"], "cost_usd": c["total_cost"]} for c in costs},
        "total_cost_this_month": sum(c["total_cost"] for c in costs)
    }
```

**Testing:**
- Unit: Mock database calls
- Integration: Create config, verify saved

**Acceptance Criteria:**
- ✅ Can enable/disable sources
- ✅ Can adjust weights
- ✅ Usage query returns accurate cost data

---

### Task 3.2: Signal History Endpoint
**Effort:** 4 hours  
**Files:** routers/prospect.py (new endpoint)

```python
@router.get("/api/prospect/signals/audit")
async def audit_signals(
    current_user: dict = Depends(get_current_user),
    limit: int = 100,
    source: Optional[str] = None
):
    """
    Audit trail of all signals discovered this month.
    Useful for debugging + understanding where leads come from.
    """
    user_id = current_user["user_id"]
    month_start = datetime.now().replace(day=1, hour=0, minute=0, second=0)
    
    query = {"user_id": user_id, "created_at": {"$gte": month_start}}
    if source:
        query["source"] = source
    
    signals = await db.signal_leads.find(query).sort("created_at", -1).limit(limit).to_list(None)
    
    return {
        "count": len(signals),
        "signals": signals,
        "sources": list(set(s["source"] for s in signals))
    }
```

**Testing:**
- Integration: Insert test signals, verify query

**Acceptance Criteria:**
- ✅ Can filter by source
- ✅ Returns audit trail with timestamps

---

## Wave 4: Quota + Dashboard (Days 12-13)
**Goal:** Enforce plan-based limits + UI updates  
**Dependencies:** Wave 3 complete  
**Effort:** 2 days

### Task 4.1: Quota Enforcement
**Effort:** 8 hours  
**Files:** routers/prospect.py, database.py, models.py

**Schema:**
```python
# models.py
class TenantQuota(BaseModel):
    user_id: str                # Email of broker
    plan: str                   # 'free' | 'pro' | 'enterprise'
    monthly_leads_limit: int    # 100 | 1000 | unlimited
    monthly_leads_used: int     # Current usage
    reset_date: datetime        # First of month
    created_at: datetime
    updated_at: datetime

# Database
{
    "user_id": "dpg.seguros@gmail.com",
    "plan": "pro",
    "monthly_leads_limit": 1000,
    "monthly_leads_used": 234,
    "reset_date": "2026-06-01T00:00:00Z",
}
```

**Quota Check:**
```python
async def check_quota(user_id: str) -> bool:
    quota = await db.tenant_quotas.find_one({"user_id": user_id})
    if not quota:
        raise HTTPException(status_code=404, detail="Quota not initialized")
    
    # Check if month reset
    today = datetime.now()
    if today.month != quota["reset_date"].month:
        # Reset
        await db.tenant_quotas.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "monthly_leads_used": 0,
                    "reset_date": datetime.now().replace(day=1)
                }
            }
        )
        quota["monthly_leads_used"] = 0
    
    if quota["monthly_leads_used"] >= quota["monthly_leads_limit"]:
        raise HTTPException(status_code=429, detail="Monthly quota exceeded")
    
    return True

# In /api/prospect
@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    # Check quota BEFORE running
    await check_quota(user_id)
    
    # ... rest of prospecting logic ...
    
    # After first lead found, increment quota
    # (tracked in cost_events)
```

**Testing:**
- Unit: Mock quota scenarios
- Integration: Run campaign, verify quota decrements

**Acceptance Criteria:**
- ✅ Cannot run campaign if quota exceeded
- ✅ Monthly reset works correctly
- ✅ Returns 429 (Too Many Requests) when exceeded

---

### Task 4.2: Quota API Endpoints
**Effort:** 4 hours  
**Files:** routers/prospect.py (new endpoints)

```python
@router.get("/api/quota/me")
@require_client  # Only clients can view their own quota
async def get_my_quota(current_user: dict = Depends(get_current_user)):
    """
    Broker-facing: What quota do I have left?
    """
    user_id = current_user["user_id"]
    quota = await db.tenant_quotas.find_one({"user_id": user_id})
    
    if not quota:
        # Auto-create if missing
        quota = await initialize_quota(user_id, plan="pro")
    
    remaining = quota["monthly_leads_limit"] - quota["monthly_leads_used"]
    reset_date = quota["reset_date"]
    days_until_reset = (reset_date - datetime.now()).days
    
    return {
        "plan": quota["plan"],
        "monthly_limit": quota["monthly_leads_limit"],
        "monthly_used": quota["monthly_leads_used"],
        "remaining": remaining,
        "reset_date": reset_date,
        "days_until_reset": days_until_reset,
        "percentage_used": int((quota["monthly_leads_used"] / quota["monthly_leads_limit"]) * 100)
    }

@router.get("/api/admin/quotas")
@require_staff  # Only staff can view all quotas
async def get_all_quotas(current_user: dict = Depends(get_current_user)):
    """
    Isomorph dashboard: View all broker quotas + analytics.
    """
    quotas = await db.tenant_quotas.find({}).to_list(None)
    
    return {
        "total_brokers": len(quotas),
        "quotas": quotas,
        "revenue": sum(q.get("monthly_leads_used", 0) * 0.50 for q in quotas),  # $0.50 per lead
        "costs": await calculate_monthly_costs()
    }
```

**Testing:**
- Integration: Create quota, query via API

**Acceptance Criteria:**
- ✅ Broker can see their own quota
- ✅ Staff can see all quotas
- ✅ Correct role-based access control

---

### Task 4.3: Dashboard Widget (Frontend)
**Effort:** 4 hours  
**Files:** frontend/src/components/QuotaWidget.tsx (if exists)

**Widget Display:**
```
┌─────────────────────────────────┐
│        PLAN STATUS               │
├─────────────────────────────────┤
│                                  │
│ Pro Plan                         │
│ 234 / 1000 leads used            │
│ [████░░░░░░░░░░░░░░]  23%        │
│                                  │
│ Reset in 12 days (June 1)        │
│ [Upgrade Plan]                   │
└─────────────────────────────────┘
```

---

## Wave 5: Testing + Validation (Days 14-18)
**Goal:** E2E testing, load testing, backup scenarios  
**Dependencies:** Waves 1-4 complete  
**Effort:** 5 days

### Task 5.1: E2E Integration Tests
**Effort:** 8 hours  
**Files:** tests/test_signal_sources_e2e.py

```python
@pytest.mark.asyncio
async def test_full_signal_to_lead_flow():
    """
    End-to-end: Signal discovery → Dedup → Ranking → Prospecting → Email
    """
    # 1. Search RUES for new companies
    rues_results = await rues_source.search("software", "Bogotá", max_results=5)
    assert len(rues_results) > 0
    
    # 2. Check deduplication
    new_nit = rues_results[0]["nit"]
    existing = await dedup_engine.find_duplicate(new_nit, rues_results[0]["razón_social"])
    assert existing is None  # First time
    
    # 3. Calculate intent score
    signal = {"new_hires": 5, "tamano_estimado": "pequeña", "fecha_señal": datetime.now()}
    score = calculate_intent_score(signal)
    assert 0 <= score <= 100
    
    # 4. Enqueue prospecting job
    run_id = str(uuid.uuid4())
    await state.arq_pool.enqueue_job("run_prospecting_job", run_id=run_id, ...)
    
    # 5. Wait for completion (with timeout)
    async with asyncio.timeout(120):
        while True:
            run = await db.runs.find_one({"_id": run_id})
            if run["status"] in ["complete", "error"]:
                break
            await asyncio.sleep(2)
    
    # 6. Verify leads were created
    leads = await db.leads.find({"run_id": run_id}).to_list(None)
    assert len(leads) > 0
```

**Testing:**
- Run E2E test 5 times (consistency)
- Monitor memory usage (no leaks)

---

### Task 5.2: Load Test
**Effort:** 8 hours  
**Files:** tests/load_test.py

```python
@pytest.mark.asyncio
async def test_load_100_concurrent_campaigns():
    """
    Simulate 100 brokers running campaigns simultaneously.
    Verify no timeouts, memory leaks, rate limiting issues.
    """
    async def run_campaign(broker_id: int):
        # Simulate broker starting campaign
        response = await client.post(
            "/api/prospect",
            json={"max_results": 20},
            headers={"Authorization": f"Bearer {tokens[broker_id]}"}
        )
        assert response.status_code == 200
        return response.json()["run_id"]
    
    # Start 100 campaigns concurrently
    run_ids = await asyncio.gather(*[run_campaign(i) for i in range(100)])
    
    # Monitor for 5 minutes
    for _ in range(300):
        # Check job queue depth
        pending_jobs = await state.arq_pool.get_job_count()
        assert pending_jobs < 50  # Should process steadily
        
        # Check memory usage
        mem_usage = psutil.Process().memory_info().rss / 1024 / 1024  # MB
        assert mem_usage < 1000  # Should not exceed 1GB
        
        await asyncio.sleep(1)
    
    # Verify all completed or in-progress
    for run_id in run_ids:
        run = await db.runs.find_one({"_id": run_id})
        assert run["status"] in ["complete", "in_progress", "queued"]
```

**Acceptance Criteria:**
- ✅ 100 campaigns run without error
- ✅ Average latency < 5 sec
- ✅ Memory stays < 1GB
- ✅ No crashes or timeouts

---

### Task 5.3: Backup + Failure Scenarios
**Effort:** 8 hours  
**Files:** tests/test_failure_scenarios.py

```python
async def test_signal_source_timeout():
    """If RUES times out, should fall back gracefully."""
    # Mock timeout
    with patch("rues_scraper.search", side_effect=asyncio.TimeoutError):
        result = await discovery_with_fallback("software", "Bogotá")
        assert len(result) > 0  # Should use fallback (Serper, Google Maps)

async def test_webhook_retry_after_crash():
    """If webhook processor crashes, verify DLQ + retry."""
    # Simulate crash
    with patch("wa_handler.process_inbound", side_effect=Exception("DB connection failed")):
        # Webhook should store in DLQ
        await whatsapp_incoming({"From": "57123", "Body": "test"})
        
        dlq_item = await db.webhook_dlq.find_one({})
        assert dlq_item is not None
        assert dlq_item["attempt_count"] == 1
        
        # Simulate retry after 5 minutes
        dlq_item["next_retry"] = datetime.now() - timedelta(seconds=1)
        # ... trigger retry logic ...
        # Should succeed on retry

async def test_quota_enforcement():
    """Verify broker cannot exceed quota."""
    # Set quota to 10
    await db.tenant_quotas.update_one(
        {"user_id": "test@broker.com"},
        {"$set": {"monthly_leads_limit": 10, "monthly_leads_used": 10}}
    )
    
    # Try to run campaign
    response = await client.post("/api/prospect", headers=auth)
    assert response.status_code == 429  # Too Many Requests
```

**Acceptance Criteria:**
- ✅ Timeouts handled gracefully (fallback works)
- ✅ DLQ captures failed webhooks
- ✅ Quota enforcement prevents over-usage
- ✅ No data loss on failures

---

## Review Checklist

- [ ] Wave 0: Timeouts on all external APIs
- [ ] Wave 0: job_timeout reduced to 600s
- [ ] Wave 0: Error handler middleware
- [ ] Wave 0: DLQ implemented + tested
- [ ] Wave 1: RUES integration (mock + real)
- [ ] Wave 1: Bright Data integration (mock)
- [ ] Wave 1: Hunter integration (mock + cost tracking)
- [ ] Wave 2: Deduplication fuzzy matching
- [ ] Wave 2: Intent scoring model + testing
- [ ] Wave 2: Signal enrichment in analyzer
- [ ] Wave 2: Compliance scoring
- [ ] Wave 3: Signal config endpoints
- [ ] Wave 3: Signal audit endpoints
- [ ] Wave 4: Quota enforcement logic
- [ ] Wave 4: Quota endpoints (/api/quota/me, /api/admin/quotas)
- [ ] Wave 4: Dashboard widget (if frontend exists)
- [ ] Wave 5: E2E tests (5+ scenarios)
- [ ] Wave 5: Load test (100 concurrent)
- [ ] Wave 5: Failure scenario tests
- [ ] Code review: Security (no SQL injection, XSS, etc)
- [ ] Performance: Avg latency < 5s, memory < 1GB
- [ ] Documentation: README updated

---

## Rollout Strategy

### Phase 24.1: Canary (Days 19-21)
- Deploy to staging
- 5 staff test campaigns
- Monitor: timeouts, crashes, quota enforcement

### Phase 24.2: Beta (Days 22-25)
- Enable for 2 client brokers (test)
- Monitor: conversion rate, signal quality, costs

### Phase 24.3: GA (Days 26+)
- Full rollout to all brokers
- Feature flag: `ENABLE_SIGNAL_SOURCES=true`
- Disable if issues: `ENABLE_SIGNAL_SOURCES=false`

---

## Notes

- **Blockers:** Phase 19 (multi-tenant) must be complete first
- **Dependencies:** All external API keys must be in .env
- **Risks:** RUES API unstable (mitigate with fallback)
- **Optimizations:** Crawl4AI truncation (6000 → 3000), concurrency (3 → 8)
- **Costs:** Bright Data ~$300/month, Hunter ~$200/month, Serper ~$100/month = $600 total

