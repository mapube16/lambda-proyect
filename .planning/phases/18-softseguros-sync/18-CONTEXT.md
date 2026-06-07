---
phase: 18-softseguros-sync
phase_name: SOFTSEGUROS Deudores Sync
from_user_discussion: true
created: "2026-05-11"
updated: "2026-05-12"
---

# Phase 18 Context: SOFTSEGUROS Deudores Sync

## User Vision

> "El cliente compró el agente de voz. Tiene sus usuarios en SOFTSEGUROS. Necesito que pueda cargar sus deudores directamente desde este servicio. SOFTSEGUROS tiene su propia documentación via API. Es importante que haya una sincronía en los datos — si algo se actualiza allá se debe actualizar acá. Hay dos tipos de personas: los que están próximos a vencer y los que ya han vencido — deben separarse en dos views."

## Architectural Decisions (locked)

1. **Persistencia: MongoDB únicamente** (extendiendo colección `debtors` existente de Phase 17). Decisión revisada y confirmada 2026-05-12 — Supabase descartado para v1: el modelo es document-oriented, Phase 17 ya está en Mongo, y agregar una segunda DB no aporta valor para queries actuales.
2. **Encriptación de credenciales**: Fernet (cryptography lib) — string ciphertext guardado en colección `softseguros_credentials` de Mongo.
3. **Multi-tenant**: filtro `user_id` en todas las queries (mismo patrón que `cobranza/debtor_crud.py`). No Supabase RLS.
4. **Consumer Phase 17**: el voice agent consume `debtors` directamente de Mongo (acceso compartido, misma colección). Pre-call check vía REST (`GET /api/debtors/{id}/verify-fresh`) para que la lógica de mutación esté centralizada.

## API Research Findings (2026-05-12, validado con smoke test real cuenta DPG)

Documentación oficial: `https://app.softseguros.com/docs/auth` (no Swagger público).
**Smoke test ejecutado con credenciales reales** (`cartera.dpg`, perfil "Cartera" id 1908) — hallazgos confirmados en vivo.

**Confirmado:**
- Auth: `POST /api-token-auth/` con body `{username, password}` → respuesta `{id, nombre_completo, perfil, perfil_name, token, nombre_marca, username}`
- Header subsiguiente: **`Authorization: Token <x>`** (Django REST Framework, NO `Bearer`)
- **El recurso correcto es `/api/poliza/`** (52,070 registros para DPG). Cada póliza ya trae embebidos los datos del cliente, aseguradora, ramo, vendedor, estado de cartera y fechas. **NO hay endpoint "deudores".**
- **`/api/cliente/` devuelve 401** para el perfil "Cartera" → NO usable, pero tampoco necesario (la póliza ya tiene `cliente_nombres`, `cliente_apellidos`, `cliente_numero_documento`, `cliente_celular`, `cliente_email`).
- **`/api/pagopoliza/` devuelve 504 Gateway Timeout** (roto del lado de SOFTSEGUROS) → inutilizable. NO usar.
- **`/api/cobro/`, `/api/recaudo/`, `/api/movimientos/` devuelven `[]`** (vacío para DPG).
- **`/api/campana-renovacion/`, `/api/pipeline-renovacion/` → 403** (sin permiso).
- **Paginación: `?page=N`, 10 registros por página, FIJO.** `page_size` ignorado. `ordering` ignorado. Ningún filtro server-side funciona (`estado_cartera=`, `search=`, etc. — todos ignorados, `count` siempre 52,070). Solo `page=N` tiene efecto. → Escaneo completo = ~5,207 requests.
- Orden de resultados: por `id` ascendente, fijo. Pólizas nuevas tienen `id` más alto (al final del listado).

