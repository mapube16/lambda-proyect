# Phase 17: Voice Cobranza Agent — Research

**Researched:** 2026-03-27
**Domain:** Vapi.ai outbound voice AI, FastAPI webhooks, MongoDB debtor management, Colombian debt collection compliance
**Confidence:** MEDIUM-HIGH (Vapi API shapes verified against official docs; compliance from official SIC/government sources; architecture patterns from Vapi community + official SDK)

---

## Summary

Phase 17 adds a complete outbound voice debt collection vertical to Landa. Any client can upload a debtor portfolio (CSV or manual), configure a collection strategy via conversational onboarding, and the system executes automated outbound voice calls through Vapi.ai — the agent negotiates, captures payment promises, and pushes status updates to the dashboard in real time via the existing WebSocket infrastructure.

**Vapi.ai is the correct choice** for this phase. It provides outbound calling, in-call server tool calls (webhooks during the live call), assistant configuration with system prompts and first messages, and an official Python async SDK (`vapi_server_sdk`). Free Vapi numbers are US-only — the project needs a Twilio Colombia number (+57) imported into Vapi. Voice: ElevenLabs (Spanish, Multilingual v2 model). STT: Deepgram Nova-3 with `language: "es"`.

The key Colombian compliance law is **Ley 2300 de 2023** ("Dejen de Fregar"), which tightly restricts automated collection call hours and frequency. The system must enforce scheduling windows and daily contact limits before initiating any Vapi call.

**Primary recommendation:** Use Vapi.ai with a Twilio +57 number imported into Vapi's dashboard. Build two FastAPI endpoints: `POST /api/vapi/tool-call` (handles real-time tool calls during a live call) and `POST /api/vapi/call-ended` (handles end-of-call-report for status updates). Pass `debtor_id` via `assistantOverrides.variableValues` so it's available inside tool call payloads. Debtor state machine: `pendiente → llamando → promesa_de_pago | sin_contacto | pagado | fallido`.

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| COBR-01 | Usuario puede subir CSV con deudores (nombre, teléfono, monto, vencimiento) o agregarlos manualmente — registros aparecen con estado `pendiente` | FastAPI `UploadFile` + `csv.DictReader` + `phonenumbers` E164 validation → MongoDB `debtors` collection |
| COBR-02 | Onboarding conversacional: Queen propone estrategia de llamadas (tono, horario, guion) que el usuario aprueba | Reusar patrón `queen_proposal.py` — OpenAI `json_object` response_format, nuevo prompt especializado en cobranza |
| COBR-03 | Al aprobar campaña, agente inicia llamadas outbound via Vapi — durante la llamada usa tool calls para consultar deuda, registrar promesas, escalar | Vapi Python SDK `AsyncVapi.calls.create()` + servidor webhook FastAPI en `/api/vapi/tool-call` con respuesta `{"results": [{"toolCallId": "...", "result": "..."}]}` |
| COBR-04 | Dashboard muestra estado de cada deudor en tiempo real: `pendiente → llamando → promesa_de_pago → pagado → sin_contacto` con historial de intentos | MongoDB `debtors` collection + `manager.send_to_user()` WebSocket (existing `ConnectionManager` pattern from main.py) |
</phase_requirements>

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| vapi_server_sdk | latest (PyPI) | Create outbound calls, async client | Official Vapi Python SDK with `AsyncVapi` support |
| phonenumbers | latest | Parse + validate E164 phone numbers | Google's libphonenumber port; handles +57 Colombia correctly |
| httpx | 0.27.0 (already in requirements.txt) | Sync/async HTTP requests (already used) | Already in project; use for Vapi REST if SDK insufficient |
| pandas | latest | CSV parsing for bulk debtor import | Standard for tabular data; `pd.read_csv(BytesIO(...))` |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-multipart | 0.0.9 (already installed) | FastAPI file upload parsing | Already installed — required for `UploadFile` |
| certifi | already transitive | TLS cert bundle | Already used in `database.py` Motor init |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vapi | Retell AI | Retell has better outbound focus + cheaper ($0.07/min flat vs Vapi variable), but Vapi has the most mature Python SDK and tool-call webhook documentation |
| Vapi | Bland AI | Bland charges $0.09/min + $0.015 per failed outbound attempt; stronger bulk campaign features but less developer-friendly API |
| ElevenLabs voice | OpenAI TTS | OpenAI TTS is cheaper but lower quality for natural-sounding Spanish; ElevenLabs Multilingual v2 is the standard for voice agents needing authentic LatAm Spanish |
| Deepgram Nova-3 | AssemblyAI | Deepgram Nova-3 has 54.3% lower WER for streaming; AssemblyAI does not have the same real-time latency profile |

**Installation:**
```bash
pip install vapi_server_sdk phonenumbers pandas
```

