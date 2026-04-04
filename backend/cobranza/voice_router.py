"""
voice_router.py — FastAPI endpoints for voice orchestrator.

Handles:
1. POST /api/cobranza/voice/webhook — TwiML (upgrades to WebSocket)
2. WebSocket /api/cobranza/voice/ws/{call_id} — Real-time bidirectional voice
3. POST /api/cobranza/voice/call/initiate-v2 — Outbound call initiation
"""
import asyncio
import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import requests as sync_requests
from fastapi import APIRouter, Depends, Form, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor
from cobranza.tts_adapter import get_tts_provider

logger = logging.getLogger("cobranza.voice")

router = APIRouter(prefix="/api/cobranza/voice", tags=["voice"])


# ── Models ───────────────────────────────────────────────────────────────────

class VoiceCallInitRequest(BaseModel):
    debtor_id: str


# ── TwiML Webhook ────────────────────────────────────────────────────────────


@router.post("/webhook")
async def twiml_webhook(request: Request):
    """
    Twilio calls this when the outbound call connects.
    We respond with TwiML that upgrades to a bidirectional WebSocket.
    """
    from twilio.twiml.voice_response import VoiceResponse, Connect

    # Twilio sends application/x-www-form-urlencoded
    form = await request.form()
    form_dict = dict(form)
    logger.info("[Webhook] Raw form data: %s", form_dict)
    call_sid = form_dict.get("CallSid", "unknown")
    Called = form_dict.get("Called", "unknown")
    Caller = form_dict.get("Caller", "unknown")
    logger.info("[Webhook] Call %s answered (from %s to %s)", call_sid, Caller, Called)

    host = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8001")
    host_clean = host.replace("https://", "").replace("http://", "")
    ws_url = f"wss://{host_clean}/api/cobranza/voice/ws/{call_sid}"

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)

    twiml = str(response)
    logger.info("[Webhook] TwiML → Stream to %s", ws_url)
    return PlainTextResponse(twiml, media_type="application/xml")


# ── WebSocket (Bidirectional Media Stream) ───────────────────────────────────