**Campos relevantes de un objeto `poliza`** (los que importan para "deudor"):
```
id, numero_poliza, cliente (id), cliente_numero_documento, cliente_nombres, cliente_apellidos,
cliente_celular, cliente_email, aseguradora_nit, ramo_nombre, ramo_global_nombre, vendedores_nombre,
estado_poliza_nombre (Vigente|Devengada|Cancelada|No renovada|Cotizacion|Expedicion|...),
estado_poliza_codigo, estado_cartera (Pagada|Pendiente por pagar|Sin pagos Asignados|Comisionada),
fecha_inicio, fecha_fin, fecha_limite_pago (a menudo null), fecha_creacion,
prima, total, total_pagado (a menudo null), recaudado (bool), numero_de_cuotas (a menudo null/0),
forma_pago_texto (JSON string), periodicidad (Anual|...), comicionada (bool, sic), activo (bool),
enviar_sms_cartera_por_vencer, enviar_whatsapp_cartera_por_vencer
```

**Asunciones / no confirmado (v2 backlog):**
- Sin filtros server-side → no hay sync incremental nativo. Estrategia: full-scan en onboarding; deltas leyendo solo las últimas páginas (ids nuevos al final).
- Rate limits no documentados → asumir backoff con `Retry-After`. El `/api/poliza/` aguantó ~5 requests rápidos sin 429 en el smoke test.
- Token sin expiración documentada → asumir persistente, refrescar bajo demanda en 401.
- Webhooks existen como módulo pero sin eventos documentados → no se usan en v1.

**Modelo conceptual (REVISADO):**
Un "deudor" en nuestra plataforma = una **`poliza`** que cumple el criterio de cartera cobrable, mapeada a un documento en la colección `debtors`. Definición de cobrable (confirmada con el usuario):
- **`ya_vencidos`**: `estado_cartera == "Pendiente por pagar"` (deuda en mora). Clasificar por `fecha_fin` (o `fecha_limite_pago` si no es null) — si es pasado, está vencido.
- **`proximos_a_vencer`**: póliza vigente (`estado_poliza_nombre in ("Vigente","Devengada")`) con `fecha_fin` entre hoy y hoy+30, Y sin pago registrado (`estado_cartera in ("Sin pagos Asignados","Pendiente por pagar")` o `recaudado == false`).
- **`pagado`**: `estado_cartera in ("Pagada","Comisionada")` o `recaudado == true` → no se sincroniza como deudor activo (o si ya existía local, se marca `is_active=false, status='pagado'`).
- Pólizas `Cancelada`/`No renovada` con `Pendiente por pagar`: se sincronizan igual (el usuario quiere cobrarlas), pero el voice agent podría des-priorizarlas. Campo `estado_poliza_nombre` queda guardado para que la UI/agente decida.

**Identificador de idempotencia**: `softseguros_poliza_id` = el `id` numérico de la póliza (único globalmente). Unique index `(user_id, softseguros_poliza_id)`.

## Sync Strategy (Four Modes)

### Modo 1: Onboarding Sync (one-shot, MUY pesado)
- Disparado cuando el corredor conecta credenciales SOFTSEGUROS por primera vez
- Full-scan paginado de `/api/poliza/` — ~5,207 páginas (10/pág, 52K pólizas). Sin filtros server-side, hay que traer todo y filtrar localmente.
- Concurrencia controlada (`asyncio.Semaphore(5)`) + backoff. Estimado: **~25-40 minutos** para 52K pólizas.
- Solo persiste como `debtors` las pólizas que cumplen el criterio cobrable (ver "Modelo conceptual" arriba) — el resto se descarta. Probablemente termine con cientos-miles de deudores, no 52K.
- UI muestra progreso real vía polling (`debtors_scanned / total_count`) — "Importando 12,340 / 52,070 pólizas..."
- Onboarding corre en background; el corredor puede cerrar la pestaña y volver.

