# Requirements: retell-voice

**Defined:** 2026-05-09
**Core Value:** Una llamada de cobranza automatizada que conversa con naturalidad, ejecuta acciones reales sobre la BD vía tools deterministas, y deja trazabilidad completa por intento — sin operadores humanos en el primer contacto y con multi-tenancy desde día uno.

## v1 Requirements

### Foundation

- [ ] **FOUND-01**: El servicio valida todas las env vars al boot con Zod y falla rápido si falta o es inválida
- [ ] **FOUND-02**: El servicio expone `/health` (liveness) y `/ready` (readiness con check de Mongo)
- [ ] **FOUND-03**: El servicio maneja graceful shutdown (drena conexiones HTTP/WS, cierra Mongo)
- [ ] **FOUND-04**: El servicio se construye con Dockerfile multi-stage y se despliega a Railway
- [ ] **FOUND-05**: GitHub Actions corre lint (Biome) + typecheck + test en cada PR
- [ ] **FOUND-06**: Logs estructurados Pino con bindings `tenantId`, `callId`, `debtorExternalId`, `requestId` — sin PII a nivel INFO
- [ ] **FOUND-07**: Migrations versionadas para colecciones propias (índices creados en deploy, no en runtime)
- [ ] **FOUND-08**: Rate limiting en endpoints HTTP públicos

### Data Model

- [ ] **DATA-01**: Colección `tenants` con config por tenant: `cadenceMaxPerWeek`, `callingWindow{tz, days, hours}`, `tone`, `promptOverrides`, `retellAgentIds{overdue, upcoming}`
- [ ] **DATA-02**: Colección `call_attempts` con `tenantId, debtorExternalId, callId, campaignType, outcome, transcript, durationSec, promptVersion, toolCalls[]`
- [ ] **DATA-03**: Colección `call_events` con eventos crudos del webhook + idempotencia por `eventId`
- [ ] **DATA-04**: Colección `payment_promises` con `tenantId, debtorExternalId, callAttemptId, monto, fecha, medio`
- [ ] **DATA-05**: Colección `callbacks` con `tenantId, debtorExternalId, callAttemptId, fechaHora, motivo`
- [ ] **DATA-06**: Todo documento lleva `tenantId` y todo índice lo tiene como primer campo
- [ ] **DATA-07**: Helper tipado `tenantQuery(tenantId)` obliga a incluir `tenantId` en cada query (compile-time check)
- [ ] **DATA-08**: Índice único `callId` en `call_attempts`; índice único compuesto `(callAttemptId, toolCallId)` en escrituras de tools; índice compound `(tenantId, debtorExternalId)` en `debtors` (lectura)

### Webhook Receiver

- [ ] **WEB-01**: Endpoint webhook Retell verifica firma HMAC con svix antes de procesar
- [ ] **WEB-02**: Payloads de webhook validados con Zod; payload inválido devuelve 4xx tipado
- [ ] **WEB-03**: Eventos `call_started`, `function_call`, `call_ended` despachados al handler correcto
- [ ] **WEB-04**: Reintentos de Retell son idempotentes — upsert por `callId` en `call_attempts` y por `eventId` en `call_events`
- [ ] **WEB-05**: Webhook responde en < 3s (Retell Custom LLM es síncrono); operaciones largas no bloquean

### Custom LLM Body

- [ ] **LLM-01**: Custom LLM webhook (HTTP + WebSocket Hono) compatible con protocolo Retell
- [ ] **LLM-02**: System prompt construido al inicio de la llamada inyectando config del tenant desde `tenants`
- [ ] **LLM-03**: Anthropic SDK invocado con prompt caching habilitado (cache breakpoints en system prompt)
- [ ] **LLM-04**: `promptVersion` persistido en `call_attempts` por cada llamada
- [ ] **LLM-05**: Dos prompts distintos por `campaignType`: `overdue` (cobranza dura) y `upcoming` (recordatorio preventivo)
- [ ] **LLM-06**: Apertura obligatoria con identificación del agente y aviso de grabación (compliance Ley 1581)
- [ ] **LLM-07**: Retries con backoff hacia Anthropic ante errores transitorios

### Tools (Deterministic Handlers)

- [ ] **TOOL-01**: `get_debt_info(debtor_id)` — lectura en vivo de `debtors` (sin cache); devuelve `{status:"data_unavailable"}` si campos críticos null
- [ ] **TOOL-02**: `register_payment_promise(debtor_id, monto, fecha, medio)` — idempotente por `(callAttemptId, toolCallId)`
- [ ] **TOOL-03**: `schedule_callback(debtor_id, fecha_hora, motivo)` — idempotente
- [ ] **TOOL-04**: `mark_dispute(debtor_id, motivo)` — idempotente; marca `call_attempt` y crea registro de disputa
- [ ] **TOOL-05**: `transfer_to_human(motivo)` — marca `call_attempt` para escalamiento
- [ ] **TOOL-06**: Validación Zod estricta en input y output de cada tool
- [ ] **TOOL-07**: Latencia p95 < 800ms en `get_debt_info` (evita dead air); presupuesto total tool < 3s

### Agent Configuration

- [ ] **AGENT-01**: Agent Config Registry mapea `(tenantId, campaignType)` → `{retellAgentId, systemPrompt, toolset}`
- [ ] **AGENT-02**: Dos agentes distintos en Retell por campaignType (no un solo agente con ambos toolsets)
- [ ] **AGENT-03**: Conversation Flow de Retell documentado en repo (export JSON o markdown) para: verificación de identidad, transferencia a humano, despedida
- [ ] **AGENT-04**: Handoff documentado entre Conversation Flow → Custom LLM webhook

