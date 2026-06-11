# Phase 25: Agentic Multi-Tenant Architecture - Pattern Map

**Mapped:** 2026-06-10
**Files analyzed:** 10 (8 new + 2 modified)
**Analogs found:** 10 / 10

---

## File Classification

| Archivo nuevo/modificado | Role | Data Flow | Analog más cercano | Calidad |
|--------------------------|------|-----------|-------------------|---------|
| `backend/cobranza/tenant_config.py` | service | CRUD | `backend/database.py` (upsert_client_profile, upsert_prospecting_knowledge, update_wa_session) | exact |
| `backend/cobranza/cobranza_orchestrator.py` | service | event-driven | `backend/cobranza/voice_orchestrator.py` (VoiceOrchestrator) | role-match |
| `backend/cobranza/sub_agents/debtor_updater.py` | service | CRUD | `backend/cobranza/debtor_crud.py` (update_debtor) | exact |
| `backend/cobranza/sub_agents/whatsapp_notifier.py` | service | request-response | `backend/routers/whatsapp.py` (send_whatsapp_text pattern) | role-match |
| `backend/cobranza/sub_agents/identity_verifier.py` | service | request-response | `backend/cobranza/claude_decision.py` | role-match |
| `backend/cobranza/sub_agents/escalation_handler.py` | service | CRUD | `backend/cobranza/debtor_crud.py` (update_debtor) + `voice_orchestrator.py` escalate path | role-match |
| `backend/cobranza/voice_pipecat.py` (MODIFY) | service | streaming | sí mismo (es el archivo a modificar) — ver excerpts actuales | exact |
| `backend/cobranza/voice_router.py` (MODIFY) | route | request-response | sí mismo (es el archivo a modificar) — ver excerpts actuales | exact |
| `backend/cobranza/rag_service.py` | service | batch + request-response | `backend/rag.py` (ingest_document, query cosine similarity) | role-match |
| `backend/routers/tenant_admin.py` | route | CRUD | `backend/routers/knowledge.py` + `backend/routers/prospect.py` | role-match |

---

## Pattern Assignments

### `backend/cobranza/tenant_config.py` (service, CRUD)

**Analog:** `backend/database.py`

**Imports pattern** (database.py líneas 1-12):
```python
import os
import logging
from typing import Optional
from datetime import datetime, timezone
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorClient
from database import get_db
```

**Core CRUD pattern — upsert con $setOnInsert** (database.py líneas 401-425):
```python
async def upsert_client_profile(user_id: str, profile: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    set_payload = {
        "user_id": user_id,
        "business_summary": profile.get("business_summary", ""),
        "updated_at": now,
    }
    await db.client_profiles.update_one(
        {"user_id": user_id},
        {
            "$set": set_payload,
            "$setOnInsert": {"created_at": now},
        },
        upsert=True,
    )
```

**Prompt history rotation — dos operaciones separadas** (database.py líneas 1182-1205, wa_sessions pattern):
```python
# CRÍTICO: Motor + mongomock no soportan $push + $slice en una sola op.
# Patrón de dos pasos: push primero, luego trim si len > 5.
async def update_wa_session(phone: str, new_turn: dict) -> None:
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.wa_sessions.update_one(
        {"phone": phone},
        {
            "$push": {"history": new_turn},
            "$set": {"updated_at": now},
        }
    )
    # Trim to keep only last 10 (separate op — mongomock no soporta $push $slice)
    doc = await db.wa_sessions.find_one({"phone": phone})
    if doc and len(doc.get("history", [])) > 10:
        trimmed = doc["history"][-10:]
        await db.wa_sessions.update_one(
            {"phone": phone},
            {"$set": {"history": trimmed}},
        )
```
Adaptar para `prompt_history`: reemplazar `10` con `5`, `"history"` con `"prompt_history"`, filtro `"user_id"`.

**Index creation pattern** (database.py líneas 22-28 + líneas 70-116):
```python
async def _safe_index(collection, keys, **kwargs):
    """Crea índice ignorando conflictos con índices existentes."""
    try:
        await collection.create_index(keys, **kwargs)
    except OperationFailure as exc:
        if exc.code == 86:  # IndexKeySpecsConflict
            logger.warning("Index conflict on %s (skipped): %s", collection.name, exc.details.get("errmsg", ""))
        else:
            raise

# En init_db() agregar:
await _safe_index(db.tenant_configs, "user_id", unique=True)
await _safe_index(db.agent_instances, "user_id", unique=True)
await _safe_index(db.rag_documents, [("user_id", 1), ("filename", 1)])
await _safe_index(db.rag_documents, [("user_id", 1), ("created_at", -1)])
```

