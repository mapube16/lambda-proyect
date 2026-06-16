# retell-voice

## What This Is

Microservicio independiente de voice agent para cobranza, runtime de voz en Retell AI, cerebro en Anthropic (Claude con prompt caching) vía Custom LLM webhook, persistencia en la Mongo compartida de Landa. Cliente piloto: Softseguros — cartera vencida (overdue) y por vencer (upcoming). Multi-tenant día uno (`tenantId` en todo documento). Vive en `services/retell-voice/` dentro del repo `hive-pixel-office`, con su propio `.planning/` aislado del de la raíz.

## Core Value

Una llamada de cobranza automatizada que conversa con naturalidad, ejecuta acciones reales sobre la BD vía tools deterministas (no inventa datos), y deja trazabilidad completa por intento — para que Softseguros recupere cartera y registre promesas de pago sin operadores humanos en el primer contacto, y la arquitectura permita sumar tenants sin reescribir.

## Architecture Decisions (locked)

- **Híbrido Retell**: `Conversation Flow` para bordes deterministas (verificación de identidad al inicio, `transfer_to_human`, despedida). `Custom LLM` (webhook a este servicio) para el cuerpo de la negociación, manejo de objeciones, registro de promesas, agendamiento.
- **NO RAG en POC** (decisión explícita: simplicidad > sofisticación). El conocimiento que el agente necesita se inyecta directo en el system prompt desde la config del tenant en Mongo. Si crecen los docs por tenant, evaluamos Retell KB nativo (no construirlo nosotros).
- **Identidad del deudor**: ID externo de Softseguros, no `_id` Mongo nuevo — ambos servicios hablan el mismo idioma.
- **Idempotencia de tool writes**: por `(callAttemptId, toolCallId)`.
- **Anthropic prompt caching activo** desde día uno.

## Requirements

### Validated

(None yet — ship to validate)

### Active

**Setup & infra**
- [ ] Scaffolding del servicio con TS strict, Biome, Vitest configurados
- [ ] Dockerfile multi-stage
- [ ] Deploy a Railway con env vars
- [ ] CI GitHub Actions (lint + typecheck + test)
- [ ] Validación de env al boot (falla fuerte si falta variable)
- [ ] Healthchecks `/health` y `/ready`
- [ ] Graceful shutdown
- [ ] Rate limiting en bordes públicos
- [ ] Migrations versionadas para colecciones propias

**Modelo de datos (multi-tenant)**
- [ ] Colección `tenants` con config (cadencia, horarios, tono, prompt overrides, agentIds Retell por campaignType)
- [ ] Colección `call_attempts` (transcript, outcome, duración, promptVersion, tool calls)
- [ ] Colección `call_events` (eventos crudos del webhook de Retell con idempotencia)
- [ ] Colección `payment_promises` (monto, fecha, medio, callAttemptId)
- [ ] Colección `callbacks` (cuándo, motivo, tenantId)
- [ ] `tenantId` obligatorio en todo documento; queries forzadas con scoping
- [ ] Índices: `callId` único, `{tenantId, debtorExternalId}`, idempotencia por `(callAttemptId, toolCallId)`

**Custom LLM webhook (cuerpo de la negociación)**
- [ ] Endpoint webhook compatible con Retell Custom LLM (HTTP + WebSocket via Hono)
- [ ] Verificación de firma de webhook Retell
- [ ] System prompt construido al inicio de la llamada inyectando config del tenant
- [ ] Anthropic SDK con prompt caching habilitado
- [ ] Versionado del prompt en `call_attempts.promptVersion`
- [ ] Dos system prompts diferenciados por `campaignType`: `overdue` / `upcoming`
- [ ] Identificación obligatoria del agente al inicio del turno (compliance)
- [ ] Aviso de grabación en primer turno

**Tools deterministas (todas idempotentes en escritura)**
- [ ] `get_debt_info(debtor_id)` — saldo, vencimiento, último pago. Lectura en vivo, sin cache
- [ ] `register_payment_promise(debtor_id, monto, fecha, medio)` — idempotente por `(callAttemptId, toolCallId)`
- [ ] `schedule_callback(debtor_id, fecha_hora, motivo)` — idempotente
- [ ] `mark_dispute(debtor_id, motivo)` — idempotente
- [ ] `transfer_to_human(motivo)` — marca el call_attempt para escalamiento
- [ ] Validación Zod estricta en input/output de cada tool
- [ ] Latencia de tool < 3s (Retell webhook es síncrono)

**Outbound**
- [ ] HTTP `POST /calls` con `{tenantId, debtorExternalId, campaignType}` para disparar llamada
- [ ] Worker interno simple que lee `debtors` + config de tenant y agenda llamadas (cadencia mínima respetada)
- [ ] Calling window por tenant (timezone) — el worker no dispara fuera de horario

**Inbound**
- [ ] Webhook receiver de Retell para llamadas entrantes
- [ ] Resolución de `tenantId` por número entrante
- [ ] Lookup de deudor por `from_number` con fallback unknown

