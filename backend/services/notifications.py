import os
import logging
import base64
import httpx

from services.connection_manager import manager


async def send_whatsapp_text(phone: str, message: str) -> None:
    # Puente Baileys (numero desechable, SOLO equipo interno — allowlist en el
    # propio servicio) mientras Meta aprueba la cuenta oficial de DPG. Si esta
    # configurado y responde, listo; si falla o no esta, cae al camino Twilio
    # de siempre (que hoy es no-op por el numero placeholder, pero queda para
    # cuando haya WhatsApp oficial).
    bridge_url = os.getenv("BAILEYS_BRIDGE_URL", "").rstrip("/")
    if bridge_url:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{bridge_url}/send",
                    json={"to": phone, "text": message},
                    headers={"Authorization": f"Bearer {os.getenv('BAILEYS_BRIDGE_TOKEN', '')}"},
                )
            if resp.status_code == 200:
                return
            logging.error("[WA] baileys-bridge %d: %s — fallback Twilio", resp.status_code, resp.text[:200])
        except Exception as e:
            logging.error("[WA] baileys-bridge error: %s — fallback Twilio", e)

    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "")
    if not sid or not token or not from_number:
        logging.warning("[WA] Twilio creds not configured — skipping WA send")
        return
    wa_to = phone if phone.startswith("whatsapp:") else f"whatsapp:{phone}"
    auth = "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={"Authorization": auth},
                data={"To": wa_to, "From": from_number, "Body": message},
            )
            if resp.status_code not in (200, 201):
                logging.error("[WA] Twilio send error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logging.error("[WA] send_whatsapp_text error: %s", e)


def _format_wa_notification(event: dict) -> str:
    event_type = event.get("type", "")
    empresa = event.get("empresa", "")
    if event_type == "lead_checkpoint":
        puntaje = event.get("puntaje", 0)
        return f"Lead listo para revision: {empresa} (puntaje: {puntaje}). Escribe 'ver leads' para revisarlos."
    elif event_type == "lead_handover":
        canal = event.get("canal", "email")
        return f"{empresa} respondio. Escribe 'ver oportunidad' para tomar el control. Canal: {canal}."
    elif event_type == "lead_archived":
        return f"{empresa} fue archivado."
    else:
        return f"Actualizacion de Landa: {event_type}"


async def notify_user(user_id: str, event: dict) -> None:
    from landa.company_voice import get_or_create_company_voice
    cv = await get_or_create_company_voice(user_id)
    channel = cv.get("notification_channel", "web")

    if channel in ("web", "both"):
        await manager.send_to_user(user_id, event)

    if channel in ("whatsapp", "both"):
        wa_number = cv.get("wa_phone_number")
        if wa_number:
            await send_whatsapp_text(wa_number, _format_wa_notification(event))
