"""
whatsapp_notifier.py — Sub-agent for sending WhatsApp messages to the DEBTOR.

Fase 6 (entregable #8 del contrato lambda-handoff): este módulo encolaba un
job ARQ "send_whatsapp_job" que NINGÚN worker registra (confirmado contra
landa-agent-service) — cada mensaje al deudor se perdía en silencio. Ahora
hace el handoff REAL a landa-agent-service (dueño del canal WhatsApp del
deudor — Meta Cloud API, sus 13 capas de seguridad, Chatwoot) vía
cobranza/wa_bridge.py (Contrato A: POST /case/handoff).

Threat: T-25-05 — el envío real (HTTP a WA) puede tardar; se corre con un
timeout corto (15s en wa_bridge) para no bloquear el turno de Gemini Live
más allá de lo razonable. Nunca lanza — un fallo de red no tumba la llamada.
"""
import logging

from database import get_db

logger = logging.getLogger("cobranza.sub_agents.whatsapp_notifier")


async def send_whatsapp(user_id: str, phone: str, message: str) -> dict:
    """
    Envía `message` al DEUDOR con ese `phone` vía el puente a landa-agent-service.

    Busca el deudor por (user_id, phone) para armar el payload completo del
    handoff (case_id, póliza, etc.) — el llamador (voice_pipecat) solo tenía
    el teléfono, no el documento completo.

    Returns:
        {"ok": True, "case_id": ..., "sent": bool}  — handoff intentado.
        {"ok": False, "error": "..."}                — validación o fallo de red.
    """
    if not phone or not message:
        logger.warning("[whatsapp_notifier] phone y message requeridos user=%s", user_id)
        return {"ok": False, "error": "phone y message requeridos"}

    db = get_db()
    debtor = await db.debtors.find_one({"user_id": user_id, "telefono": phone})
    if debtor is None:
        logger.warning("[whatsapp_notifier] deudor no encontrado phone=%s user=%s", phone[:6] + "***", user_id)
        return {"ok": False, "error": "deudor no encontrado"}

    from cobranza.wa_bridge import handoff_to_wa
    return await handoff_to_wa(db, user_id, debtor, message=message)
