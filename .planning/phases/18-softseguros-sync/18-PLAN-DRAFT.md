# Phase 18 Plan: SOFTSEGUROS Deudores Sync Microservice

## Phase Overview

**Phase**: 18 — SOFTSEGUROS Deudores Sync Microservice
**Goal**: Integrar deudores de SOFTSEGUROS al backend con sync en 3 modos (onboarding / cron diario / manual) + pre-call freshness check para el voice agent (Phase 17), respetando que la API solo expone `cliente` + `pagopoliza` con paginación fija de 10 y sin filtro incremental.
**Depends On**: Phase 1 (JWT auth), Phase 2 (tenant isolation)
**Consumed By**: Phase 17 (voice-cobranza-agent)

## Key Design Decisions (from research + discussion)

1. **No hay endpoint "deudores"**: se construye desde `pagopoliza` (deuda) + `cliente` (contacto). Un cliente con N cuotas pendientes = N filas locales.
2. **Auth header es `Token`, no `Bearer`** (Django REST Framework).
3. **Paginación fija 10/página** → sync paginado con `asyncio.Semaphore(5)` para concurrencia controlada.
4. **No polling continuo cada 15 min**: en su lugar, 3 modos discretos (onboarding, cron diario, manual).
5. **Pre-call check** antes de cada llamada del voice agent: 1 request a `/api/pagopoliza/{id}` → cancela llamada + marca local pagado si `comisionada=true`.
6. **Credenciales per-user** encriptadas en DB (no env globales).

## Requirements Addressed

- SOFTSEGUROS-01 → Plan 18-01 (auth adapter + credential storage)
- SOFTSEGUROS-02 → Plan 18-02 (fetch + enrich + paginación + concurrencia)
- SOFTSEGUROS-03 → Plan 18-02 (clasificación)
- SOFTSEGUROS-04 → Plan 18-02 (3 modos de sync)
- SOFTSEGUROS-05 → Plan 18-04 (pre-call freshness check)
- SOFTSEGUROS-06 → Plan 18-03 (REST endpoints)
- SOFTSEGUROS-07 → Plan 18-02 (resilience) + 18-04
- SOFTSEGUROS-08 → Plan 18-02 (validación)
- SOFTSEGUROS-09 → Plan 18-01 (credential storage)
- SOFTSEGUROS-10 → Plan 18-01 (architecture)

## Success Criteria (Acceptance)

Ver `18-CONTEXT.md` § Success Criteria (12 criterios observables).

---

## Wave 1: Foundation

### Plan 18-01: DB Schema + Credential Storage + Auth Adapter

**Objective**: Crear schema de DB (debtors, sync_logs, softseguros_credentials), implementar storage encriptado de credenciales per-user, y adapter HTTP a SOFTSEGUROS con auth Token + retry/backoff.

**Files**:
- `backend/models/debtor.py` (new) — Pydantic models: `Debtor`, `DebtorCreate`, `SyncLog`, `SoftSegurosCredentials`
- `backend/database.py` (modify) — Migraciones para 3 tablas nuevas + índices
- `backend/softseguros/adapter.py` (new) — `SoftSegurosAdapter` con auth, retry, paginación
- `backend/softseguros/credentials.py` (new) — Encrypt/decrypt con Fernet
- `backend/config.py` (modify) — `SOFTSEGUROS_ENCRYPTION_KEY`, `SOFTSEGUROS_BASE_URL`
- `.env.example` (modify) — Placeholder para `SOFTSEGUROS_ENCRYPTION_KEY`

**Tasks**:

1. **Schema migrations** (`database.py`):
   - Crear tablas `softseguros_credentials`, `debtors`, `sync_logs` con todos los campos del CONTEXT
   - Crear índices: `idx_debtors_user_status`, `idx_debtors_pagopoliza`, `idx_sync_logs_user_completed`

2. **Pydantic models** (`models/debtor.py`):
   - `Debtor`: refleja tabla completa con `cliente_*` y `valor_a_pagar/fecha_pago/comisionada/status`
   - `DebtorCreate`: subset para insertar
   - `SyncLog`: con `mode` ∈ {onboarding, cron_daily, manual, pre_call_check}
   - `SoftSegurosCredentials`: `username`, `password` (al recibir del usuario, NUNCA persistir plaintext)
   - `VerifyFreshResponse`: `should_call: bool`, `reason: Literal["already_paid","not_found","outdated","ok"]`, `fresh_data: Optional[dict]`

