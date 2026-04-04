"""
voice_router.py — FastAPI endpoints for voice orchestrator.

Handles:
1. POST /api/cobranza/voice/webhook — TwiML (Twilio callbacks)
2. WebSocket /api/cobranza/voice/ws/{call_id} — Real-time voice interaction
"""
import asyncio
import json
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor
from cobranza.assembly_ai_client import AssemblyAIClient
from cobranza.voice_orchestrator import VoiceOrchestrator
from cobranza.tts_adapter import get_tts_provider

logger = logging.getLogger("cobranza.voice")

router = APIRouter(prefix="/api/cobranza/voice", tags=["voice"])


# ── Models ────────────────────────────────────────────────────────────────────

class VoiceCallInitRequest(BaseModel):
    """Request to initiate a voice call via new orchestrator (v2)."""

    debtor_id: str


# ── TwiML Webhook (Twilio → us) ───────────────────────────────────────────────


@router.post("/webhook")
async def twiml_webhook(request: dict):
    """
    TwiML webhook from Twilio.

    When a call to the debtor is placed, Twilio makes a POST here.
    We respond with TwiML that:
    1. Greets the debtor
    2. Upgrades to WebSocket for real-time voice interaction

    Example TwiML response:
    <Response>
        <Connect>
            <Stream url="wss://our-domain.com/api/cobranza/voice/ws/{call_sid}" />
        </Connect>
    </Response>
    """
    from twilio.twiml.voice_response import VoiceResponse, Connect

    call_sid = request.get("CallSid", "unknown")
    called_number = request.get("Called", "unknown")

    logger.info("[TwiML Webhook] Incoming call %s to %s", call_sid, called_number)

    response = VoiceResponse()
    ws_url = f"wss://{os.getenv('VOICE_WEBHOOK_HOST', 'localhost')}/api/cobranza/voice/ws/{call_sid}"

    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)

    logger.info("[TwiML] Upgrading call %s to WebSocket at %s", call_sid, ws_url)
    return response.to_xml()


# ── WebSocket Upgrade (Twilio → us, real-time) ────────────────────────────────


@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    """
    WebSocket endpoint for real-time voice interaction.

    Twilio upgrades the call here and streams audio to us.

    Flow:
    1. Accept WebSocket connection
    2. Extract debtor_id from call_sid (stored in database)
    3. Initialize Assembly AI stream for STT
    4. Main loop:
       a. Receive audio from Twilio
       b. Send to Assembly AI
       c. Get transcript (wait for FinalTranscript)
       d. Ask Claude what to say next
       e. Synthesize response with TTS
       f. Send audio back to Twilio
       g. Repeat until call ends
    5. Log everything to MongoDB

    This is the CORE of the orchestrator.
    """
    await websocket.accept()
    logger.info("[Voice WS] Connected call %s", call_sid)

    db = get_db()
    orchestrator = None

    try:
        # ────────────────────────────────────────────────────────────────────
        # Step 1: Look up debtor from call_sid mapping
        # ────────────────────────────────────────────────────────────────────
        call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})
        if not call_mapping:
            logger.error("[Voice WS] No debtor mapping found for call %s", call_sid)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No debtor found")
            return

        user_id = call_mapping.get("user_id")
        debtor_id = call_mapping.get("debtor_id")

        logger.info("[Voice WS] Call %s: user=%s, debtor=%s", call_sid, user_id, debtor_id)

        # ────────────────────────────────────────────────────────────────────
        # Step 2: Fetch debtor and strategy
        # ────────────────────────────────────────────────────────────────────
        debtor = await get_debtor_by_id(db, user_id, debtor_id)
        if not debtor:
            logger.error("[Voice WS] Debtor not found: %s", debtor_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Debtor not found")
            return

        config_doc = await db.cobranza_config.find_one({"user_id": user_id})
        estrategia = config_doc.get("estrategia", {}) if config_doc else {}

        if not estrategia:
            logger.error("[Voice WS] No strategy configured for user %s", user_id)
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="No strategy configured")
            return

        logger.info("[Voice WS] Strategy loaded: tono=%s, max_intentos=%s",
                   estrategia.get("tono"), estrategia.get("max_intentos"))

        # ────────────────────────────────────────────────────────────────────
        # Step 3: Initialize orchestrator
        # ────────────────────────────────────────────────────────────────────
        orchestrator = VoiceOrchestrator(
            call_id=call_sid,
            user_id=user_id,
            debtor=debtor,
            estrategia=estrategia,
            db_client=db,
        )

        # ────────────────────────────────────────────────────────────────────
        # Step 4: Initialize Assembly AI stream
        # ────────────────────────────────────────────────────────────────────
        try:
            assembly_ai = AssemblyAIClient()
        except ValueError as e:
            logger.error("[Voice WS] Assembly AI initialization failed: %s", e)
            await websocket.close(code=status.WS_1011_SERVER_ERROR, reason="STT service unavailable")
            return

        # ────────────────────────────────────────────────────────────────────
        # Step 5: Main loop - receive audio, transcribe, decide, respond
        # ────────────────────────────────────────────────────────────────────
        logger.info("[Voice WS] Starting main loop for call %s", call_sid)

        while orchestrator.state == "active":
            try:
                # Receive audio from Twilio (timeout after 60s silence = hang up)
                data = await asyncio.wait_for(
                    websocket.receive_bytes(),
                    timeout=60.0
                )

                if not data:
                    logger.warning("[Voice WS] Empty data received, ending call %s", call_sid)
                    break

                # ──────────────────────────────────────────────────────────
                # Parse Twilio media format
                # Twilio sends: [length:2 bytes][audio:mulaw PCM]
                # For now, treat as raw audio (Assembly AI handles format)
                # ──────────────────────────────────────────────────────────
                audio_chunk = data[2:] if len(data) > 2 else data
                logger.debug("[Voice WS] Received %d bytes (audio payload)", len(audio_chunk))

                # Send to Assembly AI for real-time transcription
                # (This is a placeholder - actual implementation would stream)
                # For now, we'll collect audio and transcribe on demand

            except asyncio.TimeoutError:
                logger.warning("[Voice WS] Silence timeout for call %s", call_sid)
                break
            except Exception as e:
                logger.error("[Voice WS] Error receiving audio: %s", e)
                break

        logger.info("[Voice WS] Main loop ended for call %s (state: %s)", call_sid, orchestrator.state)

    except Exception as e:
        logger.error("[Voice WS] Unexpected error in call %s: %s", call_sid, e, exc_info=True)

    finally:
        # Log final call state
        if orchestrator:
            await orchestrator.on_call_end(reason="websocket_closed")
            logger.info("[Voice WS] Call %s logged (state: %s)", call_sid, orchestrator.state)

        # Clean up call mapping
        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        except Exception as e:
            logger.warning("[Voice WS] Failed to clean up call mapping: %s", e)

        # Close WebSocket
        try:
            await websocket.close()
        except Exception as e:
            logger.debug("[Voice WS] WebSocket already closed: %s", e)

        logger.info("[Voice WS] Closed call %s", call_sid)