### Modo 2: Cron Diario (delta liviano)
- Una vez al día a las 3am UTC (default; configurable por env var)
- **NO re-escanea las 52K.** Estrategia delta: guarda `last_total_count` y `last_max_poliza_id` del sync anterior. Lee solo las **últimas N páginas** (donde están los `id` nuevos, porque el orden es ascendente por id) hasta cubrir las pólizas con `id > last_max_poliza_id`. Típicamente 1-5 páginas/día.
- Adicionalmente, una vez por semana (domingo), re-escanea las últimas ~200 páginas para captar cambios de `estado_cartera` en pólizas recientes (pagos registrados).
- Captura: pólizas nuevas cobrables (INSERT), pólizas que pasaron a `Pagada`/`Comisionada` (→ marcar local `is_active=false, status='pagado'`).
- Retry automático en la siguiente hora si SOFTSEGUROS está caído.

### Modo 3: Botón "Actualizar Ahora" (on-demand)
- Usuario hace clic en UI cuando sospecha desactualización
- Ejecuta el sync delta (mismo que el cron, modo `manual`) — NO el full-scan (eso solo en onboarding o si el usuario lo pide explícitamente con un botón "Re-escanear todo").
- **Rate-limit del lado nuestro**: máximo 1 sync manual cada 5 min por usuario (consultado contra `softseguros_sync_logs`)
- Feedback inmediato: "Última actualización hace 3 min" + spinner

### Modo 4: Pre-Call Freshness Check (puntual, por llamada)
- Disparado por el voice agent (Phase 17) justo ANTES de iniciar cada llamada
- 1 sola request: `GET /api/poliza/{softseguros_poliza_id}` a SOFTSEGUROS
- Decisión:
  - `estado_cartera in ("Pagada","Comisionada")` o `recaudado == true` → **CANCELAR llamada + marcar local como pagado** (`is_active=false, status='pagado'`)
  - 404 → CANCELAR + marcar local como eliminado (`is_active=false, status='eliminado'`)
  - `fecha_fin`, `total`, o `estado_poliza_nombre` cambió → actualizar local antes de llamar (re-clasificar)
  - Sin cambios → proceder con llamada
- **Fail-open**: si SOFTSEGUROS timeout/5xx, retornar `should_call=true` con warning → mejor llamar y errar por exceso que bloquear cobranza por una caída del proveedor.

## MongoDB Schema (extiende colección `debtors` existente)

