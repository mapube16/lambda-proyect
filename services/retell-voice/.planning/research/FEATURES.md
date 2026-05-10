# Feature Research

**Domain:** AI Voice Collections Agents (Cobranza / Debt Recovery)
**Researched:** 2026-05-09
**Confidence:** MEDIUM — Training data through Aug 2025. WebSearch/WebFetch blocked in this session. Findings based on documented Retell AI, Vapi, Bland AI, Replicant, Skit.ai, Gnani, Saarthi capabilities + public compliance literature. Flag: verify Retell-specific API surface against current docs before implementation.

---

## Framing

This research maps features across two axes:

1. **Category**: Table Stakes / Differentiator / Anti-Feature
2. **Type**: Regulatorio (compliance-driven, non-negotiable legally) vs Operacional (product/UX-driven)

Jurisdiction context: Colombia (Habeas Data — Ley 1581/2012, SFC circulares de cobranza), potential expansion to US (TCPA, FDCPA, CFPB Reg F), Mexico (LFPDPPP). Colombia is the primary jurisdiction for Softseguros pilot.

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features sin los cuales el producto no es competitivo ni operable para cobranza.

| Feature | Why Expected | Type | Complexity | Notes |
|---------|--------------|------|------------|-------|
| Outbound dialing — HTTP-triggered | Toda plataforma de cobranza dispara llamadas programáticamente | Operacional | LOW | POST /calls con debtorId + campaignType. Retell SDK provee `createCall`. |
| Outbound dialing — batch/campaign worker | Sin esto los operadores deben disparar una por una | Operacional | MEDIUM | Worker interno que lee `debtors` con cadencia y ventana horaria. Dependencia: campaña configurada por tenant. |
| Inbound IVR / call reception | Deudores devuelven llamadas; deben ser identificados | Operacional | MEDIUM | Retell webhook en llamada entrante; identificación por CLI (caller ID). Fallback: pedir número de documento. |
| Debtor identification en llamada | Sin identity verification, la conversación no tiene contexto de deuda | Operacional | LOW | Tool `get_debt_info` llamada al inicio; en inbound también. |
| Conversación en lenguaje natural (NLU/NLG) | Diferencial vs IVR DTMF legacy; el deudor espera poder responder libremente | Operacional | HIGH | Responsabilidad de Retell + Anthropic. El servicio diseña el prompt. |
| Detección de idioma / acento LatAm | Español colombiano difiere de castellano neutro; voces roboticas generan abandono | Operacional | MEDIUM | Retell soporta voces ElevenLabs y Azure en ES-CO. Verificar disponibilidad de voz ES-CO nativa. |
| Tool: consultar estado de deuda | El agente necesita datos reales para negociar | Operacional | LOW | `get_debt_info` — lectura de colección `debtors`. Ya definido en PROJECT.md. |
| Tool: registrar promesa de pago | Core outcome de una llamada de cobranza | Operacional | LOW | `register_payment_promise` — monto + fecha comprometida. |
| Tool: agendar callback | Deudor pide hablar en otro momento | Operacional | LOW | `schedule_callback` — ventana solicitada. |
| Tool: marcar disputa | Deudor rechaza o cuestiona la deuda — dato crítico para cumplimiento | Regulatorio + Operacional | LOW | `mark_dispute`. En FDCPA (US) y SFC (CO) es obligatorio registrar y escalar disputas. |
| Tool: transferir a humano | Casos complejos, disputas escaladas, deudores alterados | Operacional | LOW | `transfer_to_human` — marca call_attempt para SIP transfer o notificación. |
| Persistencia por call_attempt | Auditabilidad, seguimiento de gestión, base para reportes | Regulatorio + Operacional | LOW | call_attempts con transcript, duración, outcome, tool calls invocadas. |
| Transcripción de llamada | Auditoría y compliance requieren registro de lo que se dijo | Regulatorio | MEDIUM | Retell provee transcript post-call en webhook `call_ended`. Almacenar en call_attempt. |
| Grabación de llamada (audio) | En Colombia (SFC), empresas de cobranza deben conservar evidencia de la gestión | Regulatorio | MEDIUM | Retell puede entregar recording URL. Almacenar referencia, no el audio en Mongo (S3/GCS preferible). |
| Consentimiento de grabación (aviso al inicio) | Ley 1581 CO + buenas prácticas SFC: informar que la llamada se graba | Regulatorio | LOW | Primer turno del agente debe incluir aviso de grabación. Part of system prompt. |
| Múltiples campaignTypes con prompts distintos | Overdue vs upcoming requieren tono radicalmente distinto | Operacional | LOW | Discriminator en system prompt + toolset por campaignType. Ya en PROJECT.md. |
| Multi-tenancy (tenantId en todos los documentos) | Plataforma SaaS de cobranza debe aislar datos por cliente | Operacional | LOW | Obligatorio desde día uno. Ya en PROJECT.md. |
| Validación y sanitización de payloads | Cobranza maneja PII sensible; entradas malformadas pueden corromper registros | Regulatorio + Operacional | LOW | Zod en todos los bordes. Ya definido. |
| Logs estructurados con PII-awareness | Compliance requiere que PII no quede en logs planos | Regulatorio | LOW | Pino con campos tenantId, callId, debtorId — redactar números de documento y montos en nivel debug. |
| Horario de llamada respetado (calling window) | Colombia: Resolución SFC limita llamadas de cobranza a horas hábiles. TCPA en US: 8am-9pm hora local del deudor | Regulatorio | MEDIUM | Worker debe validar timezone del deudor y ventana permitida antes de disparar. |
| Cadencia mínima entre intentos | Harassment prevention — SFC CO y FDCPA US limitan frecuencia | Regulatorio | MEDIUM | Worker aplica cooldown configurable por tenant y campaignType. |
| Outcome tracking por call_attempt | Sin clasificar el resultado (promesa, disputa, no contest, no answer, etc.) no hay KPIs | Operacional | LOW | Enum `outcome` en call_attempt: `promise` / `dispute` / `callback_scheduled` / `transferred` / `no_answer` / `voicemail` / `hung_up` / `error`. |

