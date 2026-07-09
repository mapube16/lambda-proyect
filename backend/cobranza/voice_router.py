"""
voice_router.py — FastAPI endpoints for Pipecat voice orchestrator.

Endpoints:
1. POST /webhook — TeXML (Telnyx; upgrades to WebSocket)
2. WebSocket /ws/{call_control_id} — Pipecat pipeline handles everything
3. POST /call/initiate-v2 — Outbound call initiation via Telnyx Call Control
"""
import logging
import os
import asyncio
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor
from cobranza.voice_pipecat import run_bot, CallResult
from services.connection_manager import manager as _ws_manager

_TERMINAL_ESTADOS = {"promesa_de_pago", "escalado", "pagado", "reagendado", "disputa", "pago_reportado", "pausado"}

logger = logging.getLogger("cobranza.voice")

router = APIRouter(prefix="/api/cobranza/voice", tags=["voice"])


class VoiceCallInitRequest(BaseModel):
    debtor_id: str


# ── TeXML Webhook (Telnyx) ───────────────────────────────────────────────────


@router.post("/webhook")
async def twilio_webhook(request: Request):
    """
    Twilio calls this when a call connects — SALIENTE (outbound-api, nosotros
    marcamos) o ENTRANTE de verdad (inbound, un deudor devuelve la llamada,
    informe §9.4). `Direction` en el form distingue los dos casos; antes de
    este fix, un `From` forjado igual al de un deudor real podía hacer que
    ARIA recitara sus datos sin que hubiese llamada real — por eso la firma
    de Twilio ahora es obligatoria (antes no se validaba acá).
    """
    form = dict(await request.form())
    if not _twilio_signature_ok(request, form, "/api/cobranza/voice/webhook"):
        raise HTTPException(403, "Invalid Twilio signature")

    call_sid = form.get("CallSid", "unknown")
    direction = form.get("Direction", "")
    answered_by = form.get("AnsweredBy", "")
    logger.info("[Webhook] TWILIO call %s (Direction=%s AnsweredBy=%s)", call_sid, direction, answered_by)

    # AMD: if a machine/voicemail answered, hang up immediately. Streaming to a
    # voicemail wastes Gemini tokens and leaves a zombie pipeline running for
    # minutes (the recording never says goodbye, so end_call never fires).
    if answered_by.startswith("machine") or answered_by == "fax":
        logger.warning("[Webhook] %s answered by %s — hanging up (no stream)", call_sid, answered_by)
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
            media_type="application/xml",
        )

    if direction == "inbound":
        return await _handle_inbound_call(call_sid, form)

    host = (
        os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
        .replace("https://", "")
        .replace("http://", "")
    )
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_sid}"

    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Connect><Stream url="{ws_url}" /></Connect>'
        "</Response>"
    )
    logger.info("[Webhook] TwiML -> Stream %s", ws_url)
    return PlainTextResponse(twiml, media_type="application/xml")


_SIN_MATCH_TWIML = (
    '<?xml version="1.0" encoding="UTF-8"?><Response>'
    '<Say language="es-MX">Gracias por llamar a DPG Seguros. '
    "No pudimos verificar su información en este momento, "
    "un asesor se comunicará con usted pronto.</Say><Hangup/></Response>"
)


async def _handle_inbound_call(call_sid: str, form: dict):
    """§9.4: un deudor devuelve la llamada perdida. CUALQUIERA puede llamar a
    este número — la identidad NUNCA se decide por el teléfono desde el que
    marca (puede llamar desde un celular prestado, uno nuevo, un fijo), la
    decide SIEMPRE el número de documento marcado por teclado. Este primer
    paso solo reproduce el saludo + Gather DTMF; la resolución real ocurre en
    /inbound/document-captured."""
    host_raw = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

    import pytz
    hora_co = datetime.now(pytz.timezone("America/Bogota")).hour
    variante = "manana" if hora_co < 12 else "tarde"
    greeting_url = f"{host_raw}/api/cobranza/voice/static/inbound-greeting/{variante}"
    action_url = f"{host_raw}/api/cobranza/voice/inbound/document-captured"

    # DTMF (teclado), no voz: con cientos de deudores distintos, un STT de
    # nombre hablado es fragil (acentos, nombres parecidos, audio de
    # telefono) — el numero de documento marcado por teclado es una
    # comparacion EXACTA (informe: valida identidad por numero de documento).
    # finishOnKey="#" porque las cedulas colombianas no tienen longitud fija.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf" finishOnKey="#" timeout="15" action="{action_url}" method="POST">'
        f"<Play>{greeting_url}</Play>"
        "</Gather>"
        '<Say language="es-MX">No recibimos respuesta. Que tenga un buen día.</Say>'
        "<Hangup/></Response>"
    )
    logger.info("[Webhook][Inbound] %s from=%s -> saludo=%s", call_sid, form.get("From"), variante)
    return PlainTextResponse(twiml, media_type="application/xml")


