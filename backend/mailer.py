"""
mailer.py — MailerSend integration for Isomorph platform.

Three email templates:
  1. send_welcome_email      — New client onboarded: credentials + agent team + campaign
  2. send_lead_outreach      — Automated outreach to a prospected lead (AI draft)
  3. send_staff_summary      — Staff notification when a new client is configured
"""

import logging
import os
import re

logger = logging.getLogger("mailer")

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _env_clean(key: str, default: str = "") -> str:
  """
  Read env var and sanitize common misconfigurations:
  - trims spaces
  - strips inline comments after '#'
  """
  raw = os.getenv(key, default) or ""
  return raw.split("#", 1)[0].strip()


def _validate_email(value: str, field_name: str) -> str:
  email = (value or "").strip()
  if not email:
    raise RuntimeError(f"{field_name} is empty")
  if not _EMAIL_RE.match(email):
    raise RuntimeError(f"{field_name} is invalid: '{email}'")
  return email

# ─────────────────────────────────────────────────────────────────────────────
# Shared palette / base styles
# ─────────────────────────────────────────────────────────────────────────────
_BG        = "#0f0f1a"
_BG2       = "#1a1a2e"
_BORDER    = "#2a2a4a"
_CYAN      = "#78dce8"
_GREEN     = "#a9dc76"
_YELLOW    = "#ffd866"
_PINK      = "#ff6188"
_WHITE     = "#e0e0e0"
_MUTED     = "#888888"
_AGENT_COLORS = ["#78dce8", "#a9dc76", "#ffd866", "#ff6188", "#ab9df2", "#fc9867"]

_BASE_STYLE = """
  body { margin:0; padding:0; background:#0f0f1a; font-family:'Segoe UI',Arial,sans-serif; color:#e0e0e0; }
  .wrapper { max-width:600px; margin:0 auto; background:#1a1a2e; border-radius:12px; overflow:hidden; }
  .header  { background:linear-gradient(135deg,#16162a,#1e1e3a); padding:32px 36px; border-bottom:1px solid #2a2a4a; }
  .logo    { font-size:28px; font-weight:800; color:#78dce8; letter-spacing:-1px; }
  .logo span { color:#ffd866; }
  .tagline { font-size:12px; color:#888; margin-top:4px; }
  .body    { padding:32px 36px; }
  .section { margin-bottom:28px; }
  .section-title { font-size:11px; font-weight:700; text-transform:uppercase; letter-spacing:1.5px; color:#78dce8; margin-bottom:12px; }
  .card    { background:#131326; border:1px solid #2a2a4a; border-radius:10px; padding:16px 20px; }
  .row     { display:flex; align-items:flex-start; gap:12px; margin-bottom:8px; }
  .label   { font-size:11px; color:#888; min-width:120px; padding-top:2px; }
  .value   { font-size:13px; color:#e0e0e0; flex:1; }
  .agent-row { display:flex; align-items:center; gap:12px; padding:8px 0; border-bottom:1px solid #2a2a4a; }
  .agent-dot { width:10px; height:10px; border-radius:50%; flex-shrink:0; }
  .agent-name { font-size:13px; font-weight:600; color:#e0e0e0; }
  .agent-role { font-size:11px; color:#888; margin-top:2px; }
  .pill    { display:inline-block; padding:3px 10px; border-radius:20px; font-size:11px; background:#2a2a4a; color:#aaa; }
  .cta     { display:block; text-align:center; margin:24px 0; padding:14px 0; background:linear-gradient(135deg,#7c3aed,#06b6d4); border-radius:10px; color:#fff; font-weight:700; font-size:15px; text-decoration:none; }
  .divider { border:none; border-top:1px solid #2a2a4a; margin:24px 0; }
  .footer  { padding:20px 36px; border-top:1px solid #2a2a4a; text-align:center; font-size:11px; color:#555; }
  .highlight { color:#ffd866; font-weight:600; }
  .code-box { background:#0f0f1a; border:1px solid #2a2a4a; border-radius:8px; padding:14px 18px; font-family:monospace; font-size:14px; color:#a9dc76; letter-spacing:0.5px; text-align:center; }
""".strip()


