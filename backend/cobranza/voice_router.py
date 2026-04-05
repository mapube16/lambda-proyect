"""
voice_router.py — FastAPI endpoints for voice orchestrator.

Architecture:
  Twilio ←WebSocket→ our server → Assembly AI SDK (real-time STT)
                         ↕
                  OpenAI (GPT-4o) for conversation decisions
                         ↕
                  Azure TTS (Salome, es-CO) for voice synthesis
"""
import asyncio
import audioop
import base64
import io
import json
import logging
import os
import threading
import time
import wave
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor
from cobranza.tts_adapter import get_tts_provider

logger = logging.getLogger("cobranza.voice")

router = APIRouter(prefix="/api/cobranza/voice", tags=["voice"])


class VoiceCallInitRequest(BaseModel):
    debtor_id: str


# ── TwiML Webhook ────────────────────────────────────────────────────────────


@router.post("/webhook")
async def twiml_webhook(request: Request):
    """Twilio calls this when outbound call connects. Upgrades to bidirectional WebSocket."""
    from twilio.twiml.voice_response import VoiceResponse, Connect

    form = dict(await request.form())
    call_sid = form.get("CallSid", "unknown")
    logger.info("[Webhook] Call %s answered", call_sid)

    host = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002").replace("https://", "").replace("http://", "")
    ws_url = f"wss://{host}/api/cobranza/voice/ws/{call_sid}"

    # Look up debtor name for greeting
    db = get_db()
    call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})
    debtor_name = "señor o señora"
    if call_mapping:
        debtor_name = call_mapping.get("debtor_name", debtor_name)

    response = VoiceResponse()
    # TwiML greeting first (reliable audio), then upgrade to WebSocket for conversation
    response.say(
        f"Aló, buenas tardes, será que hablo con {debtor_name}?",
        voice="alice", language="es-MX"
    )
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)
    # Keep call alive — Twilio hangs up after TwiML ends, so add a long pause
    response.pause(length=300)  # 5 minutes max call duration

    logger.info("[Webhook] TwiML -> Stream %s", ws_url)
    return PlainTextResponse(str(response), media_type="application/xml")


# ── WebSocket (Bidirectional Media Stream) ───────────────────────────────────