async def _alerta_llamada_no_identificada(db, detalle: str) -> None:
    """Alerta cuando un desconocido llama (0 matches por documento) — antes
    esto NO generaba ninguna alerta pese a que el mensaje hablado promete
    'un asesor se comunicará con usted'. Sin un deudor resuelto no hay a
    quién atribuirla; se manda al primer tenant con cobranza activa (hoy
    solo DPG). Nunca lanza — no puede tumbar la llamada."""
    try:
        from cobranza.sequence_engine import _tenant_ids
        from cobranza.alerts import crear_alerta
        tenant_ids = await _tenant_ids(db)
        if not tenant_ids:
            return
        await crear_alerta(
            db, tenant_ids[0], {}, "llamada_entrante_no_identificada", detalle=detalle,
        )
    except Exception:
        logger.exception("[Inbound] alerta no_identificada falló (no fatal)")


_DYNAMIC_VOICE_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "voice_dynamic")


async def _synthesize_aoede(text: str) -> bytes | None:
    """TTS con la MISMA voz de ARIA (Gemini, voice_id='Aoede' — igual que
    scripts/gen_inbound_greeting.py y voice_pipecat.py) para que la
    enumeración de pólizas suene consistente con el resto de la llamada, no
    con la voz robótica por defecto de Twilio. None si falla (el llamador
    debe tener un fallback — nunca debe tumbar la llamada)."""
    import httpx
    import wave
    import base64
    import io

    key = os.getenv("GOOGLE_API_KEY")
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://generativelanguage.googleapis.com/v1beta/models/"
                "gemini-2.5-flash-preview-tts:generateContent",
                params={"key": key},
                json={
                    "contents": [{"parts": [{"text": text}]}],
                    "generationConfig": {
                        "responseModalities": ["AUDIO"],
                        "speechConfig": {
                            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Aoede"}}
                        },
                    },
                },
            )
            r.raise_for_status()
            part = r.json()["candidates"][0]["content"]["parts"][0]["inlineData"]
            pcm = base64.b64decode(part["data"])
    except Exception:
        logger.exception("[Inbound] _synthesize_aoede falló (usará fallback Twilio)")
        return None

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm)
    return buf.getvalue()


@router.get("/inbound/policy-audio/{call_sid}")
async def get_policy_audio(call_sid: str):
    """Sirve el WAV generado al vuelo por _pedir_seleccion_poliza (voz Aoede).
    Se borra después de servirlo — es contenido de una sola llamada."""
    from fastapi.responses import FileResponse
    from starlette.background import BackgroundTask

    path = os.path.join(_DYNAMIC_VOICE_DIR, f"{call_sid}.wav")
    if not os.path.exists(path):
        raise HTTPException(404, "audio not found")
    return FileResponse(
        path, media_type="audio/wav",
        background=BackgroundTask(lambda: os.path.exists(path) and os.remove(path)),
    )