def _html_wrap(title: str, body_html: str, preheader: str = "") -> str:
    """Wrap body HTML in base email shell."""
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title}</title>
  <style>{_BASE_STYLE}</style>
</head>
<body>
  {"<div style='display:none;max-height:0;overflow:hidden;'>" + preheader + "</div>" if preheader else ""}
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f1a;padding:32px 16px;">
    <tr><td align="center">
      <div class="wrapper">
        <div class="header">
          <div class="logo">ISOMORPH<span>.</span></div>
          <div class="tagline">Plataforma de Prospección B2B Automatizada</div>
        </div>
        <div class="body">
          {body_html}
        </div>
        <div class="footer">
          © 2026 Isomorph · Prospección inteligente con IA<br>
          Este correo fue generado automáticamente por la plataforma.
        </div>
      </div>
    </td></tr>
  </table>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────────────
# Template 1 — Bienvenida al cliente
# ─────────────────────────────────────────────────────────────────────────────

def _render_welcome(
    client_email: str,
    client_password: str,
    agents: list,
    campaign: dict,
    business_summary: str,
    login_url: str = "http://localhost:5173",
) -> tuple[str, str]:
    """Returns (subject, html)."""
    subject = f"🐝 Tu equipo de prospección está listo — {campaign.get('empresa_remitente', 'Isomorph')}"

    # Agents rows
    agents_html = ""
    for i, ag in enumerate(agents):
        color = _AGENT_COLORS[i % len(_AGENT_COLORS)]
        channel_badge = ""
        if ag.get("channel") == "whatsapp":
            channel_badge = f"<span style='font-size:10px;background:#1a3a1a;color:#a9dc76;padding:2px 7px;border-radius:10px;margin-left:8px;'>WhatsApp</span>"
        agents_html += f"""
        <div class="agent-row">
          <div class="agent-dot" style="background:{color};"></div>
          <div>
            <div class="agent-name">{ag.get('name', ag.get('id', 'Agente'))}{channel_badge}</div>
            <div class="agent-role">{ag.get('persona', ag.get('role', ''))}</div>
          </div>
        </div>"""

    # Campaign vars
    camp_labels = {
        "industria_objetivo": "Industria objetivo",
        "ciudad_objetivo":    "Ciudad",
        "dolor_operativo":    "Dolor operativo",
        "solucion_ofrecida":  "Solución ofrecida",
        "software_clave":     "Software clave",
        "jerarquia_decisores":"Decisores",
    }
    camp_rows = ""
    for key, label in camp_labels.items():
        val = campaign.get(key)
        if val:
            camp_rows += f"""
            <div class="row">
              <span class="label">{label}</span>
              <span class="value">{val}</span>
            </div>"""

    body = f"""
      <div class="section">
        <p style="font-size:22px;font-weight:700;color:#e0e0e0;margin:0 0 8px;">
          ¡Bienvenido a Isomorph! 🐝
        </p>
        <p style="color:#888;font-size:14px;margin:0;">
          Tu equipo de agentes de prospección está configurado y listo para trabajar.
        </p>
      </div>

      <div class="section">
        <div class="section-title">Resumen del negocio</div>
        <div class="card" style="font-size:13px;color:#ccc;line-height:1.6;">{business_summary}</div>
      </div>

      <div class="section">
        <div class="section-title">Tus datos de acceso</div>
        <div class="card">
          <div class="row">
            <span class="label">Email</span>
            <span class="value highlight">{client_email}</span>
          </div>
          <div class="row">
            <span class="label">Contraseña</span>
            <span class="value">
              <div class="code-box">{client_password}</div>
            </span>
          </div>
        </div>
        <a href="{login_url}" class="cta">Acceder a la plataforma →</a>
      </div>

      <div class="section">
        <div class="section-title">Tu equipo de agentes ({len(agents)} agentes)</div>
        <div class="card">{agents_html}</div>
      </div>

      <div class="section">
        <div class="section-title">Configuración de campaña</div>
        <div class="card">{camp_rows}</div>
      </div>

      <p style="font-size:12px;color:#555;text-align:center;margin-top:8px;">
        Si tienes dudas, responde a este correo y un estratega de Isomorph te atenderá.
      </p>
    """

    return subject, _html_wrap(subject, body, preheader=f"Tu equipo de {len(agents)} agentes está listo para prospectar.")