### Differentiators (Competitive Advantage)

Features que distinguen a los mejores productos del mercado vs el mínimo operable.

| Feature | Value Proposition | Type | Complexity | Notes |
|---------|-------------------|------|------------|-------|
| Detección de voicemail vs persona viva (AMD) | Evita dejar mensajes de deuda en buzón (compliance risk) o gastar tokens en voicemail | Regulatorio + Operacional | MEDIUM | Answering Machine Detection. Retell puede reportar `call_analysis.user_sentiment` y metadata de inicio; AMD dedicado requiere lógica adicional o proveedor telefonía. Dejar mensaje de deuda en voicemail puede violar FDCPA (US) y SFC (CO). |
| Negociación de monto parcial | El agente propone descuentos o planes — aumenta tasa de recuperación | Operacional | HIGH | Requiere lógica en tool `register_payment_promise` para planes y aprobación de descuento (regla de negocio por tenant). |
| Detección de emoción / sentimiento del deudor | Escalar automáticamente cuando el deudor está alterado o en crisis | Operacional | HIGH | Requiere análisis de audio (no solo texto). Retell provee `call_analysis.user_sentiment` post-call; en tiempo real es más complejo. |
| Follow-up SMS/WhatsApp post-llamada | Refuerza la promesa de pago con recordatorio escrito | Operacional | MEDIUM | Out of scope de este servicio; integración con canal SMS/WA. Evento post-call dispara otro servicio. |
| Confirmación de promesa de pago por SMS | Deudor recibe comprobante inmediato — aumenta cumplimiento de promesas | Operacional | MEDIUM | Mismo patrón que follow-up SMS. |
| Dashboard de recuperación en tiempo real | Supervisores ven tasas de promesa, disputas, transferencias por campaña | Operacional | HIGH | Out of scope v1 — Softseguros consume Mongo directamente. |
| Retry inteligente con backoff por outcome | Si no contestó, reintenta en 4h; si prometió, no llama hasta fecha comprometida | Operacional | MEDIUM | Lógica de cadencia en worker. Diferencia entre "no answer" y "promise made". |
| Grabación diferida + transcripción con redaction de PII | Cumplimiento de Habeas Data sin exponer PII en logs/transcripts | Regulatorio | HIGH | Redaction pipeline sobre transcript antes de persistir. Hook Nivel 2 en PROJECT.md. |
| Scripts A/B por campaignType | Optimizar conversión probando variaciones de prompt | Operacional | HIGH | Requiere instrumentación de outcomes por variante. Post-v1. |
| Voz clonada del brand del cliente | Deudores reconocen la voz de la empresa — menor tasa de cuelgue | Operacional | HIGH | ElevenLabs voice cloning + Retell. Post-v1. |
| Detección de idioma automática | LatAm tiene deudores que mezclan idiomas (ES/Wayuunaiki en CO, ES/indigenas) | Operacional | HIGH | Niche para Softseguros v1; relevante para expansión. |
| Integración con core bancario / CRM existente | Cobranza real necesita actualizar el sistema de origen, no solo Mongo interno | Operacional | HIGH | Webhook post-call hacia sistema Softseguros. Posible extensión de tools. |
| Payment link en llamada | Agente envía link de pago por SMS durante la llamada y el deudor paga antes de colgar | Operacional | HIGH | Requiere integración PSP (Wompi, PayU en CO). Post-v1. |