async def _pedir_seleccion_poliza(db, call_sid: str, from_number: str, digits: str, candidates: list) -> PlainTextResponse:
    """El documento marcado matcheó 2+ pólizas del mismo titular (mismo
    documento = misma persona, no es fuga de datos enumerarlas). Las lee
    numeradas — más urgente primero, con la voz de ARIA — y pide elegir por
    teclado, ANTES de conectar nada; el pipeline solo arranca una vez hay
    UNA póliza resuelta, así que no hay riesgo de mezclar datos entre
    pólizas de la misma persona.
    """
    from xml.sax.saxutils import escape as _xml_escape

    ids = [str(d["_id"]) for d in candidates]
    await db.cobranza_calls_in_progress.update_one(
        {"call_sid": call_sid},
        {"$set": {
            "call_sid": call_sid, "candidate_ids": ids, "from_number": from_number,
            "documento": digits, "started_at": datetime.now(timezone.utc),
            "direction": "inbound", "pending_policy_selection": True,
        }},
        upsert=True,
    )

    partes = []
    for i, d in enumerate(candidates, start=1):
        ramo = d.get("ramo_nombre") or "su póliza"
        riesgo = d.get("objeto_asegurado")
        desc = f"{ramo}, {riesgo}" if riesgo else f"{ramo}, póliza {d.get('numero_poliza', '')}"
        partes.append(f"Para la póliza de {desc}, marque {i}.")
    enumeracion = f"Encontramos {len(candidates)} pólizas asociadas a su documento. " + " ".join(partes)

    host_raw = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
    action_url = f"{host_raw}/api/cobranza/voice/inbound/policy-selected"

    wav_bytes = await _synthesize_aoede(enumeracion)
    if wav_bytes:
        os.makedirs(_DYNAMIC_VOICE_DIR, exist_ok=True)
        with open(os.path.join(_DYNAMIC_VOICE_DIR, f"{call_sid}.wav"), "wb") as f:
            f.write(wav_bytes)
        prompt_tag = f"<Play>{host_raw}/api/cobranza/voice/inbound/policy-audio/{call_sid}</Play>"
    else:
        # Fallback si Gemini TTS falla (cuota, red): sigue siendo audible y
        # correcto, solo con la voz por defecto de Twilio en vez de Aoede.
        prompt_tag = f'<Say language="es-MX">{_xml_escape(enumeracion)}</Say>'

    # SOLO finishOnKey (sin numDigits): con numDigits="1" el Gather se cerraba
    # apenas llegaba el PRIMER digito, y el "#" que la persona presiona despues
    # por costumbre (mismo habito que el paso del documento) llegaba tarde —
    # se colaba como tono DTMF crudo dentro del <Connect><Stream> YA conectado
    # a Gemini Live, que al "oir" el pitido en vez de voz respondia confundido
    # en otro idioma (observado en pruebas reales). finishOnKey="#" solo hace
    # que el Gather espere el mismo gesto que ya funciona en el paso anterior.
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Gather input="dtmf" finishOnKey="#" timeout="15" action="{action_url}" method="POST">'
        f"{prompt_tag}"
        "</Gather>"
        '<Say language="es-MX">No recibimos respuesta. Que tenga un buen día.</Say>'
        "<Hangup/></Response>"
    )
    logger.info(
        "[Inbound][DocumentCaptured] %s documento %r -> %d pólizas, pidiendo selección (voz=%s)",
        call_sid, digits, len(candidates), "aoede" if wav_bytes else "twilio-fallback",
    )
    return PlainTextResponse(twiml, media_type="application/xml")


@router.post("/inbound/policy-selected")
async def inbound_policy_selected(request: Request):
    """Respuesta al Gather de _pedir_seleccion_poliza: qué póliza (de las
    varias que comparten documento) eligió por teclado."""
    form = dict(await request.form())
    if not _twilio_signature_ok(request, form, "/api/cobranza/voice/inbound/policy-selected"):
        raise HTTPException(403, "Invalid Twilio signature")

    call_sid = form.get("CallSid", "")
    from_number = form.get("From", "")
    digits = "".join(c for c in form.get("Digits", "") if c.isdigit())
    db = get_db()

    pending = await db.cobranza_calls_in_progress.find_one(
        {"call_sid": call_sid, "pending_policy_selection": True}
    )
    if not pending:
        logger.warning("[Inbound][PolicySelected] %s sin selección pendiente", call_sid)
        return PlainTextResponse(_SIN_MATCH_TWIML, media_type="application/xml")

    candidate_ids = pending.get("candidate_ids") or []
    try:
        idx = int(digits) - 1
    except ValueError:
        idx = -1

    if idx < 0 or idx >= len(candidate_ids):
        logger.warning(
            "[Inbound][PolicySelected] %s selección inválida digits=%r (de %d opciones)",
            call_sid, digits, len(candidate_ids),
        )
        await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        return PlainTextResponse(_SIN_MATCH_TWIML, media_type="application/xml")

    debtor = await db.debtors.find_one({"_id": ObjectId(candidate_ids[idx])})
    if not debtor:
        await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        return PlainTextResponse(_SIN_MATCH_TWIML, media_type="application/xml")

    user_id = str(debtor["user_id"])
    await db.cobranza_calls_in_progress.update_one(
        {"call_sid": call_sid},
        {
            "$set": {
                "user_id": user_id, "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
                "debtor_phone": from_number, "direction": "inbound",
                "caller_stated_document": pending.get("documento", ""),
            },
            "$unset": {"pending_policy_selection": "", "candidate_ids": ""},
        },
    )

    host = (
        os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
        .replace("https://", "")
        .replace("http://", "")
    )
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_sid}"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Connect><Stream url="{ws_url}" /></Connect></Response>'
    )
    logger.info(
        "[Inbound][PolicySelected] %s eligió póliza %s (%s) -> Stream",
        call_sid, debtor.get("numero_poliza"), debtor.get("nombre"),
    )
    return PlainTextResponse(twiml, media_type="application/xml")


