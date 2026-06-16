# Análisis Profundo: Arquitectura Backend Lambda Office

**Fecha:** May 2026 | **Versión:** 0.4.21 | **Stack:** FastAPI + Motor (MongoDB) + ARQ (Redis) + Pipecat

---

## 1. ESTRUCTURA GENERAL

### 1.1 Organización del Proyecto

```
backend/
├── main.py                 # Entry point + lifespan + middleware
├── routers/               # Módulos por dominio (11 archivos)
│   ├── auth.py            # JWT + register/login + OAuth
│   ├── leads.py           # Lead CRUD + email outreach
│   ├── prospect.py        # Prospecting pipeline + chat
│   ├── staff.py           # Admin dashboard + client management
│   ├── whatsapp.py        # Twilio webhooks + bot routing
│   ├── secop.py           # NIT enrichment + radar de licitaciones
│   ├── onboarding.py      # Staff: client setup flow
│   ├── knowledge.py       # RAG: file/URL ingestion
│   ├── agents_legacy.py   # [deprecated]
│   ├── websocket.py       # WebSocket connections
│   └── misc.py            # Health, roadmap state
├── services/              # Shared business logic
│   ├── connection_manager.py  # WebSocket broadcast
│   └── notifications.py       # [minimal]
├── cobranza/              # Voice + Collections (separate product)
│   ├── router.py          # Debtor CRUD endpoints
│   ├── voice_router.py    # Voice call orchestration
│   ├── webhooks.py        # Vapi callbacks + events
│   ├── voice_orchestrator.py
│   └── [8 more modules]
├── database.py            # Motor client + index setup
├── auth.py                # JWT creation/validation + deps
├── models.py              # Pydantic models
├── orchestrator.py        # HiveOrchestrator (multi-agent state)
├── prospector.py          # B2B prospecting engine
├── rate_limiting.py       # In-memory rate limiter
├── arq_pool.py            # ARQ Redis pool factory
├── worker.py              # ARQ job worker (separate process)
├── requirements.txt       # Dependencies
└── [40+ other modules]    # Helpers, integrations, seeds
```

---

### 1.2 Flujo Principal: Request → Handler → Database → Response

```
HTTP Request
    ↓
    ├─→ CORSMiddleware + SecurityHeadersMiddleware
    ├─→ [Rate Limiting] (login/register only)
    ├─→ [Auth] get_current_user(token from header/cookie)
    ├─→ Router Handler
    │   ├─→ Input Validation (Pydantic)
    │   ├─→ DB Query (Motor/MongoDB)
    │   ├─→ [If long-running] Enqueue ARQ job
    │   └─→ Build response
    ├─→ WebSocket broadcast (via ConnectionManager)
    └─→ JSON Response
```

**Componentes clave y responsabilidades:**

