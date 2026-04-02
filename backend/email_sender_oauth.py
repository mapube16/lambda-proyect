"""
email_sender_oauth.py — Envío de correos vía Gmail API y Microsoft Graph
para usuarios que conectaron sus cuentas personales.

Requerimientos:
- google-auth-oauthlib, google-auth-httplib2, google-api-python-client (Gmail)
- msal, msgraph-core (Outlook)
"""

import logging
import asyncio
import base64
import json
from typing import Optional
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Gmail API
# ─────────────────────────────────────────────────────────────────────────────

async def send_gmail(
    access_token: str,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    sender_email: str,
    sender_name: str,
    reply_to: str = "",
) -> Optional[str]:
    """
    Envía un correo vía Gmail API.
    Retorna el message_id si es exitoso, None si falla.
    """
    try:
        import httpx

        # Crear el mensaje
        msg = MIMEText(html_body, "html", "utf-8")
        msg["Subject"] = subject
        msg["From"] = f"{sender_name} <{sender_email}>"
        msg["To"] = f"{to_name} <{to_email}>"
        if reply_to:
            msg["Reply-To"] = reply_to

        # Codificar en base64
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()

        # Enviar vía Gmail API
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://www.googleapis.com/gmail/v1/users/me/messages/send",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"raw": raw},
                timeout=30
            )

            if resp.status_code not in (200, 201):
                logger.error(f"[email_sender_oauth] Gmail API error {resp.status_code}: {resp.text[:200]}")
                return None

            data = resp.json()
            message_id = data.get("id")
            logger.info(f"[email_sender_oauth] Gmail sent to {to_email}, message_id: {message_id}")
            return message_id

    except Exception as e:
        logger.error(f"[email_sender_oauth] Gmail send failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft Graph (Outlook)
# ─────────────────────────────────────────────────────────────────────────────

async def send_outlook(
    access_token: str,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    sender_email: str,
    sender_name: str,
    reply_to: str = "",
) -> Optional[str]:
    """
    Envía un correo vía Microsoft Graph (Outlook).
    Retorna el message_id si es exitoso, None si falla.
    """
    try:
        import httpx

        message_body = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": html_body,
            },
            "toRecipients": [
                {
                    "emailAddress": {
                        "address": to_email,
                        "name": to_name,
                    }
                }
            ],
            "from": {
                "emailAddress": {
                    "address": sender_email,
                    "name": sender_name,
                }
            },
        }

        if reply_to:
            message_body["replyTo"] = [
                {
                    "emailAddress": {
                        "address": reply_to,
                    }
                }
            ]

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://graph.microsoft.com/v1.0/me/sendMail",
                headers={"Authorization": f"Bearer {access_token}"},
                json={"message": message_body, "saveToSentItems": True},
                timeout=30
            )

            if resp.status_code not in (200, 202):
                logger.error(f"[email_sender_oauth] Outlook API error {resp.status_code}: {resp.text[:200]}")
                return None

            # Microsoft no devuelve el message_id en el response, generamos uno
            import uuid
            message_id = str(uuid.uuid4())
            logger.info(f"[email_sender_oauth] Outlook sent to {to_email}, message_id: {message_id}")
            return message_id

    except Exception as e:
        logger.error(f"[email_sender_oauth] Outlook send failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper público
# ─────────────────────────────────────────────────────────────────────────────

async def send_email_oauth(
    provider: str,
    access_token: str,
    to_email: str,
    to_name: str,
    subject: str,
    html_body: str,
    sender_email: str,
    sender_name: str,
    reply_to: str = "",
) -> Optional[str]:
    """
    Envía un correo usando la cuenta OAuth del usuario.
    provider: "gmail" | "outlook"
    Retorna el message_id si es exitoso.
    """
    if provider == "gmail":
        return await send_gmail(
            access_token=access_token,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_body=html_body,
            sender_email=sender_email,
            sender_name=sender_name,
            reply_to=reply_to,
        )
    elif provider == "outlook":
        return await send_outlook(
            access_token=access_token,
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html_body=html_body,
            sender_email=sender_email,
            sender_name=sender_name,
            reply_to=reply_to,
        )
    else:
        logger.error(f"[email_sender_oauth] Unknown provider: {provider}")
        return None