3. **Credential storage** (`softseguros/credentials.py`):
   - `encrypt_password(plain: str) -> str` usando Fernet con `SOFTSEGUROS_ENCRYPTION_KEY` (32 bytes base64)
   - `decrypt_password(cipher: str) -> str`
   - `save_credentials(user_id, username, password) -> None`
   - `get_credentials(user_id) -> Optional[(username, password)]`
   - Si `SOFTSEGUROS_ENCRYPTION_KEY` falta al boot → fail-fast con mensaje claro

4. **Adapter** (`softseguros/adapter.py`):
   ```python
   class SoftSegurosAdapter:
       def __init__(self, username: str, password: str, base_url: str = "https://app.softseguros.com"):
           self.base_url = base_url
           self.username = username
           self.password = password
           self.token: Optional[str] = None
           self.http = httpx.AsyncClient(timeout=30, limits=httpx.Limits(max_connections=10))

       async def authenticate(self) -> str:
           r = await self.http.post(f"{self.base_url}/api-token-auth/",
                                    json={"username": self.username, "password": self.password})
           r.raise_for_status()
           self.token = r.json()["token"]
           return self.token

       async def _headers(self) -> dict:
           if not self.token:
               await self.authenticate()
           return {"Authorization": f"Token {self.token}"}

       async def _get(self, path: str, params: dict = None) -> dict:
           # Wrapped con @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=10))
           # Si 401 → re-authenticate una vez y reintentar
           # Si 429 → respetar header Retry-After si existe
           ...

       async def list_pagopoliza(self, page: int = 1, only_pending: bool = True) -> dict:
           # GET /api/pagopoliza/?page=N&order_by=fecha_pago&sort_by=asc
           # Retorna {"count": int, "next": str|null, "results": [...]}
           ...

       async def get_pagopoliza(self, pagopoliza_id: str) -> dict:
           # GET /api/pagopoliza/{id}
           ...

       async def get_cliente(self, cliente_id: str) -> dict:
           # GET /api/cliente/{id}
           ...

       async def get_poliza(self, poliza_id: str) -> dict:
           # Para obtener cliente_id desde poliza
           ...

       async def close(self):
           await self.http.aclose()
   ```

**Verification**:
- [ ] Las 3 tablas existen en SQLite tras correr migraciones
- [ ] `encrypt_password / decrypt_password` round-trip correcto
- [ ] `adapter.authenticate()` retorna token real con credenciales válidas (test manual)
- [ ] `adapter._headers()` devuelve `Authorization: Token <x>` (NO Bearer)
- [ ] 401 dispara re-authenticate transparente
- [ ] 429 con `Retry-After: 30` espera 30s antes de reintentar
- [ ] Test unit con httpx mock cubre: auth ok, auth fail (401 inicial), retry en 5xx, respeto de Retry-After

**Done Criteria**:
- Adapter listo para ser consumido por sync engine (Plan 18-02)
- Credenciales jamás se loguean ni se serializan en respuestas API
- Schema deploy idempotente (re-run sin errores)

---

## Wave 2: Sync Engine + REST API (paralelo después de Wave 1)

### Plan 18-02: Sync Engine (3 modes + classification + resilience)

**Objective**: Implementar motor de sync que pagina `pagopoliza`, enriquece con `cliente`, clasifica por `fecha_pago`, hace upsert idempotente, y se expone en 3 modos (onboarding, cron diario, manual).

**Files**:
- `backend/softseguros/sync.py` (new) — Motor de sync
- `backend/softseguros/classifier.py` (new) — Lógica de clasificación pura (testable)
- `backend/softseguros/scheduler.py` (new) — APScheduler setup
- `backend/main.py` (modify) — Startup hook para scheduler
- `backend/database.py` (modify) — CRUD ops para debtors + sync_logs

**Tasks**:

1. **Classifier puro** (`classifier.py`):
   ```python
   def classify_pagopoliza(fecha_pago: date, comisionada: bool, today: date) -> str:
       if comisionada:
           return "pagado"
       if fecha_pago < today:
           return "ya_vencidos"
       if fecha_pago <= today + timedelta(days=30):
           return "proximos_a_vencer"
       return "futuro"  # no se sincroniza si > 30 días (out of scope para v1)
   ```

2. **Sync engine** (`sync.py`):
   ```python
   async def run_sync(user_id: str, mode: Literal["onboarding","cron_daily","manual"]) -> SyncLog:
       creds = get_credentials(user_id)
       if not creds:
           raise NoCredentialsError()

       adapter = SoftSegurosAdapter(*creds)
       sync_log = create_sync_log(user_id, mode)
       sem = asyncio.Semaphore(5)
       cliente_cache: dict[str, dict] = {}  # cache durante este sync
       poliza_cache: dict[str, dict] = {}

       try:
           # 1. Paginar pagopoliza pendientes
           page = 1
           all_pagos: list[dict] = []
           while True:
               async with sem:
                   resp = await adapter.list_pagopoliza(page=page)
               results = resp.get("results", [])
               all_pagos.extend(results)
               if not resp.get("next"):
                   break
               page += 1

           # 2. Filtrar comisionada=false + futuro fuera de ventana
           today = date.today()
           candidates = [
               p for p in all_pagos
               if not p["comisionada"]
               and date.fromisoformat(p["fecha_pago"]) <= today + timedelta(days=30)
           ]

           # 3. Enrich con cliente (concurrente, cacheado)
           async def enrich(pagopoliza: dict) -> dict:
               async with sem:
                   poliza_id = pagopoliza["poliza"]
                   if poliza_id not in poliza_cache:
                       poliza_cache[poliza_id] = await adapter.get_poliza(poliza_id)
                   cliente_id = poliza_cache[poliza_id]["cliente"]
                   if cliente_id not in cliente_cache:
                       cliente_cache[cliente_id] = await adapter.get_cliente(cliente_id)
                   return {"pagopoliza": pagopoliza, "cliente": cliente_cache[cliente_id], "cliente_id": cliente_id, "poliza_id": poliza_id}

           enriched = await asyncio.gather(*[enrich(p) for p in candidates])

           # 4. Upsert idempotente
           seen_pagopoliza_ids = set()
           for item in enriched:
               status = classify_pagopoliza(...)
               upsert_debtor(user_id, item, status)
               seen_pagopoliza_ids.add(item["pagopoliza"]["id"])
               sync_log.debtors_updated_or_created += 1

           # 5. Detectar deudores que ya no aparecen (probablemente pagados o eliminados)
           if mode in ("cron_daily", "manual"):
               existing_ids = get_active_debtor_pagopoliza_ids(user_id)
               missing = existing_ids - seen_pagopoliza_ids
               for pid in missing:
                   # Verificar con request puntual si fue pagado vs eliminado
                   try:
                       data = await adapter.get_pagopoliza(pid)
                       if data["comisionada"]:
                           mark_debtor_paid(user_id, pid)
                           sync_log.debtors_marked_paid += 1
                   except HTTPStatusError as e:
                       if e.response.status_code == 404:
                           mark_debtor_deleted(user_id, pid)
                           sync_log.debtors_marked_deleted += 1

           sync_log.status = "success"
       except Exception as e:
           sync_log.status = "failed"
           sync_log.error_message = str(e)
           raise
       finally:
           sync_log.completed_at = datetime.utcnow()
           save_sync_log(sync_log)
           await adapter.close()

       return sync_log
   ```

3. **Scheduler** (`scheduler.py`):
   ```python
   def setup_scheduler(app):
       scheduler = AsyncIOScheduler()
       # Cron diario a las 3am de cada usuario (simplificación v1: todos a 3am UTC)
       scheduler.add_job(
           run_daily_sync_for_all_users,
           CronTrigger(hour=3, minute=0),
           id="softseguros-cron-daily"
       )
       scheduler.start()
       app.state.softseguros_scheduler = scheduler

   async def run_daily_sync_for_all_users():
       users_with_creds = list_users_with_softseguros_creds()
       for user_id in users_with_creds:
           try:
               await run_sync(user_id, mode="cron_daily")
           except Exception as e:
               logger.error(f"Cron sync failed for {user_id}: {e}")
   ```