| Componente | Responsabilidad | Patrón |
|-----------|-----------------|--------|
| **main.py** | Inicializar FastAPI, lifespan, routers, middleware | Singleton app + lifespan context manager |
| **routers/** | Handlers de endpoints, validación Pydantic | REST → database query |
| **database.py** | Motor client, índices, CRUD functions | Centralized DB access (no direct Motor import en routers) |
| **auth.py** | JWT, password hashing, dependency injection | OAuth2PasswordBearer + Depends() |
| **orchestrator.py** | Multi-agent state machine + OpenAI Swarm | Broadcast callback for real-time updates |
| **worker.py** | ARQ job execution (prospecting pipeline) | Separate process, independent lifespan |
| **services/** | WebSocket broadcast, notifications | Injection via state.* globals |

---

### 1.3 Patrón de Responsabilidades

```
┌────────────────────────────────────────┐
│        HTTP Layer (FastAPI)            │
│  - CORS, Security Headers, Rate Limit  │
└────────────────────────────────────────┘
              ↓
┌────────────────────────────────────────┐
│    Auth Layer (JWT + Dependencies)     │
│  - get_current_user()                  │
│  - require_staff()                     │
└────────────────────────────────────────┘
              ↓
┌────────────────────────────────────────┐
│    Router Layer (Validation + Logic)   │
│  - Pydantic request validation         │
│  - Business logic orchestration        │
└────────────────────────────────────────┘
              ↓
┌────────────────────────────────────────┐
│    Data Access Layer (Motor)           │
│  - Centralized in database.py          │
│  - No direct Motor imports in routers  │
└────────────────────────────────────────┘
              ↓
┌────────────────────────────────────────┐
│    MongoDB (collections + indexes)     │
└────────────────────────────────────────┘
```

---

## 2. MANEJO DE ERRORES

### 2.1 Estrategia General

**Patrón predominante: HTTPException + logger.error()**

```python
# PATRÓN 1: HTTPException (synchronous)
raise HTTPException(status_code=404, detail="Lead not found or not yours")

# PATRÓN 2: logger.error() + raise
try:
    await external_api_call()
except Exception as e:
    logger.error("[context] Error description: %s", e)
    raise HTTPException(status_code=503, detail="Service unavailable")

# PATRÓN 3: Silent error handling (problematic)
except Exception:
    pass  # Swallowed
```

### 2.2 Ejemplos de Error Handling por Router

#### **auth.py** (login)
```python
@router.post("/auth/login")
async def login(user: UserCreate, request: Request):
    from rate_limiting import check_login_rate_limit
    check_login_rate_limit(user.email, request)
    # ✅ Rate limiting enforced
    
    db_user = await get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(
            status_code=401, 
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    # ✅ 401 (auth failure) + WWW-Authenticate header
    
    token = create_access_token(data={"sub": str(db_user["id"]), "role": db_user.get("role", "client")})
    response = JSONResponse(content={...}, status_code=200)
    response.set_cookie(key="hive_token", value=token, httponly=True, secure=True, samesite="lax")
    return response
    # ✅ httpOnly cookie + Secure + SameSite (CSRF mitigation)
```

**✅ Lo que está bien:**
- Rate limiting en login + registration
- Secure httpOnly cookies
- Standard HTTP status codes (401, 403, 422, 503)
- JWT + fallback cookie auth

**⚠️ Necesita mejora:**
- No hay retry logic en external calls
- Error messages exponen detalles (email already registered = user enumeration)
- No logging de intentos fallidos para auditoría

---

#### **leads.py** (email send)
```python
@router.post("/api/leads/{lead_id}/send-email")
async def send_lead_email(lead_id: str, request: SendEmailRequest, current_user: dict = Depends(get_current_user)):
    if not os.getenv("MAILERSEND_API_KEY"):
        raise HTTPException(status_code=503, detail="MAILERSEND_API_KEY not configured")
    # ✅ 503 Service Unavailable (env var missing)
    
    user_id = str(current_user["user_id"])
    db = get_db()
    lead = await db.leads.find_one({"_id": lead_id, "user_id": user_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    try:
        status = await send_lead_outreach(
            to_email=to_email, 
            subject=subject, 
            body_text=body,
            ...
        )
    except RuntimeError as e:
        # ❌ Catches RuntimeError but logic after is incomplete
```

**✅ Lo que está bien:**
- Validates lead ownership (tenant isolation)
- 503 for missing configuration
- Email validation before send

**⚠️ Problemas:**
- RuntimeError handler incomplete (exception swallowed)
- No timeout on `send_lead_outreach()`
- No retry policy
- Error doesn't update lead status

---

#### **prospect.py** (prospecting job)
```python
@router.post("/api/prospect")
async def prospect(request: ProspectRequest, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="OPENAI_API_KEY not configured")
    
    campaign = request.campaign or await get_active_campaign(user_id)
    
    run_id = str(uuid.uuid4())
    await create_run(...)
    
    await state.arq_pool.enqueue_job(
        "run_prospecting_job",
        run_id=run_id,
        ...,
        _job_id=run_id,  # deduplication
    )
    return {"status": "queued", "run_id": run_id}
    # ❌ No timeout on job enqueue; job_timeout=3600 on worker side
```

**✅ Lo que está bien:**
- Async job enqueue (non-blocking)
- Job deduplication via run_id

**⚠️ Problemas:**
- 1-hour job timeout is high (user sees spinner for too long)
- No user notification on timeout
- Job failure updates status but doesn't notify UI

---

#### **whatsapp.py** (webhook)
```python
@router.post("/api/whatsapp/incoming")
async def whatsapp_incoming(request: Request):
    # Signature validation
    if not wa_handler.validate_twilio_signature(url, signature, dict(form)):
        logging.warning("[WA] Invalid Twilio signature from %s", from_raw)
        return Response(content="<Response/>", media_type="text/xml")
    # ✅ Webhook signature validation
    
    profile = await wa_handler.get_profile(from_phone)
    if profile is None:
        logging.warning("[WA] Unknown number %s", from_phone)
        return Response(content="<Response/>", media_type="text/xml")
    # ✅ Silently rejects unknown numbers (security)
    
    asyncio.create_task(_safe_task(wa_handler.process_inbound(...), "process_inbound"))
    # ❌ Fire-and-forget; errors not propagated
    
    return Response(content="<Response/>", media_type="text/xml")
```

**✅ Lo que está bien:**
- Twilio signature validation
- Tenant isolation via phone_number→profile

**⚠️ Problemas:**
- `_safe_task()` swallows exceptions silently
- No retry on transient failures
- No dead-letter queue

---

### 2.3 Logger Centralizado

**Configuración en main.py:**
```python
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s", 
    datefmt="%H:%M:%S"
)

# Selectively lower log level for verbose modules
for _log in ("hive_adapter", "hive_llm", "hive_tools", "hive_graph", "framework.graph.event_loop_node", "framework.graph.executor", "wa_handler"):
    logging.getLogger(_log).setLevel(logging.INFO)
```

**✅ Lo que está bien:**
- Centralized logging setup
- Per-module level control

**⚠️ Necesita mejora:**
- No structured logging (no JSON fields like user_id, request_id, trace_id)
- No log aggregation setup (dev-only console logging)
- No ERROR alerting mechanism
- Logger names are strings (hardcoded, not module-aware in some cases)

---

### 2.4 Diferenciación de Errores

| Tipo | Status | Ejemplo | Manejo |
|------|--------|---------|--------|
| **4xx (Client)** | 400, 401, 403, 404, 422 | Invalid input, auth, permissions | Log warning, return detail |
| **5xx (Server)** | 500, 503 | LLM timeout, DB down, missing config | Log error + trace, return generic detail |
| **Custom** | HTTPException | FastAPI raises internally | Middleware could catch |

**Patrón: No hay error handler centralizado.**

```python
# ❌ No existe @app.exception_handler() para:
# - Validation errors (422) — usar custom model validator
# - TimeoutError / asyncio.TimeoutError
# - Database connection errors
# - External API failures (Serper, OpenAI, Mailgun, etc.)
```

---

## 3. ENDPOINTS PRINCIPALES

### 3.1 Mapa de Endpoints (11 routers, ~50 endpoints totales)

```
Auth (8 endpoints)
  POST   /auth/register
  POST   /auth/login
  POST   /auth/google-login
  POST   /auth/register-request
  GET    /admin/registration-requests
  PATCH  /admin/registration-requests/{request_id}/status
  POST   /auth/register-welcome
  POST   /api/ws-ticket

Leads (8 endpoints)
  GET    /api/leads
  GET    /api/leads/checkpoint
  GET    /api/leads/{lead_id}
  GET    /api/leads/{lead_id}/draft
  POST   /api/leads/{lead_id}/send-email
  POST   /api/leads/{lead_id}/hitl-decision
  GET    /api/leads/ideal
  GET    /api/leads/rejected

Prospect (12 endpoints)
  POST   /api/prospect
  POST   /api/chat
  POST   /api/chat/leads
  POST   /api/campaigns
  GET    /api/campaigns/active
  GET    /api/runs
  GET    /api/runs/{run_id}/report
  POST   /api/runs/{run_id}/checkpoint-debug
  POST   /api/prospect/nl
  POST   /api/prospect/knowledge/upsert
  GET    /api/prospect/knowledge
  POST   /api/prospect/sources/exclude

Staff (12+ endpoints)
  GET    /api/staff/stats
  GET    /api/staff/clients
  POST   /api/staff/clients/{client_id}/enable
  POST   /api/staff/clients/{client_id}/onboard-start
  POST   /api/staff/onboard/discard/{client_id}
  POST   /api/staff/onboard/chat/{client_id}
  POST   /api/staff/onboard/save-conversation/{client_id}
  POST   /api/staff/onboard/propose/{client_id}
  GET    /api/staff/onboard/debug-knowledge/{client_id}
  POST   /api/staff/clients/{client_id}/reset-password
  POST   /api/staff/clients/{client_id}/revoke-access

Cobranza (8+ endpoints)
  GET    /api/cobranza/status
  POST   /api/cobranza/debtors/csv
  POST   /api/cobranza/debtors
  GET    /api/cobranza/debtors
  GET    /api/cobranza/debtors/{debtor_id}
  PATCH  /api/cobranza/debtors/{debtor_id}
  DELETE /api/cobranza/debtors/{debtor_id}
  POST   /api/cobranza/calls/initiate

WhatsApp (6 endpoints)
  POST   /api/whatsapp/webhook (legacy)
  POST   /api/whatsapp/incoming (new routing)
  POST   /api/whatsapp-agents
  GET    /api/whatsapp-agents
  GET    /api/whatsapp-agents/{phone_number}
  DELETE /api/whatsapp-agents/{phone_number}

SECOP (3 endpoints)
  POST   /api/secop/enrich-nit
  POST   /api/secop/radar-polizas
  GET    /api/secop/procesos-abiertos

Knowledge (2 endpoints)
  POST   /api/staff/clients/{client_id}/knowledge/upload
  POST   /api/staff/clients/{client_id}/knowledge/url

Onboarding (5 endpoints)
  [covered in Staff section]

WebSocket
  /ws/{user_id}  (no HTTP counterpart)

Misc (2 endpoints)
  GET    /api/health
  GET/POST /api/roadmap-state
```

---

### 3.2 Top 10 Endpoints + Flujos

#### **1. POST /auth/login**
- **Método:** POST
- **Auth:** None (public)
- **Parámetros:** `email`, `password`
- **Rate Limiting:** 5 intentos / 15 min por email
- **Response:** `{access_token, token_type, email, role, user_id}`
- **Cookie:** `hive_token` (httpOnly, Secure, SameSite=Lax)
- **Errores:** 401 (wrong creds), 429 (rate limited)

**Flujo:**
```
1. Check rate limit (in-memory store)
2. Lookup user by email
3. Verify bcrypt password
4. Create JWT token (15 min expiry)
5. Set httpOnly cookie
6. Return user_id + role + email
```

**Calidad:** ✅ Buena (tiene rate limiting, secure cookies)

---

#### **2. POST /api/prospect**
- **Método:** POST
- **Auth:** Required (current_user)
- **Parámetros:** `campaign`, `max_results`, `source_priority`
- **Timeout:** **None en handler (pero 3600s en worker job)**
- **Response:** `{status: "queued", run_id, message}`
- **Job Dedup:** Via run_id

**Flujo:**
```
1. Validate current_user (JWT)
2. Load active campaign (or use provided)
3. Create run DB record (status="queued")
4. Enqueue ARQ job (run_prospecting_job)
   └─ Job timeout: 3600s (1 hour)
   └─ Max retries: 1 (no auto-retry)
5. Return run_id to user
6. [Async] Worker broadcasts events via WebSocket
```

**Cadena de llamadas:**
```
/api/prospect (handler) 
  ↓ 
state.arq_pool.enqueue_job() 
  ↓ 
worker.run_prospecting_job() 
  ↓ 
HiveAdapter.start_run() 
  ↓ 
prospector.py (4-stage pipeline: search → scrape → analyze → write)
```

**Calidad:** ⚠️ Necesita mejora
- Job timeout es muy alto (1 hora)
- User no ve timeout (spinner indefinido)
- No hay backoff exponencial en retries

---

#### **3. POST /api/leads/{lead_id}/send-email**
- **Método:** POST
- **Auth:** Required
- **Parámetros:** `subject_index` (0-based)
- **Timeout:** **None (external Mailgun call)**
- **Response:** `{status: "queued", message_id}`
- **Dependencies:** MAILERSEND_API_KEY

**Flujo:**
```
1. Validate lead ownership (user_id match)
2. Extract email draft from lead.expediente_json
3. Call send_lead_outreach() → Mailgun API
4. Update lead.estado = "enviado"
5. Return {status, message_id}
```

**Calidad:** ❌ Problemas críticos
- No timeout on Mailgun call → blocks request
- On error: RuntimeError swallowed (incomplete exception handler)
- No retry logic (transient failures = permanent failure)
- No update to lead status if send fails

---

#### **4. POST /api/whatsapp/incoming**
- **Método:** POST
- **Auth:** None (webhook, but Twilio signature verified)
- **Parámetros:** Form data from Twilio (From, To, Body, NumMedia, MediaUrl0)
- **Signature Validation:** ✅ HMAC-SHA1 (Twilio-required)
- **Response:** `<Response/>` (TwiML XML)

**Flujo:**
```
1. Extract phone, message from form
2. Validate Twilio signature (HMAC-SHA1)
3. Get agent config by phone_number
4. Determine bot mode (legacy, calendar, landa)
5. Fire-and-forget: asyncio.create_task(process_inbound())
6. Return immediately (TwiML)
```

**Cadena de llamadas:**
```
/api/whatsapp/incoming (webhook)
  ↓
wa_handler.process_inbound() or whatsapp_agent.handle_inbound_message()
  ↓
[Bot logic: calendar, SECOP, Landa]
  ↓
send_whatsapp_text() → Twilio API
```

**Calidad:** ⚠️ Problemas
- Fire-and-forget: errors not captured
- No dead-letter queue (lost messages on crash)
- No backoff (rapid retries = rate limit from Twilio)
- Signature validation ✅ good

---

#### **5. GET /api/leads/checkpoint**
- **Método:** GET
- **Auth:** Required
- **Query:** None
- **Response:** `[{id, empresa, puntaje, criterios, canales, estado, ...}]`
- **Timeout:** None

**Flujo:**
```
1. Get user_id from current_user
2. Query: db.leads.find({user_id, estado: "checkpoint"})
3. Sort by estado_updated_at (descending)
4. Limit 100
5. Project fields + format response
```

**Calidad:** ✅ Buena
- Simple, no external calls
- Tenant isolation ✓
- Indexed query (user_id, estado)

---

#### **6. POST /api/cobranza/debtors/csv**
- **Método:** POST
- **Auth:** Required
- **Parámetros:** File (CSV), mode (create/update)
- **Response:** `{created: N, updated: N, errors: [...]}`
- **Validation:** Custom CSV parser

**Flujo:**
```
1. Check cobranza_enabled (guard)
2. Parse CSV → validate phone, vencimiento
3. If mode="create": bulk_create_debtors()
4. If mode="update": bulk_upsert_debtors() (by phone)
5. Return stats + errors
```

**Calidad:** ⚠️ Parcial
- ✅ Mode selection (create vs update)
- ✅ Per-row error collection
- ❌ No streaming (reads entire file into memory)
- ❌ No max file size validation

---

#### **7. GET /api/staff/stats**
- **Método:** GET
- **Auth:** require_staff (role=staff only)
- **Response:** `{global: {...}, per_client: [...]}`

**Flujo:**
```
1. Get all users (role=client)
2. Parallel gather:
   - Total leads, approved leads, runs, checkpoint leads
   - Per-client summaries
3. Get active_run_ids from state.hive_adapter._runs
4. Assemble stats
```

**Calidad:** ✅ Buena
- Staff-only (authorization)
- Parallelized queries (asyncio.gather)
- Real-time active runs (from state)

---

#### **8. POST /api/chat**
- **Método:** POST
- **Auth:** Required
- **Parámetros:** `messages` (conversation history)
- **External Call:** OpenAI API (Claude via OpenRouter)
- **Timeout:** **None**
- **Auto-save:** Attempts to parse campaign from reply

**Flujo:**
```
1. Build campaign context (from active campaign + profile + RAG)
2. Call chat_turn() → OpenAI API
3. Parse reply for "CAMPAIGN_READY:" marker
4. If found: extract JSON → save_campaign()
5. Return reply
```

**Calidad:** ⚠️ Problemas
- OpenAI call not wrapped in timeout
- Auto-save logic tries JSON extraction but swallows errors
- No streaming (full response waits for completion)

---

#### **9. POST /api/cobranza/calls/initiate**
- **Método:** POST
- **Auth:** Required
- **Parámetros:** `debtor_id`
- **External Call:** Vapi (voice API)
- **Response:** `{call_id, status}`

**Flujo:**
```
1. Check cobranza_enabled
2. Get debtor
3. Check call scheduling (time-of-day rules)
4. Generate cobranza strategy (Claude prompt)
5. Initiate Vapi call
6. Store call record
7. Broadcast via WebSocket
```

**Calidad:** ⚠️ Problemas
- Vapi call not wrapped in timeout
- Strategy generation not cached (re-runs on each call)
- No max_calls_per_day enforcement
- On Vapi failure: unclear error propagation

---

#### **10. POST /api/staff/clients/{client_id}/knowledge/url**
- **Método:** POST
- **Auth:** require_staff
- **Parámetros:** `urls` (list), `source_type`
- **External Call:** fetch_url_text() (HTTP fetch + parse)
- **Timeout:** **None**
- **Response:** `{total_urls, stored_urls, results}`

**Flujo:**
```
1. Deduplicate URLs
2. For each URL:
   - fetch_url_text() (HTTP, BeautifulSoup)
   - ingest_document() (chunking + embedding)
3. Collect errors + results
4. If at least 1 success: return 200
5. Else: return 422 (validation error)
```

**Calidad:** ⚠️ Problemas
- HTTP fetch not wrapped in timeout (hangs on slow servers)
- No max URL count validation
- No max content size validation (could OOM on huge pages)
- Parallel fetches would be faster but not implemented

---

### 3.3 Endpoints que Llaman Otros Endpoints

```
/api/prospect (enqueues job)
  ↓ worker.run_prospecting_job()
    ├→ save_lead() (database.py)
    └→ publish_event() (WebSocket broadcast)

/api/leads/{lead_id}/send-email
  ↓ send_lead_outreach() (mailer.py)
    ├→ Mailgun API (external)
    └→ update_lead_status() (database.py)

/api/whatsapp/incoming (webhook)
  ↓ wa_handler.process_inbound()
    ├→ [Agent logic]
    └→ send_whatsapp_text() (Twilio API)

/api/chat
  ↓ chat_turn() (onboarding.py)
    ├→ OpenAI API (external)
    ├→ extract_campaign_from_nl() (parsing)
    └→ save_campaign() (database.py)

/api/staff/stats
  ├→ get_all_users() (database.py)
  ├→ get_leads_by_user() (database.py)
  ├→ get_client_profile() (database.py)
  └→ [No external calls]

/api/cobranza/calls/initiate
  ├→ get_debtor() (database.py)
  ├→ generate_cobranza_proposal() (Claude API)
  ├→ initiate_vapi_call() (Vapi API)
  └→ publish event (WebSocket)
```

---

## 4. LIMITACIONES Y RESTRICCIONES

### 4.1 Rate Limiting

**Status:** ⚠️ Existe pero muy limitado

**Ubicación:** `rate_limiting.py` (in-memory store)

```python
def check_rate_limit(
    identifier: str,       # IP, email, user_id
    endpoint: str,         # "login", "register"
    max_attempts: int = 5,
    window_seconds: int = 900  # 15 min
) -> bool:
    # In-memory: {key: [(timestamp, count), ...]}
    # Cleanup runs every hour (CLEANUP_INTERVAL=3600)
```

**Endpoints protegidos:**
```python
check_login_rate_limit(email, request)           # 5 attempts / 15 min
check_registration_rate_limit(request)           # 5 attempts / 15 min
```

**Problemas:**

| Problema | Impacto | Solución |
|----------|---------|----------|
| In-memory store (no persistence) | Rate limits reset on server restart | Redis-backed store |
| No per-IP limit on API endpoints | Brute-force on /api/prospect, /api/leads, etc. | Global rate limiter middleware |
| No throttling on external calls | DDoS Serper, OpenAI, Mailgun | Circuit breaker pattern |
| No cost-aware limiting | High-cost operations (1h job) unlimited | Budget-based quotas |

**✅ Lo que está bien:**
- 15-min sliding window is reasonable
- Per-endpoint configuration

**❌ Lo que está roto:**
- Not applied to most endpoints
- Lost on restart (not production-ready)
- No webhook protection (WhatsApp incoming not rate-limited)

---

### 4.2 Validaciones de Entrada

**Patrón:** Pydantic BaseModel validators en cada router

```python
# leads.py
class SendEmailRequest(BaseModel):
    subject_index: int = 0

# prospect.py
class ProspectRequest(BaseModel):
    campaign: dict = {}
    max_results: int = 20
    source_priority: str = "serper"

# knowledge.py
class UrlIngestRequest(BaseModel):
    user_id: str | None = None
    url: str | None = None
    urls: list[str] = Field(default_factory=list)
    source_type: str = "url_empresa"

# cobranza/router.py
class DebtorCreate(BaseModel):
    nombre: str
    telefono: str
    monto: float
    vencimiento: str  # "YYYY-MM-DD" (NO validation)
    notas: Optional[str] = None
    max_intentos: int = 5
```

**Validaciones presentes:**

| Campo | Validación | Código |
|-------|-----------|--------|
| `ProspectRequest.max_results` | No min/max | `int = 20` ❌ |
| `ProspectRequest.source_priority` | No enum | `str = "serper"` ❌ |
| `DebtorCreate.vencimiento` | Parse datetime in handler | `await datetime.strptime(...)` ✅ |
| `DebtorCreate.monto` | Type only | `float` ❌ (no min > 0) |
| `UrlIngestRequest.urls` | No max length | `list[str]` ❌ |

**Problemas:**

| Validación | Presente | Ejemplo |
|-----------|----------|---------|
| Max payload size | ❌ | 100 MB file uploads allowed |
| Max string length | ❌ | Campaign name unlimited |
| Enum values | ❌ | source_priority not validated |
| Email format | ❌ | Relied on database unique constraint |
| Phone format | ✅ | `normalize_phone()` in cobranza |
| Date format | ✅ | `DebtorCreate.vencimiento` |
| Numeric ranges | ❌ | monto can be negative |

**✅ Lo que está bien:**
- Pydantic used consistently
- Database validation as fallback

**❌ Lo que está roto:**
- No input size limits (file uploads, bulk CSV, URL lists)
- No enum constraints on choice fields
- No custom validators for business rules

---

### 4.3 Timeouts

**Status:** ❌ No hay timeouts en la mayoría de llamadas

```
┌─────────────────────────────────────┐
│       Prospecting Job Timeout       │
├─────────────────────────────────────┤
│ job_timeout: 3600 (1 hour)          │ ❌ Too high
│ Location: worker.py WorkerSettings  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│    External API Calls (None)        │
├─────────────────────────────────────┤
│ OpenAI (chat_turn)        | No      │ ❌ Can hang 30+ sec
│ Mailgun (send_lead_email) | No      │ ❌ Can hang
│ Vapi (voice call)         | No      │ ❌ Can hang
│ Serper (web search)       | No      │ ❌ Can hang
│ Bright Data (scraping)    | No      │ ❌ Can timeout
│ URL fetch (knowledge)     | No      │ ❌ Can hang on 404
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│   MongoDB Queries (Implicit)        │
├─────────────────────────────────────┤
│ Motor connections have defaults:    │
│ - Connection timeout: 30s            │ ✅ Reasonable
│ - Command timeout: None              │ ❌ Can hang
│ - Socket timeout: 30s                │ ✅ Reasonable
└─────────────────────────────────────┘
```

**Ejemplos problemáticos:**

```python
# ❌ No timeout on OpenAI call (can hang indefinitely)
reply = await chat_turn(request.messages, api_key, context=context)

# ❌ No timeout on Mailgun API (can hang)
status = await send_lead_outreach(to_email=..., subject=..., body_text=...)

# ❌ No timeout on URL fetch (slow/dead servers can hang)
text = await fetch_url_text(target_url)

# ❌ No timeout on Vapi call
await initiate_vapi_call(debtor_phone, strategy)

# ✅ Good: Job timeout on worker
job_timeout = 3600  # but still too high
```

**Impacto:**
- User requests block indefinitely
- Server connection pool exhausted
- WebSocket clients freeze
- No timeout → retry forever (if implemented)

---

### 4.4 Máximo de Payload/Response Size

**Status:** ❌ No validación de tamaño

```python
# ❌ No limit on file upload (except FastAPI default 25MB)
async def upload_knowledge_docs(
    client_id: str,
    files: List[UploadFile] = File(...),  # No max_size
    ...
):
    for file in files:
        file_bytes = await file.read()  # Entire file loaded into memory
        # If file is 24 MB, this OOMs the pod

# ❌ No limit on bulk CSV upload
@router.post("/api/cobranza/debtors/csv")
async def upload_debtors_csv(
    file: UploadFile = File(...),  # No max_size
    ...
):
    file_bytes = await file.read()  # No streaming

# ❌ No limit on URL list in knowledge ingestion
class UrlIngestRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)  # Could be 1000 URLs
    # Each URL fetch is sequential + eats bandwidth
```

**Problemas:**
- File upload DoS attack (single 100MB file)
- CSV bulk upload DoS (1000 debtors × slow parsing)
- URL ingestion DoS (fetch 100 slow URLs sequentially)

**✅ Lo que está bien:**
- FastAPI default 25MB global limit
- Per-request size check implicit

**❌ Lo que está roto:**
- No endpoint-specific limits
- No streaming (everything loaded into RAM)
- CSV parser not optimized (no lazy evaluation)

---

## 5. DEPENDENCIAS Y FLUJOS

### 5.1 Integración de Signal Sources (Phase 24)

**Contexto:** Phase 24 introduce fuentes de señales colombianas (SECOP adjudicados, Google Maps, etc.)

**Puntos de integración propuestos:**

```
/api/prospect (existing)
  ├→ source_priority: str  (input: "serper", "google_maps", "secop_adjudicados")
  ├→ excluded_domains: list (from user preferences)
  └→ runtime_agents: list (from profile)
    
    ↓ (enqueues job)
    
worker.run_prospecting_job()
  ├→ Dispatch by source_priority
  │   ├─ "serper" → Serper API (existing)
  │   ├─ "secop_adjudicados" → SECOP API
  │   ├─ "google_maps" → Google Places API
  │   └─ [new] Chainsaw / Clarity (scrapers)
  ├→ Scraper stage (common for all)
  ├→ Analyzer stage (common for all)
  └→ Writer stage (common for all)

[New] API Integrations Required:
  ├─ SECOP API (licitaciones + adjudicados)
  ├─ Google Places API (PlacesNearby)
  ├─ Chainsaw / Clarity / Apollo APIs
  └─ Bright Data rotation (existing, scale up)
```

**Changes to backend:**

```python
# prospector.py — NEW stages
async def search_secop_adjudicados(sector: str, ciudad: str, max_results: int) -> list[dict]:
    """Query SECOP API for awarded contracts."""
    # API key: os.getenv("SECOP_API_KEY")
    # Returns: [{empresa, nit, monto, fecha, ...}]

async def search_google_places(industria: str, ciudad: str) -> list[dict]:
    """Query Google Places NearbySearch."""
    # API key: os.getenv("GOOGLE_PLACES_API_KEY")
    # Returns: [{company_name, address, phone, website_url, ...}]

# orchestrator.py — NEW agent roles (optional)
class AgentRole(str, Enum):
    RESEARCHER = "researcher"        # [existing] Web search
    PLANNER = "planner"              # [existing] Scraper
    REVIEWER = "reviewer"            # [existing] Analyzer
    WRITER = "writer"                # [existing] Email writer
    SIGNAL_ENRICHER = "signal_enricher"  # [NEW] SECOP/regulatory data
    COMPLIANCE_CHECKER = "compliance_checker"  # [NEW] Legal due diligence

# database.py — NEW indexes
await _safe_index(db.leads, [("source", 1), ("sector", 1)], sparse=True)
await _safe_index(db.signal_events, [("user_id", 1), ("event_type", 1)])
```

**Database Schema Changes:**

```python
# leads collection — NEW fields
{
    _id: ObjectId,
    user_id: str,
    run_id: str,
    source: "secop_adjudicados" | "google_maps" | "serper" | "bright_data",
    empresa: str,
    nit: str,  # NEW
    sector: str,
    ciudad: str,
    señales: [
        {
            signal_type: "adjudicacion_reciente" | "licitacion_abierta" | "ubicacion" | "tamaño_empresa",
            valor: any,
            fecha: datetime,
            confianza: float (0-1),
            fuente: str,
        }
    ],
    ...existing fields...
}

# NEW collection: signal_events (audit trail)
{
    _id: ObjectId,
    user_id: str,
    event_type: "secop_hit" | "gm_hit" | "chainsaw_hit",
    empresa: str,
    nit: str,
    señal: dict,
    timestamp: datetime,
    processed: bool,
}
```

**Rate Limiting for APIs:**

```python
# rate_limiting.py — NEW
SECOP_API_LIMIT = 1000  # per day
GOOGLE_PLACES_LIMIT = 100  # per day per location
BRIGHT_DATA_LIMIT = 500  # concurrent proxies

async def check_api_quota(user_id: str, api_name: str) -> bool:
    """Check user's remaining quota for the API."""
    # Could use Redis for per-user quotas
```

---

### 5.2 Puntos de Fricción Actuales

| Fricción | Ubicación | Impacto | Prioridad |
|----------|-----------|--------|-----------|
| 1h job timeout | worker.py:job_timeout=3600 | User sees spinner too long | 🔴 High |
| No timeout on external API calls | prospector.py, mailer.py | Hangs indefinitely | 🔴 High |
| Fire-and-forget WebSocket errors | whatsapp.py:_safe_task() | Lost messages | 🔴 High |
| Email send error not captured | leads.py send_lead_email | Half-sent state | 🔴 High |
| No rate limiting on /api/leads, /api/prospect | routers | Brute force possible | 🟠 Medium |
| In-memory rate limiter not persistent | rate_limiting.py | Lost on restart | 🟠 Medium |
| No input size limits | all routers | DoS possible | 🟠 Medium |
| Enum validation missing | prospect.py, knowledge.py | Invalid choices accepted | 🟡 Low |
| No error handler middleware | main.py | Generic 500 errors | 🟡 Low |

---

### 5.3 Cambios Esperados en Phase 24

**Endpoints nuevos:**
```python
POST   /api/prospect/signal-sources/config    # Enable/disable sources
GET    /api/prospect/signal-sources/usage     # Quota status
POST   /api/prospect/signals/audit            # View signal history
```

**Cambios a endpoints existentes:**
```python
# POST /api/prospect — ADD parameters
source_priority: str | list[str]   # Prioritize sources
weight_signals: bool               # Boost by signal strength
exclude_compliant_only: bool       # Filter by compliance risk

# GET /api/leads/{lead_id}/detail — NEW fields in response
signals: [{type, value, confidence, source, date}]
compliance_score: float (0-1)
```

**Cambios arquitectónicos:**
```
1. Expand prospector.py to handle new sources
2. New signal enrichment stage in pipeline
3. New database indexes on (source, sector, ciudad)
4. New rate limiting per-API
5. Signal audit trail collection
6. Compliance scoring in analyzer agent
```

---

## 6. RESUMEN: ✅ ⚠️ ❌

### 6.1 Estado General

```
┌──────────────────────────────────┐
│       Architecture Score: 7/10   │
└──────────────────────────────────┘

Fortalezas:
  ✅ Clean separation of routers/services/database
  ✅ Async-first (FastAPI + Motor + ARQ)
  ✅ Multi-agent orchestration (Hive)
  ✅ Webhook signature validation (Twilio)
  ✅ Tenant isolation (user_id checks)
  ✅ Rate limiting on auth endpoints
  ✅ Secure cookies (httpOnly, Secure, SameSite)

Debilidades principales:
  ❌ No timeouts on external API calls
  ❌ 1-hour job timeout (user hangs)
  ❌ Fire-and-forget errors (lost messages)
  ❌ No input size validation
  ❌ No error handler middleware
  ❌ Rate limiting not persistent (in-memory)
  ❌ No structured logging
```

### 6.2 Matriz: Lo que está bien / Necesita mejora / Roto

| Aspecto | ✅ Bien | ⚠️ Mejora | ❌ Roto |
|--------|---------|----------|--------|
| **Estructura** | Separation of concerns | Config management | - |
| **Error Handling** | HTTPException pattern | Middleware needed | Fire-and-forget |
| **Rate Limiting** | 5/15min on auth | Per-endpoint missing | Transient store |
| **Timeouts** | Job timeout (high) | External APIs needed | Most APIs |
| **Validation** | Pydantic models | Enum/size limits | - |
| **Auth** | JWT + cookies | - | - |
| **Logging** | Per-module setup | Structured logging | No alerting |
| **WebSocket** | Broadcast callback | Reconnect handling | Error recovery |
| **Queuing** | ARQ + dedup | Retry policy | No dead-letter |

---

### 6.3 Acciones para Phase 24

**CRÍTICAS (bloquean usuarios):**
1. ✏️ Add `asyncio.timeout()` wrapper on all external API calls (OpenAI, Mailgun, Vapi, Serper)
2. ✏️ Reduce job_timeout from 3600 to 600 seconds (10 min)
3. ✏️ Implement error handler middleware for 5xx errors
4. ✏️ Add dead-letter queue for webhook failures

**IMPORTANTES (improve reliability):**
5. ✏️ Migrate rate limiting to Redis (persistent)
6. ✏️ Add input size validation (file uploads, CSV, URL lists)
7. ✏️ Implement retry policy with exponential backoff
8. ✏️ Add structured logging (JSON + trace_id)

**MEJORAS (quality of life):**
9. ✏️ Add circuit breaker for API quotas
10. ✏️ Implement per-endpoint rate limits (non-auth)
11. ✏️ Add metrics/monitoring hooks
12. ✏️ Implement request/response caching for RAG

---

## Apéndice: Flujos de Integración Detallados

### A1. Flujo Completo: Prospecting Run

```
Usuario en UI
  ↓ (click "Buscar")
  ↓ POST /api/prospect {campaign, max_results: 20}
  ↓
main.py router
  ├─ get_current_user() → {"user_id": "abc", "role": "client"}
  ├─ Validate OPENAI_API_KEY
  ├─ Load active campaign
  ├─ Generate run_id = uuid.uuid4()
  ├─ create_run(user_id, campaign_id, run_id) → DB record
  ├─ state.arq_pool.enqueue_job("run_prospecting_job", ...)
  ├─ Return {status: "queued", run_id}
  ↓
[Async] ARQ Worker Process (worker.py)
  ├─ run_prospecting_job() starts
  ├─ HiveAdapter(send_to_user_callback=publish_event)
  ├─ adapter.start_run()
  │   ├─ Stage 1: Buscador (search by industry + city)
  │   │   ├─ prospector.search_companies() → Serper API
  │   │   ├─ Result: [{url, titulo, snippets}] (up to 20)
  │   │   └─ Broadcast: {type: "lead_found", ...}
  │   ├─ Stage 2: Scraper (parallel, max 3 concurrent)
  │   │   ├─ For each URL:
  │   │   │   ├─ prospector.scrape_url() (curl_cffi + BeautifulSoup)
  │   │   │   ├─ Extract text, metadata, tech stack
  │   │   │   └─ Broadcast: {type: "scrape_done", ...}
  │   ├─ Stage 3: Analista B2B (LLM analysis)
  │   │   ├─ OpenAI async call (personalidad.md template)
  │   │   ├─ Output: {decisor, puntaje, criterios, senales}
  │   │   └─ save_lead() to DB
  │   ├─ Stage 4: Redactor (email generation)
  │   │   ├─ LLM call (email subject + body)
  │   │   └─ Update lead.expediente_json.borradores
  │   └─ broadcast: {type: "run_complete", results_count: 20}
  ├─ update_run_status(run_id, "complete")
  └─ Return {status: "complete", run_id}

[Parallel] WebSocket Stream
  ├─ User connected: /ws/{user_id}
  ├─ Receive events via Redis pubsub:
  │   └─ ws:{user_id}:{run_id}
  ├─ Display in real-time:
  │   ├─ "Buscando empresas..."
  │   ├─ "Analizando empresa XYZ..."
  │   └─ "Redactando emails..."
  └─ On complete: show 20 leads in list

User clicks lead
  ↓ GET /api/leads/{lead_id}
  ↓
main.py: get_lead_detail()
  ├─ Validate ownership (lead.user_id == current_user.user_id)
  ├─ Return full lead + expediente_json
  ↓
User sees: company data + draft email

User clicks "Enviar Email"
  ↓ POST /api/leads/{lead_id}/send-email
  ↓
leads.py: send_lead_email()
  ├─ send_lead_outreach() → Mailgun API
  ├─ On success: update lead.estado = "enviado"
  ├─ Broadcast: {type: "email_sent", lead_id}
  └─ Return {status: "queued", message_id}

[Async] Mailgun Webhook (hours later)
  ├─ Receives: bounce, complaint, delivery, open, click
  └─ Updates: lead.email_events collection
```

---

### A2. Flujo: WhatsApp Webhook Handling

```
User sends message on WhatsApp
  ↓
Twilio Service
  ↓ (routes to configured webhook URL)
  ↓ POST /api/whatsapp/incoming
    {From: "whatsapp:+1234567890", To: "+1111111111", Body: "Hola"}
    {X-Twilio-Signature: "HMAC-SHA1(...)", ...}

whatsapp.py: whatsapp_incoming()
  ├─ Extract: from_phone, to_number, body, signature
  ├─ Validate signature
  │   └─ wa_handler.validate_twilio_signature(url, signature, form)
  │       └─ Compute: hmac.new(TWILIO_AUTH_TOKEN, url+params, sha1)
  │       └─ Compare with header signature
  │   └─ If invalid: log warning + return 403
  ├─ Get profile by from_phone
  │   └─ wa_handler.get_profile(from_phone)
  │   └─ Returns: {user_id, bot_mode, agente_config, ...}
  ├─ If unknown number: return 403
  ├─ Check for commands: /secop, /landa → set bot mode
  ├─ Determine bot mode (legacy, calendar, landa)
  ├─ asyncio.create_task(_safe_task(...))
  │   └─ Fire-and-forget: wa_handler.process_inbound(from_phone, body, ...)
  │       ├─ [Bot logic based on mode]
  │       ├─ Generate response
  │       └─ send_whatsapp_text(from_phone, response) → Twilio API
  │           └─ Calls: client.messages.create(from=..., to=..., body=...)
  └─ Return <Response/> (empty TwiML)

[Error if exception in process_inbound]
  ├─ _safe_task() catches Exception
  ├─ logger.error("[WA] ... crashed: %s")
  ├─ Exception swallowed
  └─ User sees no response (hung) or timeout
```

---

## Conclusión

El backend es **funcional pero frágil**. Tiene una buena estructura general pero sufre de:

1. **Falta de timeouts** en llamadas externas (crítico para producción)
2. **Error handling incompleto** (swallowed exceptions en WebSocket)
3. **Rate limiting débil** (solo auth, en memoria, no persistente)
4. **Validación incompleta** (sin enums, sin size limits)

Para **Phase 24**, enfocarse primero en **timeouts + error middleware** (high impact, low effort).
