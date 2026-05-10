# Pitfalls Research

**Domain:** AI Voice Agent — Debt Collection (LatAm/Colombia, Español)
**Researched:** 2026-05-09
**Confidence:** MEDIUM — Training knowledge + prior Landa voice orchestrator experience. WebSearch unavailable. Compliance claims flagged per confidence level.

---

## Critical Pitfalls

### Pitfall 1: LLM Inventa Datos de Deuda (Hallucination en Function Return)

**What goes wrong:**
El LLM recibe un tool result con deuda parcial o ambigua (ej. `amount: null`, campo faltante) y en lugar de pedirle al deudor que espere o escalarlo, *infiere* un valor — le dice al deudor "su deuda es $1.200.000" cuando el dato real es $1.280.000 o no existe. En cobranza esto es un error legal: el agente habló de un monto incorrecto en nombre de la empresa.

**Why it happens:**
Los LLMs son completion engines. Si el contexto sugiere que la deuda debería tener un valor, completan el hueco. Prompts sin instrucciones explícitas sobre datos faltantes llevan al modelo a inventar.

**How to avoid:**
- En `get_debt_info`, validar con Zod antes de devolver. Si algún campo crítico (`amount`, `dueDate`, `contractId`) es `null` o `undefined`, devolver `{ status: "data_unavailable", reason: "..." }` en vez de el objeto parcial.
- En el system prompt: "Si `status` es `data_unavailable`, di exactamente: 'No tenemos disponible esa información en este momento, la verificaremos y te contactamos.' No inventes ningún monto."
- Nunca poner ejemplos de montos en el system prompt (el modelo los usa como ancla).
- Unit test: llamar la tool con un deudor que tiene `amount: null` y verificar que el tool output tiene `status: "data_unavailable"`.

**Warning signs:**
- Transcripciones con montos que no existen en `debtors`.
- Deudores que llaman a reclamar un monto distinto al que el agente dijo.
- Logs donde `get_debt_info` devolvió campos vacíos pero el agente siguió la conversación normalmente.

**Phase to address:** Phase de implementación de tools deterministas (tool layer). Antes de cualquier llamada real.

---

### Pitfall 2: Webhook Retell Procesado Múltiples Veces (No-Idempotencia)

**What goes wrong:**
Retell reintenta webhooks ante timeout o 5xx. Si el handler de `call_ended` no es idempotente, un mismo `call_id` genera dos `call_attempt` en Mongo, dos registros de `payment_promise`, o dos emails de seguimiento. En cobranza, una promesa doble puede generar un cobro doble.

**Why it happens:**
El handler escribe en Mongo sin verificar si el documento ya existe. El patrón `await CallAttempt.create({...})` falla silenciosamente o duplica si el webhook llega dos veces.

**How to avoid:**
- Usar `upsert` con `callId` como clave única: `CallAttempt.findOneAndUpdate({ callId }, { $setOnInsert: {...} }, { upsert: true, new: true })`.
- Índice único en `callId` en la colección `call_attempts`.
- Para `register_payment_promise`: índice único compuesto `{ callId, toolInvocationId }` — Retell incluye un ID por invocación de function call.
- Responder 200 inmediatamente (dentro de 3s) y procesar async en background para evitar timeouts que disparen reintentos.

**Warning signs:**
- Documentos duplicados en `call_attempts` con el mismo `callId`.
- MongoServerError 11000 (duplicate key) en logs — significa que el índice único está funcionando pero el código no lo maneja.
- Promesas de pago duplicadas para el mismo call.

**Phase to address:** Phase de webhook receiver — es la primera cosa a blindar antes de conectar tools.

---

### Pitfall 3: Silencio Largo por Tool Execution Lenta (Dead Air)

**What goes wrong:**
Retell pausa el audio del agente mientras espera el resultado de una function call. Si `get_debt_info` tarda >2s (Mongo lento, cold start, query sin índice), el deudor escucha silencio y cuelga o asume que la llamada falló. Churn técnico que parece churn conversacional.

**Why it happens:**
Mongo queries sin índice en colecciones grandes, o la query busca por `phoneNumber` sin índice. En Railway con plan básico, el cold start del servidor puede añadir 1-3s a la primera llamada.

