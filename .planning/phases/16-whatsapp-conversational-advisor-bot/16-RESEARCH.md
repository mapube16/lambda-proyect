# Phase 16: WhatsApp como Canal Completo de Landa — Research

**Researched:** 2026-03-23
**Domain:** Twilio webhook + MongoDB sessions + LLM tool-calling + OpenAI Whisper + notify_user routing
**Confidence:** HIGH (all critical questions answered from codebase + official docs)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **Proveedor:** Twilio (credenciales TWILIO_ACCOUNT_SID + TWILIO_AUTH_TOKEN ya en el proyecto)
- **Endpoint entrante:** `POST /api/whatsapp/incoming` — Twilio llama este webhook al recibir un mensaje
- **Validación de firma:** verificar `X-Twilio-Signature` header para rechazar requests no-Twilio
- **Formato de respuesta:** TwiML vacío `<Response/>` inmediato + procesamiento async (no bloquear el webhook)
- **Routing:** `To` (número de Landa) y `From` (número del usuario) — buscar en MongoDB `company_voice` por `wa_phone_number == From` → cliente; si no, buscar en `users` por número asesor
- **Sesiones:** MongoDB `wa_sessions` collection, TTL 24h, máximo 10 turnos sliding window
- **LLM:** tool calling — diferentes tool sets para `cliente` vs `asesor_interno`
- **Notas de voz:** Twilio MediaUrl0 → httpx download → OpenAI Whisper → LLM
- **notify_user():** reemplaza llamadas directas a `send_to_user` en checkpoints de main.py; enruta a WS, WA, o ambos según `notification_channel`
- **Formato saliente:** máximo 1600 chars, listas de máximo 5 leads, texto plano + emojis, sin markdown rico

### Claude's Discretion

- Arquitectura interna de `wa_handler.py` (nombre de módulo, estructura de funciones)
- Sistema de tool calling: si usar openai function-calling nativo o parseo manual
- Manejo de errores en transcripción de voz (fallback message)
- Cómo hacer `asyncio.create_task()` desde dentro del webhook de forma segura

### Deferred Ideas (OUT OF SCOPE)

- Self-service de registro via WhatsApp (el cliente se registra él mismo mandando su NIT) — Phase 17
- Respuestas en audio por defecto — primero validar que la transcripción funciona bien en la práctica
- Notificaciones proactivas programadas (daily digest) — puede agregarse en Phase 16.5 o Phase 17
- Soporte para imágenes/documentos adjuntos en WhatsApp — Phase 17
- Multi-idioma (inglés/portugués) — cuando Landa expanda fuera de Colombia

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| WA-01 | Webhook Twilio POST /api/whatsapp/incoming con validación de firma, routing por From/To, sesiones MongoDB TTL 24h | Twilio RequestValidator + Motor TTL index pattern confirmed |
| WA-02 | LLM tool calling con perfiles cliente/asesor_interno — tools ejecutan lógica real del sistema | OpenAI function-calling via existing openai>=1.30.0 client |
| WA-03 | Notas de voz: Twilio MediaUrl → httpx download → Whisper transcripción → LLM | Whisper API OGG supported, auth optional by default |
| WA-04 | notify_user() reemplaza send_to_user() en 3 puntos de main.py — routing condicional WS/WA/both | 3 exact call sites identified in codebase scan |

</phase_requirements>

---

## Summary

Phase 16 construye el canal WhatsApp completo de Landa sobre una base sólida: el proyecto ya tiene `whatsapp_sender.py` (Meta Graph API), `whatsapp_agent.py` (POC con sesiones en memoria y flujo de selección), y todas las herramientas de backend que los LLM tools invocarán (`secop_radar`, `nit_enricher`, `run_outreach`, `get_or_create_company_voice`). El trabajo de esta fase es reemplazar el POC con un sistema de producción: sesiones en MongoDB, validación de firma Twilio, LLM tool-calling con perfiles diferenciados, transcripción de voz con Whisper, y la función `notify_user()` que conecta los eventos de lead con el canal correcto.