---

## Architecture Patterns

### Recommended Project Structure

```
backend/
├── cobranza/
│   ├── __init__.py
│   ├── router.py          # FastAPI APIRouter: /api/cobranza/* + /api/vapi/*
│   ├── debtor_crud.py     # MongoDB debtors CRUD (no logic, pure DB ops)
│   ├── csv_parser.py      # CSV upload → validated debtor dicts
│   ├── vapi_client.py     # AsyncVapi wrapper: create_call(), cancel_call()
│   ├── call_scheduler.py  # Ley 2300 compliance: is_allowed_hour(), schedule_next()
│   ├── cobranza_queen.py  # Queen prompt for collection strategy onboarding
│   └── webhooks.py        # /api/vapi/tool-call + /api/vapi/call-ended handlers
```

### MongoDB `debtors` Collection Schema

```python
{
    "_id": ObjectId,
    "user_id": str,               # tenant isolation — REQUIRED index
    "nombre": str,
    "telefono": str,              # E164 format, e.g. "+573001234567"
    "monto": float,               # pesos colombianos
    "vencimiento": datetime,
    "estado": str,                # "pendiente"|"llamando"|"promesa_de_pago"|"sin_contacto"|"pagado"|"fallido"
    "vapi_call_id": Optional[str], # Vapi call ID once call initiated
    "intentos": int,              # number of call attempts
    "historial_llamadas": [       # array of call records
        {
            "call_id": str,
            "fecha": datetime,
            "duracion_segundos": int,
            "resultado": str,     # "promesa"|"sin_contacto"|"rechazo"|"error"
            "transcript": Optional[str],
            "monto_prometido": Optional[float],
            "fecha_promesa": Optional[datetime],
            "notas": Optional[str]
        }
    ],
    "created_at": datetime,
    "updated_at": datetime,
    # Compliance tracking (Ley 2300)
    "ultimo_contacto_fecha": Optional[datetime],
    "canal_usado_esta_semana": Optional[str],  # "voz"|"sms"|"email"
}
```

**Index strategy** (add to `database.py init_db()`):
```python
await db.debtors.create_index([("user_id", 1), ("estado", 1)])
await db.debtors.create_index([("user_id", 1), ("created_at", -1)])
await db.debtors.create_index("vapi_call_id", sparse=True)
await db.debtors.create_index([("user_id", 1), ("telefono", 1)], unique=True)
```

### Pattern 1: Vapi Outbound Call Creation

**What:** Initiate an outbound call with debtor data injected via `variableValues` so the assistant's system prompt has the debtor context and tool call webhooks can look up the debtor by ID.

**When to use:** When a campaign is approved or the scheduler fires a retry for a `pendiente` or `sin_contacto` debtor.

**Example:**
```python
# Source: https://docs.vapi.ai/calls/outbound-calling + https://docs.vapi.ai/assistants/dynamic-variables
from vapi import AsyncVapi
import os

async def create_cobranza_call(debtor: dict, assistant_id: str, phone_number_id: str) -> str:
    """Returns vapi_call_id."""
    client = AsyncVapi(token=os.getenv("VAPI_API_KEY"))
    call = await client.calls.create(
        assistant_id=assistant_id,
        phone_number_id=phone_number_id,
        customer={"number": debtor["telefono"]},  # E164
        assistant_overrides={
            "variable_values": {
                "debtor_id": str(debtor["_id"]),
                "debtor_name": debtor["nombre"],
                "monto": str(debtor["monto"]),
                "vencimiento": debtor["vencimiento"].strftime("%d de %B de %Y"),
            }
        },
    )
    return call.id
```

### Pattern 2: Vapi Tool Call Webhook Handler

**What:** FastAPI endpoint that Vapi calls during a live conversation when the assistant needs to query data or register an outcome. Must respond within ~5 seconds. Must always return HTTP 200.

**When to use:** `POST /api/vapi/tool-call` — registered as `serverUrl` on the Vapi assistant config.