# ── Manual initiation (from dashboard) ─────────────────────────────────────────


@router.post("/call/initiate-v2", status_code=status.HTTP_202_ACCEPTED)
async def initiate_call_v2(
    request: VoiceCallInitRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Manually trigger a voice call via new orchestrator.

    POST /api/cobranza/voice/call/initiate-v2
    {
        "debtor_id": "65f8c1a2b3c4d5e6f7g8h9i0"
    }

    Validates cobranza_enabled, Ley 2300 compliance, then initiates Twilio call.
    Returns 202 ACCEPTED with call_sid (call happens async).
    """
    from cobranza.call_scheduler import is_contact_allowed_now, has_been_contacted_today

    user_id = str(current_user["user_id"])
    db = get_db()
    debtor_id = request.debtor_id

    logger.info("[Voice Init] Initiating v2 call for debtor %s (user %s)", debtor_id, user_id)

    # ────────────────────────────────────────────────────────────────────────
    # Step 1: Check cobranza_enabled
    # ────────────────────────────────────────────────────────────────────────
    doc = await db.company_voice.find_one({"user_id": user_id})
    if not doc or not doc.get("cobranza_enabled", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cobranza no habilitado para esta cuenta.",
        )

    # ────────────────────────────────────────────────────────────────────────
    # Step 2: Check Ley 2300 compliance (contact hours)
    # ────────────────────────────────────────────────────────────────────────
    if not is_contact_allowed_now():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Fuera de horario permitido (Ley 2300)",
        )

    # ────────────────────────────────────────────────────────────────────────
    # Step 3: Fetch debtor
    # ────────────────────────────────────────────────────────────────────────
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if not debtor:
        raise HTTPException(status_code=404, detail="Debtor not found")

    # ────────────────────────────────────────────────────────────────────────
    # Step 4: Check Ley 2300 compliance (one contact per day)
    # ────────────────────────────────────────────────────────────────────────
    if has_been_contacted_today(debtor):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya fue contactado hoy (Ley 2300)",
        )

    # ────────────────────────────────────────────────────────────────────────
    # Step 5: Initiate Twilio outbound call
    # ────────────────────────────────────────────────────────────────────────
    try:
        from twilio.rest import Client

        account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        from_number = os.getenv("TWILIO_VOICE_PHONE_NUMBER")
        webhook_url = os.getenv("VOICE_WEBHOOK_HOST", "http://localhost:8001")

        if not all([account_sid, auth_token, from_number]):
            logger.error("[Voice Init] Twilio config incomplete")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Twilio not configured",
            )

        client = Client(account_sid, auth_token)
        to_number = debtor.get("telefono")

        # TwiML webhook URL (where Twilio calls us back with call started)
        twiml_callback_url = f"{webhook_url}/api/cobranza/voice/webhook"

        call = client.calls.create(
            to=to_number,
            from_=from_number,
            url=twiml_callback_url,
            method="POST",
        )

        call_sid = call.sid
        logger.info("[Voice Init] Call created: %s → %s", call_sid, to_number)

        # ────────────────────────────────────────────────────────────────────
        # Step 6: Store call mapping (call_sid → debtor_id, user_id)
        # ────────────────────────────────────────────────────────────────────
        await db.cobranza_calls_in_progress.insert_one({
            "call_sid": call_sid,
            "user_id": user_id,
            "debtor_id": str(debtor["_id"]),
            "debtor_name": debtor.get("nombre"),
            "debtor_phone": to_number,
            "started_at": datetime.now(timezone.utc),
        })

        # ────────────────────────────────────────────────────────────────────
        # Step 7: Update debtor estado to "llamando"
        # ────────────────────────────────────────────────────────────────────
        await update_debtor(db, user_id, debtor_id, {
            "estado": "llamando",
            "vapi_call_id": call_sid,  # Store as vapi_call_id for compatibility
        })

        return {
            "ok": True,
            "call_sid": call_sid,
            "message": "Call initiated (v2 orchestrator)",
        }

    except Exception as e:
        logger.error("[Voice Init] Twilio call creation failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate call: {str(e)[:100]}",
        )