**Dependencia crítica con Phase 15:** Los campos `notification_channel` y `wa_phone_number` en `company_voice` son añadidos por Phase 15-02-PLAN.md. En el estado actual del código NO existen estos campos en ningún documento. El planner de Phase 16 debe asumir que Phase 15 ha corrido y estos campos están disponibles — si Phase 16 corre antes, `notify_user()` debe tener fallback a `channel="web"` cuando el campo no existe (que es el comportamiento correcto: `cv.get("notification_channel", "web")`).

**Paquete `twilio` no instalado:** `requirements.txt` no incluye el paquete `twilio`. Debe añadirse para usar `RequestValidator`. Sin él, la validación de firma requiere implementación manual de HMAC-SHA1, lo cual es propenso a errores. Añadir `twilio>=9.0.0` a requirements.txt es la primera acción del Wave 0.

**Primary recommendation:** Crear `backend/wa_handler.py` como módulo central con 4 funciones: `validate_twilio_signature()`, `get_or_create_session()`, `update_session()`, `process_inbound()`. El webhook en `main.py` llama `asyncio.create_task(process_inbound(...))` y retorna `<Response/>` inmediatamente.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `twilio` | `>=9.0.0` | `RequestValidator` para validación de firma Twilio | Única forma confiable de validar X-Twilio-Signature — evita bug de empty-value params |
| `openai` | `>=1.30.0` (ya instalado) | Whisper transcripción + LLM tool calling | Ya en requirements.txt — usar `AsyncOpenAI` |
| `motor` | `3.3.2` (ya instalado) | CRUD de `wa_sessions` con TTL index | Ya en requirements.txt |
| `httpx` | `0.27.0` (ya instalado) | Descargar audio desde Twilio MediaUrl | Ya en requirements.txt y patrón establecido en el proyecto |
| `fastapi` | `0.109.0` (ya instalado) | Endpoint webhook + `BackgroundTasks` | Ya en requirements.txt |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `python-multipart` | ya instalado (Phase 12) | Parsear `Form(...)` data del webhook Twilio | Requerido por FastAPI para Form data — ya instalado |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `twilio.request_validator.RequestValidator` | Manual HMAC-SHA1 | Manual implementación ignora empty-value params — produce falsos negativos de validación |
| `asyncio.create_task()` | FastAPI `BackgroundTasks` | `BackgroundTasks` es más limpio y garantiza ejecución post-response — ambos válidos, `create_task()` es el patrón ya establecido en main.py |
| `whisper-1` (Whisper v2) | `gpt-4o-transcribe` | `gpt-4o-transcribe` es más preciso con español colombiano coloquial pero más costoso — `whisper-1` es el estándar del proyecto |

**Installation (nuevo paquete):**
```bash
pip install "twilio>=9.0.0"
# Agregar a requirements.txt: twilio>=9.0.0
```

---

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── wa_handler.py          # Módulo central: validate, session CRUD, process_inbound, tool dispatch
├── main.py                # +POST /api/whatsapp/incoming  +notify_user()
├── database.py            # +wa_sessions CRUD (get/upsert/delete)
├── whatsapp_sender.py     # Ya existe — sin cambios (send_whatsapp_text)
├── whatsapp_agent.py      # Ya existe — REFERENCIA SOLO, no reusar directamente
└── tests/
    └── test_wa_handler.py # Tests: validate_sig, session CRUD, routing, notify_user
```

### Pattern 1: Webhook Endpoint — Retorno Inmediato + Async Background

**What:** El endpoint responde TwiML `<Response/>` vacío en < 200ms y despacha el procesamiento en background.

**When to use:** Siempre — Twilio tiene timeout de 15s para webhooks y reintenta si no recibe respuesta.

```python
# Source: Twilio FastAPI tutorial + project pattern (asyncio.create_task already used in main.py)
from fastapi import Request, Form, Response
from twilio.request_validator import RequestValidator
import asyncio