**How to avoid:**
- Índice en `debtors.phoneNumber` + `debtors.tenantId` (compound index, query más frecuente).
- En Retell, configurar un `filler_phrase` (frase de relleno) en la tool: "Dame un momento para consultar tu información." — esto reproduce audio mientras la tool ejecuta.
- Target: tool response < 800ms en p95. Medir con Pino timings: `const t0 = Date.now(); ... logger.info({ duration: Date.now() - t0 }, 'get_debt_info')`.
- Keep-alive de Railway: endpoint `/health` con ping cada 5min desde Railway o UptimeRobot para evitar cold starts.

**Warning signs:**
- Logs con `get_debt_info duration > 1500ms`.
- Tasas de abandono altas en llamadas donde el agente ejecuta tools al inicio.
- Deudores que dicen "se cortó" cuando la llamada técnicamente siguió.

**Phase to address:** Phase de tool layer e infraestructura (indexing + Railway config). Validar con load test sintético antes del piloto.

---

### Pitfall 4: Loop Infinito de Conversación (Token Burn + Costos Descontrolados)

**What goes wrong:**
El deudor dice algo ambiguo repetidamente ("no puedo pagar"), el agente reformula y pregunta de nuevo, el deudor vuelve a decir lo mismo. La llamada no termina nunca — Retell cobra por minuto, Anthropic cobra por token. Una llamada de 30 minutos puede costar 10-20x más de lo previsto.

**Why it happens:**
El system prompt no define condición de salida explícita. El modelo optimiza por ser útil (seguir intentando) en lugar de por cerrar la llamada. Sin límite de turns implementado, el loop puede durar mientras Retell permita.

**How to avoid:**
- Definir en el system prompt: "Después de 3 intentos sin compromiso, ofrece agendar un callback o transferir a un asesor. Después de 5 turnos sin resolución, cierra la llamada con: [frase exacta] y llama a `end_call`."
- Implementar contador de turns en el agente (variable de estado en Retell o contado desde `call_analysis`).
- Límite duro en Retell: configurar `max_duration_seconds` en el agente (ej. 300s para cartera vencida, 180s para cartera por vencer).
- Alertas de costo: Anthropic y Retell tienen billing alerts — configurar desde día uno.

**Warning signs:**
- Llamadas con duración > 5 minutos sin `payment_promise` ni `schedule_callback` registrados.
- Facturas de Retell/Anthropic con spikes inesperados.
- Transcripciones con el mismo patrón repetido 4+ veces.

**Phase to address:** Phase de prompt engineering + configuración del agente Retell.

---

### Pitfall 5: PII en Transcripciones Almacenadas en Texto Plano

**What goes wrong:**
`call_attempt.transcript` guarda la conversación completa. El deudor puede haber dicho su número de cédula, dirección, salud, situación familiar durante la llamada. Mongo en texto plano + acceso de múltiples microservicios = exposición de datos sensibles sin control.

**Why it happens:**
La transcripción es el output natural del sistema. Guardarla completa parece lo correcto para auditoría. El problema es que nadie define qué está permitido guardar bajo Habeas Data (Ley 1581).

**How to avoid:**
- En el hook Nivel 2 de PII redaction: dejar la interfaz desde el inicio (`interface TranscriptRedactor { redact(transcript: string): string }`), aunque el no-op sea `return transcript` en v1.
- Documentar en el call_attempt model que `transcript` puede contener PII y requiere control de acceso.
- No exponer `transcript` en APIs hacia Softseguros sin autenticación fuerte.
- Para v1 piloto: en el system prompt instruir al agente a NO pedir cédula, dirección exacta, o información de salud — solo validar identidad por nombre + monto aproximado.

**Warning signs:**
- Transcripciones con patrones de cédula (10 dígitos seguidos) o números de tarjeta.
- Consultas directas a Mongo `call_attempts` sin filtro de campos.

**Phase to address:** Model design (Nivel 2 hook de redaction) + system prompt (restricción de qué preguntar).

---

### Pitfall 6: Multi-Tenancy Rota — Filtro `tenantId` Olvidado

**What goes wrong:**
Una query sin `{ tenantId }` en el filtro devuelve datos de todos los tenants. Softseguros ve datos de otro cliente. O peor: un call attempt de tenant A registra una promesa de pago en el deudor de tenant B.