### Anti-Features (Deliberately NOT Building in v1)

Features que parecen buenas pero que en cobranza crean problemas de compliance, complejidad o mala UX.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Mensajes de deuda en buzón de voz (voicemail drop) | Automatizar contacto aunque no conteste | En Colombia y bajo FDCPA (US), dejar mensaje con monto de deuda en buzón puede violar privacidad de terceros que accedan al buzón. CFPB Reg F (US) permite "ringless voicemail" solo con opt-in específico. | Detectar voicemail vía AMD, no dejar mensaje de deuda; solo dejar mensaje genérico de "llamar a [empresa]" si tenant lo habilita explícitamente con asesoría legal. |
| Guardar audio de grabación en Mongo (BLOB) | Tener todo en un solo store | Mongo no es apto para audio binario a escala; infla BD, complica retención/borrado requerido por Habeas Data | Almacenar solo la URL de grabación (Retell hosting o S3). Audio en object storage con TTL. |
| PII en campos de log (número de documento, monto exacto) | Facilita debugging | Viola Habeas Data CO y GDPR si se expande. Logs van a sistemas de terceros (Railway, Datadog). | Campos de log: tenantId, callId, debtorId (UUID interno). Monto y documento solo en BD encriptada. |
| Negociación de deuda sin aprobación de regla de negocio | Agente que ofrece descuentos libremente | Riesgo legal y financiero; un agente puede hacer ofertas que la empresa no autorizó | Tool `register_payment_promise` solo acepta montos dentro de rangos definidos por tenant. Descuentos requieren rule engine configurable. |
| Llamadas fuera de horario hábil | Maximizar contactos | Ilegal bajo regulación SFC Colombia y análogos LatAm; TCPA en US expone a multas de $500-$1500 por llamada | Worker con calling window por timezone. |
| Identificación del deudor solo por caller ID | Simplicidad | Caller ID spoofable; riesgo de dar info de deuda a tercero | Verificar identidad con dato adicional (ej. últimos 4 dígitos documento). |
| Agente que nunca transfiere a humano | Reducir costo operador | Deudores en crisis, disputas legales, amenazas — el agente debe poder escalar. Regulación SFC exige acceso a humano | Tool `transfer_to_human` obligatorio con threshold claro en prompt. |
| Almacenar transcripts sin encriptación | Simplicidad | Transcripts contienen PII (nombres, montos, situación financiera) — Habeas Data CO requiere protección | Encriptación at rest. En v1: hook preparado. En v2: implementar. |
| Multi-idioma automático sin validación legal | Escalar a nuevos mercados rápido | Cada idioma/jurisdicción tiene compliance distinto. Un agente español-correcto puede ser incorrecto-legal en otro país | Jurisdicción y idioma como configuración explícita por tenant, no inferida. |