4. **Manual sync rate-limit**: en el endpoint (Plan 18-03), antes de invocar `run_sync(mode="manual")`, verificar último sync_log de modo `manual` del usuario; si < 5 min, retornar 429.

**Verification**:
- [ ] Classifier tests cubren: vencido, próximo, futuro, pagado
- [ ] Sync de 100 pagopoliza completa en < 30s (con SOFTSEGUROS responding en ~200ms)
- [ ] Semáforo limita correctamente a 5 requests concurrentes (test con mock que registra timestamps)
- [ ] Onboarding sync con 0 datos previos crea N filas correctas
- [ ] Cron sync detecta y marca como `pagado` cuotas con `comisionada=true`
- [ ] Re-run idempotente: dos syncs seguidos no duplican filas
- [ ] Si SOFTSEGUROS 5xx persistente: sync_log queda en `failed` con error_message, no crashea
- [ ] Multi-tenant: sync de user A no toca filas de user B

**Done Criteria**:
- Función `run_sync(user_id, mode)` consumible desde endpoints REST y desde scheduler
- Sync_logs registrados con counts correctos
- Scheduler corre en startup y dispara cron diario

---

### Plan 18-03: REST Endpoints (list / detail / sync-status / sync-now / configure)

**Objective**: Exponer los datos sincronizados y las acciones de sync via REST, con JWT auth y rate-limiting del sync manual.

**Files**:
- `backend/routes/debtors.py` (new) — Router completo
- `backend/main.py` (modify) — Registrar router

**Endpoints**:

```
POST /api/debtors/configure-softseguros    Body: {username, password}
  → Valida credenciales contra SOFTSEGUROS, encripta y guarda, dispara onboarding sync en background
  → Retorna {sync_id, status: "started"}

GET  /api/debtors/configure-softseguros
  → Retorna {configured: bool, configured_at: datetime|null}
  → NUNCA retorna el password

GET  /api/debtors?status=proximos_a_vencer|ya_vencidos&page=N
  → Lista debtors del user autenticado, filtrada, paginada (50/página local)
  → WHERE user_id = current_user.id AND is_active = 1 AND status = ?

GET  /api/debtors/{id}
  → Detalle. 404 si no es del user.

GET  /api/debtors/sync-status
  → Último sync_log + próximo cron + flag is_syncing_now

POST /api/debtors/sync-now
  → Rate-limit: si último manual < 5 min → 429
  → Dispara run_sync(mode="manual") en background, retorna {sync_id}

GET  /api/debtors/sync-logs?limit=20
  → Historial de syncs del user

GET  /api/debtors/health
  → 200 {status: "ok"} (no auth)
```

**Tasks**:

1. Implementar cada endpoint con `Depends(get_current_user)` (Phase 1)
2. Rate-limit del `sync-now` consulta `sync_logs` para detectar último manual
3. `configure-softseguros` ejecuta `adapter.authenticate()` para validar antes de guardar; si 401 → 400 al cliente
4. `list_debtors` usa el índice `idx_debtors_user_status`

**Verification**:
- [ ] Todos los endpoints requieren JWT excepto `/health`
- [ ] User A no puede leer/modificar nada de User B (test con dos tokens)
- [ ] `configure-softseguros` con credenciales inválidas → 400, no se guarda nada
- [ ] `sync-now` dos veces seguidas → segunda llamada 429
- [ ] `list_debtors?status=ya_vencidos` retorna solo `ya_vencidos AND is_active=1`
- [ ] OpenAPI docs generados (FastAPI auto) reflejan los schemas

**Done Criteria**:
- Endpoints consumibles por frontend y por Phase 17
- Validación + autorización + rate-limit funcionando

---

## Wave 3: Pre-Call Check + Frontend + Tests

### Plan 18-04: Pre-Call Freshness Check + Phase 17 Integration Hook

**Objective**: Implementar el endpoint que el voice agent llama antes de cada llamada para garantizar que el deudor sigue debiendo, marcando local como pagado si la deuda ya fue saldada.

