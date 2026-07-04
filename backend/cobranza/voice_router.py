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
    Twilio calls this when an outbound call connects.
    Returns TwiML <Connect><Stream> to establish bidirectional WebSocket.
    """
    form = dict(await request.form())
    call_sid = form.get("CallSid", "unknown")
    answered_by = form.get("AnsweredBy", "")
    logger.info("[Webhook] TWILIO call %s answered (AnsweredBy=%s)", call_sid, answered_by)

    # AMD: if a machine/voicemail answered, hang up immediately. Streaming to a
    # voicemail wastes Gemini tokens and leaves a zombie pipeline running for
    # minutes (the recording never says goodbye, so end_call never fires).
    if answered_by.startswith("machine") or answered_by == "fax":
        logger.warning("[Webhook] %s answered by %s — hanging up (no stream)", call_sid, answered_by)
        return PlainTextResponse(
            '<?xml version="1.0" encoding="UTF-8"?><Response><Hangup/></Response>',
            media_type="application/xml",
        )

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
        )

        logger.info("[WS] Pipecat finished for call %s (duration=%ss)", call_sid, call_result.duration_seconds)

        # ── Post-call: update debtor status & log history ────────────
        if call_mapping:
            await _process_call_ended(db, debtor, call_result)

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


async def _process_call_ended(db, debtor: dict, result: CallResult):
    """Update debtor status and save call history after Pipecat pipeline ends."""
    try:
        # El estado se relee de la DB: las tools de la llamada (reagendar_llamada,
        # update_debtor→promesa, escalate, notify_payment_claim) escriben durante
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
        # max del deudor como fallback para cargas manuales.
        try:
            from cobranza.config_cache import get_tenant_config
            cfg = await get_tenant_config(str(debtor["user_id"]))
            timings = ((cfg or {}).get("cobranza") or {}).get("timings") or {}
            max_intentos = int(timings.get("max_intentos") or debtor.get("max_intentos", 3))
        except Exception:
            max_intentos = debtor.get("max_intentos", 3)
        current_intentos = debtor.get("intentos", 0)
        new_intentos = current_intentos + 1
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
        }

        now = datetime.now(timezone.utc)
        debtor_oid = ObjectId(debtor["_id"]) if isinstance(debtor["_id"], str) else debtor["_id"]
        await db.debtors.update_one(
            {"_id": debtor_oid},
            {
                "$set": {
                    "estado": new_estado,
                    "updated_at": now,
                    "ultimo_contacto_fecha": now,
                },
                "$inc": {"intentos": 1},
                "$push": {"historial_llamadas": call_record},
                # proximo_intento_at se borra para que el planner de la secuencia
                # recalcule el siguiente intento con el nuevo conteo (offset L2/L3).
                "$unset": {"vapi_call_id": "", "proximo_intento_at": "", "proximo_intento_numero": ""},
            },
        )

        logger.info("[PostCall] %s -> estado=%s, intentos=%d, duration=%ds",
                     result.call_sid, new_estado, new_intentos, result.duration_seconds)

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
    from cobranza.minutes import MinutesExhaustedError, require_saldo
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