```javascript
// Colección: debtors (existente, Phase 17)
// Campos NUEVOS para SOFTSEGUROS (todos opcionales, no rompen Phase 17):
{
  // ... campos existentes de Phase 17 (user_id, nombre, telefono, monto, vencimiento,
  //     estado, vapi_call_id, intentos, max_intentos, historial_llamadas, escalado,
  //     notas, ultimo_contacto_fecha, created_at, updated_at) ...

  // SOFTSEGUROS-specific (nuevos):
  "source": "softseguros" | "manual" | "csv",         // cobranza usa default "manual"; sync SOFTSEGUROS setea "softseguros"
  "softseguros_poliza_id": <int>,                     // el `id` de la póliza en SOFTSEGUROS (único globalmente) — clave de idempotencia
  "softseguros_cliente_id": <int>,                    // el campo `cliente` (id) de la póliza
  "numero_poliza": "<string>",                        // numero_poliza humano-legible
  "cliente_documento": "<string|null>",               // cliente_numero_documento
  "cliente_email": "<string|null>",
  "cliente_celular": "<string|null>",                 // = telefono pero preservado tal cual del API
  "aseguradora_nit": "<string|null>",
  "ramo_nombre": "<string|null>",
  "ramo_global_nombre": "<string|null>",
  "vendedores_nombre": "<string|null>",
  "estado_poliza_nombre": "<string>",                 // Vigente|Devengada|Cancelada|No renovada|...
  "estado_cartera": "<string>",                       // Pagada|Pendiente por pagar|Sin pagos Asignados|Comisionada
  "prima": <number|null>,
  "total": <number|null>,                             // = monto (el valor a cobrar)
  "total_pagado": <number|null>,
  "recaudado": <bool>,
  "fecha_inicio": "<ISO date|null>",
  "fecha_fin": "<ISO date|null>",                     // = vencimiento (fecha que determina vencido/por-vencer)
  "fecha_limite_pago": "<ISO date|null>",             // si no es null, tiene prioridad sobre fecha_fin para clasificar
  "periodicidad": "<string|null>",
  "comicionada": <bool>,                              // sic — flag de SOFTSEGUROS
  "status_softseguros": "proximos_a_vencer" | "ya_vencidos" | "pagado" | "eliminado",  // clasificación local
  "last_synced": "<ISO datetime>",
  "last_verified": "<ISO datetime>",                  // timestamp del último pre-call check
  "is_active": <bool>                                 // false si pagado/comisionado/eliminado
}

// Índice nuevo: (user_id, softseguros_poliza_id) UNIQUE SPARSE
//   - Garantiza idempotencia de sync; sparse para no afectar docs de Phase 17 sin source=softseguros

// Colección NUEVA: softseguros_credentials
{
  "_id": ObjectId,
  "user_id": "<string>",          // UNIQUE
  "username": "<string>",
  "password_encrypted": "<base64 Fernet>",
  "base_url": "https://app.softseguros.com",
  "last_token": "<string|null>",  // cache opcional para evitar re-auth en cada sync
  "last_token_at": "<ISO datetime|null>",
  "configured_at": "<ISO datetime>",
  "updated_at": "<ISO datetime>"
}

// Colección NUEVA: softseguros_sync_logs
{
  "_id": ObjectId,
  "user_id": "<string>",
  "mode": "onboarding" | "cron_daily" | "manual" | "pre_call_check",
  "started_at": "<ISO datetime>",
  "completed_at": "<ISO datetime|null>",
  "status": "success" | "partial" | "failed" | "in_progress",
  "error_message": "<string|null>",
  "polizas_scanned": <int>,                  // cuántas páginas/pólizas se leyeron
  "total_count": <int>,                      // count reportado por la API (52070)
  "max_poliza_id_seen": <int|null>,          // para deltas del próximo sync
  "debtors_created": <int>,
  "debtors_updated": <int>,
  "debtors_marked_paid": <int>,
  "debtors_marked_deleted": <int>,
  "total_requests": <int>,
  "duration_seconds": <float|null>
}

// Colección NUEVA: softseguros_sync_state  (1 doc por user — checkpoint para deltas)
{
  "_id": ObjectId,
  "user_id": "<string>",                     // UNIQUE
  "last_full_scan_at": "<ISO datetime|null>",
  "last_total_count": <int|null>,
  "last_max_poliza_id": <int|null>,
  "last_weekly_rescan_at": "<ISO datetime|null>",
  "updated_at": "<ISO datetime>"
}

// Índices nuevos:
// - softseguros_credentials: user_id (unique)
// - softseguros_sync_state: user_id (unique)
// - debtors: (user_id, softseguros_poliza_id) unique sparse
// - softseguros_sync_logs: (user_id, completed_at desc)
```

## Carga estimada SOFTSEGUROS API

Para 10 corredores activos:

| Evento | Requests/día/corredor | Total estimado |
|---|---|---|
| Onboarding | 100-200 (1 vez en la vida) | — |
| Cron diario | 100-200 | 1000-2000/día |
| Botón manual | ~10 (rate-limited) | hasta 1000/día |
| Pre-call check | 1 por llamada del voice agent | ~100-500/día |
| **Total** | | **~2500-3500/día** |

## Key Requirements (resumen, full text en REQUIREMENTS.md)

- **SOFTSEG-01**: Token auth contra SOFTSEGUROS (header `Token`, no Bearer)
- **SOFTSEG-02**: Credenciales encriptadas per-user con Fernet
- **SOFTSEG-03**: Fetch + enrich pagopoliza con cliente (paginación 10/pág)
- **SOFTSEG-04**: Concurrencia `Semaphore(5)` + resilience tenacity
- **SOFTSEG-05**: Clasificación `proximos_a_vencer` vs `ya_vencidos`
- **SOFTSEG-06**: 3 modos de sync (onboarding, cron diario, manual rate-limited)
- **SOFTSEG-07**: Pre-call freshness check con fail-open
- **SOFTSEG-08**: REST API filtrada + multi-tenant
- **SOFTSEG-09**: Soft-delete only (preservar histórico)
- **SOFTSEG-10**: Frontend onboarding + dashboard 2-tabs

