"""
wa_handler.py — WhatsApp inbound message handler for Landa (Phase 16).

Handles:
- Twilio signature validation (WA-01)
- Phone number → profile routing (WA-01)
- wa_sessions CRUD (WA-02)
- Voice note transcription via Whisper (WA-03)
- LLM tool calling for cliente and asesor_interno (WA-03, WA-04)

Two coexisting WA senders:
  - wa_handler.py (this file) → Twilio replies to inbound messages
  - whatsapp_sender.py → Meta Graph API for proactive outreach
These MUST NOT be confused. This file ONLY uses Twilio.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Optional

from database import get_db
from landa.state_machine import update_lead_estado

logger = logging.getLogger(__name__)

# ── Signature Validation (WA-01) ─────────────────────────────────────────────

def validate_twilio_signature(url: str, signature: str, post_data: dict) -> bool:
    """Validate X-Twilio-Signature header to reject non-Twilio requests.

    Returns True if valid. Falls back to True if creds not configured
    (allows local dev and test environments without Twilio setup).
    """
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not sid or not token:
        logger.warning("[WA] Twilio creds not set — skipping signature validation")
        return True
    try:
        from twilio.request_validator import RequestValidator
        validator = RequestValidator(token)
        return validator.validate(url, post_data, signature)
    except Exception as e:
        logger.error("[WA] Signature validation error: %s", e)
        return False


# ── Profile Lookup (WA-01) ────────────────────────────────────────────────────

async def get_profile(phone: str) -> Optional[dict]:
    """Resolve a phone number to a Landa user profile.

    Lookup order:
    1. company_voice collection by wa_phone_number → profile: "cliente"
    2. env var WA_STAFF_NUMBERS (comma-separated) → profile: "asesor_interno"
    3. None → caller is unknown, will be ignored

    phone: clean phone number (no 'whatsapp:' prefix).
    """
    from database import get_db

    db = get_db()

    # 1. Check company_voice (cliente)
    cv = await db.company_voice.find_one({"wa_phone_number": phone})
    if cv:
        user_id = str(cv.get("user_id", ""))
        return {
            "profile": "cliente",
            "user_id": user_id,
            "phone": phone,
            "company_voice": cv,
        }

    # 2. Check staff numbers (asesor_interno)
    staff_numbers_raw = os.getenv("WA_STAFF_NUMBERS", "")
    staff_numbers = [n.strip() for n in staff_numbers_raw.split(",") if n.strip()]
    if phone in staff_numbers:
        # Try to find a user record for this staff member
        staff_user = await db.users.find_one({"wa_phone_number": phone})
        user_id = str(staff_user["_id"]) if staff_user else phone
        return {
            "profile": "asesor_interno",
            "user_id": user_id,
            "phone": phone,
        }

    # 3. Unknown
    logger.warning("[WA] Unknown phone number: %s", phone)
    return None


# ── Inbound Processing Skeleton (WA-02, WA-03, WA-04) ────────────────────────

async def process_inbound(
    from_phone: str,
    to_number: str,
    body: str,
    media_url: str,
    profile: dict,
) -> None:
    """Process an inbound WhatsApp message end-to-end.

    Called via asyncio.create_task() — never blocks the TwiML response.

    Steps:
    1. Get or create wa_session (WA-02)
    2. If media_url present: transcribe audio with Whisper (WA-03)
    3. Call LLM with tool calling (WA-03, WA-04)
    4. Send reply via Twilio (WA-01)
    5. Update session history (WA-02)
    """
    from database import get_or_create_wa_session, update_wa_session

    user_id = profile["user_id"]
    profile_type = profile["profile"]

    # Step 1: Session
    session = await get_or_create_wa_session(
        phone=from_phone,
        profile=profile_type,
        user_id=user_id,
    )

    # Step 2: Transcribe voice note if present (implemented in Plan 04)
    text = body
    if media_url:
        transcribed = await _transcribe_voice_note(media_url)
        text = transcribed if transcribed else body
        if not transcribed:
            await _send_reply(from_phone, "No pude entender el audio, ¿puedes escribirlo?")
            return

    # Step 3: LLM tool calling (implemented in Plans 04-05)
    reply = await _call_llm_with_tools(
        message=text,
        history=session.get("history", []),
        profile=profile_type,
        user_id=user_id,
    )

    # Step 4: Send reply
    await _send_reply(from_phone, reply)

    # Step 5: Update session history
    await update_wa_session(from_phone, {"role": "user", "content": text})
    await update_wa_session(from_phone, {"role": "assistant", "content": reply})


# ── Tool Definitions (WA-03) ──────────────────────────────────────────────────

TOOLS_CLIENTE = [
    {
        "type": "function",
        "function": {
            "name": "ver_leads_checkpoint",
            "description": "Ver los leads listos para revisión en checkpoint. Muestra empresa, puntaje y canales recomendados.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "aprobar_lead",
            "description": "Aprobar un lead para iniciar outreach. Requiere lead_id y canal.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                    "canal": {"type": "string", "enum": ["email", "whatsapp", "linkedin"], "description": "Canal de contacto"},
                },
                "required": ["lead_id", "canal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pausar_lead",
            "description": "Pausar un lead (estado nurturing). Requiere lead_id.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "rechazar_lead",
            "description": "Rechazar un lead. Requiere lead_id y motivo.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                    "motivo": {"type": "string", "description": "Motivo del rechazo"},
                },
                "required": ["lead_id", "motivo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_handover",
            "description": "Ver el paquete de handover de un lead: conversación, calificación, sugerencia de cierre.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "tomar_control",
            "description": "Tomar control de un lead en handover (asesor toma el seguimiento).",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                },
                "required": ["lead_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reportar_llamada",
            "description": "Reportar el resultado de una llamada a un lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                    "resultado": {"type": "string", "enum": ["bien", "mas_o_menos", "mal", "no_pude"], "description": "Resultado de la llamada"},
                    "detalle": {"type": "string", "description": "Descripción del resultado"},
                },
                "required": ["lead_id", "resultado"],
            },
        },
    },
]

TOOLS_ASESOR = [
    {
        "type": "function",
        "function": {
            "name": "buscar_licitaciones",
            "description": "Buscar licitaciones abiertas en SECOP por sector y ciudad.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector económico (ej: construccion, salud, educacion)"},
                    "ciudad": {"type": "string", "description": "Ciudad o departamento (ej: Bogota, Medellin)"},
                },
                "required": ["sector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_adjudicados",
            "description": "Buscar contratos adjudicados en SECOP (empresas que ya ganaron contratos).",
            "parameters": {
                "type": "object",
                "properties": {
                    "sector": {"type": "string", "description": "Sector económico"},
                    "ciudad": {"type": "string", "description": "Ciudad"},
                    "nit": {"type": "string", "description": "NIT específico de empresa (opcional)"},
                },
                "required": ["sector"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enriquecer_empresa",
            "description": "Obtener información detallada de una empresa por NIT (nombre, sector, ciudad, contacto).",
            "parameters": {
                "type": "object",
                "properties": {
                    "nit": {"type": "string", "description": "NIT de la empresa (con o sin guion)"},
                },
                "required": ["nit"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_clientes",
            "description": "Ver la lista de clientes activos de Landa.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ver_leads_cliente",
            "description": "Ver los leads de un cliente específico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "ID del cliente"},
                },
                "required": ["user_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "iniciar_outreach",
            "description": "Iniciar outreach para un lead específico.",
            "parameters": {
                "type": "object",
                "properties": {
                    "lead_id": {"type": "string", "description": "ID del lead"},
                    "canal": {"type": "string", "enum": ["email", "whatsapp", "linkedin"], "description": "Canal de contacto"},
                },
                "required": ["lead_id", "canal"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "crear_reunion",
            "description": "Crear un evento en Google Calendar con link de Google Meet. Usa lenguaje natural para describir la reunión.",
            "parameters": {
                "type": "object",
                "properties": {
                    "texto": {
                        "type": "string",
                        "description": "Descripción de la reunión en lenguaje natural. Ej: 'Reunión con Juan mañana a las 3pm sobre el contrato'",
                    },
                },
                "required": ["texto"],
            },
        },
    },
]


# ── Tool Dispatch — Cliente Profile (WA-03) ───────────────────────────────────

async def dispatch_tool_cliente(tool_name: str, args: dict, user_id: str) -> str:
    """Execute a cliente tool and return a WhatsApp-friendly result string."""
    db = get_db()

    if tool_name == "ver_leads_checkpoint":
        leads = await db.leads.find(
            {"user_id": user_id, "estado": "checkpoint"}
        ).to_list(length=5)
        if not leads:
            return "No tienes leads en checkpoint en este momento."
        lines = ["Leads listos para revisión:"]
        for i, lead in enumerate(leads, 1):
            empresa = lead.get("company_name", lead.get("empresa", "Empresa"))
            puntaje = lead.get("puntaje", 0)
            lead_id = str(lead["_id"])
            canales = lead.get("canales", [])
            canal_str = canales[0].get("canal", "email") if canales else "email"
            lines.append(f"{i}. {empresa} — puntaje {puntaje} (ID: {lead_id[:8]}...) canal sugerido: {canal_str}")
        return "\n".join(lines)

    elif tool_name == "aprobar_lead":
        lead_id = args.get("lead_id", "")
        canal = args.get("canal", "email")
        try:
            updated = await update_lead_estado(lead_id, user_id, "aprobado")
            empresa = updated.get("company_name", updated.get("empresa", lead_id))
            asyncio.create_task(_run_outreach_tool(lead_id, user_id, canal))
            return f"✅ {empresa} aprobado. Iniciando outreach por {canal}."
        except Exception as e:
            return f"No pude aprobar el lead: {e}"

    elif tool_name == "pausar_lead":
        lead_id = args.get("lead_id", "")
        try:
            updated = await update_lead_estado(lead_id, user_id, "nurturing")
            empresa = updated.get("company_name", lead_id)
            return f"⏸️ {empresa} pausado. Vuelve a revisarlo cuando sea el momento."
        except Exception as e:
            return f"No pude pausar el lead: {e}"

    elif tool_name == "rechazar_lead":
        lead_id = args.get("lead_id", "")
        motivo = args.get("motivo", "")
        try:
            updated = await update_lead_estado(lead_id, user_id, "rechazado")
            empresa = updated.get("company_name", lead_id)
            return f"❌ {empresa} rechazado. Motivo: {motivo}"
        except Exception as e:
            return f"No pude rechazar el lead: {e}"

    elif tool_name == "ver_handover":
        lead_id = args.get("lead_id", "")
        lead = await db.leads.find_one({"user_id": user_id})
        if not lead:
            return f"No encontré el lead {lead_id[:8]}."
        empresa = lead.get("company_name", lead.get("empresa", ""))
        puntaje = lead.get("puntaje", 0)
        decisor = lead.get("decisor", "el decisor")
        return f"📊 {empresa} — puntaje {puntaje}. Contacto: {decisor}. Escribe 'tomar control' para proceder."

    elif tool_name == "tomar_control":
        lead_id = args.get("lead_id", "")
        try:
            updated = await update_lead_estado(lead_id, user_id, "handover")
            empresa = updated.get("company_name", lead_id)
            return f"🤝 Tomaste el control de {empresa}. ¡Mucho éxito en la negociación!"
        except Exception as e:
            return f"No pude transferir el control: {e}"

    elif tool_name == "reportar_llamada":
        lead_id = args.get("lead_id", "")
        resultado = args.get("resultado", "")
        detalle = args.get("detalle", "")
        lead = await db.leads.find_one({"user_id": user_id})
        empresa = lead.get("company_name", lead_id) if lead else lead_id
        await db.leads.update_one(
            {"user_id": user_id},
            {"$set": {"ultimo_resultado_llamada": resultado, "detalle_llamada": detalle}},
        )
        emoji = {"bien": "✅", "mas_o_menos": "🤔", "mal": "❌", "no_pude": "📵"}.get(resultado, "📞")
        return f"{emoji} Llamada a {empresa} registrada: {resultado}. {detalle}"

    else:
        return f"No reconozco la acción '{tool_name}'."


async def _run_outreach_tool(lead_id: str, user_id: str, canal: str) -> None:
    """Fire-and-forget outreach trigger for dispatch_tool_cliente."""
    try:
        from landa.agents.outreach import run_outreach
        await run_outreach(lead_id, user_id, canal, intento=1)
    except Exception as e:
        logger.error("[WA] Outreach error for lead %s: %s", lead_id, e)


# ── Private helpers ───────────────────────────────────────────────────────────

async def _transcribe_voice_note(media_url: str) -> Optional[str]:
    """Download Twilio MediaUrl and transcribe with OpenAI Whisper.

    Twilio media URLs require Basic Auth (TWILIO_ACCOUNT_SID:TWILIO_AUTH_TOKEN).
    Returns transcription text on success, None on any failure.
    """
    import base64
    import httpx
    from openai import AsyncOpenAI

    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    api_key = os.getenv("OPENAI_API_KEY", "")

    if not api_key:
        logger.warning("[WA] OPENAI_API_KEY not set — cannot transcribe")
        return None

    try:
        auth_header = "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode() if (sid and token) else ""
        headers = {"Authorization": auth_header} if auth_header else {}
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(media_url, headers=headers)
            if resp.status_code != 200:
                logger.error("[WA] Twilio media download error %d: %s", resp.status_code, resp.text[:200])
                return None
            audio_bytes = resp.content
            content_type = resp.headers.get("content-type", "audio/ogg").split(";")[0].strip()
            logger.info("[WA] Audio downloaded: %d bytes, type=%s", len(audio_bytes), content_type)
    except Exception as e:
        logger.error("[WA] Audio download error: %s", e)
        return None

    try:
        openai_client = AsyncOpenAI(api_key=api_key)
        ext_map = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "mp4",
                   "audio/amr": "amr", "audio/wav": "wav", "audio/webm": "webm"}
        ext = ext_map.get(content_type, "ogg")
        transcript = await openai_client.audio.transcriptions.create(
            model="whisper-1",
            file=(f"voice_note.{ext}", audio_bytes, content_type),
        )
        text = transcript.text.strip()
        logger.info("[WA] Whisper transcription: %s", text[:100])
        return text if text else None
    except Exception as e:
        logger.error("[WA] Whisper transcription error: %s", e)
        return None


async def _call_llm_with_tools(
    message: str,
    history: list,
    profile: str,
    user_id: str,
) -> str:
    """Call OpenAI with tool definitions for the given profile.

    Uses function-calling loop: model decides which tool to call,
    dispatcher executes it, result fed back to model for final reply.
    """
    from openai import AsyncOpenAI

    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return "Sistema no disponible en este momento."

    client = AsyncOpenAI(api_key=api_key)
    tools = TOOLS_CLIENTE if profile == "cliente" else TOOLS_ASESOR

    system_prompt = (
        "Eres el asistente de Landa en WhatsApp. "
        "Ayudas a gestionar el proceso de prospección B2B. "
        "Responde en español colombiano conversacional. "
        "Usa emojis con moderación. Máximo 1600 caracteres por mensaje. "
        "Nunca uses markdown rico (negrillas, tablas, listas con guiones). "
        "Usa numeración simple para listas (1. 2. 3.)."
    )

    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(history[-8:])
    messages.append({"role": "user", "content": message})

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=tools if tools else None,
            tool_choice="auto" if tools else None,
            max_tokens=600,
        )

        choice = response.choices[0]

        if not choice.message.tool_calls:
            return (choice.message.content or "No tengo respuesta en este momento.")[:1600]

        tool_results = []
        for tool_call in choice.message.tool_calls:
            tool_name = tool_call.function.name
            try:
                tool_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                tool_args = {}

            if profile == "cliente":
                result = await dispatch_tool_cliente(tool_name, tool_args, user_id)
            else:
                result = await dispatch_tool_asesor(tool_name, tool_args, user_id)

            tool_results.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "content": result,
            })

        messages.append(choice.message.model_dump(exclude_none=True))
        messages.extend(tool_results)

        final_response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=400,
        )
        return (final_response.choices[0].message.content or "Listo.")[:1600]

    except Exception as e:
        logger.error("[WA] LLM call error: %s", e)
        return "Tuve un problema procesando tu mensaje. Intenta de nuevo."


async def _send_reply(to_phone: str, message: str) -> None:
    """Send a WhatsApp reply via Twilio REST API.

    Truncates to 1600 chars (WhatsApp limit).
    """
    import base64
    import httpx
    message = message[:1600]
    sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_number = os.getenv("TWILIO_WHATSAPP_FROM", "")
    if not sid or not token or not from_number:
        logger.warning("[WA] Twilio creds not set — cannot send reply to %s", to_phone)
        return
    wa_to = to_phone if to_phone.startswith("whatsapp:") else f"whatsapp:{to_phone}"
    auth = "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={"Authorization": auth},
                data={"To": wa_to, "From": from_number, "Body": message},
            )
            if resp.status_code not in (200, 201):
                logger.error("[WA] Reply error %d: %s", resp.status_code, resp.text[:200])
    except Exception as e:
        logger.error("[WA] _send_reply error: %s", e)


# ── Tool Dispatch — Asesor Interno Profile (WA-04) ────────────────────────────

async def dispatch_tool_asesor(tool_name: str, args: dict, user_id: str) -> str:
    """Execute an asesor_interno tool and return a WhatsApp-friendly result string."""
    db = get_db()

    if tool_name == "buscar_licitaciones":
        sector = args.get("sector", "")
        ciudad = args.get("ciudad", "")
        try:
            import secop_radar
            processes = await secop_radar.fetch_open_processes(sector, ciudad)
            if not processes:
                return f"No encontré licitaciones abiertas en {sector} para {ciudad or 'Colombia'}."
            lines = [f"Licitaciones abiertas — {sector} {ciudad} ({len(processes)} encontradas):"]
            for i, p in enumerate(processes[:5], 1):
                entidad = p.get("entidad", p.get("nombre", "Sin nombre"))
                objeto = p.get("objeto", "")[:80]
                valor = p.get("valor_estimado", p.get("valor", 0))
                valor_str = f"${valor:,.0f}" if valor else ""
                cierre = p.get("fecha_cierre", "")
                line = f"{i}. {entidad}"
                if objeto:
                    line += f" — {objeto}"
                if valor_str:
                    line += f" ({valor_str})"
                if cierre:
                    line += f" · cierre: {cierre}"
                lines.append(line)
            if len(processes) > 5:
                lines.append(f"...y {len(processes) - 5} más en SECOP.")
            return "\n".join(lines)
        except Exception as e:
            logger.error("[WA] buscar_licitaciones error: %s", e)
            return f"Error buscando licitaciones en SECOP: {e}"

    elif tool_name == "buscar_adjudicados":
        sector = args.get("sector", "")
        ciudad = args.get("ciudad", "")
        try:
            import secop_radar
            processes = await secop_radar.fetch_open_processes(sector, ciudad)
            if not processes:
                return f"No encontré adjudicados para {sector}."
            lines = [f"Adjudicados — {sector}:"]
            for i, p in enumerate(processes[:5], 1):
                entidad = p.get("entidad", p.get("nombre", "Sin nombre"))
                objeto = p.get("objeto", "")[:60]
                lines.append(f"{i}. {entidad} — {objeto}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error buscando adjudicados: {e}"

    elif tool_name == "enriquecer_empresa":
        nit = args.get("nit", "")
        try:
            import nit_enricher
            data = await nit_enricher.enrich_nit(nit)
            if not data:
                return f"No encontré información para el NIT {nit}."
            nombre = data.get("nombre", "N/D")
            sector = data.get("sector", "N/D")
            ciudad = data.get("ciudad", "N/D")
            contacto = data.get("contacto", data.get("email", "N/D"))
            return (
                f"📊 {nombre}\n"
                f"NIT: {nit}\n"
                f"Sector: {sector}\n"
                f"Ciudad: {ciudad}\n"
                f"Contacto: {contacto}"
            )
        except Exception as e:
            logger.error("[WA] enriquecer_empresa error: %s", e)
            return f"Error enriqueciendo NIT {nit}: {e}"

    elif tool_name == "ver_clientes":
        try:
            cvs = await db.company_voice.find({}).to_list(length=20)
            if not cvs:
                return "No hay clientes registrados."
            lines = ["Clientes activos de Landa:"]
            for i, cv in enumerate(cvs[:10], 1):
                nombre = cv.get("empresa", cv.get("user_id", "Cliente"))
                canal = cv.get("notification_channel", "web")
                lines.append(f"{i}. {nombre} (canal: {canal})")
            return "\n".join(lines)
        except Exception as e:
            return f"Error listando clientes: {e}"

    elif tool_name == "ver_leads_cliente":
        target_user_id = args.get("user_id", "")
        try:
            leads = await db.leads.find(
                {"user_id": target_user_id}
            ).to_list(length=5)
            if not leads:
                return f"No hay leads para el cliente {target_user_id}."
            lines = [f"Leads de {target_user_id}:"]
            for i, lead in enumerate(leads, 1):
                empresa = lead.get("company_name", lead.get("empresa", "Empresa"))
                estado = lead.get("estado", "desconocido")
                lines.append(f"{i}. {empresa} — {estado}")
            return "\n".join(lines)
        except Exception as e:
            return f"Error buscando leads: {e}"

    elif tool_name == "iniciar_outreach":
        lead_id = args.get("lead_id", "")
        canal = args.get("canal", "email")
        try:
            asyncio.create_task(_run_outreach_asesor(lead_id, user_id, canal))
            return f"✅ Outreach iniciado para lead {lead_id[:8]}... por {canal}."
        except Exception as e:
            return f"Error iniciando outreach: {e}"

    elif tool_name == "crear_reunion":
        texto = args.get("texto", "")
        try:
            from calendar_agent import crear_reunion_tool
            return await crear_reunion_tool(texto)
        except Exception as e:
            logger.error("[WA] crear_reunion error: %s", e)
            return f"Error creando la reunión: {e}"

    else:
        return f"No reconozco la herramienta '{tool_name}'."


async def _run_outreach_asesor(lead_id: str, user_id: str, canal: str) -> None:
    """Fire-and-forget outreach trigger for dispatch_tool_asesor."""
    try:
        from landa.agents.outreach import run_outreach
        await run_outreach(lead_id, user_id, canal, intento=1)
    except Exception as e:
        logger.error("[WA] Asesor outreach error for lead %s: %s", lead_id, e)