# ─────────────────────────────────────────────────────────────────────────────
# Template 2 — Outreach a lead (correo de prospección generado por IA)
# ─────────────────────────────────────────────────────────────────────────────

def _render_lead_outreach(
    subject: str,
    body_text: str,
    sender_name: str,
    sender_empresa: str,
) -> str:
    """Returns HTML for the lead outreach email. The body_text is the AI-generated draft."""
    # Convert plain text (paragraphs separated by \n\n) to HTML paragraphs
    paragraphs = [p.strip() for p in body_text.split("\n\n") if p.strip()]
    para_html = "".join(f"<p style='margin:0 0 16px;font-size:15px;line-height:1.7;color:#2d2d2d;'>{p.replace(chr(10), '<br>')}</p>" for p in paragraphs)

    # For lead outreach we use a lighter, more professional template
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{subject}</title>
</head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.08);">
        <tr>
          <td style="padding:40px 48px;">
            {para_html}
            <hr style="border:none;border-top:1px solid #eee;margin:32px 0;">
            <p style="margin:0;font-size:13px;color:#999;text-align:center;">
              {sender_name} · {sender_empresa}
            </p>
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Template 3 — Resumen de configuración para staff
# ─────────────────────────────────────────────────────────────────────────────

def _render_staff_summary(
    client_email: str,
    business_summary: str,
    agents: list,
    campaign: dict,
) -> tuple[str, str]:
    """Returns (subject, html)."""
    empresa = campaign.get("empresa_remitente", client_email)
    subject = f"🐝 Nuevo cliente onboardado: {empresa}"

    agents_html = ""
    for i, ag in enumerate(agents):
        color = _AGENT_COLORS[i % len(_AGENT_COLORS)]
        channel = ag.get("channel", "email")
        channel_color = "#a9dc76" if channel == "whatsapp" else "#78dce8"
        agents_html += f"""
        <div class="agent-row">
          <div class="agent-dot" style="background:{color};"></div>
          <div>
            <div class="agent-name">{ag.get('name', ag.get('id', 'Agente'))}
              <span style="font-size:10px;background:#1e1e35;color:{channel_color};padding:2px 7px;border-radius:10px;margin-left:6px;">{channel}</span>
            </div>
            <div class="agent-role">{ag.get('persona', ag.get('role', ''))}</div>
          </div>
        </div>"""

    camp_rows = ""
    for key, val in campaign.items():
        if val and key not in ("nombre_remitente", "empresa_remitente"):
            label = key.replace("_", " ").title()
            camp_rows += f"""
            <div class="row">
              <span class="label">{label}</span>
              <span class="value">{val}</span>
            </div>"""

    body = f"""
      <div class="section">
        <p style="font-size:20px;font-weight:700;color:#e0e0e0;margin:0 0 6px;">Nuevo cliente configurado</p>
        <p style="color:#888;font-size:13px;margin:0;">El equipo de agentes ha sido propuesto y aprobado por staff.</p>
      </div>

      <div class="section">
        <div class="section-title">Cliente</div>
        <div class="card">
          <div class="row">
            <span class="label">Email</span>
            <span class="value highlight">{client_email}</span>
          </div>
          <div class="row">
            <span class="label">Empresa</span>
            <span class="value">{empresa}</span>
          </div>
          <div class="row">
            <span class="label">Remitente</span>
            <span class="value">{campaign.get('nombre_remitente', '[sin definir]')}</span>
          </div>
        </div>
      </div>

      <div class="section">
        <div class="section-title">Resumen del negocio</div>
        <div class="card" style="font-size:13px;color:#ccc;line-height:1.6;">{business_summary}</div>
      </div>

      <div class="section">
        <div class="section-title">Equipo de agentes ({len(agents)} agentes)</div>
        <div class="card">{agents_html}</div>
      </div>

      <div class="section">
        <div class="section-title">Variables de campaña</div>
        <div class="card">{camp_rows}</div>
      </div>
    """

    return subject, _html_wrap(subject, body, preheader=f"Nuevo cliente: {empresa} — {len(agents)} agentes configurados.")