**Serialización de documentos MongoDB** (debtor_crud.py líneas 17-23):
```python
def _serialize(doc: Optional[dict]) -> Optional[dict]:
    """Convierte documento MongoDB: _id ObjectId -> str, retorna None si None."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc
```

---

### `backend/cobranza/cobranza_orchestrator.py` (service, event-driven)

**Analog:** `backend/cobranza/voice_orchestrator.py`

**Imports pattern** (voice_orchestrator.py líneas 1-28):
```python
import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from database import get_db
```

**Core class pattern — inicialización con user_id y config** (voice_orchestrator.py líneas 33-67):
```python
class VoiceOrchestrator:
    def __init__(
        self,
        call_id: str,
        user_id: str,
        debtor: dict,
        estrategia: dict,
        db_client=None,
    ):
        self.call_id = call_id
        self.user_id = user_id
        self.debtor = debtor
        self.estrategia = estrategia
        self.db = db_client or get_db()
        # State tracking
        self.state = "active"
        logger.info("[Orchestrator] Initialized for call %s, debtor %s", call_id, debtor.get("nombre"))
```

Adaptar para `CobranzaOrchestrator`:
```python
class CobranzaOrchestrator:
    """Direct-dispatch orchestrator: sub-agents son funciones async, NO AgentRunner."""
    def __init__(self, user_id: str, tenant_config: dict):
        self.user_id = user_id
        self.config = tenant_config
        self.db = get_db()
```

**Pattern de logging** (voice_orchestrator.py líneas 140-145):
```python
logger.info(
    "[Orchestrator] Turn %d action: %s | Response: %s",
    self.turn_count,
    action,
    response_text[:80],
)
```

**Error handling en MongoDB logging** (voice_orchestrator.py líneas 211-222):
```python
try:
    await db.cobranza_calls.insert_one(call_record)
    logger.info("[Orchestrator] Call %s logged (state: %s, turns: %d)", ...)
except Exception as e:
    logger.error("[Orchestrator] Failed to log call %s: %s", self.call_id, e)
```

---

### `backend/cobranza/sub_agents/debtor_updater.py` (service, CRUD)

**Analog:** `backend/cobranza/debtor_crud.py`

**Imports pattern** (debtor_crud.py líneas 1-10):
```python
from datetime import datetime, timezone
from typing import Optional
from bson import ObjectId
from pymongo.errors import BulkWriteError, DuplicateKeyError
```

**Core update pattern — siempre filtrar por user_id** (debtor_crud.py líneas 219-240):
```python
async def update_debtor(db, user_id: str, debtor_id: str, patch: dict) -> Optional[dict]:
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        return None

    patch["updated_at"] = _utcnow()

    try:
        result = await db.debtors.find_one_and_update(
            {"_id": oid, "user_id": user_id},   # user_id siempre en el filtro
            {"$set": patch},
            return_document=True,
        )
    except DuplicateKeyError:
        raise ValueError("telefono_duplicado")

    return _serialize(result)
```

**Helper de fecha** (debtor_crud.py líneas 13-14):
```python
def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
```

**Retorno de dict tipado para sub-agent** — el sub-agent debe retornar `{"ok": bool, "error": str | None}` coherente con el patrón de `result_callback` de GeminiLiveLLMService.

---

### `backend/cobranza/sub_agents/whatsapp_notifier.py` (service, request-response)

**Analog:** `backend/routers/whatsapp.py` (send pattern) + ARQ pattern de `backend/worker.py`

**Imports para WhatsApp send** — buscar en `backend/routers/whatsapp.py`:
```python
from services.notifications import send_whatsapp_text
```

