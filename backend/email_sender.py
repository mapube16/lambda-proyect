"""
email_sender.py — SMTP email delivery con credenciales personalizadas del usuario.
Soporta credenciales del usuario o fallback a valores globales.
"""
import asyncio
import logging
import os
import smtplib
from email.mime.text import MIMEText
from typing import Optional

logger = logging.getLogger(__name__)


async def send_email(
    to: str,
    subject: str,
    body: str,
    sender_name: str,
    sender_email: str,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> bool:
    """
    Send a plain-text email via SMTP.

    Si se proporcionan credenciales personalizadas (smtp_host, smtp_port, smtp_user, smtp_password),
    las usa. Si no, intenta usar variables de entorno globales (SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS).

    Returns: True on success, False on failure.
    """

    # Usar credenciales personalizadas o fallback a env vars
    host = smtp_host or os.getenv("SMTP_HOST", "")
    port_str = str(smtp_port) if smtp_port else os.getenv("SMTP_PORT", "587")
    user = smtp_user or os.getenv("SMTP_USER", "")
    password = smtp_password or os.getenv("SMTP_PASS", "")

    if not all([host, user, password]):
        logger.error("[email_sender] SMTP_HOST, SMTP_USER, or SMTP_PASS not configured")
        return False

    try:
        port = int(port_str)
    except ValueError:
        logger.error(f"[email_sender] Invalid SMTP_PORT: {port_str}")
        return False

    def _send_sync() -> bool:
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = to

            # Puerto 465 = SSL implícito (SMTPS) → SMTP_SSL, NO starttls.
            # Puerto 587/25 = texto plano + STARTTLS.
            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                    server.login(user, password)
                    server.sendmail(sender_email, [to], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    server.ehlo()
                    try:
                        server.starttls()
                        server.ehlo()
                    except smtplib.SMTPException:
                        pass  # servidor sin STARTTLS (raro en 587)
                    server.login(user, password)
                    server.sendmail(sender_email, [to], msg.as_string())

            logger.info(f"[email_sender] Email sent to {to} via {host}:{port}")
            return True
        except smtplib.SMTPAuthenticationError as e:
            logger.error(f"[email_sender] SMTP authentication failed: {e}")
            return False
        except smtplib.SMTPException as e:
            logger.error(f"[email_sender] SMTP error: {e}")
            return False
        except Exception as e:
            logger.error(f"[email_sender] Error: {e}")
            return False

    return await asyncio.to_thread(_send_sync)


async def send_email_html(
    to: str,
    subject: str,
    html_body: str,
    sender_name: str,
    sender_email: str,
    smtp_host: Optional[str] = None,
    smtp_port: Optional[int] = None,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
) -> bool:
    """
    Send an HTML email via SMTP.
    Parámetros igual que send_email() pero acepta html_body.
    """

    host = smtp_host or os.getenv("SMTP_HOST", "")
    port_str = str(smtp_port) if smtp_port else os.getenv("SMTP_PORT", "587")
    user = smtp_user or os.getenv("SMTP_USER", "")
    password = smtp_password or os.getenv("SMTP_PASS", "")

    if not all([host, user, password]):
        logger.error("[email_sender] SMTP_HOST, SMTP_USER, or SMTP_PASS not configured")
        return False

    try:
        port = int(port_str)
    except ValueError:
        logger.error(f"[email_sender] Invalid SMTP_PORT: {port_str}")
        return False

    def _send_sync() -> bool:
        try:
            msg = MIMEText(html_body, "html", "utf-8")
            msg["Subject"] = subject
            msg["From"] = f"{sender_name} <{sender_email}>"
            msg["To"] = to

            if port == 465:
                with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                    server.login(user, password)
                    server.sendmail(sender_email, [to], msg.as_string())
            else:
                with smtplib.SMTP(host, port, timeout=30) as server:
                    server.ehlo()
                    try:
                        server.starttls()
                        server.ehlo()
                    except smtplib.SMTPException:
                        pass
                    server.login(user, password)
                    server.sendmail(sender_email, [to], msg.as_string())

            logger.info(f"[email_sender] HTML email sent to {to} via {host}:{port}")
            return True
        except Exception as e:
            logger.error(f"[email_sender] Error sending HTML email: {e}")
            return False

    return await asyncio.to_thread(_send_sync)