**Example:**
```python
# Source: https://docs.vapi.ai/tools/custom-tools + https://docs.vapi.ai/tools/custom-tools-troubleshooting
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()

@router.post("/api/vapi/tool-call")
async def handle_tool_call(request: Request):
    body = await request.json()
    message = body.get("message", {})
    call_obj = message.get("call", {})

    # CRITICAL: always HTTP 200 — Vapi ignores any other status code
    results = []
    for tool_item in message.get("toolWithToolCallList", []):
        tool_name = tool_item["name"]
        tool_call_id = tool_item["toolCall"]["id"]
        params = tool_item["toolCall"].get("parameters", {})

        result_str = await dispatch_tool(tool_name, params, call_obj)
        results.append({
            "toolCallId": tool_call_id,  # MUST match exactly
            "result": result_str          # MUST be a string, not dict/list
        })

    return JSONResponse({"results": results})


async def dispatch_tool(name: str, params: dict, call_obj: dict) -> str:
    debtor_id = params.get("debtor_id") or call_obj.get("metadata", {}).get("debtor_id")
    if name == "consultar_deuda":
        debtor = await db.debtors.find_one({"_id": ObjectId(debtor_id)})
        if not debtor:
            return "Deudor no encontrado."
        return f"Deuda: ${debtor['monto']:,.0f} COP. Vencimiento: {debtor['vencimiento'].strftime('%d/%m/%Y')}."
    elif name == "registrar_promesa":
        monto = params.get("monto_prometido")
        fecha = params.get("fecha_prometida")
        await db.debtors.update_one(
            {"_id": ObjectId(debtor_id)},
            {"$set": {"estado": "promesa_de_pago", "updated_at": datetime.now(timezone.utc)}},
        )
        return f"Promesa registrada: ${monto} para {fecha}."
    elif name == "escalar_a_humano":
        await db.debtors.update_one(
            {"_id": ObjectId(debtor_id)},
            {"$set": {"estado": "escalado", "updated_at": datetime.now(timezone.utc)}},
        )
        return "Escalado a agente humano. La llamada será transferida."
    return "Herramienta no reconocida."
```

### Pattern 3: End-of-Call Webhook Handler

**What:** Updates debtor state and pushes real-time WebSocket notification when a call finishes.

**When to use:** `POST /api/vapi/call-ended` — can be the same `serverUrl` endpoint, filtered by `message.type == "end-of-call-report"`.

**Example:**
```python
# Source: https://docs.vapi.ai/server-url/events
@router.post("/api/vapi/call-ended")
async def handle_call_ended(request: Request):
    body = await request.json()
    message = body.get("message", {})
    if message.get("type") != "end-of-call-report":
        return JSONResponse({"ok": True})  # Ignore other event types

    call_obj = message.get("call", {})
    call_id = call_obj.get("id")
    ended_reason = message.get("endedReason", "unknown")
    transcript = message.get("artifact", {}).get("transcript", "")

    # Find debtor by vapi_call_id
    debtor = await db.debtors.find_one({"vapi_call_id": call_id})
    if not debtor:
        return JSONResponse({"ok": True})

    # Map endedReason to debtor estado
    if debtor["estado"] == "promesa_de_pago":
        new_estado = "promesa_de_pago"  # already set by tool call
    elif ended_reason in ("no-answer", "busy", "voicemail"):
        new_estado = "sin_contacto"
    elif ended_reason in ("customer-ended-call", "assistant-ended-call", "hangup"):
        new_estado = debtor["estado"]  # keep what tool calls set
    else:
        new_estado = "fallido"

    call_record = {
        "call_id": call_id,
        "fecha": datetime.now(timezone.utc),
        "resultado": ended_reason,
        "transcript": transcript[:2000] if transcript else None,
    }
    await db.debtors.update_one(
        {"_id": debtor["_id"]},
        {
            "$set": {"estado": new_estado, "updated_at": datetime.now(timezone.utc), "ultimo_contacto_fecha": datetime.now(timezone.utc)},
            "$inc": {"intentos": 1},
            "$push": {"historial_llamadas": call_record},
            "$unset": {"vapi_call_id": ""},
        }
    )

    # Real-time push to frontend via existing WebSocket manager
    user_id = str(debtor["user_id"])
    await manager.send_to_user(user_id, {
        "type": "debtor_update",
        "debtor_id": str(debtor["_id"]),
        "estado": new_estado,
        "intentos": debtor["intentos"] + 1,
    })
    return JSONResponse({"ok": True})
```

### Pattern 4: CSV Upload + Phone Validation

**What:** Parse a CSV file, validate phone numbers to E164 (Colombia +57), return normalized debtor dicts for bulk MongoDB insert.