**Conversation Flow (Retell, no código)**
- [ ] Identidad verificación al inicio (Conversation Flow)
- [ ] Nodo de transferencia a humano (Conversation Flow)
- [ ] Nodo de despedida (Conversation Flow)
- [ ] Documentación de los flows en repo (export JSON o doc markdown)

**Robustez Nivel 1**
- [ ] Errores tipados
- [ ] Logging estructurado Pino con `tenantId`, `callId`, `debtorExternalId`, `requestId`
- [ ] Retries con backoff hacia Anthropic y Retell
- [ ] Idempotencia en webhook receiver (upsert por `callId` + `eventId`)

**Tests**
- [ ] Unit tests de cada tool (input válido, input malformado, datos faltantes)
- [ ] Tests del prompt builder por campaignType
- [ ] Tests de webhook handler (firma inválida, replay, payload malformado)
- [ ] Tests de scoping multi-tenant (query sin `tenantId` debe fallar)

**Hooks Nivel 2 (preparados, no implementados)**
- [ ] Outbox pattern: campo `outbox` en `call_events`/escrituras + colección `outbox` (sin consumer)
- [ ] OpenTelemetry: spans nombrados en operaciones críticas (sin exportador conectado)
- [ ] Feature flags: interfaz `getFlag(tenantId, key)` con implementación dummy
- [ ] `TranscriptRedactor` interface con no-op default (PII redaction)

### Out of Scope

- Scheduler de cadencia automática avanzado (worker simple sí; fase futura para sofisticado)
- UI de configuración de tenants (otro servicio futuro)
- Importación de cartera desde API Softseguros (otro microservicio paralelo)
- RAG / Retell KB en v1 — decisión explícita
- Dashboards, replay UI, load testing pesado
- Implementación efectiva de hooks Nivel 2 (solo interfaces y puntos de extensión)
- Secret manager externo (Railway env vars suficiente)
- Multi-modelo de voz: solo Retell en v1

## Context

- **Ecosistema Landa**: vive en `services/retell-voice/` dentro del repo `hive-pixel-office`. La raíz del repo tiene su propio `.planning/` que NO se debe tocar.
- **Mongo compartida**: lectura sobre `debtors` (poblada por otro microservicio que consume API Softseguros). Escrituras propias en colecciones del servicio.
- **Cliente piloto Softseguros (Colombia)**: dos campañas — cartera vencida y por vencer. Compliance LatAm (Habeas Data Ley 1581, SFC Circular 100-000003/2020, Ley 2300/2023 sobre frecuencia) — gate legal antes del piloto real.
- **Equipo**: hoy 1 dev (Maximiliano), entra otro dev en algún punto. Estructura legible para alguien nuevo.
- **Branch**: `feature/retell-voice-poc` desde `origin/master`.

## Constraints

- **Tech stack**: Node 20 + TypeScript strict + Hono (HTTP + WebSocket) + Mongoose + Zod + `@anthropic-ai/sdk` (prompt caching) + `retell-sdk` + Pino + Vitest + Biome — decidido y cerrado.
- **BD**: Mongo compartida con Landa. Lectura `debtors`; escrituras en colecciones propias.
- **Deploy**: Railway. Secretos vía env vars de Railway (sin secret manager).
- **CI**: GitHub Actions (lint + typecheck + test).
- **Multi-tenancy**: obligatoria día uno; `tenantId` en todo, scoping forzado en queries.
- **Robustez**: Producción Nivel 1 — el piloto Softseguros corre sin operador humano detrás. Hooks Nivel 2 preparados, no implementados.
- **Latencia tool**: < 3s (Retell Custom LLM webhook es síncrono).
- **Compliance**: identificación, aviso de grabación, calling window, cadencia mínima — go-live blockers.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Retell AI runtime de voz | Madurez para español LatAm; alternativa no robótica vs Vapi | — Pending |
| Híbrido Conversation Flow + Custom LLM | Bordes deterministas en UI Retell, cuerpo flexible con tools en webhook | — Pending |
| Sin RAG en POC | Simplicidad > sofisticación; system prompt + config tenant suficiente | — Pending |
| Tools deterministas con persistencia | Auditabilidad + accionabilidad real | — Pending |
| Multi-tenant día uno (`tenantId` en todo) | Evita migración dolorosa al entrar cliente #2 | — Pending |
| Identidad deudor = ID externo Softseguros | Ambos servicios hablan el mismo idioma | — Pending |
| Idempotencia tool writes por `(callAttemptId, toolCallId)` | Retell reintenta; sin esto duplicamos promesas | — Pending |
| Outbound vía HTTP + worker interno simple | Disparo puntual + cadencia básica para piloto | — Pending |
| `campaignType` discrimina prompt + agentId Retell | Overdue y upcoming requieren tono y toolset distintos | — Pending |
| Anthropic prompt caching activo desde día uno | Costos y latencia | — Pending |
| Hooks Nivel 2 preparados (outbox/OTel/flags/redactor) | Producción Nivel 1 suficiente; evitamos sobre-ingeniería | — Pending |
| Railway env vars como secret store | Suficiente para piloto | — Pending |

---
*Last updated: 2026-05-09 after architectural briefing update*