**Why it happens:**
El `tenantId` se pasa correcto en el primer endpoint, pero en las tools internas (llamadas desde el webhook handler) el contexto se pierde — nadie pasa el `tenantId` al llamar `getDebtInfo(debtorId)` sin el tenant.

**How to avoid:**
- Todas las funciones de acceso a datos deben tener `tenantId` como primer parámetro, no como opcional: `getDebtInfo(tenantId: string, debtorId: string)`.
- En el webhook receiver de Retell: extraer `tenantId` del metadata de la llamada (enviado al crear la llamada outbound) y propagarlo a cada tool invocation.
- Test de tenant isolation: crear dos deudores en tenants distintos, hacer llamada en tenant A, verificar que las queries solo devuelven datos del tenant A.
- Lint rule o comentario de arquitectura: toda query a Mongoose debe incluir `tenantId` como campo de filtro.

**Warning signs:**
- Query en logs sin `tenantId` en el filter.
- Resultado de `get_debt_info` devuelve deudor de otro tenant (el deudor no reconoce la deuda).

**Phase to address:** Desde el primer modelo y primera query. No se puede añadir después sin auditar toda la codebase.

---

### Pitfall 7: Buzón de Voz / IVR del Operador Tratado como Deudor Real

**What goes wrong:**
La llamada outbound conecta con el buzón de voz de Claro/Movistar/Tigo y el agente empieza a hablar con el mensaje pregrabado del operador. Retell detecta "hola" y el agente procede como si fuera el deudor. Se registra un `call_attempt` con outcome positivo sin haber hablado con nadie. O el agente le "registra" una promesa de pago al buzón.

**Why it happens:**
Retell tiene detección de AMD (Answering Machine Detection) pero no está habilitada por defecto. En Colombia, los IVRs de operadores móviles suelen comenzar con voz humana que luego transfiere al buzón, lo que confunde al AMD.

**How to avoid:**
- Habilitar AMD en la configuración de la llamada outbound en Retell (`amd_enabled: true`).
- En el system prompt: "Si nadie responde tus preguntas de verificación de identidad en los primeros 10 segundos, cierra la llamada."
- En el webhook `call_ended`, revisar `call_analysis.user_sentiment` y `transcript` — si el transcript muestra solo el saludo del agente sin respuesta real, marcar el `call_attempt.outcome` como `voicemail`.
- Implementar lógica de detección simple: si `transcript` tiene < 3 turnos del deudor, outcome = `no_contact`.

**Warning signs:**
- `call_attempt` con outcome `contacted` pero transcript de 2 líneas.
- Promesas de pago registradas en llamadas de < 30 segundos.
- Logs de Retell mostrando AMD detection result `machine`.

**Phase to address:** Configuración del agente Retell outbound + post-processing de webhook `call_ended`.

---

### Pitfall 8: Tono Inadecuado para Cobranza (Agresivo o Condescendiente)

**What goes wrong:**
En cobranza de cartera vencida, el LLM sin instrucciones de tono específicas puede sonar intimidante ("Su deuda está en mora GRAVE"), o al contrario, tan empático que no genera urgencia ("No se preocupe, cuando pueda nos avisa"). Ambos extremos fallan: el primero crea quejas de acoso, el segundo no convierte.

**Why it happens:**
Anthropic entrenó Claude para ser helpful/harmless. En cobranza, "harmless" sin calibrar lleva a evitar presión legítima. Sin ejemplos de tono correcto, el modelo oscila entre extremos.

**How to avoid:**
- Definir el tono en el system prompt con ejemplos explícitos de cómo NO hablar y cómo SÍ hablar:
  - NO: "Si no paga tendremos que tomar acciones legales." (amenaza)
  - NO: "Entiendo perfectamente, no hay ningún problema." (sin urgencia)
  - SÍ: "Entiendo que no es el mejor momento. Podemos explorar un plan de pago que se ajuste a su situación. ¿Qué posibilidades tiene esta semana?"
- Para `overdue` vs `upcoming`: prompts completamente separados con tono distinto.
- Revisar 10 transcripciones reales antes del piloto completo y ajustar.

**Warning signs:**
- Quejas de deudores a Softseguros sobre el trato.
- Transcripciones con palabras como "consecuencias", "acciones legales", "reportado" (términos que pueden violar ley 1527/2012 de cobranza en Colombia).
- Tasa de conversión < 5% (señal de que el tono no genera compromiso).