**Pattern ARQ enqueue — despacho asíncrono para no bloquear tool call** (arq_pool pattern de Phase 18):
```python
# Sub-agent devuelve INMEDIATAMENTE con acknowledgement, ARQ completa en background
async def send_whatsapp(self, phone: str, message: str) -> dict:
    """whatsapp_notifier — encola ARQ job para envío asíncrono."""
    try:
        # Validación rápida
        if not phone or not message:
            return {"ok": False, "error": "phone y message requeridos"}
        # Encolar en ARQ (no await el resultado completo)
        from arq_pool import get_arq_pool
        pool = await get_arq_pool()
        await pool.enqueue_job(
            "send_whatsapp_job",
            user_id=self.user_id,
            phone=phone,
            message=message,
        )
        return {"ok": True, "queued": True}
    except Exception as e:
        logger.error("[whatsapp_notifier] enqueue failed: %s", e)
        return {"ok": False, "error": str(e)[:100]}
```

---

### `backend/cobranza/sub_agents/identity_verifier.py` (service, request-response)

**Analog:** `backend/cobranza/claude_decision.py`

**Patrón de LLM como fallback para verificación** — búsqueda por patrón regex primero, LLM si ambiguo:
```python
import re
import logging
from typing import Optional

logger = logging.getLogger("cobranza.identity_verifier")

# Patrones simples primero (sin LLM, sub-100ms)
_CONFIRM_PATTERNS = re.compile(
    r"\b(si|soy|claro|correcto|eso es|afirmativo|con gusto)\b", re.I
)
_DENY_PATTERNS = re.compile(
    r"\b(no|incorrecto|equivocado|otro numero|no es aqui)\b", re.I
)

async def verify_identity(utterance: str, debtor_name: str) -> dict:
    """Verifica si el utterance confirma que el deudor es quien contesta."""
    if _CONFIRM_PATTERNS.search(utterance):
        return {"confirmed": True, "confidence": "high"}
    if _DENY_PATTERNS.search(utterance):
        return {"confirmed": False, "confidence": "high"}
    # Fallback: LLM ligero (gpt-4o-mini, no realtime)
    return await _llm_verify(utterance, debtor_name)
```

---

### `backend/cobranza/sub_agents/escalation_handler.py` (service, CRUD)

**Analog:** `backend/cobranza/debtor_crud.py` (update_debtor) + `voice_orchestrator.py` (escalate path, líneas 148-157)

**Pattern de escalación** (voice_orchestrator.py líneas 148-157):
```python
if action == "escalate":
    self.state = "ended_escalated"
    self.intentos_failed += 1
    if self.intentos_failed >= self.debtor.get("max_intentos", 5):
        logger.warning("[Orchestrator] Max intentos reached for debtor %s", ...)
        return response_text
```

**Update MongoDB + WS push** (voice_router.py líneas 195-242, `_process_call_ended`):
```python
await db.debtors.update_one(
    {"_id": debtor_oid},
    {
        "$set": {"estado": new_estado, "updated_at": now},
        "$inc": {"intentos": 1},
        "$push": {"historial_llamadas": call_record},
    },
)
# Push WS event al dashboard
try:
    from main import manager
    await manager.send_to_user(
        str(debtor["user_id"]),
        {"type": "debtor_update", "debtor_id": str(debtor["_id"]), "estado": new_estado},
    )
except Exception as ws_exc:
    logger.warning("[PostCall] WS push failed (non-fatal): %s", ws_exc)
```

---

### `backend/cobranza/voice_pipecat.py` (MODIFY — Telnyx + Gemini Live)

**Analog:** sí mismo (voice_pipecat.py) — 3 cambios quirúrgicos

**Cambio 1 — Imports (líneas 25-31, reemplazar):**
```python
# ANTES:
from pipecat.serializers.twilio import TwilioFrameSerializer
from pipecat.services.openai.realtime.llm import OpenAIRealtimeLLMService
from pipecat.services.openai.realtime import events as rt_events

# DESPUÉS:
from pipecat.serializers.telnyx import TelnyxFrameSerializer
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
# Agregar también:
from cobranza.config_cache import get_tenant_config, invalidate_tenant_config
```

**Cambio 2 — Transport (líneas 205-220, reemplazar bloque transport):**
```python
# ANTES (Twilio, 24kHz):
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_sample_rate=24000,
        audio_out_sample_rate=24000,
        serializer=TwilioFrameSerializer(stream_sid=stream_sid, ...),
    ),
)

# DESPUÉS (Telnyx, 8kHz PCMU):
transport = FastAPIWebsocketTransport(
    websocket=websocket,
    params=FastAPIWebsocketParams(
        audio_in_enabled=True,
        audio_out_enabled=True,
        audio_in_sample_rate=8000,    # CRÍTICO: Telnyx usa 8kHz, NO 24kHz
        audio_out_sample_rate=8000,
        vad_enabled=False,
        serializer=TelnyxFrameSerializer(
            stream_id=stream_id,
            outbound_encoding="PCMU",
            inbound_encoding="PCMU",
            call_control_id=call_control_id,
            api_key=os.getenv("TELNYX_API_KEY"),
        ),
    ),
)
```