@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams bidirectional WebSocket.

    Protocol (per https://www.twilio.com/docs/voice/media-streams/websocket-messages):
      Twilio → us:  { "event": "connected" | "start" | "media" | "stop" }
      us → Twilio:  { "event": "media", "streamSid": "...", "media": {"payload": "<base64 mulaw>"} }

    Audio format: audio/x-mulaw, 8 kHz, mono, base64-encoded. No file headers.
    """
    await websocket.accept()
    logger.info("[WS] Accepted for call %s", call_sid)

    db = get_db()
    stream_sid: Optional[str] = None
    audio_buffer = bytearray()
    transcript_history: list[dict] = []
    turn = 0
    greeting_sent = False

    try:
        # ── Load call context ────────────────────────────────────────────
        call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})
        if not call_mapping:
            logger.error("[WS] No call mapping for %s", call_sid)
            await websocket.close(1008, "No call mapping")
            return

        user_id = call_mapping["user_id"]
        debtor_id = call_mapping["debtor_id"]
        debtor = await get_debtor_by_id(db, user_id, debtor_id)
        config_doc = await db.cobranza_config.find_one({"user_id": user_id})
        estrategia = (config_doc or {}).get("estrategia", {})

        if not debtor or not estrategia:
            logger.error("[WS] Missing debtor/strategy for call %s", call_sid)
            await websocket.close(1008, "Missing config")
            return

        debtor_name = debtor.get("nombre", "señor o señora")
        tts = get_tts_provider()
        logger.info("[WS] Ready: debtor=%s, tts=%s", debtor_name, tts.name())

        # ── Main loop ────────────────────────────────────────────────────
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                logger.warning("[WS] 30 s silence — hanging up")
                break
            except WebSocketDisconnect:
                logger.info("[WS] Disconnected")
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            # ── connected ────────────────────────────────────────────────
            if event == "connected":
                logger.info("[WS] Connected event received")

            # ── start ────────────────────────────────────────────────────
            elif event == "start":
                stream_sid = msg.get("start", {}).get("streamSid") or msg.get("streamSid")
                logger.info("[WS] Stream started — streamSid=%s", stream_sid)

                # Send greeting as soon as stream starts
                if stream_sid and not greeting_sent:
                    greeting = f"Aló, buenas tardes, será que hablo con {debtor_name}?"
                    logger.info("[WS] Sending greeting: %s", greeting)
                    audio = await _tts_to_mulaw(tts, greeting)
                    if audio:
                        await _send_audio(websocket, stream_sid, audio)
                        transcript_history.append({"speaker": "agent", "text": greeting})
                        greeting_sent = True
                        logger.info("[WS] Greeting sent (%d bytes mulaw)", len(audio))
                    else:
                        logger.error("[WS] TTS failed for greeting")

            # ── media (inbound audio from caller) ────────────────────────
            elif event == "media":
                payload = msg.get("media", {}).get("payload", "")
                if payload:
                    chunk = base64.b64decode(payload)
                    audio_buffer.extend(chunk)

                    # Accumulate ~3 seconds of audio (8000 bytes/sec for mulaw 8kHz)
                    if len(audio_buffer) >= 24000:
                        turn += 1
                        logger.info("[WS] Turn %d — %d bytes of audio collected", turn, len(audio_buffer))

                        # Transcribe
                        transcript = await _transcribe_mulaw(bytes(audio_buffer))
                        audio_buffer.clear()

                        if not transcript or len(transcript.strip()) < 2:
                            logger.info("[WS] Empty transcript, waiting for more audio")
                            continue

                        logger.info("[WS] Debtor said: «%s»", transcript)
                        transcript_history.append({"speaker": "debtor", "text": transcript})

                        # Claude decides what Camila says next
                        from cobranza.claude_decision import get_next_action
                        decision = await get_next_action(
                            estrategia=estrategia,
                            debtor=debtor,
                            transcript_history=transcript_history,
                            latest_debtor_input=transcript,
                            turn_number=turn,
                        )

                        camila_text = decision.get("response_text", "Entendido, gracias.")
                        action = decision.get("action", "continue")
                        logger.info("[WS] Camila [%s]: %s", action, camila_text[:120])
                        transcript_history.append({"speaker": "agent", "text": camila_text})

                        # Synthesize and send back
                        response_audio = await _tts_to_mulaw(tts, camila_text)
                        if response_audio and stream_sid:
                            await _send_audio(websocket, stream_sid, response_audio)
                            logger.info("[WS] Sent response (%d bytes)", len(response_audio))

                        # If Claude says end the call, break
                        if action in ("end", "escalate"):
                            logger.info("[WS] Call ending: action=%s", action)
                            break

            # ── stop ─────────────────────────────────────────────────────
            elif event == "stop":
                logger.info("[WS] Stream stopped by Twilio")
                break

        logger.info("[WS] Call %s ended after %d turns", call_sid, turn)

    except Exception as e:
        logger.error("[WS] Fatal: %s", e, exc_info=True)
    finally:
        # Log conversation to MongoDB
        try:
            await db.cobranza_calls.insert_one({
                "call_sid": call_sid,
                "user_id": user_id if "user_id" in dir() else None,
                "debtor_id": debtor_id if "debtor_id" in dir() else None,
                "transcript": transcript_history,
                "turns": turn,
                "created_at": datetime.now(timezone.utc),
            })
        except Exception as e:
            logger.warning("[WS] Failed to log call: %s", e)

        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        except:
            pass
        try:
            await websocket.close()
        except:
            pass
        logger.info("[WS] Cleanup done for %s", call_sid)


# ── Helpers ──────────────────────────────────────────────────────────────────


async def _tts_to_mulaw(tts, text: str) -> Optional[bytes]:
    """
    Synthesize text and convert to raw mulaw 8 kHz (no file headers).

    Twilio requires: audio/x-mulaw, 8000 Hz, mono, no headers.
    """
    try:
        audio = await tts.synthesize(text)
        if not audio:
            return None

        # The TTS provider might return MP3, WAV, or raw PCM.
        # We need raw mulaw. Use audioop for conversion if we get PCM.
        # If we get MP3/WAV from Azure, we need to decode first.
        # For now, try to convert assuming raw PCM int16 at some sample rate.
        try:
            import audioop
            import io
            import wave

            # Try to parse as WAV first
            try:
                wav_io = io.BytesIO(audio)
                with wave.open(wav_io, "rb") as wf:
                    pcm_data = wf.readframes(wf.getnframes())
                    sample_width = wf.getsampwidth()
                    sample_rate = wf.getframerate()
                    channels = wf.getnchannels()

                # Convert to mono if stereo
                if channels == 2:
                    pcm_data = audioop.tomono(pcm_data, sample_width, 1, 1)

                # Resample to 8000 Hz if needed
                if sample_rate != 8000:
                    pcm_data, _ = audioop.ratecv(pcm_data, sample_width, 1, sample_rate, 8000, None)

                # Convert to mulaw
                mulaw = audioop.lin2ulaw(pcm_data, sample_width)
                logger.debug("[TTS→mulaw] WAV %dHz/%dch → %d bytes mulaw", sample_rate, channels, len(mulaw))
                return mulaw

            except wave.Error:
                # Not a WAV — maybe it's already mulaw or raw PCM
                # Try treating as 16-bit PCM at 16kHz
                pcm_data, _ = audioop.ratecv(audio, 2, 1, 16000, 8000, None)
                mulaw = audioop.lin2ulaw(pcm_data, 2)
                logger.debug("[TTS→mulaw] Raw PCM → %d bytes mulaw", len(mulaw))
                return mulaw

        except Exception as conv_err:
            logger.warning("[TTS→mulaw] Conversion failed: %s — returning raw", conv_err)
            return audio

    except Exception as e:
        logger.error("[TTS→mulaw] Error: %s", e)
        return None


async def _send_audio(websocket: WebSocket, stream_sid: str, mulaw_audio: bytes) -> None:
    """
    Send mulaw audio back to Twilio over the bidirectional Media Stream.

    Sends in 20 ms chunks (160 bytes of mulaw at 8 kHz).
    """
    CHUNK = 160  # 20 ms at 8 kHz mulaw (1 byte per sample)
    for i in range(0, len(mulaw_audio), CHUNK):
        chunk = mulaw_audio[i:i + CHUNK]
        payload = base64.b64encode(chunk).decode("ascii")
        await websocket.send_json({
            "event": "media",
            "streamSid": stream_sid,
            "media": {
                "payload": payload,
            },
        })
        # Pace at roughly real-time so Twilio's jitter buffer stays happy
        await asyncio.sleep(0.018)

    # Send a mark so we know when playback finishes
    await websocket.send_json({
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": f"response_{int(time.time())}"},
    })


async def _transcribe_mulaw(audio: bytes) -> Optional[str]:
    """
    Transcribe mulaw audio using Assembly AI (upload → submit → poll).

    Converts mulaw 8kHz to WAV before uploading (Assembly AI needs a proper format).
    """
    import audioop
    import io
    import wave

    api_key = os.getenv("ASSEMBLY_AI_API_KEY")
    if not api_key:
        logger.error("[STT] ASSEMBLY_AI_API_KEY not set")
        return None

    # Convert mulaw to WAV
    try:
        pcm = audioop.ulaw2lin(audio, 2)  # mulaw → 16-bit PCM
        wav_buf = io.BytesIO()
        with wave.open(wav_buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm)
        wav_bytes = wav_buf.getvalue()
        logger.info("[STT] Converted %d bytes mulaw → %d bytes WAV", len(audio), len(wav_bytes))
    except Exception as e:
        logger.error("[STT] mulaw→WAV conversion failed: %s", e)
        return None

    headers = {"Authorization": api_key, "Content-Type": "application/octet-stream"}

    try:
        # 1. Upload WAV audio
        up = sync_requests.post(
            "https://api.assemblyai.com/v2/upload",
            headers=headers,
            data=wav_bytes,
            timeout=10,
        )
        up.raise_for_status()
        audio_url = up.json()["upload_url"]

        # 2. Submit transcription job
        sub = sync_requests.post(
            "https://api.assemblyai.com/v2/transcript",
            headers={"Authorization": api_key},
            json={
                "audio_url": audio_url,
                "language_code": "es",
                "speech_models": ["universal-3-pro"],
            },
            timeout=10,
        )
        if sub.status_code != 200:
            logger.error("[STT] Submit failed %d: %s", sub.status_code, sub.text[:300])
            return None
        tid = sub.json()["id"]

        # 3. Poll (up to 30 s)
        poll_url = f"https://api.assemblyai.com/v2/transcript/{tid}"
        deadline = time.time() + 30
        while time.time() < deadline:
            r = sync_requests.get(poll_url, headers={"Authorization": api_key}, timeout=10)
            r.raise_for_status()
            body = r.json()
            if body["status"] == "completed":
                return body.get("text", "")
            if body["status"] == "error":
                logger.error("[STT] Assembly AI error: %s", body.get("error"))
                return None
            await asyncio.sleep(1)

        logger.warning("[STT] Timed out waiting for transcript")
        return None

    except Exception as e:
        logger.error("[STT] Error: %s", e)
        return None


# ── Outbound Call Initiation ─────────────────────────────────────────────────


@router.post("/call/initiate-v2", status_code=status.HTTP_202_ACCEPTED)
async def initiate_call_v2(
    request: VoiceCallInitRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger a voice call.

    POST /api/cobranza/voice/call/initiate-v2
    { "debtor_id": "..." }
    """
    from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today

    user_id = str(current_user["user_id"])
    db = get_db()
    debtor_id = request.debtor_id

    logger.info("[Init] Call for debtor %s (user %s)", debtor_id, user_id)

    # Check cobranza enabled
    doc = await db.company_voice.find_one({"user_id": user_id})
    if not doc or not doc.get("cobranza_enabled", False):
        raise HTTPException(403, "Cobranza no habilitado para esta cuenta.")

    # Fetch debtor
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if not debtor:
        raise HTTPException(404, "Debtor not found")

    # Ley 2300 (one contact / day)
    if has_been_contacted_today(debtor):
        raise HTTPException(400, "Ya fue contactado hoy (Ley 2300)")

    # Twilio call
    try:
        from twilio.rest import Client

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8001")

        if not all([account_sid, auth_token, from_number]):
            raise HTTPException(500, "Twilio not configured")

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        twiml_url = f"{webhook_url}/api/cobranza/voice/webhook"

        call = client.calls.create(to=to_number, from_=from_number, url=twiml_url, method="POST")
        call_sid = call.sid
        logger.info("[Init] Call %s → %s", call_sid, to_number)

        # Store mapping
        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid,
            "user_id": user_id,
            "debtor_id": str(debtor["_id"]),
            "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number,
            "started_at": datetime.now(timezone.utc),
        })

        # Update debtor status
        await update_debtor(db, user_id, debtor_id, {
            "estado": "llamando",
            "vapi_call_id": call_sid,
        })

        return {"ok": True, "call_sid": call_sid, "message": "Call initiated (v2 orchestrator)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Init] Failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed to initiate call: {str(e)[:100]}")
