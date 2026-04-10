"""
voice_router.py — FastAPI endpoints for Pipecat voice orchestrator.

Endpoints:
1. POST /webhook — TwiML (upgrades to WebSocket)
2. WebSocket /ws/{call_sid} — Pipecat pipeline handles everything
3. POST /call/initiate-v2 — Outbound call initiation
"""
import logging
import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, status
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import get_debtor_by_id, update_debtor

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

    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=ws_url)
    response.append(connect)

    logger.info("[Webhook] TwiML -> Stream %s", ws_url)
    return PlainTextResponse(str(response), media_type="application/xml")


# ── WebSocket (Pipecat handles everything) ───────────────────────────────────


@router.websocket("/ws/{call_sid}")
async def voice_websocket(websocket: WebSocket, call_sid: str):
    """
    Twilio Media Streams WebSocket.

    Pipecat takes over: STT → LLM → TTS all streaming in parallel.
    """
    logger.info("[WS] Incoming connection for call %s", call_sid)

    db = get_db()

    try:
        # Load call context
        call_mapping = await db.cobranza_calls_in_progress.find_one({"call_sid": call_sid})

        if call_mapping:
            user_id = call_mapping["user_id"]
            debtor_id = call_mapping["debtor_id"]
            debtor = await get_debtor_by_id(db, user_id, debtor_id)
            config_doc = await db.cobranza_config.find_one({"user_id": user_id})
            estrategia = (config_doc or {}).get("estrategia", {})
        else:
            # POC fallback: no call mapping, use test debtor data
            print(f"[WS] No call mapping for {call_sid} — using POC test data", flush=True)
            debtor = {"nombre": "Juan", "monto": 500000, "vencimiento": "2024-01-01"}
            estrategia = {"tono": "profesional"}

        if not debtor:
            print(f"[WS] No debtor for {call_sid}, closing", flush=True)
            await websocket.accept()
            await websocket.close(1008, "Missing debtor")
            return

        logger.info("[WS] Starting Pipecat for call %s (debtor=%s)", call_sid, debtor.get("nombre"))

        # Pipecat needs the websocket already accepted
        await websocket.accept()
        logger.info("[WS] WebSocket accepted, handing to Pipecat")

        from cobranza.voice_pipecat import run_bot
        await run_bot(
            websocket=websocket,
            call_sid=call_sid,
            debtor=debtor,
            estrategia=estrategia,
        )

        logger.info("[WS] Pipecat finished for call %s", call_sid)

    except Exception as e:
        logger.error("[WS] Error: %s", e, exc_info=True)
    finally:
        # Cleanup
        try:
            await db.cobranza_calls_in_progress.delete_one({"call_sid": call_sid})
        except:
            pass
        logger.info("[WS] Cleanup done for %s", call_sid)


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

        return {"ok": True, "call_sid": call_sid, "message": "Call initiated (Pipecat)"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("[Init] Failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Failed: {str(e)[:100]}")
