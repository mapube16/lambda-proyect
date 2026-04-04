"""
voice_router.py — FastAPI endpoints for voice orchestrator.

Handles:
1. POST /api/cobranza/voice/webhook — TwiML (Twilio callbacks)
2. WebSocket /api/cobranza/voice/ws/{call_id} — Real-time voice interaction
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, status
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor

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
    We:
    1. Receive audio frames
    2. Send to Assembly AI
    3. Get transcript
    4. Ask Claude what to say
    5. Synthesize with Google TTS
    6. Send audio back to Twilio

    This is the CORE of the orchestrator.
    """
    await websocket.accept()
    logger.info("[Voice WS] Connected call %s", call_sid)

    # TODO: Implement voice orchestrator loop
    # For now, we'll implement a skeleton

    try:
        # Step 1: Receive media stream from Twilio
        # Twilio sends audio frames in a specific format
        # We need to parse them and feed to Assembly AI

        # Step 2: Initialize Assembly AI stream
        # from cobranza.assembly_ai_client import AssemblyAIClient
        # assembly_ai = AssemblyAIClient()

        # Step 3: Main loop
        # - Receive audio frame from Twilio
        # - Send to Assembly AI
        # - Get transcript
        # - Ask Claude for decision
        # - Synthesize response
        # - Send audio back to Twilio

        while True:
            data = await websocket.receive_bytes()
            if not data:
                break

            # TODO: Parse Twilio media format
            # TODO: Send to Assembly AI
            # TODO: Process transcript
            # TODO: Get Claude decision
            # TODO: Synthesize response
            # TODO: Send back

            logger.debug("[Voice WS] Received %d bytes from %s", len(data), call_sid)

    except Exception as e:
        logger.error("[Voice WS] Error in call %s: %s", call_sid, e, exc_info=True)
    finally:
        await websocket.close()
        logger.info("[Voice WS] Closed call %s", call_sid)


# ── Manual initiation (from dashboard) ─────────────────────────────────────────


@router.post("/call/initiate-v2")
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
    """
    user_id = str(current_user["user_id"])
    db = get_db()

    # TODO: Check cobranza_enabled
    # TODO: Check Ley 2300 compliance
    # TODO: Fetch debtor
    # TODO: Initiate Twilio outbound call

    logger.info("[Voice Init] Initiating v2 call for debtor %s (user %s)", request.debtor_id, user_id)

    return {
        "ok": True,
        "message": "Call initiated (v2 orchestrator)",
        # "call_sid": "...",  # Once implemented
    }
