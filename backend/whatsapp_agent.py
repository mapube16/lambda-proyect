"""
whatsapp_agent.py — Agente de WhatsApp para prospección de pólizas de cumplimiento.

Flujo conversacional:
  1. Asesor: "construccion bogota"  →  Bot corre radar y presenta prospectos
  2. Asesor: "1"                    →  Bot pregunta canal (E=Email / W=WhatsApp)
  3. Asesor: "E"                    →  Bot envía email y confirma

POC: sesiones en memoria.
A futuro: configuración por cliente desde MongoDB
  {phone_number, sector, ciudad, nombre_asesor, from_whatsapp}
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from typing import Optional

import httpx
from debug_logger import get_payload_logger

logger = logging.getLogger(__name__)
debug_log = get_payload_logger()

# ── Configuración Twilio ──────────────────────────────────────────────────────

def _twilio_creds() -> tuple[str, str]:
    return (
        os.getenv("TWILIO_ACCOUNT_SID", ""),
        os.getenv("TWILIO_AUTH_TOKEN", ""),
    )

def _twilio_auth(sid: str, token: str) -> str:
    return "Basic " + base64.b64encode(f"{sid}:{token}".encode()).decode()

async def _send_whatsapp(to: str, from_: str, body: str) -> bool:
    """Send simple text message via Twilio WhatsApp."""
    sid, token = _twilio_creds()
    if not sid or not token:
        return False
    wa_to   = to   if to.startswith("whatsapp:")   else f"whatsapp:{to}"
    wa_from = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={"Authorization": _twilio_auth(sid, token)},
                data={"To": wa_to, "From": wa_from, "Body": body},
            )
            ok = resp.status_code in (200, 201)
            return ok
    except Exception as e:
        return False


async def _send_whatsapp_template(
    to: str,
    from_: str,
    content_sid: str,
    variables: Optional[list[str]] = None,
) -> bool:
    """Send WhatsApp message using a pre-approved Twilio Content Template.
    
    Args:
        to: recipient phone
        from_: sender phone (Twilio number)
        content_sid: Template content SID (format: HXxxxxxxxxxxxxxxxxxxxxxxx)
        variables: Optional list of template variables (e.g., ["{{1}}", "{{2}}"])
    
    Returns:
        bool: True if sent successfully, False otherwise
    """
    if not content_sid or content_sid.strip() == "":
        return False
    
    sid, token = _twilio_creds()
    if not sid or not token:
        return False
    
    wa_to   = to   if to.startswith("whatsapp:")   else f"whatsapp:{to}"
    wa_from = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
    
    payload = {
        "To": wa_to,
        "From": wa_from,
        "ContentSid": content_sid.strip(),
    }
    
    # If template has variables, pass them
    if variables:
        import json
        payload["ContentVariables"] = json.dumps(variables)
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json",
                headers={"Authorization": _twilio_auth(sid, token)},
                data=payload,
            )
            ok = resp.status_code in (200, 201)
            if ok:
                logger.info(f"[TWILIO-TEMPLATE] Sent to {to} with ContentSid {content_sid}")
            else:
                logger.warning(f"[TWILIO-TEMPLATE] Failed: {resp.status_code} {resp.text}")
            return ok
    except Exception as e:
        logger.error(f"[TWILIO-TEMPLATE] Exception: {e}")
        return False


async def _send_whatsapp_buttons(
    to: str,
    from_: str,
    body: str,
    buttons: list[dict],
    template_type: str = "prospect_select",
) -> bool:
    """Send interactive button message via Twilio WhatsApp Templates.
    
    Args:
        to: recipient phone
        from_: sender phone (Twilio number)
        body: header text (fallback if template not available)
        buttons: list of {"id": "1", "title": "Option 1"} dicts (max 3)
        template_type: "prospect_select", "channel_select", or "confirmation"
    
    Note: Uses Twilio's WhatsApp Content API (templates).
    If template ContentSid not configured, falls back to text with numbered options.
    """
    sid, token = _twilio_creds()
    if not sid or not token:
        return False
    
    wa_to   = to   if to.startswith("whatsapp:")   else f"whatsapp:{to}"
    wa_from = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
    
    # Try to use template if available
    template_map = {
        "prospect_select": os.getenv("TWILIO_TEMPLATE_PROSPECT_SELECT", ""),
        "channel_select": os.getenv("TWILIO_TEMPLATE_CHANNEL_SELECT", ""),
        "confirmation": os.getenv("TWILIO_TEMPLATE_CONFIRMATION", ""),
    }
    
    content_sid = template_map.get(template_type, "")
    if content_sid and content_sid.strip():
        # Template is available — use it
        ok = await _send_whatsapp_template(to, from_, content_sid)
        if ok:
            return True
        # If template send fails, fall through to text fallback
    
    # ── Fallback: send text with numbered options ──────────────────────────────
    text_msg = body + "\n\n" + "\n".join([f"{i+1}. {b['title']}" for i, b in enumerate(buttons)])
    return await _send_whatsapp(to, from_, text_msg)

# ── Sesiones en memoria ───────────────────────────────────────────────────────
# Estructura por número de teléfono del asesor:
# {
#   "state": "idle" | "awaiting_selection" | "awaiting_send_confirmation",
#   "prospects": [...],        # lista de prospectos mostrados
#   "selected": {...},         # prospecto seleccionado
#   "send_method": "email" | "whatsapp",  # método de envío
#   "from_number": str,        # número Twilio del cliente
# }
_SESSIONS: dict[str, dict] = {}

# ── Filtro: descartar entidades públicas ──────────────────────────────────────

_PUBLIC_KEYWORDS = (
    # Gobierno local/regional
    "municipio", "municipalidad", "alcaldia", "alcaldía", "gobernacion", "gobernación",
    "gobernadora", "alcalde", "concejo", "asamblea departamental", "diputado",
    
    # Entidades nacionales
    "ministerio", "departamento ", "secretaría", "secretaria", "instituto",
    "dirección general", "direccion general", "agencia nacional",
    
    # Organismos públicos y mixtos
    "empresa social del estado", "ese", "eice", "empresa de servicios",
    "fondo de ", "corporacion", "corporación", "autoridad ",
    "junta de accion", "junta de acción", "juntas de agua",
    
    # Educación superior
    "universida", "escola", "colegio", "liceo",  # universidaD, escolA, etc con typos
    
    # Salud (CRÍTICO - muchas son públicas)
    "hospital", "clinica", "clínica", "centro de salud", "centro médico",
    "red de salud", "empresa social", "ese ",
    
    # Agua/saneamiento
    "empresa de acueducto", "acueducto", "agua potable",
    "empresa de servicios publicos",
    
    # Cajas de compensación familiar y similares
    "comfenalco", "comfamiliar", "cafam", "caja de compensacion", "caja de compensación",
    "caja de ahorro", "fondo de empleados", "fondos de empleados",
    
    # Organismos de control y regulación
    "superintendencia", "defensoría", "defensor", "procuraduría", "fiscal", 
    "tribunal", "juzgado", "corte ", "registro civil",
    
    # Otros
    "parque nacional", "museo", "biblioteca pública", "archivo municipal",
    "policia", "policía", "bomberos", "armada", "fuerzas armadas",
    "cruz roja", "ong ", "oenegé", "asociacion ", "asociación ",
    "sindicato", "cooperativa de trabajadores",
)

def _is_public_entity(razon_social: str) -> bool:
    """Detecta si es entidad pública."""
    name = (razon_social or "").lower().strip()
    
    # Direct keyword match
    for kw in _PUBLIC_KEYWORDS:
        if kw in name:
            print(f"[PUBLIC-MATCH] '{razon_social}' matched keyword '{kw}'")
            return True
    
    # Nombres que comienzan con público
    public_prefixes = ("municipio de ", "gobernacion de ", "gobernación de ", "instituto de ",
                       "departamento de ", "secretaria de ", "secretaría de ", "empresa de ",
                       "ministerio de ", "universidad de ", "colegio ", "hospital ",
                       "armada ", "policia ", "policía ", "fuerzas armadas", "caja de ")
    for p in public_prefixes:
        if name.startswith(p):
            print(f"[PUBLIC-PREFIX] '{razon_social}' matched prefix '{p}'")
            return True
    
    return False


# ── Generar razón de contacto con LLM ────────────────────────────────────────

async def _generate_pitch_reason(prospect: dict, sector: str) -> str:
    """Genera en 2 líneas por qué es buena idea contactar esta empresa hoy."""
    api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        return f"Empresa activa con {prospect.get('contratos_secop', 0)} contratos públicos. Requiere póliza de cumplimiento."

    nombre   = prospect.get("razon_social", "")
    contratos = prospect.get("contratos_secop", 0)
    valor    = prospect.get("valor_total_fmt", "N/D")
    ultimo   = prospect.get("ultimo_contrato", "")[:120]
    entidades = ", ".join(prospect.get("entidades_contratantes", [])[:3])

    prompt = f"""