**Phase to address:** Prompt engineering — campaña overdue vs upcoming. Requiere revisión por alguien con experiencia en cobranza.

---

### Pitfall 9: Compliance LatAm — Habeas Data (Ley 1581/2012) y Cobranza (Decreto 1746/2016)

**What goes wrong:**
Llamadas automatizadas a deudores en Colombia sin cumplir: (1) identificación clara del acreedor, (2) consentimiento de grabación, (3) horarios permitidos, (4) prohibición de llamar a terceros, (5) limitaciones en la frecuencia de contacto. Consecuencia: multas de la SIC (Superintendencia de Industria y Comercio) o denuncia penal.

**Specific Colombian rules (MEDIUM confidence — verificar con abogado):**
- **Horarios:** Decreto 1746/2016 y Ley 2300/2023 limitan gestión de cobro. Generalmente: lunes a viernes 7am-7pm, sábados 8am-3pm, prohibido domingos y festivos. Verificar texto actualizado.
- **Identificación:** El agente DEBE identificarse con nombre (ficticio está bien) y el nombre del acreedor en los primeros 30 segundos.
- **Grabación:** En Colombia no es estrictamente necesario el consentimiento previo para grabar (a diferencia de EEUU bipartito), pero la política de privacidad de Softseguros debe cubrir el tratamiento de estas grabaciones.
- **Frecuencia:** No más de 3 intentos de contacto por semana al mismo deudor (Ley 2300/2023 — verificar artículo exacto).
- **Terceros:** Jamás dejar mensajes con información de la deuda a terceros que atiendan el teléfono.

**How to avoid:**
- Ventana de llamadas: el worker de outbound y el endpoint `POST /calls` deben rechazar llamadas fuera de horario permitido (con timezone explícita `America/Bogota`).
- Script de apertura obligatorio en el system prompt: "Hola, habla [Nombre] de parte de [Softseguros/nombre acreedor]. ¿Estoy hablando con [Nombre Deudor]?"
- Si alguien distinto al deudor contesta: el agente dice "Gracias, ¿podría indicarle que lo llame al [número]?" y cierra. NO menciona la deuda.
- Límite de intentos por semana: campo `weeklyAttempts` en el modelo `debtor` o calculado desde `call_attempts`.
- Consultar abogado especializado antes del piloto completo con deudores reales.

**Warning signs:**
- Llamadas salientes registradas en domingo o antes de las 7am.
- Transcripciones donde el agente menciona la deuda sin confirmar identidad del deudor.
- Deudores diciendo "cómo saben que debo" (señal de que un tercero atendió y el agente reveló la deuda).

**Phase to address:** Worker de outbound + system prompt. Compliance gate antes del primer piloto real.

---

### Pitfall 10: Retell Function Call con Tool Invocada Incorrectamente (Wrong Arguments)

**What goes wrong:**
Retell envía al webhook un function call event con argumentos malformados o incompletos. El handler hace `const { amount, date } = body.arguments` sin validar — `amount` es `undefined`, se persiste una `PaymentPromise` con `amount: undefined`. Mongo acepta el documento, el registro queda corrupto.

**Why it happens:**
El LLM puede malinterpretar lo que dijo el deudor. "Puedo pagar como la mitad" → el modelo invoca `register_payment_promise` con `amount: "la mitad"` (string no numérico). Sin validación en el borde, el dato corrupto entra a BD.

**How to avoid:**
- Zod schema estricto en cada tool handler. Para `register_payment_promise`:
  ```typescript
  const schema = z.object({
    amount: z.number().positive(),
    promisedDate: z.string().datetime(),
    currency: z.enum(['COP']).default('COP'),
  })
  const parsed = schema.safeParse(body.arguments)
  if (!parsed.success) {
    return { success: false, error: 'Invalid arguments', details: parsed.error.flatten() }
  }
  ```
- Si la validación falla, devolver error al LLM con mensaje descriptivo — Retell se lo entrega al agente y el agente puede reformular la pregunta al deudor.
- Unit tests con argumentos malformados para cada tool.

**Warning signs:**
- `PaymentPromise` documents con `amount: null`, `amount: 0`, o `amount: NaN`.
- Errores de Mongoose validation en logs (si el schema de Mongoose los tiene — añadirlos como respaldo).
- Tool calls en transcript donde el deudor nunca dio un monto concreto pero el agente procedió.