@app.post("/api/whatsapp/incoming")
async def whatsapp_incoming(
    request: Request,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(default=""),
    MediaUrl0: str = Form(default=None),
    MediaContentType0: str = Form(default=None),
    NumMedia: str = Form(default="0"),
):
    # 1. Validar firma Twilio PRIMERO
    validator = RequestValidator(os.environ.get("TWILIO_AUTH_TOKEN", ""))
    form_data = await request.form()
    sig = request.headers.get("X-Twilio-Signature", "")
    if not validator.validate(str(request.url), form_data, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # 2. Despachar procesamiento async — no bloquear
    asyncio.create_task(
        process_inbound(From, To, Body, MediaUrl0, MediaContentType0)
    )

    # 3. Responder TwiML vacío INMEDIATAMENTE
    return Response(content="<Response/>", media_type="application/xml")
```

### Pattern 2: Sesiones MongoDB con TTL

**What:** `wa_sessions` collection con TTL index en `updated_at` de 86400 segundos (24h). Sliding window de 10 turnos.

**When to use:** Al iniciar init_db() — crear el índice una sola vez, Motor lo ignora si ya existe.

```python
# Source: MongoDB TTL docs + project database.py init_db pattern
async def init_db(...):
    # ... existing indexes ...
    # TTL index: sesiones expiran 24h después del último update
    await db.wa_sessions.create_index(
        "updated_at",
        expireAfterSeconds=86400
    )
    await db.wa_sessions.create_index("phone", unique=True)
```

**CRUD pattern para wa_sessions:**
```python
# Source: project database.py upsert pattern
async def get_or_create_wa_session(phone: str, user_id: str, profile: str) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    doc = await db.wa_sessions.find_one({"phone": phone})
    if not doc:
        doc = {
            "phone": phone,
            "user_id": user_id,
            "profile": profile,
            "history": [],
            "voice_responses": False,
            "updated_at": now,
        }
        await db.wa_sessions.insert_one(doc)
    return doc

async def update_wa_session(phone: str, history: list) -> None:
    db = get_db()
    # Sliding window: keep last 10 turns
    trimmed = history[-10:]
    await db.wa_sessions.update_one(
        {"phone": phone},
        {"$set": {"history": trimmed, "updated_at": datetime.now(timezone.utc)}},
        upsert=True
    )
```

### Pattern 3: LLM Tool Calling (OpenAI function-calling)

**What:** Definir tools como JSON schema, pasar al LLM con `tool_choice="auto"`, ejecutar la tool llamada, devolver resultado como `tool` message, obtener respuesta final.

**When to use:** Para ambos perfiles (cliente y asesor_interno) — el tool set cambia pero el loop es el mismo.

```python
# Source: OpenAI function-calling pattern, project openai>=1.30.0
from openai import AsyncOpenAI

client_oai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

TOOLS_CLIENTE = [
    {
        "type": "function",
        "function": {
            "name": "ver_leads_checkpoint",
            "description": "Muestra los leads listos para decisión del cliente",
            "parameters": {"type": "object", "properties": {}, "required": []},
        }
    },
    {
        "type": "function",
        "function": {
            "name": "aprobar_lead",
            "description": "Aprueba un lead para outreach",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string"},
                    "canal": {"type": "string", "enum": ["email", "whatsapp"]},
                },
                "required": ["lead_id", "canal"],
            },
        }
    },
    # ... resto de tools
]

async def call_llm_with_tools(messages: list, tools: list, tool_executor) -> str:
    response = await client_oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=messages,
        tools=tools,
        tool_choice="auto",
        max_tokens=500,
    )
    msg = response.choices[0].message

    if msg.tool_calls:
        # Execute each tool call
        tool_results = []
        for tc in msg.tool_calls:
            result = await tool_executor(tc.function.name, tc.function.arguments)
            tool_results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": str(result),
            })
        # Get final response
        messages_with_results = messages + [msg] + tool_results
        final = await client_oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages_with_results,
            max_tokens=500,
        )
        return final.choices[0].message.content or ""

    return msg.content or ""
```

### Pattern 4: Transcripción de Voz con Whisper

**What:** Descargar audio de Twilio MediaUrl con httpx (auth básica Twilio), pasar a Whisper API como bytes en memoria.

**When to use:** Cuando `NumMedia >= 1` y `MediaContentType0` contiene "audio".

```python
# Source: Twilio media download + OpenAI Whisper API
import io
from openai import AsyncOpenAI

