import os
import asyncio
import logging
import json
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request, Body
from fastapi.responses import Response
from pydantic import BaseModel

from auth import get_current_user, require_staff
from database import (
    get_db, get_whatsapp_agent, upsert_whatsapp_agent,
    list_whatsapp_agents, delete_whatsapp_agent,
)
from services.notifications import send_whatsapp_text
import state

logger = logging.getLogger(__name__)

router = APIRouter()


class WhatsAppAgentConfig(BaseModel):
    phone_number: str
    twilio_from: str
    nombre_asesor: str
    empresa: str
    telefono_asesor: Optional[str] = None
    sectores: list[str] = []
    ciudad_default: Optional[str] = None
    cliente_id: Optional[str] = None
    activo: bool = True


async def _push_dlq(reason: str, payload: dict, error: Exception | None = None) -> None:
    try:
        arq_pool = state.arq_pool
        if arq_pool is None:
            logger.warning("[WA] DLQ unavailable: arq_pool is not ready")
            return
        item = {
            "type": "whatsapp_webhook",
            "reason": reason,
            "error": str(error) if error else "",
            "payload": payload,
        }
        await arq_pool.rpush("dlq:webhooks:whatsapp", json.dumps(item))
    except Exception as dlq_exc:
        logger.error("[WA] DLQ push failed: %s", dlq_exc)


async def _safe_task(coro, label: str, payload: dict):
    try:
        await coro
    except Exception as exc:
        logging.error("[WA] %s crashed: %s", label, exc, exc_info=True)
        await _push_dlq(label, payload, exc)


# ── Old Twilio webhook (legacy) ───────────────────────────────────────────────

@router.post("/api/whatsapp/webhook")
async def whatsapp_webhook(request: Request):
    from whatsapp_agent import handle_inbound_message
    form = await request.form()
    from_phone = (form.get("From") or "").replace("whatsapp:", "")
    from_twilio = form.get("To") or os.getenv("TWILIO_FROM_NUMBER", "")
    body = form.get("Body") or ""
    if not from_phone or not body:
        return {"ok": False, "error": "Missing From or Body"}
    agent_config = await get_whatsapp_agent(from_phone) or {}

    async def _run():
        try:
            await handle_inbound_message(from_phone, body, from_twilio, agent_config)
        except Exception as e:
            logger.error("[WA] handle error: %s", e, exc_info=True)
            await _push_dlq("legacy_webhook", {"from_phone": from_phone, "to_number": from_twilio, "body": body}, e)

    asyncio.create_task(_run())
    return Response(content="", media_type="text/xml")


# ── New routing webhook (multi-bot) ──────────────────────────────────────────

@router.post("/api/whatsapp/incoming")
async def whatsapp_incoming(request: Request):
    import wa_handler
    from debug_logger import get_payload_logger
    from database import get_wa_bot_config, set_wa_bot_mode

    debug_log = get_payload_logger()
    form = await request.form()
    from_raw = str(form.get("From", ""))
    to_number = str(form.get("To", ""))
    body = str(form.get("Body", ""))
    num_media = int(form.get("NumMedia", "0"))
    media_url = str(form.get("MediaUrl0", "")) if num_media > 0 else ""
    from_phone = from_raw.replace("whatsapp:", "")

    debug_log.log_event("webhook_received", {"from_phone": from_phone, "to_number": to_number, "body": body, "has_media": num_media > 0, "media_url": media_url or None, "body_length": len(body)}, level="DEBUG")

    forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    forwarded_host = request.headers.get("X-Forwarded-Host", "") or request.headers.get("Host", "")
    url = f"{forwarded_proto}://{forwarded_host}{request.url.path}" if forwarded_proto and forwarded_host else str(request.url)
    signature = request.headers.get("X-Twilio-Signature", "")
    if not wa_handler.validate_twilio_signature(url, signature, dict(form)):
        logging.warning("[WA] Invalid Twilio signature from %s", from_raw)
        return Response(content="<Response/>", media_type="text/xml")

    profile = await wa_handler.get_profile(from_phone)
    if profile is None:
        logging.warning("[WA] Unknown number %s", from_phone)
        return Response(content="<Response/>", media_type="text/xml")

    cmd = body.strip().lower()
    if cmd in ("/secop", "/landa"):
        config = await get_wa_bot_config(from_phone)
        target = "legacy" if cmd == "/secop" else "landa"
        flag_key = "secop" if cmd == "/secop" else "landa"
        if not config["bots"].get(flag_key):
            await send_whatsapp_text(from_phone, "Ese bot no esta habilitado para tu cuenta.")
        else:
            await set_wa_bot_mode(from_phone, target)
            await send_whatsapp_text(from_phone, f"Modo {'SECOP' if target == 'legacy' else 'Landa'} activado.")
        return Response(content="<Response/>", media_type="text/xml")

    config = await get_wa_bot_config(from_phone)
    bot_mode = config["active"]

    if bot_mode == "legacy":
        from whatsapp_agent import handle_inbound_message
        agent_config = await get_whatsapp_agent(from_phone) or {}
        async def _legacy():
            try:
                await handle_inbound_message(from_phone, body, to_number, agent_config)
            except Exception as e:
                logging.error("[WA] legacy bot error: %s", e)
                await _push_dlq("legacy_bot", {"from_phone": from_phone, "to_number": to_number, "body": body}, e)
        asyncio.create_task(_legacy())
    elif bot_mode == "calendar":
        try:
            from calendar_agent import process_calendar_message
            asyncio.create_task(process_calendar_message(from_phone, body, media_url))
        except ImportError:
            asyncio.create_task(_safe_task(wa_handler.process_inbound(from_phone=from_phone, to_number=to_number, body="Agente de calendario no disponible aun.", media_url="", profile=profile), "process_inbound/calendar", {"from_phone": from_phone, "to_number": to_number, "body": body, "media_url": media_url}))
    else:
        asyncio.create_task(_safe_task(wa_handler.process_inbound(from_phone=from_phone, to_number=to_number, body=body, media_url=media_url, profile=profile), "process_inbound", {"from_phone": from_phone, "to_number": to_number, "body": body, "media_url": media_url}))

    return Response(content="<Response/>", media_type="text/xml")


# ── WhatsApp Agents CRUD ──────────────────────────────────────────────────────

@router.post("/api/whatsapp-agents", dependencies=[Depends(require_staff)])
async def create_whatsapp_agent(config: WhatsAppAgentConfig):
    return await upsert_whatsapp_agent(config.model_dump())


@router.get("/api/whatsapp-agents", dependencies=[Depends(require_staff)])
async def list_agents(cliente_id: Optional[str] = None):
    return await list_whatsapp_agents(cliente_id)


@router.get("/api/whatsapp-agents/{phone_number}", dependencies=[Depends(require_staff)])
async def get_agent(phone_number: str):
    doc = await get_whatsapp_agent(phone_number)
    if not doc:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return doc


@router.delete("/api/whatsapp-agents/{phone_number}", dependencies=[Depends(require_staff)])
async def remove_agent(phone_number: str):
    ok = await delete_whatsapp_agent(phone_number)
    if not ok:
        raise HTTPException(status_code=404, detail="Agente no encontrado")
    return {"ok": True}
