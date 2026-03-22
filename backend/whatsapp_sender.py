"""
whatsapp_sender.py — Meta Graph API v18.0 text message delivery for Landa outreach pipeline.
Env vars required: WA_TOKEN, WA_PHONE_ID
"""
import logging
import os

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API_URL = "https://graph.facebook.com/v18.0/{phone_id}/messages"


async def send_whatsapp_text(phone: str, message: str) -> bool:
    """Send a WhatsApp text message via Meta Graph API. Returns True on success, False on failure."""
    token = os.getenv("WA_TOKEN", "")
    phone_id = os.getenv("WA_PHONE_ID", "")

    if not token or not phone_id:
        logger.error("[whatsapp_sender] WA_TOKEN or WA_PHONE_ID not configured")
        return False

    url = _GRAPH_API_URL.format(phone_id=phone_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": phone,
        "type": "text",
        "text": {"body": message},
    }

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=payload)
            ok = resp.status_code in (200, 201)
            if not ok:
                logger.error("[whatsapp_sender] API error %d: %s", resp.status_code, resp.text[:200])
            return ok
    except Exception as exc:
        logger.error("[whatsapp_sender] Request error: %s", exc)
        return False