# ─────────────────────────────────────────────────────────────────────────────
# Send helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_client():
    from mailersend import MailerSendClient
    api_key = _env_clean("MAILERSEND_API_KEY")
    if not api_key:
        raise RuntimeError("MAILERSEND_API_KEY not configured")
    return MailerSendClient(api_key=api_key)


def _send(
    from_email: str,
    from_name: str,
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    text: str = "",
    reply_to_email: str = "",
    reply_to_name: str = "",
) -> int:
    """Send one email via MailerSend. Returns HTTP status code.

    EmailBuilder.from_email/.to/.reply_to take raw (email, name) strings, NOT
    a pre-built EmailContact — the SDK constructs EmailContact internally.
    Passing an EmailContact object (the previous code here) double-wraps it
    and fails pydantic validation. Confirmed against the installed SDK via
    inspect.signature since this diverges from what older docs/snippets show."""
    from mailersend import EmailBuilder

    from_email = _validate_email(from_email, "MAILERSEND_FROM_EMAIL")
    to_email = _validate_email(to_email, "to_email")
    if reply_to_email:
        reply_to_email = _validate_email(reply_to_email, "reply_to_email")

    builder = (
        EmailBuilder()
        .from_email(from_email, from_name)
        .to(to_email, to_name)
        .subject(subject)
        .html(html)
    )
    if text:
        builder = builder.text(text)
    if reply_to_email:
        builder = builder.reply_to(reply_to_email, reply_to_name or reply_to_email)

    email_obj = builder.build()
    client = _get_client()
    response = client.emails.send(email_obj)
    status = getattr(response, "status_code", 202)
    logger.info(f"[mailer] sent '{subject}' → {to_email} (status {status})")
    return status


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def send_welcome_email(
    client_email: str,
    client_password: str,
    agents: list,
    campaign: dict,
    business_summary: str,
    login_url: str = "http://localhost:5173",
) -> None:
    """Send onboarding welcome email to the new client."""
    from_email = _env_clean("MAILERSEND_FROM_EMAIL", "noreply@isomorph.co")
    from_name = "Isomorph"
    subject, html = _render_welcome(client_email, client_password, agents, campaign, business_summary, login_url)
    _send(from_email, from_name, client_email, campaign.get("nombre_remitente", ""), subject, html)


async def send_lead_outreach(
    to_email: str,
    to_name: str,
    subject: str,
    body_text: str,
    sender_name: str,
    sender_empresa: str,
    reply_to_email: str = "",
    user_id: str = None,
) -> int:
    """
    Send the AI-generated prospecting email to a lead.
    Intenta en este orden:
    1. SMTP del usuario (si está configurado)
    2. OAuth tokens (Gmail/Outlook)
    3. Fallback a MailerSend global

    Retorna el status code HTTP (202 si éxito, otro si falla).
    """
    html = _render_lead_outreach(subject, body_text, sender_name, sender_empresa)

    if user_id:
        # Intentar SMTP primero (más rápido)
        success = await _send_lead_outreach_smtp(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html=html,
            sender_name=sender_name,
            sender_empresa=sender_empresa,
            reply_to_email=reply_to_email,
            user_id=user_id,
        )
        if success:
            logger.info(f"[mailer] Sent outreach email via SMTP to {to_email}")
            return 202

        # Intentar OAuth si SMTP no funcionó
        message_id = await _send_lead_outreach_oauth(
            to_email=to_email,
            to_name=to_name,
            subject=subject,
            html=html,
            sender_name=sender_name,
            sender_empresa=sender_empresa,
            reply_to_email=reply_to_email,
            user_id=user_id,
        )
        if message_id:
            logger.info(f"[mailer] Sent outreach email via OAuth to {to_email}, message_id: {message_id}")
            return 202

    # Fallback a MailerSend global
    from_email = _env_clean("MAILERSEND_FROM_EMAIL", "noreply@isomorph.co")
    from_name = f"{sender_name} vía Isomorph" if sender_name else "Isomorph"
    return _send(
        from_email, from_name,
        to_email, to_name,
        subject, html, text=body_text,
        reply_to_email=reply_to_email or from_email,
        reply_to_name=sender_name,
    )


