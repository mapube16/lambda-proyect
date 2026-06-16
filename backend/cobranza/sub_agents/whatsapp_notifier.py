"""
whatsapp_notifier.py — Sub-agent for sending WhatsApp messages via ARQ.

Pattern: Fire-and-forget via ARQ job — returns IMMEDIATELY with acknowledgement.
Never awaits send completion to stay under the 3s Gemini tool-response limit (RESEARCH Pitfall 3).

Threat: T-25-05 — WhatsApp dispatched to ARQ; handler stays <3s.
"""
import logging

logger = logging.getLogger("cobranza.sub_agents.whatsapp_notifier")

# Lazily-imported ARQ pool helper (injected in tests via monkeypatch)
_arq_pool = None


async def get_arq_pool():
    """Get or create the shared ARQ pool. Importable for monkeypatching in tests."""
    global _arq_pool
    if _arq_pool is None:
        from arq_pool import create_arq_pool
        _arq_pool = await create_arq_pool()
    return _arq_pool


async def send_whatsapp(user_id: str, phone: str, message: str) -> dict:
    """
    Enqueue an ARQ job to send a WhatsApp message.

    Returns immediately with {"ok": True, "queued": True} after enqueue.
    NEVER awaits send completion — required by Gemini Live <3s tool limit.

    Args:
        user_id: Tenant's user_id (passed to the ARQ job for scoping).
        phone: Destination phone number (E.164 preferred).
        message: Message body to send.

    Returns:
        {"ok": True, "queued": True}             — on successful enqueue.
        {"ok": False, "error": "..."}            — on validation failure or enqueue error.
    """
    if not phone or not message:
        logger.warning("[whatsapp_notifier] phone y message requeridos user=%s", user_id)
        return {"ok": False, "error": "phone y message requeridos"}

    try:
        pool = await get_arq_pool()
        await pool.enqueue_job(
            "send_whatsapp_job",
            user_id=user_id,
            phone=phone,
            message=message,
        )
        logger.info("[whatsapp_notifier] enqueued for user=%s phone=%s", user_id, phone[:6] + "***")
        return {"ok": True, "queued": True}
    except Exception as e:
        logger.error("[whatsapp_notifier] enqueue failed user=%s: %s", user_id, e)
        return {"ok": False, "error": str(e)[:100]}