Eres un asesor de seguros colombiano. En 2 líneas explica POR QUÉ es urgente contactar HOY a esta empresa para ofrecerle una póliza de cumplimiento. Sé específico: menciona el valor contratado, el sector, o el tipo de entidad con la que trabaja.

No inventes datos. Si no tienes información, responde exactamente: 'No disponible'. Usa solo los datos proporcionados abajo.

Empresa: {nombre}
Sector: {sector}
Contratos públicos ganados: {contratos} por un total de {valor}
Último contrato: {ultimo}
Entidades con las que trabaja: {entidades}

Responde solo las 2 líneas. Sin saludos. Sin "Razón:" ni prefijos.
"""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "gpt-5.4-2026-03-05",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_completion_tokens": 80,
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"Con {contratos} contratos públicos ganados ({valor}), necesitan póliza de cumplimiento vigente."


# ── Formatear lista de prospectos para WhatsApp ───────────────────────────────

def _format_prospect_list(prospects: list[dict], sector: str, ciudad: str, reasons: list[str]) -> str:
    """Text version (fallback if buttons don't work)."""
    ciudad_txt = ciudad or "Colombia"
    lines = [f"🎯 *{sector.title()} · {ciudad_txt.title()}*\n"]

    for i, p in enumerate(prospects, 1):
        nombre    = (p.get("razon_social") or "Empresa")[:35]
        phone     = p.get("rep_legal_telefono") or p.get("phone") or "N/D"
        email     = p.get("rep_legal_email") or p.get("email") or "N/D"
        reason    = (reasons[i - 1] if i <= len(reasons) else "")[:200]

        lines.append(f"*{i}.* {nombre}")
        lines.append(f"📞 {phone}  📧 {email}")
        if reason:
            lines.append(f"_{reason}_")
        lines.append("")

    lines.append("Responde el *número* para contactar.")
    return "\n".join(lines)


def _format_prospect_buttons(prospects: list[dict], sector: str, ciudad: str) -> tuple[str, list[dict]]:
    """
    Generate header text + button payload for prospect selection.
    Returns (header_text, button_list).
    """
    ciudad_txt = ciudad or "Colombia"
    header = f"🎯 {sector.title()} · {ciudad_txt.title()}\n\nSelecciona un prospecto:"
    buttons = [
        {
            "id": str(i),
            "title": (p.get("razon_social") or "Empresa")[:18],  # WhatsApp button limit ~18 chars
        }
        for i, p in enumerate(prospects, 1)
    ]
    return header, buttons


# ── Enviar email de prospección ───────────────────────────────────────────────

async def _send_prospect_email(
    prospect: dict,
    sector: str,
    sender_name: str = "",
    sender_company: str = "",
    sender_phone: str = "",
) -> bool:
    """Envía email al prospecto usando MailerSend."""
    email = prospect.get("rep_legal_email") or prospect.get("email")
    if not email or email in ("no provisto", "N/D"):
        return False

    nombre_empresa = prospect.get("razon_social", "")
    rep = prospect.get("representante_legal") or "Equipo de contratación"
    valor = prospect.get("valor_total_fmt", "")
    contratos = prospect.get("contratos_secop", 0)

    asunto = f"Póliza de cumplimiento para sus contratos públicos — {nombre_empresa}"
    cuerpo = f"""Estimado(a) {rep},

Mi nombre es {sender_name} de {sender_company}.

Me dirijo a usted porque {nombre_empresa} tiene un historial destacado en contratación pública — {contratos} contratos por un total de {valor}. Empresas con este perfil frecuentemente requieren pólizas de cumplimiento vigentes para participar y ejecutar contratos del Estado.

Me gustaría presentarles nuestras opciones de pólizas de cumplimiento, que incluyen:
• Expedición en menos de 24 horas
• Tarifas competitivas por el volumen de contratación
• Acompañamiento durante toda la ejecución del contrato

¿Tendría 15 minutos esta semana para una llamada rápida?

Quedo atento,
{sender_name}
{sender_company}
{sender_phone}"""

    api_key = os.getenv("MAILERSEND_API_KEY", "")
    from_email = os.getenv("MAILERSEND_FROM_EMAIL", "")
    if not api_key or not from_email:
        return False

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                "https://api.mailersend.com/v1/email",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": {"email": from_email, "name": os.getenv("SENDER_NAME", "Asesor")},
                    "to": [{"email": email, "name": rep}],
                    "subject": asunto,
                    "text": cuerpo,
                },
            )
            ok = resp.status_code in (200, 201, 202)
            return ok
    except Exception as e:
        return False