**Cambio 3 — LLM (líneas 244-270, reemplazar bloque llm):**
```python
# ANTES (OpenAI Realtime):
llm = OpenAIRealtimeLLMService(
    api_key=os.getenv("OPENAI_API_KEY"),
    settings=OpenAIRealtimeLLMService.Settings(
        model="gpt-4o-realtime-preview-2024-12-17",
        system_instruction=system_prompt,
        ...
    ),
)

# DESPUÉS (Gemini Live):
llm = GeminiLiveLLMService(
    api_key=os.getenv("GOOGLE_API_KEY"),
    system_instruction=system_prompt,   # cargado de tenant_configs via Redis
    tools=[end_call_tool, update_debtor_tool, send_whatsapp_tool, verify_identity_tool, escalate_tool],
    params=GeminiLiveLLMService.InputParams(
        voice_id="Charon",
        language_code="es-419",
    ),
)
```

**Cambio 4 — Hot-reload system_prompt desde tenant_configs (nuevo bloque antes de transport):**
```python
# HOT-RELOAD: Redis cache (5min TTL) → MongoDB fallback
tenant_config = await get_tenant_config(user_id)
if not tenant_config.get("modules", {}).get("voice", True):
    await websocket.close(1008, "Voice module disabled")
    return CallResult()

system_prompt = tenant_config.get("voice_system_prompt") or _build_default_prompt(debtor, estrategia)
brand_name = tenant_config.get("brand_name", "nuestra empresa")
# string.replace() — SIN template engine (decisión locked)
system_prompt = system_prompt.replace("{brand_name}", brand_name)
system_prompt = system_prompt.replace("{debtor_name}", debtor.get("nombre", ""))
```

**Cambio 5 — end_call handler (líneas 321-339, reemplazar twilio por telnyx):**
```python
# ANTES: twilio_client.calls(call_sid).update(status="completed")
# DESPUÉS: TelnyxFrameSerializer maneja hang-up automáticamente si api_key está presente.
# Solo remover el bloque `from twilio.rest import Client` y el `twilio_client.calls(...)`.
# El EndFrame es suficiente.
async def _handle_end_call(params):
    reason = params.arguments.get("reason", "conversacion finalizada")
    logger.info("[VOICE] end_call invoked: reason=%s", reason)
    await params.result_callback({"status": "ending", "reason": reason})
    import asyncio
    await asyncio.sleep(4.0)
    # TelnyxFrameSerializer con api_key maneja hang-up automaticamente
    await task.queue_frames([EndFrame()])
```

---

### `backend/cobranza/voice_router.py` (MODIFY — Telnyx webhook)

**Analog:** sí mismo (voice_router.py) — 2 cambios quirúrgicos

**Cambio 1 — Webhook TwiML → TeXML (líneas 38-56, reemplazar):**
```python
# ANTES:
@router.post("/webhook")
async def twiml_webhook(request: Request):
    from twilio.twiml.voice_response import VoiceResponse, Connect
    form = dict(await request.form())
    call_sid = form.get("CallSid", "unknown")
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)
    return PlainTextResponse(str(response), media_type="application/xml")

# DESPUÉS (TeXML — misma idea, formato Telnyx):
@router.post("/webhook")
async def telnyx_webhook(request: Request):
    form = dict(await request.form())
    call_control_id = form.get("call_control_id", "unknown")
    host = os.getenv("VOICE_WEBHOOK_HOST", "").replace("https://", "").replace("http://", "")
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_control_id}"
    texml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Connect>
    <Stream url="{ws_url}" bidirectionalMode="rtp" />
  </Connect>
  <Pause length="40"/>
</Response>"""
    return PlainTextResponse(texml, media_type="application/xml")
```