---

## Feature Dependencies

```
[Outbound worker]
    └──requires──> [calling_window validation] (regulatorio)
    └──requires──> [cadencia/cooldown] (regulatorio)
    └──requires──> [get_debt_info tool] (identidad + contexto)

[Inbound IVR]
    └──requires──> [debtor identification] (CLI + fallback)
    └──requires──> [get_debt_info tool]

[get_debt_info tool]
    └──requires──> [debtors collection populated by otro microservicio]

[register_payment_promise]
    └──requires──> [get_debt_info] (necesita contexto de deuda primero)
    └──enhances──> [call_attempt outcome = "promise"]

[mark_dispute]
    └──requires──> [get_debt_info]
    └──enhances──> [call_attempt outcome = "dispute"]
    └──triggers (future)──> [human escalation workflow]

[transfer_to_human]
    └──requires──> [SIP transfer endpoint o notificación a supervisor]
    └──enhances──> [call_attempt outcome = "transferred"]

[call_attempt persistencia]
    └──requires──> [Retell webhook call_ended] (para transcript + duración)
    └──requires──> [tenantId en todos los documentos]

[Grabación / recording URL]
    └──requires──> [call_attempt] (FK para almacenar referencia)
    └──requires──> [consentimiento en primer turno del agente]

[AMD / voicemail detection]
    └──enhances──> [outbound worker] (skip voicemail, no gastar tokens)
    └──conflicts──> [voicemail drop] (anti-feature)

[Retry inteligente]
    └──requires──> [call_attempt outcome] (para saber cuándo y cómo reintentar)
    └──requires──> [cadencia/cooldown]

[Payment link en llamada]
    └──requires──> [register_payment_promise] (debe sincronizarse)
    └──requires──> [integración PSP] — out of scope v1
```

### Dependency Notes

- `get_debt_info` es la puerta de entrada a toda conversación: debe resolverse antes de negociar monto, registrar promesa o marcar disputa.
- `call_attempt` solo puede cerrarse con transcript completo cuando llega el webhook `call_ended` de Retell — los tools intermedios escriben en el mismo documento como array de `tool_calls`.
- La calling window validation debe ejecutarse en el worker antes de hacer `createCall`, no dentro del agente — el agente no debe tomar decisiones de "si llamar o no".
- `mark_dispute` y `transfer_to_human` pueden coexistir en el mismo call (marcar disputa Y transferir), por eso son tools independientes.

---

## MVP Definition

### Launch With (v1) — Piloto Softseguros

- [x] Outbound HTTP-triggered (`POST /calls`) — core del servicio
- [x] Outbound worker con calling window y cadencia mínima — compliance básico
- [x] Inbound reception con identificación por CLI + fallback — deudores devuelven llamadas
- [x] Tool `get_debt_info` — sin esto el agente no puede negociar
- [x] Tool `register_payment_promise` — el KPI principal del piloto
- [x] Tool `schedule_callback` — reducir abandoned rate
- [x] Tool `mark_dispute` — regulatorio, no opcional
- [x] Tool `transfer_to_human` — regulatorio + UX, no opcional
- [x] Persistencia `call_attempt` completa (transcript, outcome, tool_calls, duración)
- [x] Aviso de grabación en primer turno (consentimiento) — regulatorio CO
- [x] Dos campaignTypes (`overdue` / `upcoming`) con prompts distintos
- [x] Multi-tenancy (`tenantId` en todo) — no negociable
- [x] Logs con tenantId/callId/debtorId, sin PII en campos de log
- [x] Zod validation en todos los bordes

### Add After Validation (v1.x)