**Example:**
```python
# Source: https://fastapi.tiangolo.com/tutorial/request-files/ + phonenumbers PyPI
import csv
import io
import phonenumbers
from phonenumbers import PhoneNumberFormat, NumberParseException
from fastapi import UploadFile

def normalize_phone(raw: str, default_region: str = "CO") -> str | None:
    """Return E164 string or None if invalid."""
    try:
        n = phonenumbers.parse(raw.strip(), default_region)
        if phonenumbers.is_valid_number(n):
            return phonenumbers.format_number(n, PhoneNumberFormat.E164)
    except NumberParseException:
        pass
    return None

async def parse_debtor_csv(file: UploadFile) -> tuple[list[dict], list[str]]:
    """Returns (valid_debtors, error_rows)."""
    contents = await file.read()
    text = contents.decode("utf-8-sig")  # strip BOM if Excel-exported
    reader = csv.DictReader(io.StringIO(text))
    valid, errors = [], []
    for i, row in enumerate(reader, start=2):
        telefono = normalize_phone(row.get("telefono", ""))
        if not telefono:
            errors.append(f"Row {i}: telefono inválido '{row.get('telefono')}'")
            continue
        try:
            monto = float(str(row.get("monto", "0")).replace(",", "").replace("$", ""))
        except ValueError:
            errors.append(f"Row {i}: monto inválido '{row.get('monto')}'")
            continue
        valid.append({
            "nombre": row.get("nombre", "").strip(),
            "telefono": telefono,
            "monto": monto,
            "vencimiento": row.get("vencimiento", ""),  # parse date downstream
            "estado": "pendiente",
            "intentos": 0,
            "historial_llamadas": [],
        })
    return valid, errors
```

### Pattern 5: Vapi Assistant Configuration (stored in DB or hardcoded)

**What:** The full assistant JSON object used when creating the assistant in Vapi dashboard or via API. Tools are "server tools" pointing to the FastAPI webhook.

**Example:**
```json
{
  "name": "Agente Cobranza Landa",
  "model": {
    "provider": "openai",
    "model": "gpt-4o",
    "messages": [
      {
        "role": "system",
        "content": "Eres un agente de cobranza profesional y empático de {{empresa_nombre}}. Tu misión es contactar a {{debtor_name}} sobre una deuda de {{monto}} COP vencida el {{vencimiento}}. Sigue este flujo: 1) Verificar identidad 2) Informar deuda 3) Ofrecer acuerdo de pago 4) Registrar promesa o escalar. Sé siempre respetuoso. Nunca preguntes por qué no pagaron. Máximo 1 contacto por día. ID interno: {{debtor_id}}"
      }
    ],
    "temperature": 0.3,
    "tools": [
      {
        "type": "function",
        "function": {
          "name": "consultar_deuda",
          "description": "Consulta el monto exacto y fecha de vencimiento de la deuda del deudor actual",
          "parameters": {
            "type": "object",
            "properties": {
              "debtor_id": {"type": "string", "description": "ID del deudor"}
            },
            "required": ["debtor_id"]
          }
        },
        "server": {"url": "https://your-domain.com/api/vapi/tool-call"}
      },
      {
        "type": "function",
        "function": {
          "name": "registrar_promesa",
          "description": "Registra una promesa de pago del deudor",
          "parameters": {
            "type": "object",
            "properties": {
              "debtor_id": {"type": "string"},
              "monto_prometido": {"type": "number"},
              "fecha_prometida": {"type": "string", "description": "Fecha en formato YYYY-MM-DD"}
            },
            "required": ["debtor_id", "monto_prometido", "fecha_prometida"]
          }
        },
        "server": {"url": "https://your-domain.com/api/vapi/tool-call"}
      },
      {
        "type": "function",
        "function": {
          "name": "escalar_a_humano",
          "description": "Escala la llamada a un agente humano cuando el deudor lo solicita o la situación es compleja",
          "parameters": {
            "type": "object",
            "properties": {
              "debtor_id": {"type": "string"},
              "motivo": {"type": "string"}
            },
            "required": ["debtor_id", "motivo"]
          }
        },
        "server": {"url": "https://your-domain.com/api/vapi/tool-call"}
      }
    ]
  },
  "voice": {
    "provider": "11labs",
    "voiceId": "pNInz6obpgDQGcFmaJgB",
    "model": "eleven_multilingual_v2"
  },
  "transcriber": {
    "provider": "deepgram",
    "model": "nova-3",
    "language": "es"
  },
  "firstMessage": "Hola, buenos días. ¿Estoy hablando con {{debtor_name}}?",
  "firstMessageMode": "assistant-speaks-first",
  "endCallMessage": "Gracias por su tiempo. Que tenga un buen día.",
  "maxDurationSeconds": 300,
  "serverUrl": "https://your-domain.com/api/vapi/call-ended"
}
```

### Anti-Patterns to Avoid