**Files**:
- `backend/routes/debtors.py` (modify) — Agregar `GET /api/debtors/{id}/verify-fresh`
- `backend/softseguros/sync.py` (modify) — Función `verify_pagopoliza_fresh(user_id, debtor_id)`
- `services/retell-voice/` (modify) — Hook que llame al endpoint antes de iniciar la llamada (puede quedarse stub si Phase 17 aún no consume)

**Endpoint**:
```
GET /api/debtors/{id}/verify-fresh
  → Resuelve debtor.softseguros_pagopoliza_id
  → adapter.get_pagopoliza(softseguros_id)
  → Reglas:
      - comisionada=true OR fecha_recibo_comision != null:
          UPDATE debtors SET status='pagado', is_active=0, last_verified=NOW()
          return {should_call: false, reason: "already_paid", fresh_data: {...}}
      - HTTP 404:
          UPDATE debtors SET status='eliminado', is_active=0, last_verified=NOW()
          return {should_call: false, reason: "not_found"}
      - fecha_pago O valor_a_pagar cambió:
          UPDATE local con datos frescos, last_verified=NOW()
          return {should_call: true, reason: "outdated", fresh_data: {...}}
      - Sin cambios:
          UPDATE last_verified=NOW()
          return {should_call: true, reason: "ok"}
  → Cualquier 5xx / timeout de SOFTSEGUROS:
      return {should_call: true, reason: "ok", warning: "verification_unavailable"}
      (fail-open: mejor llamar y tener falso-positivo que bloquear todo el cobranza si SOFTSEGUROS está caído)
```

**Tasks**:

1. Función pura `verify_pagopoliza_fresh(user_id, debtor_id) -> VerifyFreshResponse` en `sync.py`
2. Registrar cada invocación como `sync_log` con `mode='pre_call_check'` (1 request HTTP, mode separado para analítica)
3. Endpoint REST que envuelve la función + JWT auth
4. Documentar en `services/retell-voice/.claude/` el contrato del endpoint para que Phase 17 lo consuma cuando se ejecute
5. Stub en Phase 17 si aplica: agregar TODO comment donde se haría la llamada (no implementar end-to-end aquí)

**Verification**:
- [ ] Mock de SOFTSEGUROS respondiendo `comisionada=true` → endpoint retorna `should_call=false, reason="already_paid"` Y la fila local queda `is_active=0, status='pagado'`
- [ ] Mock con 404 → `reason="not_found"`, fila local `status='eliminado'`
- [ ] Mock con `fecha_pago` distinta → `reason="outdated"`, fila local actualizada
- [ ] Mock con SOFTSEGUROS timeout → `should_call=true, warning="verification_unavailable"`, fila local sin cambios
- [ ] `last_verified` se actualiza en todos los casos exitosos
- [ ] User A no puede verify un debtor de User B (403)
- [ ] Latencia p95 < 500ms (1 request HTTP a SOFTSEGUROS + 1 UPDATE local)

**Done Criteria**:
- Endpoint listo para ser consumido por Phase 17
- Comportamiento fail-open documentado y testeado
- Cada invocación deja traza en `sync_logs` para análisis posterior

---

### Plan 18-05: Frontend (2 tabs + onboarding + manual sync) + E2E Tests

**Objective**: UI completa para el corredor: configurar credenciales SOFTSEGUROS, ver los 2 listados de deudores, botón "Actualizar ahora".

**Files**:
- `frontend/src/pages/DebtorsPage.tsx` (new)
- `frontend/src/pages/SoftSegurosSetupPage.tsx` (new) — Onboarding
- `frontend/src/components/DebtorCard.tsx` (new)
- `frontend/src/components/SyncStatusBadge.tsx` (new) — "Última sync hace 3 min" + spinner si is_syncing
- `frontend/src/hooks/useDebtors.ts` (new)
- `frontend/src/hooks/useSoftSegurosSetup.ts` (new)
- `backend/tests/test_softseguros_*.py` (new) — Unit + integration

**UI Flow**:

1. **Si no hay credenciales configuradas** (`GET /configure-softseguros` → `configured: false`):
   - Redirect a `/onboarding/softseguros`
   - Form con username + password + botón "Conectar"
   - Submit → `POST /configure-softseguros` → si OK, redirect a `/debtors` con loader "Importando deudores, esto puede tardar 1-2 min..."
   - Poll `GET /sync-status` cada 2s hasta `is_syncing_now=false`
2. **DebtorsPage**:
   - Header: `<SyncStatusBadge />` con timestamp + botón "Actualizar ahora" (deshabilitado si rate-limited)
   - Tabs: "Próximos a vencer (N)" | "Ya vencidos (N)"
   - Cada tab lista `<DebtorCard />` con: nombre completo, teléfono/email clicables, valor_a_pagar formateado, fecha_pago con días restantes
   - Empty state si lista vacía
3. **Error states**:
   - Sync falló: banner rojo "Última sync falló: <error_message>. [Reintentar]"
   - SOFTSEGUROS caído: aviso "Mostrando datos de hace Xh"

**Tests** (`backend/tests/`):

```
test_softseguros_credentials.py
  - encrypt/decrypt round-trip
  - save/get/delete per-user
  - encryption_key missing fails fast

test_softseguros_adapter.py
  - authenticate returns token
  - 401 triggers re-auth
  - 429 respects Retry-After
  - paginación list_pagopoliza

test_softseguros_classifier.py
  - vencido, próximo, futuro, pagado

test_softseguros_sync.py
  - run_sync onboarding crea filas
  - run_sync idempotente
  - run_sync detecta pagados y marca local
  - run_sync respeta semáforo de 5
  - run_sync con SOFTSEGUROS 5xx persistente → sync_log failed, no crash

test_debtors_endpoints.py
  - configure con creds inválidas → 400
  - list_debtors filtrado por status
  - tenant isolation (user A no ve de user B)
  - sync-now rate-limit
  - verify-fresh: already_paid, not_found, outdated, ok, fail-open

test_softseguros_e2e.py (con SOFTSEGUROS mock server)
  - onboarding completo: configure → sync → list devuelve los datos esperados
  - cron sync simulado: marca pagado lo que SOFTSEGUROS ahora devuelve comisionada=true
```

**Verification**:
- [ ] Frontend funciona: configure, list, switch tabs, manual sync
- [ ] Spinner aparece durante sync activa
- [ ] Rate-limit del manual sync se refleja en UI (botón disabled + tooltip)
- [ ] Todos los tests passing (target: > 80% coverage en `backend/softseguros/`)
- [ ] No secrets en logs ni en responses

**Done Criteria**:
- Corredor puede conectar SOFTSEGUROS y ver sus deudores en < 3 min desde primer login
- Phase 17 puede consumir `GET /api/debtors?status=ya_vencidos` para su cola de llamadas
- Pre-call check listo para ser invocado desde el voice agent

---

## Rollout Plan

1. **Wave 1**: 18-01 (foundation: schema + adapter + credentials)
2. **Wave 2** (paralelo después de Wave 1): 18-02 (sync engine) + 18-03 (REST endpoints)
3. **Wave 3** (paralelo después de Wave 2): 18-04 (pre-call check) + 18-05 (frontend + tests)

**Estimación**: ~45-55 horas Claude execution (5 sub-planes).

**Deploy**: integrado al backend existente, sin servicio separado.

## Post-Phase Handoff

Cuando Phase 18 esté completa:
- ✓ Corredor conecta SOFTSEGUROS y ve deudores clasificados
- ✓ Cron diario mantiene la BD fresca
- ✓ Pre-call check listo para Phase 17
- ✓ API documentada para integración con voice agent

**Próximo paso (Phase 17 ejecutándose)**: integrar `GET /api/debtors?status=ya_vencidos` como source de la cola de llamadas, y llamar `GET /api/debtors/{id}/verify-fresh` antes de iniciar cada llamada.

## Tickets Pendientes con SOFTSEGUROS (no bloquean v1)

1. Confirmar si existe filtro `modified_since` o `fecha_modificacion`
2. Documentación oficial de rate limits y header `Retry-After`
3. ¿`page_size` es ajustable o fijo a 10?
4. Webhooks para eventos de cobro/recaudo
5. ¿Token expira o es persistente?