- [ ] AMD (Answering Machine Detection) — reducir desperdicio en buzones
- [ ] Retry inteligente por outcome — actualmente worker es naive
- [ ] Recording URL almacenada en call_attempt — Retell ya la expone
- [ ] Grabación referenciada + TTL en object storage — compliance Habeas Data
- [ ] Follow-up SMS post-llamada — integración con canal SMS de Landa

### Future Consideration (v2+)

- [ ] Negociación de monto parcial / planes de pago — requiere rule engine por tenant
- [ ] Detección de sentimiento en tiempo real — requiere audio analysis
- [ ] Payment link durante llamada — requiere integración PSP (Wompi/PayU)
- [ ] Dashboard de recuperación — Softseguros consume Mongo en v1
- [ ] Scripts A/B por campaignType — requiere instrumentación de variantes
- [ ] Transcripts con redaction de PII pipeline — hook preparado en v1
- [ ] Voz clonada del brand del cliente — ElevenLabs voice cloning

---

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Outbound HTTP trigger | HIGH | LOW | P1 |
| Outbound worker + calling window | HIGH | MEDIUM | P1 |
| Tool: get_debt_info | HIGH | LOW | P1 |
| Tool: register_payment_promise | HIGH | LOW | P1 |
| Tool: mark_dispute | HIGH (regulatorio) | LOW | P1 |
| Tool: transfer_to_human | HIGH (regulatorio) | LOW | P1 |
| Tool: schedule_callback | MEDIUM | LOW | P1 |
| Inbound reception | MEDIUM | MEDIUM | P1 |
| call_attempt persistencia | HIGH | LOW | P1 |
| Aviso de grabación (consentimiento) | HIGH (regulatorio) | LOW | P1 |
| Multi-tenancy | HIGH | LOW | P1 |
| AMD (voicemail detection) | MEDIUM | MEDIUM | P2 |
| Recording URL en call_attempt | MEDIUM (regulatorio) | LOW | P2 |
| Retry inteligente por outcome | MEDIUM | MEDIUM | P2 |
| Follow-up SMS post-llamada | MEDIUM | MEDIUM | P2 |
| Negociación parcial / planes de pago | HIGH | HIGH | P3 |
| Payment link en llamada | HIGH | HIGH | P3 |
| Redaction PII en transcripts | HIGH (regulatorio) | HIGH | P3 |
| Dashboard recuperación | MEDIUM | HIGH | P3 |

---

## Competitor Feature Analysis

| Feature | Replicant | Skit.ai / Gnani (LatAm focus) | Bland AI | Vapi | Our Approach (Retell + Anthropic) |
|---------|-----------|-------------------------------|----------|------|----------------------------------|
| Outbound dialing | Yes — batch campaigns | Yes — outbound collections | Yes — HTTP trigger | Yes — HTTP trigger | HTTP trigger + internal worker |
| AMD (voicemail detection) | Yes — built-in | Yes | Partial | Partial | P2 — Retell metadata + lógica custom |
| Natural conversation (LLM) | Yes — custom NLU | Yes — Indic + Spanish focus | Yes — GPT-based | Yes — multi-LLM | Anthropic via Retell function calling |
| Tool / action execution | Yes — integrations | Yes — CRM hooks | Yes — webhook tools | Yes — function calling | Deterministic tools en Node + Mongo |
| Payment promise registration | Yes | Yes | Via webhook | Via webhook | Tool nativa con persistencia directa |
| Dispute flagging | Yes (FDCPA focus) | Yes | Via webhook | Via webhook | Tool nativa con outcome tracking |
| Human handoff / transfer | Yes — SIP warm transfer | Yes | Yes | Yes — SIP | Tool transfer_to_human + SIP/notif |
| Callback scheduling | Yes | Yes | Via webhook | Via webhook | Tool nativa con colección callbacks |
| Call recording | Yes | Yes | Yes | Yes | Retell recording URL en call_attempt |
| Transcription | Yes — post-call | Yes | Yes — post-call | Yes — real-time | Retell transcript en webhook call_ended |
| Multi-language | Yes (EN focus) | Yes (ES/LatAm focus) | Yes | Yes | ES-CO como idioma primario |
| Multi-tenancy | Yes (enterprise) | Yes | Limited | Limited | Obligatorio desde día uno |
| TCPA/Compliance tooling | Yes — built-in | Partial | None built-in | None built-in | Calling window + cadencia en worker |
| Habeas Data CO | No | Partial | No | No | PII-aware logs + recording TTL (P2) |
| Sentiment analysis | Yes — post-call | Yes | No | Partial | Post-call via Retell call_analysis |
| Payment link in-call | No | Yes (some) | No | No | P3 — PSP integration |
| Reporting dashboard | Yes — full | Yes | No | Partial | Out of scope v1; Mongo directo |