@router.post("/inbound/document-captured")
async def inbound_document_captured(request: Request):
    """Twilio <Gather input="dtmf"> post-back con el número de documento
    marcado. Busca el deudor por documento (NO por teléfono — cualquiera con
    registro puede llamar desde cualquier número) y recién ahí conecta el
    stream. 0 matches = desconocido real (alerta + mensaje, sin revelar
    nada); 2+ matches = mismo documento en varias pólizas, se enumeran y se
    pide elegir por teclado (_pedir_seleccion_poliza)."""
    form = dict(await request.form())
    if not _twilio_signature_ok(request, form, "/api/cobranza/voice/inbound/document-captured"):
        raise HTTPException(403, "Invalid Twilio signature")

    call_sid = form.get("CallSid", "")
    from_number = form.get("From", "")
    digits = "".join(c for c in form.get("Digits", "") if c.isdigit())
    db = get_db()

    if not digits:
        logger.warning("[Inbound][DocumentCaptured] %s sin dígitos válidos", call_sid)
        return PlainTextResponse(_SIN_MATCH_TWIML, media_type="application/xml")

    # Match tolerante a puntuación: ~40% de los documentos de DPG son NITs con
    # guión + dígito de verificación ("801001470-9", persona jurídica) — el
    # saludo le pide al que llama NO marcar ese último dígito, así que solo
    # comparamos contra la parte ANTES del guión. Un documento sin guión
    # (cédula) se compara completo, sin cambios. El tenant es chico (~600
    # deudores), escanear en Python es instantáneo y evita mantener un índice
    # normalizado aparte.
    def _documento_base(stored) -> str:
        s = str(stored or "")
        s = s.split("-")[0] if "-" in s else s
        return "".join(c for c in s if c.isdigit())

    from cobranza.sequence_engine import _tenant_ids
    candidates = []
    for user_id in await _tenant_ids(db):
        async for d in db.debtors.find(
            {"user_id": user_id, "cliente_documento": {"$nin": [None, ""]}},
            {"cliente_documento": 1, "nombre": 1, "numero_poliza": 1, "fecha_pago": 1,
             "vencimiento": 1, "user_id": 1, "telefono": 1, "ramo_nombre": 1,
             "objeto_asegurado": 1},
        ):
            if _documento_base(d.get("cliente_documento")) == digits:
                candidates.append(d)

    if not candidates:
        logger.warning(
            "[Inbound][DocumentCaptured] %s from=%s digitos=%r -> 0 deudores, desconocido real",
            call_sid, from_number, digits,
        )
        await _alerta_llamada_no_identificada(
            db, f"Llamada entrante de {from_number}: marcó el documento '{digits}', "
                f"que no corresponde a ningún deudor registrado.",
        )
        return PlainTextResponse(_SIN_MATCH_TWIML, media_type="application/xml")

    if len(candidates) > 1:
        # Mismo documento en 2+ pólizas (mismo titular) — el documento YA
        # confirmó que es la misma persona dueña de todas ellas, así que no
        # es una fuga de datos enumerarlas. En vez de adivinar cuál le
        # interesa, se las leemos numeradas (más urgente primero) y elige
        # por teclado — mismo mecanismo confiable que el documento.
        def _urgencia(d: dict):
            venc = d.get("fecha_pago") or d.get("vencimiento")
            return str(venc)[:10] if venc else "9999-99-99"
        candidates.sort(key=_urgencia)
        return await _pedir_seleccion_poliza(db, call_sid, from_number, digits, candidates)

    debtor = candidates[0]
    user_id = str(debtor["user_id"])
    await db.cobranza_calls_in_progress.insert_one({
        "call_sid": call_sid, "user_id": user_id,
        "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
        "debtor_phone": from_number, "started_at": datetime.now(timezone.utc),
        "direction": "inbound", "caller_stated_document": digits,
    })

    host = (
        os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
        .replace("https://", "")
        .replace("http://", "")
    )
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_sid}"
    twiml = (
        '<?xml version="1.0" encoding="UTF-8"?><Response>'
        f'<Connect><Stream url="{ws_url}" /></Connect></Response>'
    )
    logger.info("[Inbound][DocumentCaptured] %s documento OK, debtor=%s -> Stream", call_sid, debtor.get("nombre"))
    return PlainTextResponse(twiml, media_type="application/xml")