**Cambio 2 — initiate_call_v2 (líneas 276-299, reemplazar bloque twilio):**
```python
# ANTES: from twilio.rest import Client + client.calls.create(...)
# DESPUÉS:
import telnyx
telnyx.api_key = os.getenv("TELNYX_API_KEY")
call = await asyncio.to_thread(
    telnyx.Call.create,
    connection_id=os.getenv("TELNYX_CONNECTION_ID"),
    to=to_number,
    from_=os.getenv("TELNYX_VOICE_PHONE_NUMBER"),
    webhook_url=f"{webhook_url}/api/cobranza/voice/webhook",
)
call_control_id = call.call_control_id
```

**Cambio 3 — WebSocket: parse_telephony_websocket en lugar de esperar start manual:**
```python
# ANTES: bucle manual esperando event == "start" para obtener stream_sid
# DESPUÉS: usar parse_telephony_websocket (verificar que exista en pipecat 0.0.108):
# from pipecat.runner.utils import parse_telephony_websocket
# transport_type, call_data = await parse_telephony_websocket(websocket)
# stream_id = call_data["stream_id"]
# call_control_id = call_data["call_control_id"]
# Si parse_telephony_websocket no existe en 0.0.108: mantener bucle manual adaptado a formato Telnyx.
```

---

### `backend/cobranza/rag_service.py` (service, batch + request-response)

**Analog:** `backend/rag.py`

**Imports pattern** (rag.py líneas 1-17):
```python
import math
import os
import logging
import asyncio
from typing import Optional

logger = logging.getLogger("rag")
EMBED_MODEL = "text-embedding-3-small"
```

**Text extraction pattern** (rag.py líneas 26-79) — reusar funciones existentes:
```python
from rag import extract_text, fetch_url_text  # reusar extractores existentes
```

**Chunking — RecursiveCharacterTextSplitter en lugar de chunk_text manual** (reemplaza rag.py líneas 84-99):
```python
# ANTES (hand-rolled):
def chunk_text(text: str, chunk_size: int = 600, overlap: int = 80) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        ...

# DESPUÉS (langchain-text-splitters, decisión locked):
from langchain_text_splitters import RecursiveCharacterTextSplitter

def chunk_text_for_rag(text: str) -> list[str]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=100,
        length_function=len,
        is_separator_regex=False,
    )
    return splitter.split_text(text)
```

**Pinecone upsert con namespace isolation** (de RESEARCH.md Pattern 4):
```python
from pinecone.asyncio import AsyncPinecone

async def upsert_to_pinecone(user_id: str, vectors: list[dict]) -> None:
    assert user_id, "user_id requerido para namespace isolation en Pinecone"
    pc = AsyncPinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "cobranza-rag"))
    await index.upsert(vectors=vectors, namespace=user_id)   # SIEMPRE namespace=user_id

async def query_pinecone(user_id: str, query_vector: list[float], top_k: int = 5) -> list[dict]:
    assert user_id, "user_id requerido para namespace isolation en Pinecone"
    pc = AsyncPinecone(api_key=os.getenv("PINECONE_API_KEY"))
    index = pc.Index(os.getenv("PINECONE_INDEX_NAME", "cobranza-rag"))
    result = await index.query(
        vector=query_vector,
        top_k=top_k,
        namespace=user_id,      # SIEMPRE namespace=user_id, NUNCA None
        include_metadata=True,
    )
    return result["matches"]
```

**Embedding — reusar OpenAI text-embedding-3-small** (de rag.py):
```python
# rag.py ya usa OPENAI_API_KEY + text-embedding-3-small — reusar la función de embed
from rag import embed_text  # si existe, o copiar el patrón directo
```

**rag_documents MongoDB CRUD** — seguir patrón de `save_knowledge_chunk` (database.py líneas 672-693):
```python
async def save_rag_document_metadata(
    user_id: str,
    filename: str,
    source_type: str,
    chunk_count: int,
) -> str:
    db = get_db()
    result = await db.rag_documents.insert_one({
        "user_id": user_id,
        "pinecone_namespace": user_id,   # = user_id siempre
        "filename": filename,
        "source_type": source_type,      # "pdf" | "url" | "text"
        "chunk_count": chunk_count,
        "created_at": datetime.now(timezone.utc),
    })
    return str(result.inserted_id)
```

---

### `backend/routers/tenant_admin.py` (route, CRUD)

**Analog:** `backend/routers/knowledge.py` + `backend/routers/prospect.py`

**Imports pattern** (knowledge.py líneas 1-14 + prospect.py líneas 1-22):
```python
import os
import logging
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field

from auth import get_current_user
from database import get_db
```