**Nota de confianza:** Replicant y Skit.ai/Gnani datos son MEDIUM confidence (entrenamiento + documentación pública hasta Aug 2025). Bland AI y Vapi son HIGH confidence (ampliamente documentados). Retell es HIGH confidence para features core, MEDIUM para AMD y sentiment (en evolución activa a la fecha de cutoff).

---

## Compliance Reference

### Colombia (Softseguros — jurisdicción primaria)

| Regulación | Requisito | Feature implicado |
|------------|-----------|------------------|
| Ley 1581/2012 (Habeas Data) | Consentimiento para tratamiento de datos; derecho a supresión | Recording TTL, PII redaction, aviso al inicio de llamada |
| Circular SFC 100-000003/2020 | Gestión de cobranza prejudicial: límite de frecuencia, horario, trato digno | Calling window, cadencia mínima, transfer_to_human |
| Ley 1328/2009 (Protección consumidor financiero) | Información veraz, no intimidación | System prompt diseñado para tono no agresivo |
| Código Penal CO (art. 220) | Prohibición hostigamiento por deudas | Cadencia mínima + mark_dispute + transfer_to_human |

### US (Expansión futura)

| Regulación | Requisito | Feature implicado |
|------------|-----------|------------------|
| TCPA | 8am-9pm hora local, consentimiento para llamadas automatizadas | Calling window + opt-in tracking |
| FDCPA | No revelar deuda a terceros, validar deuda al solicitarla, registro de disputas | AMD (no dejar deuda en buzón), mark_dispute, identity verification |
| CFPB Reg F | Límite de 7 llamadas en 7 días por deuda, ventana de opt-out | Cadencia por deuda (no solo por deudor) |

---

## Feature Dependencies (Compliance Gating)

Estos features son regulatorios y bloquean el go-live del piloto si no están:

```
[Piloto Softseguros puede operar]
    └──requires──> [calling window SFC] — ilegal sin esto
    └──requires──> [cadencia mínima] — ilegal sin esto
    └──requires──> [aviso grabación en primer turno] — ilegal sin esto
    └──requires──> [mark_dispute tool] — obligatorio registrar
    └──requires──> [transfer_to_human tool] — obligatorio acceso a humano
    └──requires──> [identity verification] — no revelar deuda a tercero
```

---

## Sources

- Retell AI documentation (retellai.com/docs) — HIGH confidence, base del stack
- Vapi documentation (vapi.ai/docs) — HIGH confidence, referencia de features del mercado
- Bland AI documentation (bland.ai) — HIGH confidence
- Replicant (replicant.ai) — MEDIUM confidence, marketing + press coverage
- Skit.ai / Gnani.ai (skit.ai, gnani.ai) — MEDIUM confidence, LatAm collections focus
- Saarthi.ai — LOW confidence, limited public documentation
- Colombia Ley 1581/2012, Ley 1328/2009, Circular SFC 100-000003/2020 — HIGH confidence (legislación pública)
- US TCPA (47 CFR 64.1200), FDCPA (15 U.S.C. § 1692), CFPB Reg F (12 CFR 1006) — HIGH confidence

---

*Feature research for: AI Voice Collections Agent (retell-voice)*
*Researched: 2026-05-09*
*Confidence overall: MEDIUM (web access blocked; training knowledge Aug 2025)*