# ── Call Status Callback (consumo del paquete de minutos) ───────────────────


def _twilio_signature_ok(request: Request, form: dict, path: str) -> bool:
    """
    Valida X-Twilio-Signature contra la URL pública. El ledger de minutos es
    ruta de facturación: un callback forjado inflaría el consumo del cliente.
    Sin TWILIO_AUTH_TOKEN (dev local) no se valida.
    """
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        return True
    try:
        from twilio.request_validator import RequestValidator
        url = f"{os.getenv('VOICE_WEBHOOK_HOST', 'http://localhost:8002')}{path}"
        signature = request.headers.get("X-Twilio-Signature", "")
        return RequestValidator(token).validate(url, form, signature)
    except Exception:
        logger.exception("[CallStatus] signature validation error")
        return False


@router.post("/call-status")
async def call_status_callback(request: Request):
    """
    Twilio lo llama al terminar la llamada (evento 'completed') con CallDuration.
    Registra el consumo del paquete de minutos (idempotente por CallSid).
    """
    form = dict(await request.form())
    if not _twilio_signature_ok(request, form, "/api/cobranza/voice/call-status"):
        raise HTTPException(403, "Invalid Twilio signature")

    call_sid = form.get("CallSid", "")
    call_status = form.get("CallStatus", "")
    duration = int(form.get("CallDuration") or 0)
    logger.info("[CallStatus] %s status=%s duration=%ss", call_sid, call_status, duration)

    if call_status == "completed":
        from cobranza import minutes
        await minutes.record_call_consumption(get_db(), call_sid, duration)
    return PlainTextResponse("OK")


# ── Recording Callback ──────────────────────────────────────────────────────


@router.post("/recording-callback")
async def recording_callback(request: Request):
    """Twilio sends this when a call recording is ready."""
    form = dict(await request.form())
    call_sid = form.get("CallSid", "")
    recording_url = form.get("RecordingUrl", "")
    recording_sid = form.get("RecordingSid", "")
    duration = int(form.get("RecordingDuration", 0))

    logger.info("[Recording] call=%s, sid=%s, duration=%ss, url=%s",
                call_sid, recording_sid, duration, recording_url)

    if recording_sid and call_sid:
        # Store proxy URL so frontend can access without Twilio auth
        proxy_url = f"/api/cobranza/voice/recording/{recording_sid}"
        db = get_db()
        await db.debtors.update_one(
            {"historial_llamadas.call_id": call_sid},
            {"$set": {"historial_llamadas.$.recording_url": proxy_url}},
        )
        logger.info("[Recording] Saved recording URL for call %s", call_sid)

    return PlainTextResponse("OK")


# ── Recording Proxy (Twilio requires auth) ──────────────────────────────────


@router.get("/recording/{recording_sid}")
async def get_recording(recording_sid: str, current_user: dict = Depends(get_current_user)):
    """Proxy Twilio recording to the frontend (Twilio URLs require auth)."""
    import httpx
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    url = f"https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Recordings/{recording_sid}.mp3"

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, auth=(account_sid, auth_token), follow_redirects=True)
        if resp.status_code != 200:
            raise HTTPException(resp.status_code, "Recording not found")

    from fastapi.responses import Response
    return Response(content=resp.content, media_type="audio/mpeg")


# ── Saludo pre-grabado para llamadas entrantes (§9.4) ────────────────────────
# Generado UNA VEZ con la misma voz de ARIA (scripts/gen_inbound_greeting.py,
# voice_id="Aoede") — Twilio lo reproduce vía <Play> sin gastar tokens de LLM
# antes de saber quién llama. Sin auth: Twilio necesita fetchearlo directo.

_GREETING_VARIANTS = {"manana", "tarde"}
_STATIC_VOICE_DIR = os.path.join(os.path.dirname(__file__), "..", "static", "voice")


@router.get("/static/inbound-greeting/{variante}")
async def get_inbound_greeting(variante: str):
    if variante not in _GREETING_VARIANTS:
        raise HTTPException(404, "greeting variant not found")
    from fastapi.responses import FileResponse
    path = os.path.join(_STATIC_VOICE_DIR, f"inbound_greeting_{variante}.wav")
    if not os.path.exists(path):
        raise HTTPException(404, "greeting audio not found")
    return FileResponse(path, media_type="audio/wav")


# ── WebSocket (Pipecat handles everything) ───────────────────────────────────