**Auth guard — get_current_user para todos los endpoints** (prospect.py línea 65):
```python
@router.post("/api/cobranza/config/{user_id}")
async def update_tenant_config(
    user_id: str,
    request: TenantConfigUpdateRequest,
    current_user: dict = Depends(get_current_user),   # SIEMPRE Depends(get_current_user)
):
    # CRÍTICO: enforcement de tenant isolation — user solo puede escribir su propio config
    if str(current_user["user_id"]) != user_id:
        raise HTTPException(403, "No autorizado")
    ...
```

**File upload pattern** (knowledge.py líneas 24-49):
```python
@router.post("/api/cobranza/config/{user_id}/rag/upload")
async def upload_rag_document(
    user_id: str,
    files: List[UploadFile] = File(...),
    current_user: dict = Depends(get_current_user),
):
    if str(current_user["user_id"]) != user_id:
        raise HTTPException(403, "No autorizado")
    results = []
    for file in files:
        file_bytes = await file.read()
        if not file_bytes:
            results.append({"filename": file.filename, "error": "empty file"})
            continue
        try:
            # usar rag_service.ingest_document(user_id, ...)
            ...
        except Exception as e:
            results.append({"filename": file.filename, "error": str(e)})
    return results
```

**Pydantic request models** (staff.py líneas 36-53, prospect.py líneas 29-59):
```python
class TenantConfigUpdateRequest(BaseModel):
    modules: Optional[dict] = None          # {"voice": True, "whatsapp": True}
    voice_system_prompt: Optional[str] = Field(None, max_length=2000)  # ASVS V5
    brand_name: Optional[str] = Field(None, max_length=200)
    language: Optional[str] = None

class AgentInstanceUpdateRequest(BaseModel):
    model: Optional[str] = None
    temperature: Optional[float] = None
    tools_enabled: Optional[list[str]] = None
    new_prompt: Optional[str] = Field(None, max_length=2000)  # dispara rotación de historia
```

**Module toggle con Redis invalidation** (combinar database.py upsert + RESEARCH.md Pattern 1):
```python
@router.patch("/api/cobranza/config/{user_id}/modules")
async def toggle_module(
    user_id: str,
    request: ModuleToggleRequest,
    current_user: dict = Depends(get_current_user),
):
    if str(current_user["user_id"]) != user_id:
        raise HTTPException(403, "No autorizado")
    db = get_db()
    now = datetime.now(timezone.utc)
    await db.tenant_configs.update_one(
        {"user_id": user_id},
        {"$set": {f"modules.{request.module}": request.enabled, "updated_at": now}},
        upsert=True,
    )
    # INMEDIATO: invalidar cache para que el siguiente call lo detecte
    from cobranza.config_cache import invalidate_tenant_config
    await invalidate_tenant_config(user_id)
    return {"ok": True, "module": request.module, "enabled": request.enabled}
```

**Error handling** (knowledge.py líneas 38-48, prospect.py patrón):
```python
try:
    async with asyncio.timeout(30):
        result = await some_async_operation()
except TimeoutError:
    raise HTTPException(504, "Operation timed out")
except Exception as e:
    logger.error("[tenant_admin] %s: %s", endpoint_name, e, exc_info=True)
    raise HTTPException(500, f"Error: {str(e)[:100]}")
```

---

## Shared Patterns

### Redis Cache (config_cache.py — nuevo archivo helper)
**Fuente:** RESEARCH.md Pattern 1 (combinado con `redis` ya instalado v5.3.1)
**Aplicar a:** `voice_pipecat.py` (al inicio de run_bot), `tenant_admin.py` (en toggles)

```python
# backend/cobranza/config_cache.py
import json
import os
import redis.asyncio as aioredis
from database import get_db

_redis_client = None

async def get_redis():
    global _redis_client
    if _redis_client is None:
        url = os.getenv("UPSTASH_REDIS_URL") or os.getenv("REDIS_URL", "redis://localhost:6379")
        # CRÍTICO: Upstash requiere rediss:// (SSL). Railway Redis usa redis://
        _redis_client = aioredis.from_url(url, encoding="utf-8", decode_responses=True)
    return _redis_client

async def get_tenant_config(user_id: str) -> dict:
    redis = await get_redis()
    key = f"tenant_config:{user_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    db = get_db()
    doc = await db.tenant_configs.find_one({"user_id": user_id}) or {}
    if doc:
        doc.pop("_id", None)
        await redis.setex(key, 300, json.dumps(doc))  # TTL 5 minutos
    return doc

async def invalidate_tenant_config(user_id: str) -> None:
    redis = await get_redis()
    await redis.delete(f"tenant_config:{user_id}")
```