**Phase to address:** Tool layer — es el núcleo. Cada tool debe ser una función pura, validada, testeable.

---

### Pitfall 11: Concurrencia de Llamadas — Race Condition en Debtor State

**What goes wrong:**
Dos llamadas salientes se disparan al mismo deudor casi simultáneamente (bug en el worker, o llamada manual + automática). Ambas pasan el check "¿tiene llamada activa?" antes de que la otra registre el attempt. Resultado: dos conversaciones activas con el mismo deudor, dos promesas de pago potencialmente contradictorias.

**Why it happens:**
El check y el insert no son atómicos. `if (await CallAttempt.findOne({ debtorId, status: 'active' })) return` tiene una ventana de race entre el find y el posterior create.

**How to avoid:**
- Usar `findOneAndUpdate` con `{ $set: { status: 'active' } }` solo si no existe un documento activo — atomic upsert con condición.
- O índice único parcial en Mongo: `{ debtorId: 1, tenantId: 1 }` con `partialFilterExpression: { status: 'active' }` — solo puede existir un attempt activo por deudor por tenant.
- El worker de outbound debe hacer rate limiting + check antes de despachar.

**Warning signs:**
- Dos `call_attempts` con `status: 'active'` para el mismo `debtorId`.
- Quejas de deudores que recibieron dos llamadas seguidas.

**Phase to address:** Worker de outbound + modelo de datos `call_attempts`.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Guardar `transcript` completo sin redaction | Simple, auditable | PII expuesto, riesgo Habeas Data, costo de remediación alto | Solo piloto con < 50 llamadas y acceso controlado. Hook Nivel 2 debe existir desde el inicio. |
| System prompt sin ejemplos de tono | Rápido de escribir | Tono impredecible, quejas de deudores, ajuste costoso post-piloto | Nunca — agregar ejemplos de tono toma 30 min y evita crisis |
| No configurar AMD en outbound | Una línea menos de config | Agente habla con buzones de voz, registra attempts falsos, datos sucios | Nunca para producción |
| Tool handlers sin Zod validation | Menos boilerplate | Datos corruptos en BD, difícil de detectar | Nunca — Zod es una dependencia ya en el stack |
| `max_duration_seconds` sin configurar | Configuración por defecto | Loop infinito = costos descontrolados en producción real | Solo en sandbox/pruebas |
| Filtros `tenantId` opcionales | Queries más simples | Data leak entre tenants, imposible de auditar retroactivamente | Nunca |
| Railway sin keep-alive | Menos infraestructura | Cold starts de 3-5s al inicio de cada llamada → dead air | Nunca para producción |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Retell webhooks | Procesar sync, responder después de 5s | Responder 200 en < 3s, procesar async con background job o `setImmediate` |
| Retell function calls | Asumir que `arguments` son válidos | Validar con Zod antes de cualquier acción |
| Retell outbound | Omitir `metadata` en la llamada | Incluir `{ tenantId, campaignType, debtorId }` en metadata — es el único mecanismo para pasar contexto al webhook handler |
| Anthropic (si se usa directo) | Prompts sin `max_tokens` | Siempre fijar `max_tokens` — respuestas largas aumentan latencia y costo |
| Mongo (shared DB) | Write en colección `debtors` | Solo lectura en `debtors`. Escrituras propias solo en colecciones del servicio |
| Mongo | Queries sin índices en prod | Crear índices explícitamente en el migration/seed script. Nunca confiar en Mongo para inferirlos |
| Railway | Asumir que el puerto es fijo | Usar `process.env.PORT` siempre — Railway lo asigna dinámicamente |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Query `debtors` por `phoneNumber` sin índice | `get_debt_info` > 2s, dead air | Índice compound `{ tenantId: 1, phoneNumber: 1 }` | Con > 1.000 deudores en la colección |
| Transcript almacenado como string plano en BSON | Queries lentas sobre transcripts | No hacer queries de texto libre sobre transcripts — usar campos estructurados | Con > 10.000 call_attempts |
| Worker outbound sin rate limiting | Decenas de llamadas simultáneas, costos explosivos | Concurrency limit (ej. máx 10 llamadas activas por tenant) | Inmediato si el worker no tiene límite |
| Cold start Railway (sin keep-alive) | Primera llamada del día tiene dead air en la tool | UptimeRobot o cron `/health` cada 5 min | 100% de probabilidad en plan básico Railway |
| Logging completo de payload Retell | Logs gigantes, difícil encontrar errores reales | Loguear solo campos relevantes (`callId`, `event`, `toolName`, durations) | Con > 100 llamadas/día los logs se vuelven inmanejables |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|------------|
| No verificar firma HMAC del webhook Retell | Cualquiera puede enviar requests falsos al endpoint de function calls, inyectar tool calls fraudulentas | Verificar `X-Retell-Signature` header en cada webhook request. Retell documenta el algoritmo de verificación. |
| PII en query params o logs | Exposición de datos de deudores en logs de Railway (que pueden tener múltiples usuarios) | Nunca loguear `phoneNumber`, nombre completo, o monto en nivel INFO. Solo en DEBUG, que en prod debe estar desactivado. |
| `tenantId` tomado del body sin validar | Un cliente malicioso puede enviar `tenantId` de otro tenant | `tenantId` debe venir del contexto de autenticación (API key + tenant mapping), nunca del body del request. |
| Mongo connection string en logs | Credenciales de BD expuestas | Asegurarse que Pino serializers no loguean `process.env` ni el connection string. Verificar en CI. |
| Retell metadata con datos sensibles | Metadata visible en dashboard de Retell | No incluir montos de deuda ni datos sensibles en el metadata de la llamada — solo IDs. |