- **Returning non-200 HTTP status from tool-call handler:** Vapi silently ignores non-200 responses — the assistant never receives the tool result and the call stalls. Always return 200.
- **Returning dict/list as `result` in tool response:** The `result` field must be a string. Serialize to JSON string if needed: `json.dumps(data)`.
- **Line breaks in tool response strings:** Multi-line strings cause Vapi parsing errors. Use `str.replace("\n", " ")` before returning.
- **Using free Vapi number for Colombia:** Free numbers are US-only — international calls will fail silently. Import a Twilio +57 number.
- **Not passing `debtor_id` via `variableValues`:** Without this, tool calls cannot look up which debtor is on the call. The `call.customer.number` can be used as fallback but phone numbers are less reliable as lookup keys.
- **Calling debtors outside Ley 2300 hours:** System must block calls outside Mon-Fri 7am-7pm and Sat 8am-3pm Colombia time. Never call on Sundays/holidays.
- **Calling the same debtor more than once per day:** Ley 2300 prohibits it. Track `ultimo_contacto_fecha` per debtor.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Phone number parsing/validation | Custom regex for +57 numbers | `phonenumbers` (Google libphonenumber) | Handles 200+ country formats, mobile vs landline detection, number formatting edge cases |
| STT during calls | Custom Deepgram WebSocket integration | Vapi handles STT internally via transcriber config | Vapi manages STT/TTS/LLM pipeline — you only handle tool call webhooks |
| TTS during calls | Custom ElevenLabs streaming | Vapi handles TTS internally via voice config | Same as above |
| Call state machine | Custom polling loop | Vapi `status-update` + `end-of-call-report` webhook events | Vapi pushes state changes — no polling needed |
| Conversation turn management | Custom LLM call loop | Vapi assistant manages full conversation | Vapi handles interruption detection, endpointing, turn-taking |
| Async HTTP for Vapi API | Raw httpx calls | `vapi_server_sdk` (`AsyncVapi`) | SDK handles auth, retries, exponential backoff, pagination automatically |

**Key insight:** With Vapi, you are only responsible for two things: (1) configuring the assistant (system prompt, voice, tools) and (2) handling webhook POSTs from Vapi during and after calls. All voice pipeline complexity is inside Vapi's infrastructure.

---

## Common Pitfalls

### Pitfall 1: Tool Call Response Must Be HTTP 200 Always
**What goes wrong:** Developer returns 400 or 422 when tool parameters are invalid. Vapi silently ignores the response. The assistant hangs waiting for a result that never arrives, then times out and ends the call abruptly.
**Why it happens:** Standard REST convention says use 4xx for bad requests. Vapi's protocol is different — it treats non-200 as "no response received."
**How to avoid:** Wrap all tool call logic in try/except. Return HTTP 200 with an error message as the `result` string: `{"results": [{"toolCallId": "...", "result": "Error: deudor no encontrado."}]}`
**Warning signs:** Calls ending mid-conversation without registering any outcome; "no result returned" in Vapi call logs.

### Pitfall 2: `result` Field Must Be a String
**What goes wrong:** Developer returns `{"result": {"monto": 5000, "vencimiento": "2024-01-01"}}`. Vapi rejects the non-string value. Assistant says it couldn't get the information.
**Why it happens:** It feels natural to return structured data.
**How to avoid:** Always stringify: `json.dumps(data)` or a human-readable sentence. The assistant reads this as text anyway.
**Warning signs:** Tool triggers but assistant says "I wasn't able to retrieve that information."

### Pitfall 3: Debtor Identification in Webhooks
**What goes wrong:** Developer tries to look up debtor by `call.customer.number` (the phone number dialed). Fails when a debtor has multiple numbers or when the number format doesn't match MongoDB exactly.
**Why it happens:** Phone number seems like a natural key.
**How to avoid:** Inject `debtor_id` via `assistantOverrides.variableValues` when creating the call. Reference `{{debtor_id}}` in the system prompt. Extract `debtor_id` from tool call `parameters` (the LLM will pass it as a required parameter).
**Warning signs:** Debtor updates applied to wrong records or `None` finds in MongoDB.

### Pitfall 4: Free Vapi Numbers Are US-Only
**What goes wrong:** Developer creates a call to a +57 Colombian number using a free Vapi number. Call fails with "international calling not supported."
**Why it happens:** Vapi dashboard creates US numbers by default.
**How to avoid:** Go to Vapi Dashboard → Phone Numbers → Import Number → select Twilio → enter Twilio credentials and +57 number SID. Required for any LatAm calling.
**Warning signs:** Call `POST /call` returns 201 but call immediately ends with `endedReason: "pipeline-error-provider-unavailable"`.

### Pitfall 5: Ley 2300 Hour Enforcement Must Be Server-Side
**What goes wrong:** Frontend blocks scheduling UI outside allowed hours, but the backend `calls.create()` endpoint has no guard. Programmatic retries (APScheduler) fire at any hour.
**Why it happens:** Compliance logic forgotten in the scheduler retry path.
**How to avoid:** `call_scheduler.py` must check Colombia local time (`pytz.timezone("America/Bogota")`) before every call initiation, including scheduled retries. Reject with 400 and log if outside window.
**Warning signs:** Calls going out at 2am; SIC complaints.