@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    """
    Twilio bidirectional WebSocket for audio streaming.

    Pipecat takes over: STT → LLM → TTS all streaming in parallel.
    """
    logger.info("[WS] TWILIO incoming connection for call %s", call_sid)

    db = get_db()
    stream_id = ""

    try:
        # ── WebSocket handshake: accept + parse Twilio start frame ───────
        await websocket.accept()

        try:
            from pipecat.runner.utils import parse_telephony_websocket
            _transport_type, call_data = await parse_telephony_websocket(websocket)
            stream_id = call_data.get("stream_id") or call_data.get("stream_sid") or call_sid
        except ImportError:
            # parse_telephony_websocket not available — fall back to manual parse
            import json as _json
            logger.warning("[WS] parse_telephony_websocket not available, using manual handshake")
            while True:
                raw = await websocket.receive_text()
                msg = _json.loads(raw)
                event = msg.get("event", "")
                if event == "start":
                    start_data = msg.get("start", {})
                    stream_id = start_data.get("stream_id") or start_data.get("stream_sid") or call_sid
                    break
                elif event == "connected":
                    continue
        except Exception as parse_err:
            logger.error("[WS] Handshake parse error: %s", parse_err)
            stream_id = stream_id or call_sid

        logger.info("[WS] Handshake: stream_id=%s call_sid=%s", stream_id, call_sid)

        # ── Load call context from in-progress mapping ───────────────────
        # Telnyx uses call_control_id as primary key (same as our call_sid field)
        call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})

        if call_mapping:
            user_id = call_mapping["user_id"]
            debtor_id = call_mapping["debtor_id"]
            is_inbound = call_mapping.get("direction") == "inbound"
            caller_stated_document = call_mapping.get("caller_stated_document", "")
            # Parallelize the two Atlas round-trips — they're independent. Run in
            # series this added ~one extra RTT of dead air before ARIA could greet.
            debtor, config_doc = await asyncio.gather(
                get_debtor_by_id(db, user_id, debtor_id),
                db.cobranza_config.find_one({"user_id": user_id}),
            )
            estrategia = (config_doc or {}).get("estrategia", {})
        else:
            logger.warning("[WS] No call mapping for %s — rejecting", call_sid)
            await websocket.close(1008, "No call mapping found")
            return

        if not debtor:
            logger.error("[WS] No debtor for %s, closing", call_sid)
            await websocket.close(1008, "Missing debtor")
            return

        logger.info("[WS] Starting Pipecat for call %s (debtor=%s)", call_sid, debtor.get("nombre"))

        # CRITICAL: pass the REAL Twilio stream_id (MZ...) parsed from the
        # handshake — NOT call_sid. The TwilioFrameSerializer tags every
        # outgoing media event with streamSid; if it's the call_sid instead
        # of the MZ stream id, Twilio silently drops all bot audio.
        logger.info("[WS] Passing stream_id=%s to run_bot (call_sid=%s)", stream_id, call_sid)
        call_result = await run_bot(
            websocket=websocket,
            call_sid=call_sid,
            debtor=debtor,
            estrategia=estrategia,
            user_id=user_id,
            stream_id=stream_id,
            call_control_id=call_sid,
            is_inbound=is_inbound,
            caller_stated_document=caller_stated_document,
        )

        logger.info("[WS] Pipecat finished for call %s (duration=%ss)", call_sid, call_result.duration_seconds)

        # ── Post-call: update debtor status & log history ────────────
        if call_mapping:
            await _process_call_ended(db, debtor, call_result, is_inbound=is_inbound)

    except Exception as e:
        logger.error("[WS] Error: %s", e, exc_info=True)
    finally:
        # Cleanup
        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        except:
            pass
        logger.info("[WS] Cleanup done for %s", call_sid)


# ── Post-call processing ────────────────────────────────────────────────────