---

## UX Pitfalls

(En este dominio, "UX" = experiencia del deudor durante la llamada)

| Pitfall | Debtor Impact | Better Approach |
|---------|---------------|-----------------|
| Agente no se identifica en los primeros 5s | Deudor cuelga (no sabe quién llama), es además obligatorio legalmente | Greeting hardcodeado: "Hola, habla [Nombre] de parte de [Acreedor]..." — primero que dice el agente, sin esperar tool |
| Agente hace pausa larga (dead air) antes del saludo | Deudor cuelga pensando que es spam | Greeting pregrabado o sin tool call al inicio — el agente habla inmediatamente, las tools se cargan en background |
| Agente no confirma identidad antes de mencionar la deuda | Tercero recibe información de deuda (ilegal) | Pregunta de verificación de identidad ANTES de cualquier mención de deuda |
| Agente pide datos que ya debería tener | Deudor molesto, experiencia de mal servicio | `get_debt_info` carga el contexto antes de la conversación; el agente NO pide información que ya está en el sistema |
| Agente no ofrece alternativas cuando deudor dice no puede pagar | Conversación sin salida, deudor cuelga | Árbol de opciones explícito en prompt: plan de pago parcial → callback → transferir a humano |
| Agente sigue insistiendo después de 3 rechazos | Experiencia de acoso, queja a Softseguros | Límite de intentos en prompt + escalada automática a `transfer_to_human` o cierre de llamada |

---

## "Looks Done But Isn't" Checklist

