"""
chat_leads.py — Queen conversational interface for lead feedback.

The Queen reads the client's recent leads as context, answers questions,
and extracts structured intent from every turn.

Intent types:
  refine_target    — adjust target company profile (sector, city, size)
  adjust_tone      — change email outreach style
  blacklist_company — exclude a company or sector from future runs
  clone_lead       — find more companies similar to a specific one
  campaign_feedback — general quality signal about the campaign
  none             — informational query, no action needed
"""

import json
import logging
import os
import re

logger = logging.getLogger("chat_leads")

SYSTEM_TEMPLATE = """\
Eres la Abeja Reina de {empresa_remitente}. Tu trabajo es conversar con el cliente sobre sus resultados de prospección B2B.

=== LEADS RECIENTES ===
{leads_context}

=== CAMPAÑA ACTIVA ===
{campaign_context}

=== TU MISIÓN ===
1. Responde preguntas del usuario sobre sus leads con datos concretos del contexto
2. Clasifica la intención del usuario en cada turno
3. Si hay intención de cambio, formula una propuesta de acción concreta

=== CÓMO INTERPRETAR EL ESTADO DE CADA LEAD ===
- "✗ RECHAZADO POR IA": el pipeline analizó la empresa y NO cumplió los criterios. El "código" es el motivo técnico y "evidencia" es lo que encontró (o no encontró) en la web. Explica POR QUÉ fue rechazada usando esos datos.
- "✗ RECHAZADO POR TI": el pipeline la aprobó (buen score) pero TÚ la rechazaste manualmente. NO sabes el motivo — pregúntale al cliente por qué la rechazó. Puede ser cliente existente, sector no deseado, o ajuste de perfil.
- "✓ APROBADO POR TI": empresa aprobada. Menciona al decisor y datos relevantes si los hay.
- "⏳ pendiente": empresa aún no revisada.

=== TIPOS DE INTENCIÓN ===
- refine_target: ajustar perfil de empresa objetivo (sector, tamaño, ciudad, facturación)
- adjust_tone: cambiar estilo/tono del correo de outreach
- blacklist_company: excluir empresa(s) o sector específico
- clone_lead: buscar más empresas similares a una aprobada
- campaign_feedback: señal de calidad general sobre la campaña
- none: pregunta informativa sin cambio sugerido

=== FRASES CLAVE → INTENCIÓN ===
"muy pequeñas / sin empleados" → refine_target (tamaño)
"fuera de la ciudad" → refine_target (ciudad)
"ya son clientes / ya los conozco" → blacklist_company
"muy corporativo / muy frío" → adjust_tone
"más como esta / empresas similares" → clone_lead
"no relevante / no son mi cliente" → refine_target o campaign_feedback
"las rechacé porque..." → campaign_feedback + posible refine_target o blacklist_company

=== FORMATO DE RESPUESTA ===
Responde normalmente en español, luego al final SIEMPRE incluye esta línea exacta:

INTENT_JSON:{{\"type\":\"none\",\"payload\":{{}},\"proposal\":null}}

Sustituye los valores según el turno. El campo "proposal" es una pregunta de confirmación al usuario, por ejemplo:
"¿Actualizo la ciudad objetivo a Medellín?"
"¿Excluyo empresas del sector financiero en futuras campañas?"
null si no hay cambio sugerido.

Ejemplo completo de línea INTENT_JSON:
INTENT_JSON:{{\"type\":\"refine_target\",\"payload\":{{\"field\":\"ciudad_objetivo\",\"value\":\"Medellín\"}},\"proposal\":\"¿Actualizo la ciudad objetivo a Medellín?\"}}

REGLAS:
- Responde siempre en español
- Sé directo y útil — cita datos específicos de los leads cuando puedas
- NUNCA digas "no se especifica el motivo" para leads rechazados POR IA — usa el código y la evidencia del contexto
- NUNCA digas "no se especifica el motivo" para leads rechazados POR TI — en ese caso PREGUNTA por qué los rechazó
- El INTENT_JSON debe estar en UNA SOLA LÍNEA al final de tu respuesta
- Siempre incluye INTENT_JSON aunque sea con type "none"\
"""

LEADS_NONE_MSG = "Aún no tienes leads analizados. Lanza una campaña desde la pestaña Campaña para empezar."


