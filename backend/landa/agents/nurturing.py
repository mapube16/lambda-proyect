"""
nurturing.py — Agente Nurturing para ciclo mensual de seguimiento.

Invocado desde:
  - backend/landa/scheduler.py cuando job tipo=nurturing se activa
  - Directo para re-engagement manual (Phase 14)
"""
from __future__ import annotations

import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from landa.company_voice import get_or_create_company_voice
from landa.sector_profiles import generate_sector_profile
from landa.core.context import call_agent, build_system_prompt, TEMP_NURTURING
from email_sender import send_email
from whatsapp_sender import send_whatsapp_text

logger = logging.getLogger(__name__)

# Content strategy instructions per motivo_nurturing
_MOTIVO_INSTRUCTIONS = {
    "score_bajo": (
        "Genera contenido educativo sobre el sector. "
        "NO hagas pitch de ventas. Foco en tendencias, datos, buenas practicas. "
        "Cierra con una pregunta abierta no comercial."
    ),
    "rechazado_humano": (
        "Genera mensaje de valor puro. "
        "NO menciones nuestra empresa ni servicios. "
        "Comparte insight valioso del sector. Mantén la relacion a largo plazo."
    ),
    "sin_respuesta": (
        "Genera un toque suave diferente a los intentos previos de outreach. "
        "Mas corto, diferente angulo. Sin presion."
    ),
    "respuesta_negativa": (
        "Genera contenido de largo plazo. Foco en tendencias del sector a 6-12 meses. "
        "No pidas nada. Posiciona como fuente de informacion."
    ),
}

NURTURING_SYSTEM_TEMPLATE = """
Eres el agente de nurturing de [EMPRESA_REMITENTE].
Voz de marca: [TONO_COMUNICACION].
Sector del prospecto: [SECTOR].
Ciclo de nurturing numero: [CICLO].
Motivo de nurturing: [MOTIVO].

Instrucciones de contenido: [INSTRUCCIONES_MOTIVO]

Senales de reentrada a detectar (si el prospecto las menciona, esta listo para retomar): [SENALES_REENTRADA]
"""


async def run_nurturing(
    lead_id: str,
    user_id: str,
) -> dict:
    """
    Run one nurturing cycle for a lead.
    Returns: {mensaje_enviado: str, senial_detectada: bool, nuevo_estado: str}
    """
    from database import get_db
    from bson import ObjectId
    from landa.state_machine import update_lead_estado

    db = get_db()
    lead = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    if not lead:
        logger.error("[nurturing_agent] Lead %s not found for user %s", lead_id, user_id)
        return {"mensaje_enviado": "", "senial_detectada": False, "nuevo_estado": "nurturing"}

    motivo = lead.get("motivo_nurturing", "sin_respuesta")
    ciclo = int(lead.get("ciclo_nurturing") or 0)
    decisor = lead.get("decisor") or {}
    canal_elegido = lead.get("canal_elegido", "email")

    company_voice = await get_or_create_company_voice(user_id)
    sector = lead.get("sector") or company_voice.get("industria_objetivo", "general")
    pais_region = lead.get("pais_region") or company_voice.get("ciudad_objetivo", "Colombia")
    sector_profile = await generate_sector_profile(sector, pais_region, "mediana")

    senales_reentrada = sector_profile.get("senales_reentrada", [])
    instrucciones = _MOTIVO_INSTRUCTIONS.get(motivo, _MOTIVO_INSTRUCTIONS["sin_respuesta"])

    system_prompt = build_system_prompt(NURTURING_SYSTEM_TEMPLATE, {
        "EMPRESA_REMITENTE": company_voice.get("industria_objetivo", "nuestra empresa"),
        "TONO_COMUNICACION": company_voice.get("tono_comunicacion", "profesional"),
        "SECTOR": sector,
        "CICLO": str(ciclo + 1),
        "MOTIVO": motivo,
        "INSTRUCCIONES_MOTIVO": instrucciones,
        "SENALES_REENTRADA": ", ".join(senales_reentrada) if isinstance(senales_reentrada, list) else "",
    })

    user_message = (
        f"Empresa: {lead.get('company_name', 'desconocida')}. "
        f"Decisor: {decisor.get('nombre', '')} ({decisor.get('cargo', '')}). "
    )

    try:
        message_text = await call_agent(system_prompt, user_message, TEMP_NURTURING)
    except Exception as exc:
        logger.error("[nurturing_agent] LLM call failed: %s", exc)
        return {"mensaje_enviado": "", "senial_detectada": False, "nuevo_estado": "nurturing"}

    # Send message
    sent = False
    if canal_elegido == "email":
        remitentes = company_voice.get("remitentes", [{}])
        sender = remitentes[0] if remitentes else {}
        to_email = decisor.get("email", "")
        if to_email:
            subject = f"Perspectivas del sector {sector} — {lead.get('company_name', '')}"
            sent = await send_email(
                to=to_email,
                subject=subject,
                body=message_text,
                sender_name=sender.get("nombre", ""),
                sender_email=sender.get("email", ""),
            )
    elif canal_elegido == "whatsapp":
        phone = decisor.get("phone", decisor.get("telefono", ""))
        if phone:
            sent = await send_whatsapp_text(phone=phone, message=message_text)

    nuevo_ciclo = ciclo + 1

    # Log to historial
    historial_entry = {
        "tipo": "nurturing",
        "canal": canal_elegido,
        "ciclo": nuevo_ciclo,
        "motivo": motivo,
        "mensaje": message_text,
        "exito": sent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.leads.update_one(
        {"_id": ObjectId(lead_id)},
        {
            "$push": {"historial_conversacion": historial_entry},
            "$set": {"ciclo_nurturing": nuevo_ciclo},
        },
    )

    # Detect re-entry signal from the most recent inbound historial entry (if any)
    historial = lead.get("historial_conversacion", [])
    latest_inbound = next(
        (h for h in reversed(historial) if h.get("tipo") == "respuesta_lead"),
        None,
    )
    senial_detectada = False
    if latest_inbound and senales_reentrada:
        respuesta_text = str(latest_inbound.get("mensaje", "")).lower()
        senial_detectada = any(s.lower() in respuesta_text for s in senales_reentrada)

    nuevo_estado = "nurturing"
    if senial_detectada:
        try:
            await update_lead_estado(lead_id, user_id, "checkpoint")
            nuevo_estado = "checkpoint"
            logger.info("[nurturing_agent] Re-entry signal detected — lead %s -> checkpoint", lead_id)
        except Exception as exc:
            logger.error("[nurturing_agent] Failed to transition to checkpoint: %s", exc)
    elif nuevo_ciclo >= 12:
        try:
            await update_lead_estado(lead_id, user_id, "archivado")
            nuevo_estado = "archivado"
            logger.info("[nurturing_agent] 12 cycles without signal — lead %s -> archivado", lead_id)
        except Exception as exc:
            logger.error("[nurturing_agent] Failed to transition to archivado: %s", exc)

    return {
        "mensaje_enviado": message_text if sent else "",
        "senial_detectada": senial_detectada,
        "nuevo_estado": nuevo_estado,
    }