### Outbound

- [ ] **OUT-01**: `POST /calls` con body validado `{tenantId, debtorExternalId, campaignType}` dispara llamada outbound vía retell-sdk
- [ ] **OUT-02**: Outbound dialer pasa metadata `{tenantId, debtorExternalId, campaignType}` a Retell para propagar al webhook
- [ ] **OUT-03**: AMD (Answering Machine Detection) habilitado en outbound — no dejar mensaje de deuda en buzón
- [ ] **OUT-04**: Worker interno simple (`setInterval`) lee `debtors` + config tenant y agenda llamadas
- [ ] **OUT-05**: Worker respeta `callingWindow` por tenant (timezone, días, horas)
- [ ] **OUT-06**: Worker respeta `cadenceMaxPerWeek` — no más de N intentos por deudor por semana
- [ ] **OUT-07**: Worker tiene cap de concurrencia por tenant
- [ ] **OUT-08**: Race condition prevenida: índice único parcial sobre intento activo por deudor

### Inbound

- [ ] **IN-01**: Webhook recibe llamadas entrantes y resuelve `tenantId` por número entrante
- [ ] **IN-02**: Lookup de deudor por `from_number` con fallback `unknown` (sin romper la llamada)

### Level 2 Hooks (interfaces, no-op default)

- [ ] **L2-01**: Outbox pattern — colección `outbox` y campo en escrituras críticas, sin consumer
- [ ] **L2-02**: OpenTelemetry — spans nombrados en operaciones críticas, sin exportador conectado
- [ ] **L2-03**: Feature flags — interfaz `getFlag(tenantId, key): boolean` con implementación dummy
- [ ] **L2-04**: `TranscriptRedactor` — interfaz con no-op default para PII redaction

### Tests

- [ ] **TEST-01**: Unit tests por cada tool: input válido, input malformado, datos faltantes (`data_unavailable`)
- [ ] **TEST-02**: Tests del prompt builder por `campaignType` (overdue / upcoming)
- [ ] **TEST-03**: Tests del webhook handler: firma inválida, replay de evento (idempotencia), payload malformado
- [ ] **TEST-04**: Tests de scoping multi-tenant — query sin `tenantId` debe fallar en compile-time
- [ ] **TEST-05**: Tests del worker: respeta calling window, respeta cadencia, no dispara fuera de horario

## v2 Requirements

### Reliability+

- **R2-01**: Implementación efectiva de OpenTelemetry exporter
- **R2-02**: Circuit breaker hacia Anthropic/Retell
- **R2-03**: Outbox consumer real (sync a sistemas downstream)
- **R2-04**: Suite E2E con Retell sandbox

### Compliance / PII

- **C2-01**: TranscriptRedactor con redaction real (números de tarjeta, identificaciones)
- **C2-02**: Encriptación de transcripciones at rest
- **C2-03**: TTL automático sobre transcripciones según política

### Voice Quality

- **V2-01**: AMD avanzado con detección de tono específico LatAm (Claro/Movistar/Tigo)
- **V2-02**: SMS de seguimiento post-llamada
- **V2-03**: Recording URL persistido en `call_attempts`

### Operational

- **O2-01**: Worker avanzado con BullMQ + Redis (vs `setInterval` actual)
- **O2-02**: Reintentos inteligentes por outcome
- **O2-03**: Métricas operacionales por tenant

## Out of Scope

| Feature | Reason |
|---------|--------|
| Scheduler de cadencia avanzado | Worker simple es suficiente para piloto; otro servicio o fase futura |
| UI de configuración de tenants | Otro servicio futuro; v1 configura vía Mongo directo |
| Importación de cartera Softseguros | Otro microservicio paralelo, fuera de alcance |
| RAG / Retell KB | Decisión explícita: simplicidad > sofisticación; system prompt + config tenant suficiente |
| Dashboards / replay UI | Fuera de alcance de este servicio |
| Load testing pesado | Pilot scale, no necesario en v1 |
| Implementación efectiva de hooks Nivel 2 | Solo interfaces y puntos de extensión |
| Secret manager externo | Railway env vars suficiente para piloto |
| Multi-modelo de voz | Solo Retell en v1 |
| Voicemail drop con info de deuda | Anti-feature regulatorio — nunca construir |
| Payment plan negotiation | v2+ |
| Real-time sentiment / link de pago en llamada | v2+ |

## Traceability

(Filled by roadmap creation)

| Requirement | Phase | Status |
|-------------|-------|--------|
| FOUND-01..08 | TBD | Pending |
| DATA-01..08 | TBD | Pending |
| WEB-01..05 | TBD | Pending |
| LLM-01..07 | TBD | Pending |
| TOOL-01..07 | TBD | Pending |
| AGENT-01..04 | TBD | Pending |
| OUT-01..08 | TBD | Pending |
| IN-01..02 | TBD | Pending |
| L2-01..04 | TBD | Pending |
| TEST-01..05 | TBD | Pending |

**Coverage:**
- v1 requirements: 58 total
- Mapped to phases: 0 (pending roadmap)
- Unmapped: 58 ⚠️ (will be 0 after roadmap)

---
*Requirements defined: 2026-05-09*
*Last updated: 2026-05-09 after initial definition*