## Architecture Context

**Integration Points:**
- **Phase 17 (voice-cobranza-agent)**: Lee `debtors` de Mongo (acceso directo compartido). Llama `GET /api/debtors/{id}/verify-fresh` antes de cada outbound call.
- **Phase 1 (auth)**: Todos los endpoints REST usan JWT del corredor.
- **Frontend**: 2 vistas — SoftSegurosSetupPage (onboarding) + DebtorsPage (2 tabs + manual sync button).

**Code Layout:**
```
backend/softseguros/
  __init__.py
  adapter.py           # SoftSegurosAdapter (httpx + tenacity)
  credentials.py       # Fernet encrypt/decrypt + Mongo CRUD
  classifier.py        # classify_pagopoliza pure function
  sync.py              # run_sync(mode), enrich logic, semáforo
  verify.py            # verify_pagopoliza_fresh function
  scheduler.py         # APScheduler setup
backend/routes/
  debtors.py           # Router REST (consume cobranza/debtor_crud + softseguros/*)
backend/tests/
  test_softseguros_*.py
frontend/src/pages/
  SoftSegurosSetupPage.tsx
  DebtorsPage.tsx
frontend/src/components/
  DebtorCard.tsx
  SyncStatusBadge.tsx
frontend/src/hooks/
  useDebtors.ts
  useSoftSegurosSetup.ts
```

**Reuse from Phase 17:**
- `cobranza/debtor_crud.py` para insert/update de documents en `debtors` — agregar funciones nuevas si hace falta (`upsert_debtor_by_softseguros_id`, `mark_debtor_paid_by_softseguros_id`)
- `database.py` `get_db()` para obtener Motor client

## Success Criteria (Observable Truths)

Ver REQUIREMENTS.md (SOFTSEG-01..10) y ROADMAP.md (10 success criteria de Phase 18).

## Out of Scope (Phase 18)

- Push sync hacia SOFTSEGUROS (marcar pagado desde nuestra UI) — v2
- Webhooks de SOFTSEGUROS — v2
- CRUD manual de deudores SOFTSEGUROS desde UI — v2 (los manuales viven solo en Phase 17 con `source='manual'`)
- Sync incremental con `modified_since` (cuando SOFTSEGUROS lo soporte) — v2
- Replicación a Supabase para reporting/BI — futuro

## Open Questions (no bloquean v1, abrir ticket con SOFTSEGUROS)

1. ¿Hay filtro `modified_since` o campo `fecha_modificacion`?
2. ¿Cuál es el rate limit real? ¿Header `Retry-After` en 429?
3. ¿`page_size` es ajustable o realmente fijo a 10?
4. ¿Existen webhooks para eventos de cobro/recaudo?
5. ¿Token expira o es persistente hasta revocación?

## Tech Stack

- **Language**: Python 3.11+ (consistente con backend)
- **Framework**: FastAPI
- **DB**: MongoDB (Motor async) — extendiendo colección `debtors` + 2 colecciones nuevas
- **Scheduler**: APScheduler (in-process)
- **HTTP**: `httpx.AsyncClient` con connection pooling
- **Retry**: `tenacity` (backoff exponencial)
- **Concurrency**: `asyncio.Semaphore(5)`
- **Encryption**: `cryptography.Fernet` para credenciales

## Timeline Estimate

**Phase 18: 5 sub-plans en 3 olas** — ver `18-PLAN.md` y archivos `18-NN-PLAN.md`.

---

*Context actualizado 2026-05-12 con decisión final Mongo-only y hallazgos de API research.*
