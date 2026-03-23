# Phase 16: WhatsApp como Canal Completo de Landa — Context

**Gathered:** 2026-03-23
**Status:** Ready for planning

<domain>
## Phase Boundary

WhatsApp es un canal alternativo equivalente a la web para dos tipos de usuarios:

1. **Cliente de Landa** — recibe notificaciones de checkpoint/handover, aprueba/rechaza leads, reporta llamadas y puede configurar campaña — todo via conversación WhatsApp. Sin abrir el dashboard si no quiere.

2. **Asesor interno de Landa** — busca empresas en SECOP, enriquece NITs, gestiona prospectos de múltiples clientes, inicia outreach — desde WhatsApp con lenguaje natural.

**Decisión clave del producto:** La web (pixel art office) y WhatsApp son canales equivalentes. El cliente elige. El campo `company_voice.notification_channel` = `"web"` | `"whatsapp"` | `"both"` controla el routing (configurado desde Phase 15 en StaffDashboard).

**Fuera de scope:** cambios al frontend web — esta fase es backend + webhook.

</domain>

<decisions>
## Implementation Decisions

### Webhook y proveedor

- **Proveedor:** Twilio (ya usado en `whatsapp_agent.py` — credenciales TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN ya en el proyecto)
- **Endpoint entrante:** `POST /api/whatsapp/incoming` — Twilio llama este webhook al recibir un mensaje
- **Validación de firma:** verificar `X-Twilio-Signature` header para rechazar requests no-Twilio
- **Formato de respuesta:** TwiML vacío `<Response/>` inmediato + procesamiento async (no bloquear el webhook)

### Routing por número de teléfono

- El webhook recibe `To` (número de Landa) y `From` (número del usuario)
- Buscar en MongoDB `company_voice` por `wa_phone_number == From` → cliente identificado
- Si no hay match: buscar en `users` collection por número registrado como asesor interno
- Si tampoco: ignorar el mensaje (log warning)
- Un mismo número de Landa (`To`) puede recibir de múltiples clientes — el `From` identifica quién escribe

### Sesiones en MongoDB (reemplaza dict en memoria de whatsapp_agent.py)

```python
# Collection: wa_sessions
{
  "phone": "+573001234567",       # From number
  "user_id": "...",               # resolved user
  "profile": "cliente" | "asesor_interno",
  "history": [                    # últimos N turnos
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "updated_at": datetime
}
```
- TTL index: sesiones expiran a las 24h de inactividad
- Máximo 10 turnos en `history` (sliding window — el resto se descarta)

### LLM con tool calling — intención libre

El LLM recibe el mensaje del usuario + historial + tools disponibles y decide qué ejecutar.

**Tools para perfil `cliente`:**
- `ver_leads_checkpoint()` → llama `GET /api/leads/checkpoint` internamente
- `aprobar_lead(lead_id, canal)` → llama `POST /api/leads/{id}/decision`
- `pausar_lead(lead_id)` → ídem con decision=pausar
- `rechazar_lead(lead_id, motivo)` → ídem con decision=rechazar
- `ver_handover(lead_id)` → llama `GET /api/leads/{id}/handover`
- `tomar_control(lead_id)` → llama `POST /api/leads/{id}/handover/tomar`
- `reportar_llamada(lead_id, resultado, detalle)` → llama `POST /api/leads/{id}/reporte-llamada`

**Tools para perfil `asesor_interno`:**
- `buscar_licitaciones(sector, ciudad)` → llama `secop_radar.fetch_open_processes()`
- `buscar_adjudicados(sector, ciudad, nit?)` → llama `secop.fetch_adjudicados()`
- `enriquecer_empresa(nit)` → llama `nit_enricher.enrich_nit()`
- `ver_clientes()` → lista clientes activos del sistema
- `ver_leads_cliente(user_id)` → leads de un cliente específico
- `iniciar_outreach(lead_id, canal)` → dispara `run_outreach()`

### Notas de voz (PRIORIDAD — feature diferenciador)

El asesor manda un audio mientras sale de una reunión y el sistema lo procesa.

**Flujo:**
```
Usuario manda nota de voz
→ Twilio webhook recibe MediaUrl0 (URL del audio .ogg)
→ Descargar audio con httpx (autenticado con Twilio creds)
→ Transcribir con OpenAI Whisper API (model="whisper-1")
→ Tratar la transcripción como texto normal → LLM tool calling
→ Responder en texto (default) o en audio (TTS, si el usuario lo prefiere)
```

**Respuesta en audio (opcional por cliente):**
```
Respuesta texto del LLM
→ OpenAI TTS API (model="tts-1", voice="alloy" o configurable)
→ Genera MP3
→ Subir a servicio temporal (o usar Twilio Media directamente)
→ Enviar como WhatsApp audio message via Twilio
```

