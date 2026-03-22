"""
email_sender.py — SMTP email delivery for Landa outreach pipeline.
Env vars required: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS
"""
import asyncio
import logging
import os
import smtplib
from email.mime.text import MIMEText

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    body: str,
    sender_name: str,
    sender_email: str,
) -> bool:
    """Send a plain-text email via SMTP STARTTLS. Returns True on success, False on failure."""
    host = os.getenv("SMTP_HOST", "")
    port_str = os.getenv("SMTP_PORT", "587")
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASS", "")

    if not all([host, user, password]):
        logger.error("[email_sender] SMTP_HOST, SMTP_USER, or SMTP_PASS not configured")
        return False

    try:
        port = int(port_str)
    except ValueError:
        logger.error("[email_sender] Invalid SMTP_PORT: %s", port_str)
        return False

    def _send_sync() -> bool:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = to
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(sender_email, [to], msg.as_string())
            return True
        except Exception as exc:
            logger.error("[email_sender] SMTP error: %s", exc)
            return False

    return await asyncio.to_thread(_send_sync)