# ── Orquestador principal del agente ─────────────────────────────────────────

async def handle_inbound_message(
    from_phone: str,          # número del asesor (e.g. "+573123528153")
    body: str,                # texto del mensaje
    from_twilio: str,         # número Twilio (e.g. "whatsapp:+14155238886")
    agent_config: dict = {},  # config desde MongoDB (si existe)
) -> None:
    """
    Procesa un mensaje entrante del asesor y responde por WhatsApp.
    Si agent_config está vacío usa env vars como fallback (modo POC).
    """
    # Log incoming message
    debug_log.log_incoming_message(from_phone, body)
    
    # Resolución de config: MongoDB > env vars
    sender_name    = agent_config.get("nombre_asesor")    or os.getenv("SENDER_NAME", "Asesor")
    sender_company = agent_config.get("empresa")          or os.getenv("SENDER_COMPANY", "Seguros")
    sender_phone   = agent_config.get("telefono_asesor")  or os.getenv("SENDER_PHONE", "")
    ciudad_default = agent_config.get("ciudad_default")   or None
    text = body.strip()
    session = _SESSIONS.get(from_phone, {"state": "idle", "from_number": from_twilio})

    async def reply(msg: str):
        await _send_whatsapp(from_phone, from_twilio, msg)

    state = session.get("state", "idle")

    # ── Estado: esperando confirmación de envío ──────────────────────────────────
    if state == "awaiting_send_confirmation":
        selected = session.get("selected", {})
        nombre = selected.get("razon_social", "la empresa")
        
        if text.strip().lower() in ("si", "ok", "y", "yes", "adelante", "yes"):
            send_method = session.get("send_method", "email")  # "email" or "whatsapp"
            
            if send_method == "email":
                email = selected.get("rep_legal_email") or selected.get("email")
                ok = await _send_prospect_email(
                    selected, session.get("sector", ""),
                    sender_name=sender_name,
                    sender_company=sender_company,
                    sender_phone=sender_phone,
                )
                if ok:
                    await reply(f"✅ Email enviado a *{nombre}*.\nQueda registrado en el seguimiento.")
                    debug_log.log_send_attempt(from_phone, nombre, "email", email, True)
                else:
                    await reply(f"⚠️ No se pudo enviar el email a {email}.\nIntenta manualmente.")
                    debug_log.log_send_attempt(from_phone, nombre, "email", email, False, "Network or API error")
            
            elif send_method == "whatsapp":
                phone = selected.get("rep_legal_telefono") or selected.get("phone") or ""
                if phone and phone not in ("No Provisto", "N/D"):
                    msg = (
                        f"Hola {selected.get('representante_legal') or 'equipo de contratación'}, "
                        f"soy {sender_name} de {sender_company}. "
                        f"Les contacto porque {nombre} tiene un historial destacado en contratación pública. "
                        f"¿Tienen póliza de cumplimiento vigente? Me gustaría contarles sobre nuestras opciones."
                    )
                    ok = await _send_whatsapp(phone, from_twilio, msg)
                    if ok:
                        await reply(f"✅ WhatsApp enviado a *{nombre}* ({phone}).")
                        debug_log.log_send_attempt(from_phone, nombre, "whatsapp", phone, True)
                    else:
                        await reply(f"⚠️ No se pudo enviar WhatsApp. Número: {phone}")
                        debug_log.log_send_attempt(from_phone, nombre, "whatsapp", phone, False, "Network error")
                else:
                    await reply(f"⚠️ {nombre} no tiene teléfono registrado.")
                    debug_log.log_send_attempt(from_phone, nombre, "whatsapp", phone or "unknown", False, "No phone available")
            
            session["state"] = "idle"
            _SESSIONS[from_phone] = session
            debug_log.log_session_state(from_phone, "awaiting_send_confirmation", "idle", {"action": "send_confirmed"})
            return
        
        elif text.strip().lower() in ("no", "n", "cancelar", "cancel"):
            await reply("Cancelado. ¿Qué más necesitas?")
            session["state"] = "idle"
            _SESSIONS[from_phone] = session
            debug_log.log_session_state(from_phone, "awaiting_send_confirmation", "idle", {"action": "send_cancelled"})
            return
        
        else:
            await reply("Por favor responde *Si* o *No*")
            return

    # ── Estado: esperando selección de prospecto ──────────────────────────────
    if state == "awaiting_selection":
        try:
            idx = int(text.strip()) - 1
            prospects = session.get("prospects", [])
            if 0 <= idx < len(prospects):
                session["selected"] = prospects[idx]
                _SESSIONS[from_phone] = session

                p = prospects[idx]
                nombre = p.get("razon_social", "")
                email = p.get("rep_legal_email") or p.get("email") or ""
                phone = p.get("rep_legal_telefono") or p.get("phone") or ""
                rep = p.get("representante_legal") or "Equipo de contratación"

                debug_log.log_event("prospect_selected", {
                    "phone": from_phone,
                    "prospect_name": nombre,
                    "prospect_index": idx + 1,
                    "has_email": bool(email and email not in ("No Provisto", "N/D", "no disponible")),
                    "has_phone": bool(phone and phone not in ("No Provisto", "N/D", "no disponible")),
                }, level="DEBUG")

                detail_msg = (
                    f"👤 *{nombre}*\n"
                    f"📧 {email if email else '(no disponible)'}\n"
                    f"📞 {phone if phone else '(no disponible)'}\n"
                )
                
                # Si tiene email, ofrece enviar directamente
                if email and email not in ("No Provisto", "N/D", "no disponible"):
                    session["state"] = "awaiting_send_confirmation"
                    session["send_method"] = "email"
                    debug_log.log_session_state(from_phone, "awaiting_selection", "awaiting_send_confirmation", {
                        "prospect": nombre,
                        "send_method": "email",
                    })
                    msg = detail_msg + f"\n❓ ¿Envío una propuesta de póliza a {email}?"
                    await reply(msg + "\n\nResponde: *Si* o *No*")
                elif phone and phone not in ("No Provisto", "N/D", "no disponible"):
                    # Si tiene teléfono pero no email, ofrece enviar por WhatsApp
                    session["state"] = "awaiting_send_confirmation"
                    session["send_method"] = "whatsapp"
                    debug_log.log_session_state(from_phone, "awaiting_selection", "awaiting_send_confirmation", {
                        "prospect": nombre,
                        "send_method": "whatsapp",
                    })
                    msg = detail_msg + f"\n❓ ¿Envío WhatsApp a {phone}?"
                    await reply(msg + "\n\nResponde: *Si* o *No*")
                else:
                    # Sin contacto
                    session["state"] = "idle"
                    debug_log.log_event("prospect_no_contact", {
                        "phone": from_phone,
                        "prospect_name": nombre,
                    })
                    await reply(
                        f"❌ {nombre} no tiene información de contacto disponible.\n"
                        f"No puedo enviar propuesta automáticamente.\n"
                        f"Prueba con otro prospecto."
                    )
                return
            else:
                await reply(f"Número inválido. Responde entre 1 y {len(prospects)}.")
                debug_log.log_event("invalid_prospect_selection", {
                    "phone": from_phone,
                    "input": text,
                    "valid_range": f"1-{len(prospects)}",
                }, level="DEBUG")
                return
        except ValueError:
            pass  # No es un número, continuar al flujo normal

    # ── Estado: idle — parsear comando ───────────────────────────────────────
    # Comandos soportados:
    #   "construccion bogota"   → sector + ciudad
    #   "construccion"          → solo sector
    #   "ayuda" / "help"        → instrucciones

    lower = text.lower()

    if lower in ("ayuda", "help", "hola", "hi", "?"):
        await reply(
            "👋 *Agente de Pólizas SECOP*\n\n"
            "Envíame el sector que quieres prospectar:\n"
            "• `construccion bogota`\n"
            "• `tecnologia medellin`\n"
            "• `transporte`\n"
            "• `de todo tipo` (busca múltiples sectores)\n\n"
            "Yo busco en SECOP las empresas que más contratan con el Estado "
            "y te digo a quiénes contactar hoy. 🎯"
        )
        return

    # ── Detectar búsqueda multi-sector ──────────────────────────────────────
    multi_sector_keywords = ("de todo tipo", "todos los sectores", "todas las industrias", "de todos", "global", "mixto")
    is_multi_sector = any(kw in lower for kw in multi_sector_keywords)
    
    if is_multi_sector:
        # Buscar en múltiples sectores comunes automáticamente
        sectores = ["construccion", "servicios", "tecnologia", "transporte", "manufactura"]
        await reply(f"🔍 Buscando en múltiples sectores: {', '.join(sectores)}...\n_Esto tarda ~30 segundos_")
        debug_log.log_event("multi_sector_search_started", {
            "phone": from_phone,
            "sectors": sectores,
        }, level="DEBUG")

        from secop_radar import build_poliza_leads

        all_prospects = []

        for sect in sectores:
            try:
                result = await build_poliza_leads(keyword=sect, ciudad=None, max_procesos=5, max_proponentes=15)
                raw_count = len(result.get("proponentes_probables", []))

                sector_prospects = []
                filtered_out = []
                for p in result.get("proponentes_probables", []):
                    razon = p.get("razon_social", "")
                    is_public = _is_public_entity(razon)
                    has_contact = p.get("rep_legal_telefono") or p.get("phone") or p.get("rep_legal_email") or p.get("email")

                    print(f"[FILTER-{sect}] {razon[:40]:40} | public={is_public} | contact={bool(has_contact)}")

                    if not is_public and has_contact:
                        sector_prospects.append(p)
                        print(f"  ✓ INCLUDED")
                    else:
                        reason = "public" if is_public else "no_contact"
                        filtered_out.append({"name": razon, "reason": reason})

                debug_log.log_search_query(from_phone, sect, "colombia", raw_count)
                if filtered_out:
                    debug_log.log_entity_filtering(from_phone, raw_count, len(filtered_out), "public_entity_or_no_contact")

                all_prospects.extend(sector_prospects)
            except Exception as e:
                debug_log.log_error(from_phone, "sector_search_error", str(e), {"sector": sect})
                pass  # Si un sector falla, continúa con los demás

        # Deduplicar por NIT/nombre
        seen = set()
        prospects = []
        for p in all_prospects:
            key = (p.get("nit"), p.get("razon_social", ""))
            if key not in seen:
                seen.add(key)
                prospects.append(p)

        prospects = prospects[:3]  # Top 3

        if not prospects:
            await reply(
                f"😕 No encontré prospectos con información de contacto en múltiples sectores.\n"
                f"Prueba con otro sector o sin filtro de ciudad."
            )
            debug_log.log_event("search_no_results", {
                "phone": from_phone,
                "sector": "multi-sector",
                "ciudad": "colombia",
                "raw_results": len(all_prospects),
                "filtered_after": 0,
            })
            return

        # Enriquecer con datos de contacto reales (email, teléfono)
        from contact_enricher import enrich_companies_with_contacts
        try:
            debug_log.log_event("enrichment_batch_started", {
                "phone": from_phone,
                "count": len(prospects),
                "sources": [p.get("razon_social", "") for p in prospects],
            }, level="DEBUG")
            prospects = await enrich_companies_with_contacts(prospects, max_concurrent=2)
            debug_log.log_event("enrichment_batch_completed", {
                "phone": from_phone,
                "count": len(prospects),
            }, level="DEBUG")
        except Exception as e:
            print(f"[CONTACT-ENRICHER] Error: {e}")
            debug_log.log_error(from_phone, "enrichment_error", str(e), {})
            # Continúa sin enriquecimiento si falla

        # Generar razones en paralelo
        reasons = await asyncio.gather(*[
            _generate_pitch_reason(p, "múltiples sectores")
            for p in prospects
        ])

        debug_log.log_event("prospect_reasons_generated", {
            "phone": from_phone,
            "count": len(reasons),
        }, level="DEBUG")

        # Guardar sesión
        session.update({
            "state":       "awaiting_selection",
            "prospects":   prospects,
            "sector":      "múltiples sectores",
            "ciudad":      "colombia",
            "from_number": from_twilio,
        })
        _SESSIONS[from_phone] = session

        debug_log.log_session_state(from_phone, "idle", "awaiting_selection", {
            "prospects_count": len(prospects),
            "sector": "múltiples sectores",
        })

        # Enviar con botones o texto
        header, buttons = _format_prospect_buttons(prospects, "múltiples sectores", "colombia")
        ok = await _send_whatsapp_buttons(from_phone, from_twilio, header, buttons, template_type="prospect_select")
        if not ok:
            debug_log.log_event("buttons_send_fallback", {
                "phone": from_phone,
                "reason": "buttons_not_supported",
            }, level="DEBUG")
            msg = _format_prospect_list(prospects, "múltiples sectores", "colombia", list(reasons))
            await reply(msg)
        else:
            debug_log.log_event("buttons_sent_success", {
                "phone": from_phone,
                "button_count": len(buttons),
            }, level="DEBUG")
        return
    else:
        # Parsear sector simple y opcionalmente ciudad
        parts = lower.split(None, 1)
        sector = parts[0]
        ciudad = parts[1] if len(parts) > 1 else None
        
        await reply(f"🔍 Buscando prospectos en *{sector.title()}*{' · ' + ciudad.title() if ciudad else ''}...\n_Esto tarda ~20 segundos_")
        
        sector_display = f"{sector.title()}{' · ' + ciudad.title() if ciudad else ''}"

        from secop_radar import build_poliza_leads
        
        debug_log.log_event("sector_search_started", {
            "phone": from_phone,
            "sector": sector,
            "ciudad": ciudad or "national",
        }, level="DEBUG")
        
        result = await build_poliza_leads(
            keyword=sector,
            ciudad=ciudad,
            max_procesos=10,
            max_proponentes=20,
        )

        # Filtrar entidades públicas y sin contacto
        raw_count = len(result.get("proponentes_probables", []))
        
        prospects = []
        filtered_out = []
        for p in result.get("proponentes_probables", []):
            razon = p.get("razon_social", "")
            is_public = _is_public_entity(razon)
            has_contact = p.get("rep_legal_telefono") or p.get("phone") or p.get("rep_legal_email") or p.get("email")
            
            print(f"[FILTER] {razon[:40]:40} | public={is_public} | contact={bool(has_contact)}")
            
            if not is_public and has_contact:
                prospects.append(p)
                print(f"  ✓ INCLUDED")
            else:
                reason = "public" if is_public else "no_contact"
                filtered_out.append({"name": razon, "reason": reason})
        
        debug_log.log_search_query(from_phone, sector, ciudad or "national", raw_count)
        if filtered_out:
            debug_log.log_entity_filtering(from_phone, raw_count, len(filtered_out), "public_entity_or_no_contact")
        
        # Reintentar búsqueda si no hay prospectos válidos (máx 2 intentos extra)
        max_retries = 2
        retries = 0
        while not prospects and retries < max_retries:
            result = await build_poliza_leads(
                keyword=sector,
                ciudad=None if ciudad else "bogota",  # Cambia ciudad si ya era None
                max_procesos=10,
                max_proponentes=20,
            )
            raw_count = len(result.get("proponentes_probables", []))
            prospects = []
            for p in result.get("proponentes_probables", []):
                razon = p.get("razon_social", "")
                is_public = _is_public_entity(razon)
                has_contact = p.get("rep_legal_telefono") or p.get("phone") or p.get("rep_legal_email") or p.get("email")
                if not is_public and has_contact:
                    prospects.append(p)
            retries += 1

        prospects = prospects[:3]  # Máximo 3 para no superar límite de 1600 chars de Twilio

        if not prospects:
            await reply(
                f"😕 No encontré prospectos con información de contacto para {sector_display}.\n"
                f"Prueba con otro sector o sin filtro de ciudad."
            )
            debug_log.log_event("search_no_results", {
                "phone": from_phone,
                "sector": sector,
                "ciudad": ciudad or "national",
                "raw_results": raw_count,
                "filtered_after": len(prospects),
            })
            return

        # Enriquecer con datos de contacto reales (email, teléfono)
        from contact_enricher import enrich_companies_with_contacts
        try:
            debug_log.log_event("enrichment_batch_started", {
                "phone": from_phone,
                "count": len(prospects),
                "sources": [p.get("razon_social", "") for p in prospects],
            }, level="DEBUG")
            prospects = await enrich_companies_with_contacts(prospects, max_concurrent=2)
            debug_log.log_event("enrichment_batch_completed", {
                "phone": from_phone,
                "count": len(prospects),
            }, level="DEBUG")
        except Exception as e:
            print(f"[CONTACT-ENRICHER] Error: {e}")
            debug_log.log_error(from_phone, "enrichment_error", str(e), {})
            # Continúa sin enriquecimiento si falla

        # Generar razones en paralelo
        reasons = await asyncio.gather(*[
            _generate_pitch_reason(p, sector_display if not is_multi_sector else "Multi-sector")
            for p in prospects
        ])

        debug_log.log_event("prospect_reasons_generated", {
            "phone": from_phone,
            "count": len(reasons),
        }, level="DEBUG")

        # Guardar sesión
        session.update({
            "state":       "awaiting_selection",
            "prospects":   prospects,
            "sector":      sector_display,
            "ciudad":      ciudad or "",
            "from_number": from_twilio,
        })
        _SESSIONS[from_phone] = session
        
        debug_log.log_session_state(from_phone, "idle", "awaiting_selection", {
            "prospects_count": len(prospects),
            "sector": sector_display,
        })

        # Send with buttons instead of text
        header, buttons = _format_prospect_buttons(prospects, sector_display, ciudad or "Colombia")
        
        ok = await _send_whatsapp_buttons(from_phone, from_twilio, header, buttons, template_type="prospect_select")
        if not ok:
            # Fallback to text if buttons fail
            debug_log.log_event("buttons_send_fallback", {
                "phone": from_phone,
                "reason": "buttons_not_supported",
            }, level="DEBUG")
            msg = _format_prospect_list(prospects, sector_display, ciudad or "Colombia", list(reasons))
            await reply(msg)
        else:
            debug_log.log_event("buttons_sent_success", {
                "phone": from_phone,
                "button_count": len(buttons),
            }, level="DEBUG")