async def _process_call_ended(db, debtor: dict, result: CallResult, *, is_inbound: bool = False):
    """Update debtor status and save call history after Pipecat pipeline ends.

    `is_inbound`: una llamada entrante (§9.4, cliente devuelve la llamada) NO
    cuenta como uno de los 3 intentos oficiales de la secuencia saliente — se
    salta el `$inc` de intentos y la lógica de `agotado`, y no se toca la cita
    saliente ya programada (`proximo_intento_at`)."""
    try:
        # El estado se relee de la DB: las tools de la llamada (reagendar_llamada,
        # informar_fecha_pago, escalate, notify_payment_claim) escriben durante
        # la conversación y el dict en memoria quedó en 'llamando' — usarlo
        # pisaba esos estados con 'contactado' al colgar.
        debtor_oid = ObjectId(debtor["_id"]) if isinstance(debtor["_id"], str) else debtor["_id"]
        fresh = await db.debtors.find_one({"_id": debtor_oid}, {"estado": 1})
        current_estado = (fresh or {}).get("estado") or debtor.get("estado", "pendiente")
        if current_estado == "llamando":
            current_estado = debtor.get("estado_previo") or "pendiente"

        # Determine new estado
        if current_estado in _TERMINAL_ESTADOS:
            new_estado = current_estado
        elif result.duration_seconds > 10 and result.user_turn_count > 0:
            # User spoke — call was answered
            new_estado = "contactado"
        elif result.duration_seconds > 5:
            new_estado = "sin_contacto"
        else:
            new_estado = "sin_contacto"

        # Check max intentos — manda la config del tenant (informe: 3), con el
        # max del deudor como fallback para cargas manuales. Una llamada
        # entrante NO consume intento ni puede agotar la secuencia.
        # new_intentos SIEMPRE se define (antes solo dentro del if, y el log +
        # el push de WS de mas abajo la leian incondicional -> UnboundLocalError
        # en TODA llamada entrante, observado en produccion).
        new_intentos = debtor.get("intentos", 0)
        if not is_inbound:
            try:
                from cobranza.config_cache import get_tenant_config
                cfg = await get_tenant_config(str(debtor["user_id"]))
                timings = ((cfg or {}).get("cobranza") or {}).get("timings") or {}
                max_intentos = int(timings.get("max_intentos") or debtor.get("max_intentos", 3))
            except Exception:
                max_intentos = debtor.get("max_intentos", 3)
            new_intentos = debtor.get("intentos", 0) + 1
            if new_intentos >= max_intentos and new_estado not in _TERMINAL_ESTADOS:
                new_estado = "agotado"

        # Build call record for historial
        transcript = result.full_transcript
        call_record = {
            "call_id": result.call_sid,
            "fecha": datetime.now(timezone.utc),
            "duracion_segundos": result.duration_seconds,
            "resultado": new_estado,
            "transcript": transcript[:2000],
            "engine": "pipecat-telnyx-gemini-live",
            "direction": "inbound" if is_inbound else "outbound",
        }

        now = datetime.now(timezone.utc)
        debtor_oid = ObjectId(debtor["_id"]) if isinstance(debtor["_id"], str) else debtor["_id"]
        update_doc: dict = {
            "$set": {
                "estado": new_estado,
                "updated_at": now,
                "ultimo_contacto_fecha": now,
            },
            "$push": {"historial_llamadas": call_record},
        }
        if is_inbound:
            update_doc["$unset"] = {"vapi_call_id": ""}
        else:
            update_doc["$inc"] = {"intentos": 1}
            # proximo_intento_at se borra para que el planner de la secuencia
            # recalcule el siguiente intento con el nuevo conteo (offset L2/L3).
            update_doc["$unset"] = {"vapi_call_id": "", "proximo_intento_at": "", "proximo_intento_numero": ""}
        await db.debtors.update_one({"_id": debtor_oid}, update_doc)

        logger.info("[PostCall] %s -> estado=%s, intentos=%d, duration=%ds",
                     result.call_sid, new_estado, new_intentos, result.duration_seconds)

        # Agotó los intentos sin contacto → alerta a cartera para seguimiento
        # manual (informe §7: "cliente que no contestó ninguna llamada...").
        if new_estado == "agotado":
            try:
                from cobranza.alerts import crear_alerta
                await crear_alerta(db, str(debtor["user_id"]), debtor, "sin_contacto_agotado")
            except Exception:
                logger.exception("[PostCall] alerta sin_contacto_agotado falló (no fatal)")

        # Push real-time WebSocket event to dashboard
        try:
            await _ws_manager.send_to_user(
                str(debtor["user_id"]),
                {
                    "type": "debtor_update",
                    "debtor_id": str(debtor["_id"]),
                    "estado": new_estado,
                    "intentos": new_intentos,
                },
            )
        except Exception as ws_exc:
            logger.warning("[PostCall] WS push failed (non-fatal): %s", ws_exc)

    except Exception as e:
        logger.error("[PostCall] Error processing call end: %s", e, exc_info=True)


# ── Outbound Call Initiation ─────────────────────────────────────────────────