async def _send_lead_outreach_smtp(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    sender_name: str,
    sender_empresa: str,
    reply_to_email: str,
    user_id: str,
) -> bool:
    """
    Intenta enviar usando SMTP del usuario.
    Retorna True si es exitoso, False si falla o no está configurado.
    """
    from database import get_smtp_config
    from email_oauth import decrypt_tokens
    from email_sender import send_email_html

    config_encrypted = await get_smtp_config(user_id)
    if not config_encrypted:
        return False

    try:
        config = decrypt_tokens(config_encrypted)
        email = config.get("email")
        password = config.get("password")
        smtp_host = config.get("smtp_host")
        smtp_port = config.get("smtp_port")

        if not all([email, password, smtp_host, smtp_port]):
            logger.warning(f"[mailer] Incomplete SMTP config for user {user_id}")
            return False

        # Enviar con SMTP del usuario
        success = await send_email_html(
            to=to_email,
            subject=subject,
            html_body=html,
            sender_name=sender_name,
            sender_email=email,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_user=email,
            smtp_password=password,
        )

        return success

    except Exception as e:
        logger.error(f"[mailer] Failed to send via SMTP for user {user_id}: {e}")
        return False


async def _send_lead_outreach_oauth(
    to_email: str,
    to_name: str,
    subject: str,
    html: str,
    sender_name: str,
    sender_empresa: str,
    reply_to_email: str,
    user_id: str,
) -> str:
    """
    Intenta enviar usando los tokens OAuth del usuario.
    Retorna message_id si es exitoso, None si falla.
    """
    from database import get_email_oauth_tokens
    from email_oauth import decrypt_tokens
    from email_sender_oauth import send_email_oauth

    tokens_info = await get_email_oauth_tokens(user_id)
    if not tokens_info:
        return None

    provider = tokens_info.get("provider")
    encrypted_tokens = tokens_info.get("encrypted_tokens")
    sender_email = tokens_info.get("email_sender_address")

    if not all([provider, encrypted_tokens, sender_email]):
        logger.warning(f"[mailer] Incomplete OAuth tokens for user {user_id}")
        return None

    # Desencriptar tokens
    try:
        tokens = decrypt_tokens(encrypted_tokens)
        access_token = tokens.get("access_token")
        if not access_token:
            logger.warning(f"[mailer] No access_token for user {user_id}")
            return None
    except Exception as e:
        logger.error(f"[mailer] Failed to decrypt tokens for user {user_id}: {e}")
        return None

    # Enviar con Gmail API o Microsoft Graph
    message_id = await send_email_oauth(
        provider=provider,
        access_token=access_token,
        to_email=to_email,
        to_name=to_name,
        subject=subject,
        html_body=html,
        sender_email=sender_email,
        sender_name=sender_name,
        reply_to=reply_to_email,
    )

    return message_id


async def send_staff_summary(
    staff_email: str,
    client_email: str,
    business_summary: str,
    agents: list,
    campaign: dict,
) -> None:
    """Send a configuration summary to the Isomorph staff email."""
    from_email = _env_clean("MAILERSEND_FROM_EMAIL", "noreply@isomorph.co")
    staff_email = _env_clean("MAILERSEND_STAFF_EMAIL", staff_email)
    subject, html = _render_staff_summary(client_email, business_summary, agents, campaign)
    _send(from_email, "Isomorph Platform", staff_email, "Staff Isomorph", subject, html)