### Pitfall 6: WebSocket Debtor Updates Require User ID
**What goes wrong:** When `end-of-call-report` arrives, developer can't push to the right user because debtor documents don't store `user_id`.
**Why it happens:** `user_id` forgotten in debtor schema.
**How to avoid:** Always store `user_id` in every debtor document (consistent with all other Landa collections). In `call-ended` handler, `debtor["user_id"]` provides the routing key for `manager.send_to_user()`.
**Warning signs:** WebSocket updates not reaching the correct client; `send_to_user` silently no-ops because user_id is `None`.

### Pitfall 7: Vapi `end-of-call-report` Can Be Intermittent
**What goes wrong:** Some calls end without triggering `end-of-call-report` (known Vapi issue: see community report on failed/busy/no-answer calls).
**Why it happens:** Vapi's telephony layer may not fire the event for non-connected calls.
**How to avoid:** Also listen for `status-update` events with `status: "ended"` as a fallback. Or poll Vapi's `GET /call/{id}` from the scheduler for calls stuck in `llamando` state after 10 minutes.
**Warning signs:** Debtors stuck in `llamando` state indefinitely.

---

## Code Examples

### Compliance: Colombia Time Window Check

```python
# Source: Ley 2300 de 2023 + pytz docs
from datetime import datetime
import pytz

COLOMBIA_TZ = pytz.timezone("America/Bogota")
COLOMBIA_HOLIDAYS_2026 = {  # expand annually — minimum set
    (1, 1), (1, 12), (3, 23), (4, 2), (4, 3), (5, 1),
    (5, 25), (6, 15), (6, 22), (6, 29), (7, 20), (8, 7),
    (8, 17), (10, 12), (11, 2), (11, 16), (12, 8), (12, 25),
}

def is_contact_allowed_now() -> bool:
    """Ley 2300 de 2023: Mon-Fri 7am-7pm, Sat 8am-3pm, Sun/holiday never."""
    now_co = datetime.now(COLOMBIA_TZ)
    weekday = now_co.weekday()  # 0=Mon, 6=Sun
    hour = now_co.hour
    if (now_co.month, now_co.day) in COLOMBIA_HOLIDAYS_2026:
        return False
    if weekday == 6:  # Sunday
        return False
    if weekday == 5:  # Saturday
        return 8 <= hour < 15
    return 7 <= hour < 19  # Mon-Fri
```

### Async Vapi Call Creation

```python
# Source: https://github.com/VapiAI/server-sdk-python
from vapi import AsyncVapi

async def initiate_call(debtor: dict, config: dict) -> str:
    client = AsyncVapi(token=config["vapi_api_key"])
    call = await client.calls.create(
        assistant_id=config["vapi_assistant_id"],
        phone_number_id=config["vapi_phone_number_id"],
        customer={"number": debtor["telefono"], "name": debtor["nombre"]},
        assistant_overrides={
            "variable_values": {
                "debtor_id": str(debtor["_id"]),
                "debtor_name": debtor["nombre"],
                "monto": f"{debtor['monto']:,.0f}",
            }
        },
    )
    return call.id
```

### Tool Call Dispatcher (FastAPI)

