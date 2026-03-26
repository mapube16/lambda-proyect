"""
outreach.py — Agente Outreach para envío de mensajes a leads aprobados.

Invocado desde:
  - backend/outreach_agent.py (re-export shim for main.py)
  - backend/landa/scheduler.py (via scheduled retries, Phase 13)
"""
from __future__ import annotations

import logging
import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from landa.company_voice import get_or_create_company_voice
from landa.sector_profiles import generate_sector_profile
from landa.core.context import call_agent, build_system_prompt, TEMP_OUTREACH
from landa.scheduler import schedule_retry
from landa.state_machine import update_lead_estado
from email_sender import send_email
from whatsapp_sender import send_whatsapp_text

logger = logging.getLogger("landa.agents.outreach")

OUTREACH_SYSTEM_TEMPLATE = """
Eres el agente de outreach de [EMPRESA_REMITENTE].
Voz de marca: [TONO_COMUNICACION].
Sector del prospecto: [SECTOR].
Decisor primario del sector: [DECISOR_PRIMARIO].
Ganchos relevantes: [GANCHOS].
Dolor operativo que resuelves: [DOLOR_OPERATIVO].
Solución ofrecida: [SOLUCION_OFRECIDA].

Intento número [INTENTO] de contacto.
Genera un mensaje profesional y personalizado. Sé conciso. No incluyas asunto en el cuerpo.
""".strip()


async def run_outreach(
    lead_id: str,
    user_id: str,
    canal: str,
    intento: int = 1,
) -> bool:
    """
    Generate and send an outreach message to a lead via canal (email|whatsapp).

    Returns True on successful send, False otherwise.
    Max 3 attempts. After 3 failed attempts, transitions lead to nurturing.

    Args:
        lead_id: MongoDB ObjectId string of the lead document.
        user_id: Owner user id.
        canal: Delivery channel — "email" or "whatsapp".
        intento: Attempt number (1-3). Default 1.
    """
    from database import get_db
    from bson import ObjectId

    db = get_db()
    lead = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    if not lead:
        logger.error("[outreach_agent] Lead %s not found for user %s", lead_id, user_id)
        return False

    decisor = lead.get("decisor") or {}
    canal_elegido = canal or lead.get("canal_elegido", "email")

    # Load company voice and sector profile
    company_voice = await get_or_create_company_voice(user_id)
    sector = lead.get("sector") or company_voice.get("industria_objetivo", "general")
    pais_region = lead.get("pais_region") or company_voice.get("ciudad_objetivo", "Colombia")

    sector_profile = await generate_sector_profile(sector, pais_region, "mediana")

    # Build system prompt
    ganchos = sector_profile.get("ganchos", [])
    system_prompt = build_system_prompt(OUTREACH_SYSTEM_TEMPLATE, {
        "EMPRESA_REMITENTE": company_voice.get("industria_objetivo", "nuestra empresa"),
        "TONO_COMUNICACION": company_voice.get("tono_comunicacion", "profesional"),
        "SECTOR": sector,
        "DECISOR_PRIMARIO": sector_profile.get("decisor_primario", ""),
        "GANCHOS": ", ".join(ganchos) if isinstance(ganchos, list) else str(ganchos),
        "DOLOR_OPERATIVO": company_voice.get("dolor_operativo", ""),
        "SOLUCION_OFRECIDA": company_voice.get("solucion_ofrecida", ""),
        "INTENTO": str(intento),
    })

    user_message = (
        f"Empresa: {lead.get('company_name', 'desconocida')}. "
        f"Decisor: {decisor.get('nombre', '')} ({decisor.get('cargo', '')}). "
        f"URL: {lead.get('url', '')}."
    )

    try:
        message_text = await call_agent(system_prompt, user_message, TEMP_OUTREACH)
    except Exception as exc:
        logger.error("[outreach_agent] LLM call failed: %s", exc)
        return False

    # Send message via appropriate channel
    sent = False
    if canal_elegido == "email":
        remitentes = company_voice.get("remitentes", [{}])
        sender = remitentes[0] if remitentes else {}
        to_email = decisor.get("email", "")
        if not to_email:
            logger.error("[outreach_agent] No email for lead %s decisor", lead_id)
            return False
        subject = f"Para {decisor.get('nombre', 'usted')} de {lead.get('company_name', '')}"
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
        else:
            # Fallback to email when no phone extracted (Phase 15)
            logger.warning(
                "[outreach_agent] No phone for lead %s — falling back to email", lead_id
            )
            to_email = decisor.get("email", "")
            if to_email:
                remitentes = company_voice.get("remitentes", [{}])
                sender = remitentes[0] if remitentes else {}
                subject = f"Para {decisor.get('nombre', 'usted')} de {lead.get('company_name', '')}"
                sent = await send_email(
                    to=to_email,
                    subject=subject,
                    body=message_text,
                    sender_name=sender.get("nombre", ""),
                    sender_email=sender.get("email", ""),
                )
                fallback_entry = {
                    "tipo": "fallback",
                    "razon": "no_phone",
                    "canal_usado": "email",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await db.leads.update_one(
                    {"_id": ObjectId(lead_id)},
                    {"$push": {"historial_conversacion": fallback_entry}},
                )
            else:
                logger.error(
                    "[outreach_agent] No phone AND no email for lead %s", lead_id
                )
                sent = False
    else:
        logger.error("[outreach_agent] Unknown canal: %s", canal_elegido)
        return False

    # Log to historial_conversacion and update intento_actual
    historial_entry = {
        "tipo": "outreach",
        "canal": canal_elegido,
        "intento": intento,
        "mensaje": message_text,
        "exito": sent,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    await db.leads.update_one(
        {"_id": ObjectId(lead_id)},
        {
            "$push": {"historial_conversacion": historial_entry},
            "$set": {"intento_actual": intento},
        },
    )

    if sent:
        # Schedule next retry if under 3 attempts
        if intento < 3:
            try:
                await schedule_retry(lead_id, canal_elegido, days=7)
            except Exception as exc:
                logger.warning("[outreach_agent] schedule_retry failed: %s", exc)
    else:
        logger.warning(
            "[outreach_agent] Send failed on intento %d for lead %s", intento, lead_id
        )
        if intento >= 3:
            # All 3 attempts failed — move to nurturing
            try:
                await db.leads.update_one(
                    {"_id": ObjectId(lead_id)},
                    {"$set": {"motivo_nurturing": "sin_respuesta"}},
                )
                await update_lead_estado(lead_id, user_id, "nurturing")
            except Exception as exc:
                logger.error(
                    "[outreach_agent] Failed to transition to nurturing: %s", exc
                )

    return sent