- [ ] **Webhook receiver:** ¿Está verificando la firma HMAC de Retell? — verificar en código que `X-Retell-Signature` se valida, no solo que el endpoint responde 200.
- [ ] **Tool `register_payment_promise`:** ¿Es idempotente? — llamar dos veces con los mismos argumentos debe producir exactamente un documento, no dos.
- [ ] **Multi-tenancy:** ¿Toda query a Mongoose incluye `tenantId` en el filtro? — grep `CallAttempt.find(` y verificar que ninguna es `.find({ debtorId })` sin `tenantId`.
- [ ] **Horarios de llamada:** ¿El worker rechaza llamadas fuera de ventana con timezone `America/Bogota`? — probar con timestamp de domingo 9am UTC (que es 4am Bogotá).
- [ ] **AMD:** ¿La llamada outbound tiene `amd_enabled: true` en el payload a Retell?
- [ ] **`max_duration_seconds`:** ¿Está configurado en el agente Retell? — verificar en dashboard de Retell o en el payload de creación del agente.
- [ ] **Índices Mongo:** ¿Existen en el script de inicialización? — `debtors.phoneNumber`, `call_attempts.callId` (unique), `call_attempts.{ debtorId, tenantId, status }` (partial unique).
- [ ] **Identificación del agente:** ¿El agente dice el nombre del acreedor en los primeros 10 segundos? — revisar transcripción de llamada de prueba.
- [ ] **Terceros:** ¿El agente cierra la llamada sin mencionar la deuda si el deudor dice "soy familiar"? — test case explícito.
- [ ] **Retell metadata:** ¿El `tenantId` se incluye en el metadata de la llamada outbound y se extrae en el webhook handler?

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Datos duplicados por webhook no idempotente | MEDIUM | Deduplication script en Mongo con `$group` por `callId`; añadir índice único; alertar a Softseguros si hay promesas duplicadas |
| PII en transcripciones en texto plano | HIGH | Implementar redaction retroactivo (regex de cédulas, teléfonos) + cifrado en reposo del campo `transcript`; revisar quién tiene acceso a Mongo |
| Llamadas fuera de horario enviadas | HIGH | Suspender worker inmediatamente; auditar `call_attempts` de últimas 24h; notificar a Softseguros; documentar para Habeas Data |
| Loop de costos descontrolados | MEDIUM | Deshabilitar campaña en Retell dashboard; auditar llamadas con duration > 10 min; ajustar `max_duration_seconds` y prompts |
| Race condition — deudor con 2 attempts activos | LOW | Script de cleanup que cierra el attempt más antiguo; agregar índice único parcial |
| Tenant data leak (query sin tenantId) | CRITICAL | Suspender acceso; auditar todas las queries ejecutadas; notificar según Ley 1581 (notificación a titulares es obligatoria); revisar logs de Railway |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Hallucination en tool return | Phase: Tool layer (models + handlers) | Unit test con datos faltantes devuelve `status: "data_unavailable"` |
| Webhook no-idempotente | Phase: Webhook receiver | Test de doble envío del mismo webhook produce un solo documento |
| Dead air por tool lenta | Phase: Tool layer + infra (índices + keep-alive) | P95 de `get_debt_info` < 800ms en staging |
| Loop infinito / costos | Phase: Prompt engineering + configuración Retell | `max_duration_seconds` verificado en config; test de conversación sin resolución termina en ≤ 5 turnos |
| PII en transcripciones | Phase: Model design + system prompt | Interfaz `TranscriptRedactor` existe; system prompt prohíbe pedir cédula/dirección |
| Multi-tenancy rota | Phase: Modelo de datos (día uno) | Test de tenant isolation pasa; grep de queries sin `tenantId` devuelve 0 resultados |
| Buzón de voz tratado como deudor | Phase: Configuración outbound Retell | AMD habilitado; test con número de buzón produce `outcome: voicemail` |
| Tono inadecuado | Phase: Prompt engineering | Revisión de 5 transcripciones de prueba por alguien con experiencia en cobranza antes del piloto |
| Compliance LatAm (horarios, identificación) | Phase: Worker outbound + system prompt + legal review | Llamada de prueba fuera de horario es rechazada; transcripción inicia con identificación del acreedor |
| Tool args inválidos | Phase: Tool layer | Unit test con args malformados devuelve error estructurado, no 500 |
| Race condition concurrencia | Phase: Worker outbound + modelo `call_attempts` | Índice único parcial existe; test de doble dispatch al mismo deudor produce un solo attempt activo |

---

## Sources

- PROJECT.md del servicio `retell-voice` (contexto de requerimientos y constraints)
- Experiencia previa Landa voice orchestrator (Assembly AI + Claude + Twilio — memory `project_voice_orchestrator.md`)
- Conocimiento de entrenamiento sobre: Retell AI webhooks y function calling, patrones de idempotencia en webhooks, Ley 1581/2012 Colombia (Habeas Data), Decreto 1746/2016 (cobranza extrajudicial), Ley 2300/2023 (gestión de cartera — MEDIUM confidence, verificar texto oficial), Multi-tenancy en MongoDB, AMD en llamadas outbound
- **Nota de confianza:** Las referencias legales colombianas (Ley 2300/2023 en particular) son MEDIUM confidence — verificar con abogado especializado antes del primer piloto con deudores reales. El número de la ley y artículos exactos deben consultarse en fuente oficial (SIC o Diario Oficial).

---
*Pitfalls research for: AI Voice Agent — Debt Collection (Retell AI + Anthropic + Node/TS + MongoDB, LatAm/Colombia)*
*Researched: 2026-05-09*