```python
# Source: https://docs.vapi.ai/tools/custom-tools
@router.post("/api/vapi/tool-call")
async def vapi_tool_call(request: Request):
    body = await request.json()
    msg = body.get("message", {})
    results = []
    for item in msg.get("toolWithToolCallList", []):
        tool_call_id = item["toolCall"]["id"]
        try:
            result = await _handle_tool(item["name"], item["toolCall"].get("parameters", {}))
        except Exception as e:
            result = f"Error interno: {str(e)}"
        # result must be string, single-line
        result = str(result).replace("\n", " ")
        results.append({"toolCallId": tool_call_id, "result": result})
    return JSONResponse({"results": results})  # always 200
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Deepgram Nova-2 | Deepgram Nova-3 (54.3% lower WER streaming) | 2025 | Better Spanish transcription accuracy; just change `"model": "nova-3"` |
| ElevenLabs v1 | ElevenLabs Multilingual v2 | 2024 | Much more natural LatAm Spanish; Vapi voice config: `"model": "eleven_multilingual_v2"` |
| Polling for call state | Vapi `status-update` + `end-of-call-report` webhooks | Vapi Server URL launch March 2025 | No polling — push-based state updates |
| Custom voice pipeline | Vapi manages STT+LLM+TTS internally | Ongoing | Builder only manages tool call webhooks |

**Deprecated/outdated:**
- "Free Vapi numbers for international": Never worked — always needed Twilio import for +57.
- Vapi `function-call` event type: Replaced by `tool-calls` event type in current Vapi docs. Use `tool-calls`.

---

## Colombian Compliance Architecture

### Ley 2300 de 2023 ("Dejen de Fregar") — MANDATORY

| Rule | Implementation Required |
|------|------------------------|
| Mon-Fri only between 7am-7pm Colombia time | `is_contact_allowed_now()` check before every `calls.create()` |
| Saturday only 8am-3pm Colombia time | Same function |
| Sunday/holiday: zero contact | Same function + holiday calendar |
| Max 1 contact per day per debtor | Check `ultimo_contacto_fecha` < today before calling |
| If voice call used this week, no SMS/email same week | Track `canal_usado_esta_semana` per debtor |
| Cannot contact third parties (references) | Only call `debtor.telefono` — no reference calling |
| Cannot ask why debt wasn't paid | Remove from system prompt any "¿por qué no pagó?" phrasing |

### Ley 1581 de 2012 (Habeas Data) — Data Protection

| Rule | Implementation Required |
|------|------------------------|
| Written authorization required to process personal data | Client (the company) must certify they have authorization from their debtors before uploading CSV |
| SIC authorization required for automated calls with personal data | Display compliance disclaimer in onboarding UI — client accepts liability |
| Debtors can request deletion | `DELETE /api/cobranza/debtors/{id}` endpoint required |

### Ley 1266 de 2008 (Habeas Data Financiero)

- Governs financial data (debtors are financial data subjects)
- Debt can only be reported to credit bureaus if >3 months overdue and debtor notified
- **Implementation:** Do not add credit bureau reporting to MVP — out of scope for Phase 17

**Practical compliance posture for MVP:**
1. Add a "Certifico que tengo autorización de mis deudores" checkbox to onboarding — client accepts legal responsibility
2. Enforce time windows server-side (never frontend-only)
3. Include "Llamada informativa de [empresa]" in `firstMessage` so debtor knows it's a collection call
4. Implement `DELETE /api/cobranza/debtors/{id}` for opt-out/deletion requests

---

## Validation Architecture

> `workflow.nyquist_validation` is `true` — this section is required.

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 7.4.4 + pytest-asyncio 0.23.5 |
| Config file | `backend/pytest.ini` (`asyncio_mode = auto`, `testpaths = tests`) |
| Quick run command | `cd backend && python -m pytest tests/test_cobranza.py -x -q` |
| Full suite command | `cd backend && python -m pytest tests/ -x -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| COBR-01 | CSV upload parses valid rows, rejects invalid phone | unit | `pytest tests/test_cobranza.py::test_csv_upload_valid -x` | Wave 0 |
| COBR-01 | CSV upload returns error list for invalid rows | unit | `pytest tests/test_cobranza.py::test_csv_upload_invalid_phone -x` | Wave 0 |
| COBR-01 | Manual debtor POST stores `pendiente` estado | integration | `pytest tests/test_cobranza.py::test_manual_debtor_create -x` | Wave 0 |
| COBR-01 | GET /api/cobranza/debtors returns tenant-isolated results | integration | `pytest tests/test_cobranza.py::test_debtors_list_isolated -x` | Wave 0 |
| COBR-02 | Queen proposal generates valid strategy JSON | unit | `pytest tests/test_cobranza.py::test_queen_cobranza_proposal -x` | Wave 0 |
| COBR-03 | `is_contact_allowed_now()` respects Ley 2300 hours | unit | `pytest tests/test_cobranza.py::test_ley2300_window -x` | Wave 0 |
| COBR-03 | `/api/vapi/tool-call` returns HTTP 200 with results array | unit | `pytest tests/test_cobranza.py::test_tool_call_response_format -x` | Wave 0 |
| COBR-03 | `consultar_deuda` tool returns string (not dict) | unit | `pytest tests/test_cobranza.py::test_tool_consultar_deuda -x` | Wave 0 |
| COBR-03 | `registrar_promesa` updates debtor estado in MongoDB | integration | `pytest tests/test_cobranza.py::test_tool_registrar_promesa -x` | Wave 0 |
| COBR-04 | `end-of-call-report` handler updates debtor estado | integration | `pytest tests/test_cobranza.py::test_call_ended_handler -x` | Wave 0 |
| COBR-04 | `end-of-call-report` sends WebSocket message to user | integration | `pytest tests/test_cobranza.py::test_call_ended_ws_notify -x` | Wave 0 |

### Sampling Rate