### Auth guard — tenant isolation enforcement
**Fuente:** `backend/routers/prospect.py` (Depends(get_current_user)) + `backend/routers/staff.py`
**Aplicar a:** todos los endpoints en `tenant_admin.py`

```python
from auth import get_current_user

# Patrón estándar para endpoints de tenant:
current_user: dict = Depends(get_current_user)
user_id = str(current_user["user_id"])
# Siempre verificar que el user_id del path == user_id del JWT
if user_id != path_user_id:
    raise HTTPException(403, "No autorizado")
```

### Error handling + logging
**Fuente:** `backend/cobranza/voice_router.py` líneas 160-169 + `backend/cobranza/debtor_crud.py`
**Aplicar a:** todos los nuevos archivos

```python
logger = logging.getLogger("cobranza.<module_name>")

try:
    result = await some_operation()
    logger.info("[MODULE] Operation OK: %s", result)
except HTTPException:
    raise  # nunca envolver HTTPException
except Exception as e:
    logger.error("[MODULE] Operation failed: %s: %s", type(e).__name__, e, exc_info=True)
    raise HTTPException(500, f"Error: {str(e)[:100]}")
```

### ObjectId serialization
**Fuente:** `backend/cobranza/debtor_crud.py` líneas 17-23
**Aplicar a:** `tenant_config.py`, `rag_service.py`

```python
def _serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc
```

### Post-call WS push al dashboard
**Fuente:** `backend/cobranza/voice_router.py` líneas 229-242
**Aplicar a:** `sub_agents/debtor_updater.py`, `sub_agents/escalation_handler.py`

```python
try:
    from main import manager
    await manager.send_to_user(
        str(user_id),
        {"type": "debtor_update", "debtor_id": debtor_id, "estado": new_estado},
    )
except Exception as ws_exc:
    logger.warning("[sub_agent] WS push failed (non-fatal): %s", ws_exc)
```

---

## Archivos sin análogo (no-analog)

| Archivo | Role | Data Flow | Razón |
|---------|------|-----------|-------|
| `backend/cobranza/config_cache.py` | utility | request-response | No hay Redis cache helper en el codebase. Solo existe `redis==5.3.1` instalado. El patrón viene de RESEARCH.md Pattern 1. |

---

## Notas críticas para el planner

1. **`voice_pipecat.py` línea 102-124** — El bucle manual esperando `event == "start"` de Twilio debe reemplazarse con el handshake de Telnyx. Si `parse_telephony_websocket` no existe en pipecat 0.0.108, mantener bucle manual adaptado: el campo cambia de `"streamSid"` a `"stream_id"` y `"call_control_id"`.

2. **`requirements.txt`** — Wave 0 DEBE agregar ANTES de cualquier código de Gemini Live:
   ```
   pipecat-ai[google]
   google-genai>=2.8.0
   pinecone>=9.1.0
   pinecone[asyncio]
   langchain-text-splitters>=1.1.2
   telnyx  # verificar: pip index versions telnyx
   ```

3. **`database.py` `init_db()`** — Agregar los 4 índices nuevos al final de la función usando `_safe_index` (líneas 22-28 de database.py como modelo exacto).

4. **`prompt_history` rotation** — Seguir EXACTAMENTE el patrón de `update_wa_session` (database.py líneas 1182-1205): dos ops separadas, NO `$push $slice` en una sola op.

5. **Pinecone namespace** — NUNCA pasar `namespace=None`. Agregar `assert user_id` como guardia en `rag_service.py`.

6. **Gemini Live audio rate** — `audio_in_sample_rate=8000` y `audio_out_sample_rate=8000`. El codebase actual usa 24000 — cambiar ambos valores.

---

## Metadata

**Scope de búsqueda de análogos:**
- `backend/cobranza/` (18 archivos)
- `backend/routers/` (13 archivos)
- `backend/database.py` (1752 líneas)
- `backend/rag.py`

**Archivos escaneados:** 35
**Fecha de extracción de patrones:** 2026-06-10