async def transcribe_voice_note(media_url: str) -> str | None:
    """Download Twilio audio and transcribe with Whisper. Returns None on failure."""
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")

    try:
        # Twilio media: auth with Account SID + Auth Token (Basic auth)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(media_url, auth=(sid, token))
            if resp.status_code != 200:
                logger.error("[Whisper] Media download failed: %d", resp.status_code)
                return None
            audio_bytes = resp.content

        # Pass bytes to Whisper — use BytesIO to avoid disk writes
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = "voice.ogg"  # Filename hint for format detection

        client_oai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        result = await client_oai.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language="es",  # Colombian Spanish — improves accuracy
        )
        return result.text
    except Exception as e:
        logger.error("[Whisper] Transcription error: %s", e)
        return None
```

**Note on Twilio media auth:** By default, Twilio media URLs are publicly accessible without authentication. However, using Basic auth (SID:Token) is safe and works whether or not the account has HTTP auth enabled. Always use it.

### Pattern 5: notify_user() — Router de Notificaciones

**What:** Función `async def notify_user(user_id, event)` en main.py que consulta `company_voice.notification_channel` y enruta a WS, WA, o ambos.

**When to use:** Reemplaza EXACTAMENTE estas 3 llamadas en main.py:

| Línea aprox | Endpoint | Evento | Acción actual |
|-------------|----------|--------|---------------|
| ~1764 | `POST /api/leads/{id}/decision` (decision="aprobar") | `lead_checkpoint` | `await manager.send_to_user(user_id, {...})` |
| ~1772 | `POST /api/leads/{id}/decision` (decision="rechazar") | `lead_archived` | `await manager.send_to_user(user_id, {...})` |
| ~1879 | `POST /api/leads/{id}/handover/tomar` | `lead_handover` | `await manager.send_to_user(user_id, {...})` |

La llamada de `agent_state` en `reporte_llamada` (línea ~1971) NO se reemplaza — es un evento de UI, no una notificación de negocio.

```python
# Source: CONTEXT.md pattern — implemented in main.py
def _format_wa_notification(event: dict) -> str:
    """Format a lead lifecycle event as WhatsApp-friendly text."""
    etype = event.get("type")
    empresa = event.get("empresa", "")
    if etype == "lead_checkpoint":
        return f"Nuevo lead listo para revision: {empresa}. Escribe 'ver leads' para revisarlos."
    elif etype == "lead_handover":
        return f"{empresa} respondio! Escribe 'ver oportunidad' para tomar el control."
    elif etype == "lead_archived":
        return f"{empresa} fue archivado."
    return str(event)

async def notify_user(user_id: str, event: dict) -> None:
    """Route a lead lifecycle event to WS, WA, or both based on notification_channel."""
    from landa.company_voice import get_or_create_company_voice
    from whatsapp_sender import send_whatsapp_text

    cv = await get_or_create_company_voice(user_id)
    channel = cv.get("notification_channel", "web")  # Default to "web" if Phase 15 not run

    if channel in ("web", "both"):
        await manager.send_to_user(user_id, event)

    if channel in ("whatsapp", "both"):
        wa_number = cv.get("wa_phone_number")
        if wa_number:
            message = _format_wa_notification(event)
            await send_whatsapp_text(wa_number, message)