- Flag por sesión: `voice_responses: bool` — default False, el usuario lo activa diciendo "respóndeme en audio"
- Si Whisper falla: responder "No pude entender el audio, ¿puedes escribirlo?"
- Latencia estimada: transcripción ~2s + LLM ~2s = ~4s total (aceptable para WhatsApp)

### Router de notificaciones (integración con el sistema existente)

En `main.py`, en cada punto donde se emite un WebSocket event, agregar routing condicional:

```python
async def notify_user(user_id: str, event: dict):
    cv = await get_or_create_company_voice(user_id)
    channel = cv.get("notification_channel", "web")

    if channel in ("web", "both"):
        await send_to_user(user_id, event)            # WebSocket existente

    if channel in ("whatsapp", "both"):
        wa_number = cv.get("wa_phone_number")
        if wa_number:
            message = _format_wa_notification(event)  # formatea el evento como texto
            await send_whatsapp_text(wa_number, message)
```

Eventos que deben enrutarse:
- `lead_checkpoint` → "Tengo {N} candidatos listos. Escribe 'ver leads' para revisarlos."
- `lead_handover` → "¡{empresa} respondió! Escribe 'ver oportunidad' para tomar el control."
- `lead_archived` → "{empresa} fue archivado."

### Perfiles de usuario y autenticación

- El número de teléfono del `From` es el identificador — no hay login explícito
- Asesores internos: lista fija de números en env var `WA_STAFF_NUMBERS` (comma-separated) o colección `wa_staff` en MongoDB
- Clientes: identificados por `company_voice.wa_phone_number`
- Si un número no está registrado como ninguno: mensaje de bienvenida + instrucciones de registro

### Formato de mensajes salientes

- Máximo 1600 caracteres por mensaje (límite WhatsApp)
- Listas de leads: máximo 5 por mensaje, con numeración ("1. Empresa X — puntaje 84")
- El LLM formatea para WhatsApp (sin markdown rico — solo texto plano + saltos de línea)
- Emojis aceptados para mejorar legibilidad (✅ ❌ ⏸️ 📊)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets

- `whatsapp_sender.send_whatsapp_text(phone, message)` — ya funciona vía Meta Graph API (Phase 13)
- `whatsapp_agent.py` — POC con lógica de sesiones en memoria y flujo de selección (referencia, NO reusar directamente)
- `secop_radar.fetch_open_processes(sector)` — ya implementado
- `nit_enricher.enrich_nit(nit_raw)` — ya implementado (Phase 15)
- `landa/agents/outreach.run_outreach(lead_id, user_id, canal, intento)` — ya implementado
- `landa/company_voice.get_or_create_company_voice(user_id)` — ya implementado
- APScheduler en `landa/scheduler.py` — para notificaciones proactivas futuras
- `send_to_user(user_id, event)` — WebSocket broadcast existente en main.py

### Established Patterns

- `asyncio.create_task()` — para procesamiento async del webhook (no bloquear TwiML response)
- JWT auth en main.py — NO aplica para webhook Twilio (usa firma Twilio en su lugar)
- `mongomock_motor` en tests — para sesiones MongoDB en tests

### Integration Points

- `main.py` — agregar `POST /api/whatsapp/incoming` + función `notify_user()` que reemplaza llamadas directas a `send_to_user` en los endpoints de checkpoint/handover/decision
- `database.py` — agregar CRUD para `wa_sessions` collection
- `company_voice` — ya tiene `notification_channel`, `wa_phone_number`, `wa_phone_id`, `wa_token` desde Phase 15

</code_context>

<specifics>
## Specific Ideas

- **El caso killer:** el asesor sale de una reunión, manda un audio "habló con el gerente, quedó muy interesado, me pidió una propuesta para el viernes" → el sistema transcribe, extrae intención, ejecuta `reportar_llamada(lead_id, "bien", detalle)` automáticamente y responde "Perfecto, registré que quedó interesado. ¿Quieres que programe un seguimiento para el jueves?"
- **Notificaciones proactivas:** APScheduler puede enviar un resumen diario a las 8am via WhatsApp a clientes con `notification_channel=whatsapp`: "Buenos días. Tienes 2 leads en checkpoint y 1 oportunidad lista."
- El asesor puede escribir en español coloquial colombiano — el LLM entiende "mándele un correo a esa constructora que salió en SECOP"

</specifics>

<deferred>
## Deferred Ideas

- Self-service de registro via WhatsApp (el cliente se registra él mismo mandando su NIT) — Phase 17
- Respuestas en audio por defecto — primero validar que la transcripción funciona bien en la práctica
- Notificaciones proactivas programadas (daily digest) — puede agregarse en Phase 16.5 o Phase 17
- Soporte para imágenes/documentos adjuntos en WhatsApp — Phase 17
- Multi-idioma (inglés/portugués) — cuando Landa expanda fuera de Colombia

</deferred>

---

*Phase: 16-whatsapp-conversational-advisor-bot*
*Context gathered: 2026-03-23*
