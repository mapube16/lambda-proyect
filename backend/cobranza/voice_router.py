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
from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor
from cobranza.voice_pipecat import run_bot, CallResult

_TERMINAL_ESTADOS = {"promesa_de_pago", "escalado", "pagado"}

logger = logging.getLogger("cobranza.voice")

router = APIRouter(prefix="/api/cobranza/voice", tags=["voice"])


class VoiceCallInitRequest(BaseModel):
    debtor_id: str


# ── TeXML Webhook (Telnyx) ───────────────────────────────────────────────────


@router.post("/webhook")
async def telnyx_webhook(request: Request):
    """
    Telnyx calls this when an outbound call connects.
    Returns TeXML <Connect><Stream> to establish bidirectional WebSocket.
    """
    form = dict(await request.form())
    call_control_id = form.get("call_control_id", "unknown")
    logger.info("[Webhook] TELNYX call %s answered", call_control_id)

    host = (
        os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")
        .replace("https://", "")
        .replace("http://", "")
    )
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_control_id}"

    texml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Connect><Stream url="{ws_url}" bidirectionalMode="rtp" /></Connect>'
        "<Pause length=\"40\"/>"
        "</Response>"
    )
    logger.info("[Webhook] TeXML -> Stream %s", ws_url)
    return PlainTextResponse(texml, media_type="application/xml")


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


@router.websocket("/ws/{call_control_id}")
async def voice_websocket(websocket: WebSocket, call_control_id: str):
    """
    Telnyx bidirectional WebSocket for audio streaming.

    Pipecat takes over: STT → LLM → TTS all streaming in parallel.
    Uses parse_telephony_websocket to extract stream_id + call_control_id.
    """
    logger.info("[WS] TELNYX incoming connection for call %s", call_control_id)

    db = get_db()
    stream_id = ""

    try:
        # ── WebSocket handshake: accept + parse Telnyx start frame ───────
        await websocket.accept()

        try:
            from pipecat.runner.utils import parse_telephony_websocket
            _transport_type, call_data = await parse_telephony_websocket(websocket)
            stream_id = call_data.get("stream_id", call_control_id)
            # Prefer call_control_id from handshake data if available
            parsed_cid = call_data.get("call_control_id", call_control_id)
            if parsed_cid and parsed_cid != "unknown":
                call_control_id = parsed_cid
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
                    stream_id = start_data.get("stream_id") or start_data.get("stream_sid", call_control_id)
                    call_control_id = start_data.get("call_control_id", call_control_id)
                    break
                elif event == "connected":
                    continue
        except Exception as parse_err:
            logger.error("[WS] Handshake parse error: %s", parse_err)

        logger.info("[WS] Handshake: stream_id=%s call_control_id=%s", stream_id, call_control_id)

        # ── Load call context from in-progress mapping ───────────────────
        # Telnyx uses call_control_id as primary key (same as our call_sid field)
        call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_control_id})

        if call_mapping:
            user_id = call_mapping["user_id"]
            debtor_id = call_mapping["debtor_id"]
            debtor = await get_debtor_by_id(db, user_id, debtor_id)
            config_doc = await db.cobranza_config.find_one({"user_id": user_id})
            estrategia = (config_doc or {}).get("estrategia", {})
        else:
            logger.warning("[WS] No call mapping for %s — rejecting", call_control_id)
            await websocket.close(1008, "No call mapping found")
            return

        if not debtor:
            logger.error("[WS] No debtor for %s, closing", call_control_id)
            await websocket.close(1008, "Missing debtor")
            return

        logger.info("[WS] Starting Pipecat for call %s (debtor=%s)", call_control_id, debtor.get("nombre"))

        call_result = await run_bot(
            websocket=websocket,
            call_sid=call_control_id,
            debtor=debtor,
            estrategia=estrategia,
            user_id=user_id,
            stream_id=stream_id,
            call_control_id=call_control_id,
        )

        logger.info("[WS] Pipecat finished for call %s (duration=%ss)", call_control_id, call_result.duration_seconds)

        # ── Post-call: update debtor status & log history ────────────
        if call_mapping:
            await _process_call_ended(db, debtor, call_result)

    except Exception as e:
        logger.error("[WS] Error: %s", e, exc_info=True)
    finally:
        # Cleanup
        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_control_id})
        except:
            pass
        logger.info("[WS] Cleanup done for %s", call_control_id)


# ── Post-call processing ────────────────────────────────────────────────────


async def _process_call_ended(db, debtor: dict, result: CallResult):
    """Update debtor status and save call history after Pipecat pipeline ends."""
    try:
        current_estado = debtor.get("estado", "pendiente")

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

        # Check max intentos
        current_intentos = debtor.get("intentos", 0)
        max_intentos = debtor.get("max_intentos", 5)
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
                "$unset": {"vapi_call_id": ""},
            },
        )

        logger.info("[PostCall] %s -> estado=%s, intentos=%d, duration=%ds",
                     result.call_sid, new_estado, new_intentos, result.duration_seconds)

        # Push real-time WebSocket event to dashboard
        try:
            from main import manager
            await manager.send_to_user(
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

    try:
        import telnyx

        telnyx_api_key = os.getenv("TELNYX_API_KEY")
        connection_id = os.getenv("TELNYX_CONNECTION_ID")
        from_number = os.getenv("TELNYX_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([telnyx_api_key, connection_id, from_number]):
            raise HTTPException(500, "TELNYX not configured (TELNYX_API_KEY, TELNYX_CONNECTION_ID, TELNYX_VOICE_PHONE_NUMBER required)")

        to_number = debtor.get("telefono")
        telnyx_client = telnyx.Telnyx(api_key=telnyx_api_key)

        # Telnyx SDK v4: use client.calls.dial() — telnyx.Call.create() does not exist
        try:
            async with asyncio.timeout(15):
                call = await asyncio.to_thread(
                    telnyx_client.calls.dial,
                    connection_id=connection_id,
                    to=to_number,
                    from_=from_number,
                    webhook_url=f"{webhook_url}/api/cobranza/voice/webhook",
                    webhook_url_method="POST",
                )
        except TimeoutError:
            raise HTTPException(504, "TELNYX call initiation timed out")

        call_control_id = call.call_control_id
        logger.info("[Init] TELNYX call %s -> %s", call_control_id, to_number)

        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_control_id, "user_id": user_id,
            "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await update_debtor(db, user_id, debtor_id, {"estado": "llamando", "vapi_call_id": call_control_id})

        return {"ok": True, "call_sid": call_control_id, "message": "Call initiated (Pipecat + Telnyx)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Init] Failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed: {str(e)[:100]}")
