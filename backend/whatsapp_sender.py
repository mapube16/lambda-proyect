"""
whatsapp_sender.py — Meta WhatsApp Cloud API (Graph) message delivery for the
Landa outreach pipeline.

Env vars:
  WA_TOKEN        (required)  System-User permanent access token
  WA_PHONE_ID     (required)  approved WhatsApp phone number ID
  WA_API_VERSION  (optional)  Graph API version, default "v18.0"

Dos formas de envío:
  - send_whatsapp_text:     texto libre. SOLO válido dentro de la ventana de
                            servicio de 24h (respuesta a un mensaje del usuario).
  - send_whatsapp_template: mensaje de PLANTILLA aprobada por Meta. Es el único
                            camino permitido para PRIMER contacto / fuera de las
                            24h (outreach en frío).
"""
import logging
import os
import re

import httpx

logger = logging.getLogger(__name__)

_GRAPH_API_URL = "https://graph.facebook.com/{version}/{phone_id}/messages"


def _api_version() -> str:
    return os.getenv("WA_API_VERSION", "v18.0")


def _normalize_phone(phone: str) -> str:
    """Meta espera el número en E.164 sin '+': solo dígitos (ej: 573001112233)."""
    return re.sub(r"\D", "", str(phone or ""))


# ── Builders puros (testeables sin red) ─────────────────────────────────────────

def _build_text_payload(phone: str, message: str) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(phone),
        "type": "text",
        "text": {"body": message},
    }


def _build_template_payload(
    phone: str, template_name: str, language_code: str, components: list
) -> dict:
    return {
        "messaging_product": "whatsapp",
        "to": _normalize_phone(phone),
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language_code},
            "components": components or [],
        },
    }


# ── Envío ────────────────────────────────────────────────────────────────────

async def _post_message(payload: dict) -> bool:
    """POST al Cloud API. Devuelve True en éxito, False en fallo (nunca lanza)."""
    token = os.getenv("WA_TOKEN", "")
    phone_id = os.getenv("WA_PHONE_ID", "")

    if not token or not phone_id:
        logger.error("[whatsapp_sender] WA_TOKEN or WA_PHONE_ID not configured")
        return False

    url = _GRAPH_API_URL.format(version=_api_version(), phone_id=phone_id)
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(url, headers=headers, json=payload)
            ok = resp.status_code in (200, 201)
            if not ok:
                logger.error("[whatsapp_sender] API error %d: %s", resp.status_code, resp.text[:300])
            return ok
    except Exception as exc:
        logger.error("[whatsapp_sender] Request error: %s", exc)
        return False


async def send_whatsapp_text(phone: str, message: str) -> bool:
    """
    Envía texto libre por WhatsApp (Meta Cloud API). Returns True on success.

    OJO: Meta solo entrega texto libre dentro de la ventana de 24h desde el
    último mensaje del usuario. Para primer contacto / fuera de 24h usa
    send_whatsapp_template.
    """
    return await _post_message(_build_text_payload(phone, message))


async def send_whatsapp_template(
    phone: str,
    template_name: str,
    language_code: str = "es",
    components: list | None = None,
    body_params: list | None = None,
) -> bool:
    """
    Envía un mensaje de PLANTILLA aprobada por Meta. Único camino válido para
    primer contacto / fuera de la ventana de 24h.

    Args:
      template_name: nombre EXACTO de la plantilla aprobada en el WABA.
      language_code: código de idioma de la plantilla (ej: "es", "es_CO").
      components:    estructura cruda de components de Meta (header/body/buttons)
                     para casos avanzados. Tiene prioridad sobre body_params.
      body_params:   atajo — lista de valores que rellenan las variables {{1}},
                     {{2}}… del cuerpo, en orden. Se ignora si `components` viene.
    """
    if components is None and body_params:
        components = [{
            "type": "body",
            "parameters": [{"type": "text", "text": str(p)} for p in body_params],
        }]
    return await _post_message(
        _build_template_payload(phone, template_name, language_code, components or [])
    )