@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams bidirectional WebSocket.

    Uses Assembly AI SDK (thread-based) for real-time STT.
    Audio flow: Twilio mulaw -> PCM16 -> Assembly AI SDK -> transcript -> OpenAI -> Azure TTS -> mulaw -> Twilio
    """
    await websocket.accept()
    logger.info("[WS] Accepted call %s", call_sid)

    db = get_db()
    stream_sid: Optional[str] = None
    transcript_history: list[dict] = []
    turn = 0
    greeting_sent = False
    is_speaking = False  # True while agent audio is playing
    # Persistent call state — survives across turns
    call_state = {
        "identity_confirmed": False,
        "debt_mentioned": False,
        "payment_discussed": False,
        "objection_type": None,
    }
    aai_audio_buf = bytearray()  # Buffer to accumulate audio before sending to AAI

    # Thread-safe queue for transcripts from Assembly AI
    transcript_queue: asyncio.Queue[str] = asyncio.Queue()
    loop = asyncio.get_event_loop()

    # Assembly AI SDK client
    aai_client = None

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
            logger.error("[WS] Missing debtor/strategy")
            await websocket.close(1008, "Missing config")
            return

        debtor_name = debtor.get("nombre", "señor o señora")
        tts = get_tts_provider()
        logger.info("[WS] Ready: debtor=%s, tts=%s", debtor_name, tts.name())

        # ── Initialize Assembly AI SDK ───────────────────────────────────
        aai_key = os.getenv("ASSEMBLY_AI_API_KEY")
        if not aai_key:
            logger.error("[WS] ASSEMBLY_AI_API_KEY not set")
            await websocket.close(1011, "STT not configured")
            return

        from assemblyai.streaming.v3 import (
            StreamingClient, StreamingClientOptions, StreamingParameters, StreamingEvents
        )

        aai_client = StreamingClient(
            options=StreamingClientOptions(api_key=aai_key)
        )

        def on_turn(client, turn_event):
            """Called by Assembly AI SDK (from a background thread) when a complete utterance is detected."""
            text = turn_event.transcript.strip() if turn_event.transcript else ""
            if not text or len(text) < 2:
                return
            if is_speaking:
                logger.debug("[AAI] Ignoring echo while speaking: '%s'", text[:50])
                return
            logger.info("[AAI] Turn: '%s'", text)
            loop.call_soon_threadsafe(transcript_queue.put_nowait, text)

        def on_error(client, error):
            logger.error("[AAI] Error: %s", error)

        def on_begin(client, begin):
            logger.info("[AAI] Session started: %s", str(begin.id)[:20])

        aai_client.on(StreamingEvents.Turn, on_turn)
        aai_client.on(StreamingEvents.Error, on_error)
        aai_client.on(StreamingEvents.Begin, on_begin)

        aai_client.connect(StreamingParameters(
            sample_rate=8000,
            speech_model="u3-rt-pro",
            encoding="pcm_s16le",
            prompt="Esta es una llamada telefónica en español colombiano sobre cobranza de seguros.",
        ))
        logger.info("[WS] Assembly AI SDK connected")

        # ── Background: process transcripts ──────────────────────────────
        async def _process_transcripts():
            nonlocal turn, is_speaking
            while True:
                try:
                    text = await asyncio.wait_for(transcript_queue.get(), timeout=120.0)
                except asyncio.TimeoutError:
                    logger.warning("[WS] No speech for 120s")
                    break
                except asyncio.CancelledError:
                    break

                if not text or len(text) < 2:
                    continue

                turn += 1
                logger.info("[WS] Turn %d — Debtor: '%s'", turn, text)
                transcript_history.append({"speaker": "debtor", "text": text})

                # OpenAI/Camila decides
                try:
                    from cobranza.claude_decision import get_next_action
                    t0 = time.time()
                    decision = await get_next_action(
                        estrategia=estrategia,
                        debtor=debtor,
                        transcript_history=transcript_history,
                        latest_debtor_input=text,
                        turn_number=turn,
                        call_state=call_state,
                    )
                    t_llm = time.time() - t0

                    camila_text = decision.get("response_text", "Entendido.")
                    action = decision.get("action", "continue")

                    # Update persistent call state from metadata
                    meta = decision.get("metadata", {})
                    if meta.get("identity_confirmed"):
                        call_state["identity_confirmed"] = True
                    if meta.get("debt_confirmed"):
                        call_state["debt_mentioned"] = True
                    if meta.get("payment_agreed"):
                        call_state["payment_discussed"] = True
                    if meta.get("objection_type"):
                        call_state["objection_type"] = meta["objection_type"]
                    logger.info("[WS] Camila [%s] (%.1fs): %s", action, t_llm, camila_text[:120])
                    transcript_history.append({"speaker": "agent", "text": camila_text})

                    # Synthesize and send
                    is_speaking = True
                    t0 = time.time()
                    audio = await _tts_to_mulaw(tts, camila_text)
                    t_tts = time.time() - t0
                    if audio and stream_sid:
                        await _send_audio(websocket, stream_sid, audio)
                        logger.info("[WS] Sent response (%d bytes, LLM %.1fs, TTS %.1fs)", len(audio), t_llm, t_tts)
                    # Wait a bit before accepting new transcripts (avoid echo)
                    await asyncio.sleep(1.0)
                    is_speaking = False

                    if action in ("end", "escalate"):
                        logger.info("[WS] Ending call: %s", action)
                        break

                except Exception as e:
                    logger.error("[WS] Process error: %s", e, exc_info=True)
                    is_speaking = False

        process_task = asyncio.create_task(_process_transcripts())

        # ── Main loop: Twilio -> Assembly AI ─────────────────────────────
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=120.0)
            except asyncio.TimeoutError:
                logger.warning("[WS] 120s silence")
                break
            except WebSocketDisconnect:
                logger.info("[WS] Disconnected")
                break

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            event = msg.get("event")

            if event == "connected":
                logger.info("[WS] Connected event")

            elif event == "start":
                stream_sid = msg.get("start", {}).get("streamSid") or msg.get("streamSid")
                logger.info("[WS] Stream started, streamSid=%s", stream_sid)

                # Greeting already played via TwiML <Say>, mark as speaking to ignore echo
                if not greeting_sent:
                    greeting_sent = True
                    is_speaking = True  # Ignore echo from TwiML greeting
                    greeting_text = f"Aló, buenas tardes, será que hablo con {debtor_name}?"
                    transcript_history.append({"speaker": "agent", "text": greeting_text})
                    logger.info("[WS] Greeting was played via TwiML, ignoring echo for 4s")

                    async def _unblock_after_greeting():
                        nonlocal is_speaking
                        await asyncio.sleep(4.0)  # Wait for TwiML greeting to finish playing
                        is_speaking = False
                        logger.info("[WS] Now listening for debtor speech")

                    asyncio.create_task(_unblock_after_greeting())

            elif event == "media":
                # Forward to Assembly AI as PCM16 — ONLY when agent is NOT speaking
                payload = msg.get("media", {}).get("payload", "")
                if payload and aai_client:
                    try:
                        mulaw = base64.b64decode(payload)
                        pcm = audioop.ulaw2lin(mulaw, 2)
                        if is_speaking:
                            # Send silence instead to keep AAI alive but prevent echo
                            aai_audio_buf.extend(b'\x00\x00' * len(mulaw))
                        else:
                            aai_audio_buf.extend(pcm)
                        # Send when we have >=100ms (1600 bytes at 8kHz 16-bit)
                        if len(aai_audio_buf) >= 1600:
                            aai_client.stream(bytes(aai_audio_buf))
                            aai_audio_buf.clear()
                    except Exception:
                        pass

            elif event == "stop":
                logger.info("[WS] Stream stopped by Twilio")
                break

            elif event == "mark":
                pass

        logger.info("[WS] Call %s ended, %d turns", call_sid, turn)

    except Exception as e:
        logger.error("[WS] Fatal: %s", e, exc_info=True)
    finally:
        # Cleanup
        if "process_task" in dir():
            process_task.cancel()
        if aai_client:
            try:
                aai_client.disconnect()
            except:
                pass

        # Log to MongoDB
        try:
            if transcript_history:
                await db.cobranza_calls.insert_one({
                    "call_sid": call_sid,
                    "user_id": user_id if "user_id" in dir() else None,
                    "debtor_id": debtor_id if "debtor_id" in dir() else None,
                    "transcript": transcript_history,
                    "turns": turn,
                    "created_at": datetime.now(timezone.utc),
                })
        except Exception as e:
            logger.warning("[WS] Log failed: %s", e)

        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        except:
            pass
        try:
            await websocket.close()
        except:
            pass
        logger.info("[WS] Cleanup done for %s", call_sid)


# ── Audio helpers ────────────────────────────────────────────────────────────


async def _tts_to_mulaw(tts, text: str) -> Optional[bytes]:
    """Synthesize text -> WAV -> raw mulaw 8kHz (no headers)."""
    try:
        audio = await tts.synthesize(text)
        if not audio:
            return None

        try:
            wav_io = io.BytesIO(audio)
            with wave.open(wav_io, "rb") as wf:
                pcm = wf.readframes(wf.getnframes())
                sw = wf.getsampwidth()
                sr = wf.getframerate()
                ch = wf.getnchannels()
            if ch == 2:
                pcm = audioop.tomono(pcm, sw, 1, 1)
            if sr != 8000:
                pcm, _ = audioop.ratecv(pcm, sw, 1, sr, 8000, None)
            return audioop.lin2ulaw(pcm, sw)
        except wave.Error:
            pcm, _ = audioop.ratecv(audio, 2, 1, 16000, 8000, None)
            return audioop.lin2ulaw(pcm, 2)

    except Exception as e:
        logger.error("[TTS] Error: %s", e)
        return None


async def _send_audio(websocket: WebSocket, stream_sid: str, mulaw: bytes) -> None:
    """Send mulaw audio to Twilio in 20ms chunks."""
    CHUNK = 160  # 20ms at 8kHz mulaw
    for i in range(0, len(mulaw), CHUNK):
        chunk = mulaw[i:i + CHUNK]
        payload = base64.b64encode(chunk).decode("ascii")
        await websocket.send_json({
            "event": "media",
            "streamSid": stream_sid,
            "media": {"payload": payload},
        })
        await asyncio.sleep(0.018)

    await websocket.send_json({
        "event": "mark",
        "streamSid": stream_sid,
        "mark": {"name": f"r{int(time.time())}"},
    })


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
        from twilio.rest import Client
        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8002")

        if not all([account_sid, auth_token, from_number]):
            raise HTTPException(500, "Twilio not configured")

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")
        call = client.calls.create(
            to=to_number, from_=from_number,
            url=f"{webhook_url}/api/cobranza/voice/webhook", method="POST",
        )
        call_sid = call.sid
        logger.info("[Init] Call %s -> %s", call_sid, to_number)

        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid, "user_id": user_id,
            "debtor_id": str(debtor["_id"]), "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number, "started_at": datetime.now(timezone.utc),
        })

        await update_debtor(db, user_id, debtor_id, {"estado": "llamando", "vapi_call_id": call_sid})

        return {"ok": True, "call_sid": call_sid, "message": "Call initiated (v2 orchestrator)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Init] Failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed: {str(e)[:100]}")