```

### Anti-Patterns to Avoid

- **Bloquear el webhook:** Nunca `await process_inbound(...)` dentro del handler Twilio — siempre `create_task`. Twilio reintenta si no recibe respuesta en 15s, causando mensajes duplicados.
- **Sesiones en `_SESSIONS` dict (whatsapp_agent.py):** El POC existente usa un dict en memoria — si el servidor se reinicia o escala horizontalmente, se pierden todas las sesiones. Usar MongoDB.
- **No validar firma Twilio:** Sin validación, cualquier HTTP POST al endpoint activa el bot — vector de abuso.
- **Leer `request.form()` dos veces:** FastAPI/Starlette consume el body stream una sola vez. Leer en la validación y guardar el dict resultante — no llamar `await request.form()` de nuevo.
- **Importar whatsapp_agent.py directamente:** El POC tiene lógica acoplada a un flujo específico. Usar solo como referencia de patrones, no importarlo en el nuevo código.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Validación firma Twilio | HMAC-SHA1 manual | `twilio.request_validator.RequestValidator` | Empty-value params bug — validación manual produce falsos negativos |
| TTL de sesiones | Cron job de limpieza | MongoDB TTL index en `updated_at` | Motor + MongoDB manejan expiración automáticamente |
| Sliding window de historial | Lógica de slice manual | `history[-10:]` antes de `$set` | Simple y suficiente |
| Audio format detection | Parsear Content-Type header | Pasar `audio_file.name = "voice.ogg"` a Whisper | La API acepta nombre de archivo como hint |
| Tool dispatch routing | `if/elif` por nombre de tool | Dict de funciones `{name: func}` | Más limpio y testeable |

**Key insight:** La infraestructura de sesiones, validación y routing ya existen en librerías maduras. El valor de esta fase está en el *contenido* de los tools y la voz del LLM, no en reimplementar infraestructura.

---

## Common Pitfalls

### Pitfall 1: `request.form()` se consume solo una vez

**What goes wrong:** `RequestValidator.validate()` necesita el dict de form data. Si se llama `form_data = await request.form()` para validación, y luego se intenta acceder a `Body: str = Form(...)` otra vez, FastAPI puede dar valores vacíos o error.
**Why it happens:** El body de la request HTTP es un stream — se lee una sola vez.
**How to avoid:** Usar `request.form()` UNA VEZ y extraer todos los campos del dict resultante. Declarar los parámetros `Form(...)` en la firma del endpoint o leer del dict — elegir uno y ser consistente.
**Warning signs:** `Body` es string vacío aunque el mensaje de WhatsApp tenga texto.

### Pitfall 2: `asyncio.create_task()` en endpoint FastAPI

**What goes wrong:** `create_task()` dentro de un endpoint FastAPI puede generar `RuntimeWarning: coroutine was never awaited` o perder tareas si el event loop no está activo.
**Why it happens:** FastAPI maneja el event loop internamente — `create_task()` funciona correctamente DENTRO de un endpoint async porque hay un loop activo.
**How to avoid:** Usar `asyncio.create_task(process_inbound(...))` directamente — es el mismo patrón que usa `main.py` ya en línea ~1763 para `_run_outreach`. No es necesario cambiar a `BackgroundTasks`.
**Warning signs:** Mensajes que nunca se procesan, sin logs de error.

### Pitfall 3: Twilio reintenta si no recibe TwiML

**What goes wrong:** Si el endpoint tarda más de ~15 segundos o retorna 500, Twilio reintenta el webhook — el usuario recibe el mensaje procesado 2-3 veces.
**Why it happens:** Twilio tiene timeout de 15s y política de reintentos automáticos.
**How to avoid:** SIEMPRE retornar `Response(content="<Response/>", media_type="application/xml")` antes de hacer cualquier I/O. El `create_task()` se ejecuta después del return.
**Warning signs:** Mensajes duplicados en WhatsApp del bot.

### Pitfall 4: `notification_channel` y `wa_phone_number` no existen si Phase 15 no corrió

**What goes wrong:** `cv.get("notification_channel")` retorna `None`, `notify_user()` no enruta a WA.
**Why it happens:** Los campos son añadidos por Phase 15-02 (endpoint `POST /api/staff/clients/{id}/sources`). El código actual de `company_voice.py` no los incluye en el schema.
**How to avoid:** `cv.get("notification_channel", "web")` — el default a `"web"` es el comportamiento correcto. notify_user() solo usará WA si el campo existe y tiene valor `"whatsapp"` o `"both"`.
**Warning signs:** Notificaciones WA nunca llegan incluso con Phase 15 completa — verificar que el campo fue guardado en MongoDB.

### Pitfall 5: Twilio WhatsApp usa prefijo `whatsapp:` en los números

**What goes wrong:** Twilio envía `From: whatsapp:+573001234567` — el prefijo `whatsapp:` forma parte del valor. Al buscar en MongoDB por `wa_phone_number`, el lookup falla si el número está guardado como `+573001234567`.
**Why it happens:** El formato Twilio incluye el prefijo de canal para soportar SMS y WA en el mismo número.
**How to avoid:** Strip el prefijo: `from_phone = From.replace("whatsapp:", "")` al inicio del handler. Verificar también el campo de búsqueda en `company_voice` — guardar números SIN prefijo.
**Warning signs:** Routing siempre cae al caso "número no registrado" — log warning persistente.

### Pitfall 6: `whatsapp_sender.py` usa Meta Graph API, NO Twilio Messages API

**What goes wrong:** Para responder mensajes entrantes via Twilio, se intenta usar `send_whatsapp_text()` del proyecto existente (Meta Graph API), pero ese número/token puede ser diferente del número Twilio que recibe los mensajes.
**Why it happens:** El proyecto tiene DOS integraciones WA: Twilio (para recibir) y Meta Graph API directa (para outreach de Phase 13).
**How to avoid:** Para respuestas a mensajes Twilio, usar la API de Twilio Messages directamente (como hace `whatsapp_agent.py` con `_send_whatsapp()`). Para notificaciones proactivas a clientes, `send_whatsapp_text()` de Meta Graph API es correcto. Documentar explícitamente qué sender usar en cada contexto.
**Warning signs:** Respuestas al usuario enviadas desde un número WA diferente al que recibió el mensaje.

---

## Code Examples

### Validación de Firma Twilio (patrón completo)

```python
# Source: Twilio official FastAPI tutorial + twilio.request_validator
from twilio.request_validator import RequestValidator