@router.post("/call/initiate-v2", status_code=status.HTTP_202_ACCEPTED)
async def initiate_call_v2(
    request: VoiceCallInitRequest,
    current_user: dict = Depends(get_current_user),
):
    """Trigger outbound voice call. POST { "debtor_id": "..." }"""
    from cobranza.call_scheduler import has_been_contacted_today

    user_id = str(current_user["user_id"])
    db = get_db()
    debtor_id = request.debtor_id

    logger.info("[Init] Call for debtor %s (user %s)", debtor_id, user_id)

    doc = await db.company_voice.find_one({"user_id": user_id})
    if not doc or not doc.get("cobranza_enabled", False):
        raise HTTPException(403, "Cobranza no habilitado.")

    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if not debtor:
        raise HTTPException(404, "Debtor not found")

    if has_been_contacted_today(debtor):
        raise HTTPException(400, "Ya fue contactado hoy (Ley 2300)")

    # Paquete de minutos: sin saldo no se marca (402 = payment required).
    from cobranza.minutes import MinutesExhaustedError, call_status_kwargs, require_saldo
    try:
        await require_saldo(db, user_id)
    except MinutesExhaustedError as e:
        raise HTTPException(402, str(e))

    # ── Concurrency cap (Etapa 1 of scaling plan) ─────────────────────────
    # One uvicorn process degrades visibly with 2+ simultaneous Gemini Live
    # pipelines (observed: zombie voicemail call starved a real call — slow
    # turns, missing replies). Cap active calls; the campaign scheduler
    # retries on its next tick, turning bursts into a controlled drip.
    # Stale records (crashed calls) are excluded via the 10-min cutoff and
    # cleaned up by the TTL index on started_at.
    max_concurrent = int(os.getenv("MAX_CONCURRENT_CALLS", "5"))
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    active = await db.cobranza_calls_in_progress.count_documents(
        {"started_at": {"$gte": cutoff}}
    )
    if active >= max_concurrent:
        logger.warning("[Init] Concurrency cap hit (%d/%d active) — rejecting call for %s",
                       active, max_concurrent, debtor_id)
        raise HTTPException(429, f"Capacidad de llamadas llena ({active}/{max_concurrent}). Reintenta en unos minutos.")

    try:
        from twilio.rest import Client

        twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
        twilio_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([twilio_sid, twilio_token, from_number]):
            raise HTTPException(500, "TWILIO not configured (TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_VOICE_PHONE_NUMBER required)")

        to_number = debtor.get("telefono")
        twilio_client = Client(twilio_sid, twilio_token)

        # AMD trade-off: machine_detection makes Twilio WAIT to classify
        # human-vs-machine BEFORE connecting our webhook — that wait is pure dead
        # air the caller perceives before ARIA can greet (the dominant chunk of
        # opening latency). It also FALSE-POSITIVES on a slow human "Aló" + pause,
        # hanging up real people (observed on CA9b483c). So AMD is now OFF by
        # default: every answer connects straight to the bot with NO detection
        # delay. The 240s watchdog still caps any voicemail that slips through.
        # Re-enable per-deployment with VOICE_AMD_ENABLED=true if voicemail spam
        # becomes a cost problem.
        amd_enabled = os.getenv("VOICE_AMD_ENABLED", "false").lower() in ("1", "true", "yes")
        create_kwargs = dict(
            to=to_number,
            from_=from_number,
            url=f"{webhook_url}/api/cobranza/voice/webhook",
            method="POST",
            **call_status_kwargs(),
        )
        if amd_enabled:
            # "DetectMessageEnd" is more conservative than "Enable": it waits for
            # the voicemail greeting to finish rather than guessing early, so a
            # human who says "Aló" then pauses is far less likely to be misjudged.
            create_kwargs["machine_detection"] = "DetectMessageEnd"
            create_kwargs["machine_detection_timeout"] = 8
        try:
            loop = asyncio.get_event_loop()
            call = await asyncio.wait_for(
                loop.run_in_executor(None, lambda: twilio_client.calls.create(**create_kwargs)),
                timeout=15
            )
        except asyncio.TimeoutError:
            raise HTTPException(504, "TWILIO call initiation timed out")

        call_sid = call.sid
        logger.info("[Init] TWILIO call %s -> %s", call_sid, to_number)

        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid, "user_id": user_id,
            "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await update_debtor(db, user_id, debtor_id, {"estado": "llamando", "vapi_call_id": call_sid})

        return {"ok": True, "call_sid": call_sid, "message": "Call initiated (Pipecat + Twilio)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Init] Failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed: {str(e)[:100]}")