- **Per task commit:** `cd backend && python -m pytest tests/test_cobranza.py -x -q`
- **Per wave merge:** `cd backend && python -m pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps

- [ ] `backend/tests/test_cobranza.py` — 11 xfail stubs covering all COBR-01 through COBR-04 (2-3 stubs per req)
- [ ] `backend/cobranza/__init__.py` — empty init for module
- [ ] `backend/cobranza/router.py` — empty module (import must not crash at collection time)
- [ ] No new framework needed — `pytest`, `pytest-asyncio`, `mongomock-motor`, and `httpx` already in `requirements.txt`

---

## Open Questions

1. **Vapi assistant ID storage**
   - What we know: Vapi assistants can be created once via dashboard or API and reused by `assistantId`
   - What's unclear: Should each Landa client get their own Vapi assistant (with their company name/persona) or share one assistant with `variableValues` for personalization?
   - Recommendation: Start with one shared assistant + `variableValues` for MVP. Each client gets a `cobranza_config` document in MongoDB with `vapi_assistant_id`, `vapi_phone_number_id`, and their collection strategy. This avoids managing per-client Vapi assistants in Phase 17.

2. **Vapi Colombia phone number provisioning**
   - What we know: Vapi free numbers are US-only; Twilio +57 numbers must be imported
   - What's unclear: Does Twilio allow +57 outbound calls on all account types or only verified business accounts? Twilio has country-specific requirements.
   - Recommendation: Test Twilio +57 number purchase before Phase 17 code starts. If blocked, Telnyx is a documented Vapi alternative with better LatAm coverage.

3. **Debtor data encryption**
   - What we know: Ley 1581 requires appropriate security measures for personal financial data
   - What's unclear: Whether field-level encryption in MongoDB is needed for MVP or TLS-in-transit + Atlas encryption-at-rest is sufficient
   - Recommendation: Atlas encryption-at-rest (default) + TLS is sufficient for MVP. Document in onboarding that data is stored encrypted.

4. **end-of-call-report reliability for non-connected calls**
   - What we know: Community reports that busy/no-answer calls may not always fire `end-of-call-report`
   - What's unclear: How frequently this happens and whether `status-update` with `status: "ended"` is always fired
   - Recommendation: Handle both `status-update` (with status=ended) and `end-of-call-report` in the same endpoint, deduplicated by `call_id`. Add an APScheduler job that marks debtors stuck in `llamando` for >15 minutes as `sin_contacto`.

---

## Sources

### Primary (HIGH confidence)
- `https://docs.vapi.ai/calls/outbound-calling` — Outbound call API, request body structure, phoneNumberId requirement
- `https://docs.vapi.ai/tools/custom-tools` — Tool call webhook pattern, payload structure, response format
- `https://docs.vapi.ai/tools/custom-tools-troubleshooting` — Critical pitfalls: HTTP 200 always, string-only result, toolCallId matching
- `https://docs.vapi.ai/server-url/events` — All event types, tool-calls payload shape, end-of-call-report payload shape
- `https://docs.vapi.ai/assistants/dynamic-variables` — `variableValues` via `assistantOverrides`, `{{variable}}` syntax
- `https://github.com/VapiAI/server-sdk-python` — `AsyncVapi` client, `pip install vapi_server_sdk`, `calls.create()` pattern
- `https://pypi.org/project/phonenumbers/` — Google libphonenumber Python port, E164 validation, Colombia region "CO"
- `https://www.tusdatos.co/blog/ley-2300-dejen-de-fregar` — Ley 2300 de 2023: allowed hours, prohibited actions, enforcement
- `https://www.sic.gov.co` — SIC authority on automated calls requiring personal data authorization (Habeas Data)

### Secondary (MEDIUM confidence)
- `https://vapi.ai/blog/state-of-the-art-transcriber-capabilities-2` — Deepgram Nova-3 availability in Vapi, configuration change from nova-2
- `https://www.walturn.com/insights/a-comparison-between-vapi-and-other-voice-ai-platforms` — Vapi vs Retell vs Bland comparison (pricing, latency, outbound focus)
- `https://docs.vapi.ai/api-reference/assistants/create` — Complete assistant schema including voice, transcriber, firstMessage, maxDurationSeconds
- `https://vapi.ai/community/m/1422115496903311463` — end-of-call-report reliability issue for busy/no-answer calls (community report)

### Tertiary (LOW confidence)
- `https://vapi.ai/community/m/1249244985946144798` — New tools calls response format (community, not official docs)
- General voice AI debt collection best practices (multiple industry blogs, not Colombia-specific)

---

## Metadata

**Confidence breakdown:**
- Standard stack (Vapi SDK, phonenumbers, pandas): HIGH — verified against official SDK docs and PyPI
- Architecture (tool call pattern, webhook handlers): HIGH — verified against official Vapi docs
- Compliance (Ley 2300): HIGH — sourced from official government/SIC sources
- Pitfalls (HTTP 200 always, string result): HIGH — official troubleshooting docs + community confirmation
- Voice/STT config (ElevenLabs multilingual, Nova-3): MEDIUM — verified against Vapi blog/docs but no direct test
- Phone number provisioning (Twilio +57): MEDIUM — documented path but untested for Colombia specifically

**Research date:** 2026-03-27
**Valid until:** 2026-04-27 (Vapi is fast-moving; re-verify tool-call payload structure if more than 30 days pass)