def _format_leads_context(leads: list[dict], max_leads: int = 20) -> str:
    """Convert recent leads list to a rich context string for the LLM."""
    if not leads:
        return LEADS_NONE_MSG

    lines = []
    for lead in leads[:max_leads]:
        ejson        = lead.get("expediente_json") or {}
        score        = ejson.get("score")
        empresa      = lead.get("company_name") or lead.get("url", "")
        hitl         = lead.get("hitl_status", "pending")
        system_state = lead.get("system_state", "")
        decisor      = ejson.get("decisor") or {}
        motivo_ai    = ejson.get("motivo_descalificacion") or ejson.get("motivo") or ""
        evidencia    = ejson.get("evidencia_encontrada") or ""
        tech_stack   = (ejson.get("datos_tecnicos") or {}).get("tech_stack") or ""
        dolor_ev     = ejson.get("evidencia_dolor") or ""

        # Determine the real rejection source
        ai_rejected  = system_state == "REJECTED_BY_AI"
        human_rejected = (hitl == "rejected") and not ai_rejected

        if ai_rejected:
            status_str = f"✗ RECHAZADO POR IA (score {score or 0})"
            reason = []
            if motivo_ai:
                reason.append(f"código={motivo_ai}")
            if evidencia:
                reason.append(f"evidencia='{evidencia}'")
            if reason:
                status_str += f" | {', '.join(reason)}"
        elif human_rejected:
            status_str = f"✗ RECHAZADO POR TI (el pipeline lo aprobó con score {score})"
        elif hitl == "approved":
            status_str = f"✓ APROBADO POR TI (score {score})"
        else:
            status_str = f"⏳ pendiente de revisión (score {score})" if score else "⏳ en proceso"

        extras = []
        if decisor.get("nombre"):
            extras.append(f"decisor: {decisor['nombre']} — {decisor.get('cargo', '')}"
                          + (f" <{decisor['email']}>" if decisor.get("email") else ""))
        if tech_stack:
            extras.append(f"tech: {tech_stack}")
        if dolor_ev and not ai_rejected:
            extras.append(f"dolor detectado: {dolor_ev}")

        line = f"• {empresa} — {status_str}"
        if extras:
            line += "\n  " + " | ".join(extras)
        lines.append(line)

    return "\n".join(lines)


def _format_campaign_context(campaign: dict | None) -> str:
    if not campaign:
        return "Sin campaña activa"
    fields = [
        ("empresa_remitente",   "Empresa"),
        ("industria_objetivo",  "Industria"),
        ("ciudad_objetivo",     "Ciudad"),
        ("dolor_operativo",     "Dolor"),
        ("solucion_ofrecida",   "Solución"),
        ("jerarquia_decisores", "Decisores"),
    ]
    parts = [f"{label}: {campaign.get(key,'')}" for key, label in fields if campaign.get(key)]
    return "\n".join(parts)


def _parse_intent(raw_reply: str) -> tuple[str, dict]:
    """
    Extract the INTENT_JSON line from the reply.
    Returns (clean_reply, intent_dict).
    """
    intent = {"type": "none", "payload": {}, "proposal": None}
    marker = "INTENT_JSON:"
    idx = raw_reply.rfind(marker)
    if idx == -1:
        return raw_reply.strip(), intent

    clean = raw_reply[:idx].strip()
    json_str = raw_reply[idx + len(marker):].strip()
    # Sometimes the model wraps it in ```json ... ```
    json_str = re.sub(r"```.*?```", "", json_str, flags=re.DOTALL).strip()
    try:
        intent = json.loads(json_str)
    except json.JSONDecodeError:
        logger.warning(f"[chat_leads] Could not parse intent JSON: {json_str[:200]}")

    return clean, intent


async def leads_chat_turn(
    messages: list[dict],
    user_id: str,
    openai_api_key: str,
) -> dict:
    """
    Run one turn of the leads feedback chat.
    Returns {reply: str, intent: {type, payload, proposal}}.
    """
    from openai import AsyncOpenAI
    from database import get_leads_by_user, get_active_campaign

    leads, campaign = await __import__("asyncio").gather(
        get_leads_by_user(user_id, limit=30),
        get_active_campaign(user_id),
    )

    empresa = (campaign or {}).get("empresa_remitente", "tu empresa")
    system_prompt = SYSTEM_TEMPLATE.format(
        empresa_remitente=empresa,
        leads_context=_format_leads_context(leads),
        campaign_context=_format_campaign_context(campaign),
    )

    client = AsyncOpenAI(api_key=openai_api_key)
    response = await client.chat.completions.create(
        model="gpt-5.4-2026-03-05",
        messages=[{"role": "system", "content": system_prompt}] + messages,
        temperature=0.4,
        extra_body={"max_completion_tokens": 900},
    )
    raw = response.choices[0].message.content or ""
    clean_reply, intent = _parse_intent(raw)
    return {"reply": clean_reply, "intent": intent}
