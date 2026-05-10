# retell-voice

## What This Is

Microservicio de voice agent para cobranza que usa Retell AI como runtime de voz, Anthropic como cerebro de la conversación y Mongo como persistencia. Expone tools deterministas (consultar deuda, registrar promesa de pago, agendar callback, marcar disputa, transferir a humano) que Retell invoca durante la llamada y que persisten cada interacción por `call_attempt`. Cliente piloto: Softseguros — cobranza de cartera vencida y gestión preventiva de cartera por vencer.

## Core Value

Una llamada de cobranza automatizada que conversa con naturalidad, ejecuta acciones reales sobre la BD (no solo habla), y deja trazabilidad completa por intento — para que Softseguros recupere cartera y registre promesas de pago sin operadores humanos en el primer contacto.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Outbound: disparar llamada de cobranza vía HTTP endpoint (`POST /calls`) dado un `debtorId` + `campaignType`
- [ ] Outbound: worker interno que lee `debtors` y agenda llamadas según ventana/cadencia mínima
- [ ] Inbound: recibir llamadas entrantes vía webhook de Retell e identificar al deudor por número
- [ ] Multi-tenancy: todo documento (`call_attempts`, `payment_promises`, `callbacks`, `disputes`, `transfers`) lleva `tenantId` y todas las queries lo filtran
- [ ] Dos flujos por `campaignType`: `overdue` (cartera vencida) y `upcoming` (cartera por vencer) con system prompts y toolsets distintos
- [ ] Tool `get_debt_info`: lee `debtors` y devuelve estado de deuda al agente
- [ ] Tool `register_payment_promise`: persiste promesa con monto + fecha comprometida
- [ ] Tool `schedule_callback`: agenda callback en ventana solicitada por el deudor
- [ ] Tool `mark_dispute`: registra disputa cuando el deudor cuestiona la deuda
- [ ] Tool `transfer_to_human`: marca el call_attempt para escalamiento
- [ ] Persistir `call_attempt` por llamada con transcript, duración, outcome, tool calls invocadas
- [ ] Webhook receiver de Retell: eventos de inicio/fin de llamada y function calls
- [ ] Validación de payloads con Zod en todos los bordes (HTTP, webhooks)
- [ ] Logs estructurados con Pino incluyendo `tenantId`, `callId`, `debtorId`
- [ ] Deploy en Railway con secretos por env vars
- [ ] Suite Vitest cubriendo tools deterministas y handlers de webhook
- [ ] Hooks Nivel 2 preparados (interfaces/no-ops): OpenTelemetry, retry/circuit breaker hacia Retell+Anthropic, harness E2E con sandbox Retell, encriptación/redaction de transcripciones

### Out of Scope

- Scheduler de cadencia de campañas (lo dueño otro servicio)
- UI de configuración / panel admin
- Importación de Softseguros a Mongo (otro microservicio puebla `debtors`)
- Implementación efectiva de los hooks Nivel 2 (solo dejamos puntos de extensión)
- Secret manager externo (Railway env vars suficiente para piloto)
- Multi-modelo de voz: solo Retell en v1
- Reportería/analytics para Softseguros (consumirán Mongo directo o lo construye otro servicio)

## Context

- **Ecosistema Landa**: este servicio vive dentro de `hive-pixel-office/services/retell-voice` y comparte Mongo con el resto de Landa. La colección `debtors` la pueblan otros microservicios.
- **Cliente piloto**: Softseguros opera dos campañas — cartera vencida (cobro de deuda morosa) y cartera por vencer (recordatorio preventivo). Cada una requiere tono y toolset distintos.
- **Decisión previa de stack**: usuario ya validó Node 20 + TS + Hono + Mongoose + Zod + Anthropic SDK + Retell SDK + Pino + Vitest + Biome. La research del workflow no debe cuestionarlo, sino versionarlo y profundizar en patrones (Retell function calling, manejo de webhooks, prompt engineering para cobranza).
- **Producción Nivel 1 con hooks Nivel 2**: implementar lo necesario para correr en piloto real (validación, persistencia, logs, tests core) y dejar interfaces para observabilidad/retry/E2E/PII pero NO construirlas ahora.
- **Multi-tenant día uno**: aunque el piloto es solo Softseguros, todo lleva `tenantId` para no rehacer migraciones cuando entre el segundo cliente.

## Constraints

- **Tech stack**: Node 20 + TypeScript + Hono + Mongoose + Zod + Anthropic SDK + Retell SDK + Pino + Vitest + Biome — decidido y cerrado.
- **BD**: Mongo compartida con Landa. Solo lectura sobre `debtors`; escrituras propias bajo colecciones del servicio (`call_attempts`, `payment_promises`, etc.).
- **Deploy**: Railway. Secretos vía env vars de Railway (sin secret manager).
- **Multi-tenancy**: obligatorio en el modelo de datos desde día uno.
- **Robustez**: Producción Nivel 1 — debe correr el piloto Softseguros sin operador humano detrás. Hooks Nivel 2 listos pero no implementados.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Retell AI como runtime de voz | Alternativa más madura/menos robótica vs Vapi para cobranza en español | — Pending |
| Tools deterministas que persisten en BD | Auditabilidad + accionabilidad real, no solo conversación | — Pending |
| Multi-tenant desde día uno (`tenantId` en todo) | Evita migración dolorosa cuando entre cliente #2 | — Pending |
| Outbound vía HTTP + worker interno | Otros servicios pueden disparar puntualmente; worker cubre cadencia básica del piloto | — Pending |
| `campaignType` como discriminator de flujo | Overdue y upcoming requieren prompt+tools distintos sin duplicar servicio | — Pending |
| Hooks Nivel 2 (obs/retry/E2E/PII) preparados pero no construidos | Producción Nivel 1 suficiente para piloto; evitamos sobre-ingeniería | — Pending |
| Railway env vars como secret store | Simple, suficiente para piloto; secret manager es scope futuro | — Pending |

---
*Last updated: 2026-05-09 after initialization*