@app.post("/api/whatsapp/incoming")
async def whatsapp_incoming(request: Request):
    validator = RequestValidator(os.environ.get("TWILIO_AUTH_TOKEN", ""))
    form_data = dict(await request.form())  # Read ONCE, convert to dict
    sig = request.headers.get("X-Twilio-Signature", "")

    # Use str(request.url) — must match exactly the URL configured in Twilio Console
    if not validator.validate(str(request.url), form_data, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    from_raw = form_data.get("From", "")
    from_phone = from_raw.replace("whatsapp:", "")  # Strip prefix
    body = form_data.get("Body", "")
    media_url = form_data.get("MediaUrl0")
    media_ct = form_data.get("MediaContentType0", "")

    asyncio.create_task(process_inbound(from_phone, body, media_url, media_ct))
    return Response(content="<Response/>", media_type="application/xml")
```

### TTL Index en init_db()

```python
# Source: MongoDB TTL docs + project database.py init_db() pattern
# 86400 segundos = 24 horas
await db.wa_sessions.create_index("updated_at", expireAfterSeconds=86400)
await db.wa_sessions.create_index("phone", unique=True)
```

### OpenAI Whisper desde bytes en memoria

```python
# Source: OpenAI speech-to-text guide (platform.openai.com/docs/guides/speech-to-text)
import io
from openai import AsyncOpenAI

async def transcribe_voice_note(media_url: str) -> str | None:
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    async with httpx.AsyncClient(timeout=30) as http:
        r = await http.get(media_url, auth=(sid, token))
    if r.status_code != 200:
        return None
    buf = io.BytesIO(r.content)
    buf.name = "voice.ogg"
    oai = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    result = await oai.audio.transcriptions.create(
        model="whisper-1",
        file=buf,
        language="es",
    )
    return result.text
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `_SESSIONS` dict en memoria (`whatsapp_agent.py`) | `wa_sessions` MongoDB con TTL | Phase 16 | Sessions survive restart, support horizontal scaling |
| Flujo de estados hardcodeado (idle → awaiting_selection → awaiting_channel) | LLM tool calling libre | Phase 16 | Lenguaje natural — asesor dice "mándele un correo a esa constructora" |
| Twilio Messages API para envío | Meta Graph API (`whatsapp_sender.py`) ya usado para outreach | Phase 13 | Dos integraciones WA coexisten — Twilio para inbound, Meta para outbound |

**Deprecated/outdated:**
- `whatsapp_agent.py` como orquestador: el POC tiene valor como referencia de flujo y de cómo enviar mensajes via Twilio, pero NO debe importarse en producción — las sesiones en memoria son incompatibles con producción.

---

## Open Questions

1. **Dualidad de senders WhatsApp (Twilio vs Meta Graph API)**
   - What we know: Para responder mensajes Twilio entrantes, se debe usar Twilio Messages API (no Meta Graph). `whatsapp_sender.py` usa Meta Graph, que es para outreach proactivo (Phase 13).
   - What's unclear: ¿El planner debe crear un segundo sender function para respuestas Twilio, o reutilizar el `_send_whatsapp` de `whatsapp_agent.py`?
   - Recommendation: Extraer `_send_whatsapp()` de `whatsapp_agent.py` como `send_twilio_whatsapp(to, from_, body)` en el nuevo `wa_handler.py`. Documentar explícitamente: Twilio sender = respuestas conversacionales, Meta sender = outreach proactivo.

2. **URL del webhook y validación de firma en desarrollo local**
   - What we know: `RequestValidator` necesita la URL exacta configurada en Twilio Console. En localhost no hay URL pública.
   - What's unclear: ¿Cómo correr el webhook localmente durante desarrollo?
   - Recommendation: Usar `ngrok` o Twilio CLI Dev Phone para testing local. En tests unitarios, mockear `RequestValidator.validate()` para retornar True.

3. **Phase 15 como dependencia**
   - What we know: `notification_channel` y `wa_phone_number` son campos añadidos por Phase 15-02. En el código actual NO existen.
   - What's unclear: ¿Phase 16 puede correr si Phase 15 no ha corrido?
   - Recommendation: Sí, con el fallback `cv.get("notification_channel", "web")`. Phase 16 es desarrollable independientemente — solo las notificaciones WA proactivas dependen de que Phase 15 haya configurado el número del cliente.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| Config file | `backend/pytest.ini` (asyncio_mode = auto, testpaths = tests) |
| Quick run command | `cd backend && python -m pytest tests/test_wa_handler.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| WA-01 | Signature validation rejects bad sig (403) | unit | `pytest tests/test_wa_handler.py::test_invalid_twilio_signature -x` | ❌ Wave 0 |
| WA-01 | Routing: From matches company_voice → profile=cliente | unit | `pytest tests/test_wa_handler.py::test_routing_cliente -x` | ❌ Wave 0 |
| WA-01 | Routing: From in WA_STAFF_NUMBERS → profile=asesor_interno | unit | `pytest tests/test_wa_handler.py::test_routing_asesor -x` | ❌ Wave 0 |
| WA-01 | wa_sessions TTL index created in init_db | unit | `pytest tests/test_wa_handler.py::test_wa_sessions_ttl_index -x` | ❌ Wave 0 |
| WA-01 | Session sliding window: > 10 turns → trimmed to 10 | unit | `pytest tests/test_wa_handler.py::test_session_sliding_window -x` | ❌ Wave 0 |
| WA-02 | Tool dispatch: LLM returns ver_leads_checkpoint → calls internal function | unit | `pytest tests/test_wa_handler.py::test_tool_dispatch_ver_leads -x` | ❌ Wave 0 |
| WA-02 | Profile cliente: tool set excludes asesor_interno tools | unit | `pytest tests/test_wa_handler.py::test_cliente_tool_set -x` | ❌ Wave 0 |
| WA-03 | Voice note: MediaUrl0 present → transcribe_voice_note called | unit | `pytest tests/test_wa_handler.py::test_voice_note_triggers_whisper -x` | ❌ Wave 0 |
| WA-03 | Voice note: Whisper failure → fallback text message | unit | `pytest tests/test_wa_handler.py::test_voice_note_whisper_failure_fallback -x` | ❌ Wave 0 |
| WA-04 | notify_user channel=web: only send_to_user called | unit | `pytest tests/test_wa_handler.py::test_notify_user_web_only -x` | ❌ Wave 0 |
| WA-04 | notify_user channel=whatsapp: only send_whatsapp_text called | unit | `pytest tests/test_wa_handler.py::test_notify_user_wa_only -x` | ❌ Wave 0 |
| WA-04 | notify_user channel=both: both called | unit | `pytest tests/test_wa_handler.py::test_notify_user_both -x` | ❌ Wave 0 |
| WA-04 | notify_user missing wa_phone_number: WA skipped silently | unit | `pytest tests/test_wa_handler.py::test_notify_user_no_phone_number -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_wa_handler.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_wa_handler.py` — 13 xfail stubs cubriendo WA-01 through WA-04
- [ ] `backend/wa_handler.py` — módulo nuevo (stub vacío suficiente para Wave 0)
- [ ] `backend/requirements.txt` — añadir `twilio>=9.0.0`

---

## Sources

### Primary (HIGH confidence)

- **Codebase scan — `backend/main.py`** — 3 exactos `manager.send_to_user()` calls para lead_checkpoint (~L1764), lead_archived (~L1772), lead_handover (~L1879) identificados
- **Codebase scan — `backend/whatsapp_agent.py`** — POC completo estudiado; `_send_whatsapp()` y `_twilio_auth()` son reutilizables; `_SESSIONS` dict es lo que se reemplaza
- **Codebase scan — `backend/requirements.txt`** — Confirma: `twilio` NO instalado, `openai>=1.30.0` SÍ instalado, `httpx==0.27.0` SÍ, `motor==3.3.2` SÍ
- **Codebase scan — `backend/database.py` init_db()** — Patrón de creación de índices; todos usan `await db.collection.create_index(...)` — mismo patrón para TTL
- **Codebase scan — `backend/landa/company_voice.py`** — `get_or_create_company_voice(user_id)` retorna dict; campos `notification_channel`/`wa_phone_number` NO están en el schema actual
- **Codebase scan — `.planning/phases/15-pipeline-enrichment-channels/15-02-PLAN.md`** — Confirma que `notification_channel` y `wa_phone_number` son añadidos por Phase 15
- **Twilio FastAPI webhook tutorial** — [Build a Secure Twilio Webhook with Python and FastAPI](https://www.twilio.com/en-us/blog/build-secure-twilio-webhook-python-fastapi) — `RequestValidator` usage pattern confirmado
- **Twilio webhook security docs** — [Webhooks security](https://www.twilio.com/docs/usage/webhooks/webhooks-security) — empty-value params pitfall documentado

### Secondary (MEDIUM confidence)

- **OpenAI Whisper API** — [Speech to text guide](https://platform.openai.com/docs/guides/speech-to-text) — `whisper-1` acepta OGG, `language="es"` mejora precisión — verificado via WebSearch
- **MongoDB TTL docs** — [Expire Data with TTL](https://www.mongodb.com/docs/manual/tutorial/expire-data/) — `expireAfterSeconds` patrón confirmado
- **Twilio WhatsApp media** — [Send and Receive Media](https://www.twilio.com/docs/whatsapp/tutorial/send-and-receive-media-messages-whatsapp-python) — `MediaUrl0` es el campo para adjuntos; auth básica es la práctica recomendada

### Tertiary (LOW confidence)

- `AsyncOpenAI` client para Whisper — el proyecto usa `httpx` directamente para LLM calls en `whatsapp_agent.py`. La librería `openai>=1.30.0` instalada soporta `AsyncOpenAI` pero el patrón exacto con `io.BytesIO` no fue verificado contra el código instalado.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — requirements.txt confirmado, `twilio` ausente confirmado
- Architecture: HIGH — 3 call sites identificados exactamente, patrones del codebase verificados
- Pitfalls: HIGH — Twilio form body pitfall y prefijo `whatsapp:` verificados contra docs oficiales y código del POC
- Whisper integration: MEDIUM — API shape confirmada, `io.BytesIO` patrón razonado pero no testado

**Research date:** 2026-03-23
**Valid until:** 2026-04-23 (30 días — Twilio y OpenAI APIs son estables)
