"""
calendar_agent.py — Google Calendar agent for WhatsApp (Phase 17).

Receives text or audio → extracts event details with GPT-4o-mini →
creates Google Calendar event with Google Meet link → replies via Twilio.

Supports both:
  - bot_mode="calendar": standalone calendar bot, all messages routed here
  - crear_reunion tool in wa_handler.py: called from landa bot via tool calling
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

# ── Google Calendar client ────────────────────────────────────────────────────

def _get_calendar_service():
    """Build Google Calendar API service using OAuth2 refresh token."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN", "")
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")

    if not refresh_token:
        raise ValueError("GOOGLE_REFRESH_TOKEN no configurado. Corre: python backend/google_auth.py")

    creds = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=["https://www.googleapis.com/auth/calendar"],
    )
    creds.refresh(Request())
    return build("calendar", "v3", credentials=creds)


# ── Event extraction via LLM ──────────────────────────────────────────────────

async def extract_event_details(text: str) -> Optional[dict]:
    """Use GPT-4o-mini to extract event details from natural language text.

    Returns dict with: titulo, fecha, hora_inicio, duracion_minutos,
                       participantes (list of emails), descripcion
    Returns None if the text doesn't describe a meeting.
    """
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    today = datetime.now().strftime("%Y-%m-%d")
    weekday = datetime.now().strftime("%A")

    prompt = f"""Hoy es {today} ({weekday}). Extrae los detalles de reunión del siguiente texto.
Si el texto NO describe una reunión o evento de calendario, responde exactamente: null

Si SÍ describe una reunión, responde SOLO con JSON (sin markdown):
{{
  "titulo": "título del evento",
  "fecha": "YYYY-MM-DD",
  "hora_inicio": "HH:MM",
  "duracion_minutos": 60,
  "participantes": ["email@dominio.com"],
  "descripcion": "descripción opcional"
}}

Reglas:
- Si dice "mañana", usa fecha de mañana
- Si dice "próximo lunes", calcula la fecha correcta
- Si no especifica duración, usa 60 minutos
- Si no hay emails de participantes, usa lista vacía []
- Usa formato 24 horas para la hora

Texto: {text}"""

    try:
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0,
        )
        content = response.choices[0].message.content.strip()
        if content.lower() == "null" or not content:
            return None
        return json.loads(content)
    except (json.JSONDecodeError, Exception) as e:
        logger.error("[Calendar] extract_event_details error: %s", e)
        return None


# ── Calendar event creation ───────────────────────────────────────────────────

async def create_calendar_event(details: dict) -> dict:
    """Create a Google Calendar event with Google Meet link.

    Returns dict with: event_id, meet_link, html_link, summary, start
    """
    import asyncio

    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")

    # Build datetime strings
    fecha = details.get("fecha", datetime.now().strftime("%Y-%m-%d"))
    hora = details.get("hora_inicio", "09:00")
    duracion = int(details.get("duracion_minutos", 60))

    start_dt = datetime.strptime(f"{fecha} {hora}", "%Y-%m-%d %H:%M")
    end_dt = start_dt + timedelta(minutes=duracion)

    # Timezone: Colombia (UTC-5, no DST)
    tz = "America/Bogota"
    start_str = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
    end_str = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

    # Build attendees list
    attendees = [{"email": e} for e in details.get("participantes", []) if "@" in e]

    event_body = {
        "summary": details.get("titulo", "Reunión"),
        "description": details.get("descripcion", ""),
        "start": {"dateTime": start_str, "timeZone": tz},
        "end": {"dateTime": end_str, "timeZone": tz},
        "attendees": attendees,
        "conferenceData": {
            "createRequest": {
                "requestId": f"landa-{int(datetime.now().timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 15},
                {"method": "email", "minutes": 60},
            ],
        },
    }

    # Run sync Google API call in thread pool
    def _create():
        service = _get_calendar_service()
        return service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            conferenceDataVersion=1,
            sendUpdates="all" if attendees else "none",
        ).execute()

    loop = asyncio.get_event_loop()
    event = await loop.run_in_executor(None, _create)

    meet_link = ""
    conf_data = event.get("conferenceData", {})
    for ep in conf_data.get("entryPoints", []):
        if ep.get("entryPointType") == "video":
            meet_link = ep.get("uri", "")
            break

    return {
        "event_id": event.get("id", ""),
        "meet_link": meet_link,
        "html_link": event.get("htmlLink", ""),
        "summary": event.get("summary", ""),
        "start": start_str,
        "end": end_str,
        "attendees": [a["email"] for a in attendees],
    }


# ── Format reply message ──────────────────────────────────────────────────────

def format_event_reply(event: dict) -> str:
    """Format a WhatsApp-friendly reply for a created calendar event."""
    start = event["start"]
    try:
        dt = datetime.strptime(start, "%Y-%m-%dT%H:%M:%S")
        fecha_str = dt.strftime("%a %d %b · %H:%M")
    except Exception:
        fecha_str = start

    lines = [
        f"✅ Reunión creada: {event['summary']}",
        f"📅 {fecha_str}",
    ]
    if event["meet_link"]:
        lines.append(f"🎥 Meet: {event['meet_link']}")
    if event["attendees"]:
        lines.append(f"👥 Invitados: {', '.join(event['attendees'])}")
    lines.append(f"📆 Ver en Calendar: {event['html_link']}")
    return "\n".join(lines)


# ── Main entry point (bot_mode="calendar") ───────────────────────────────────

async def process_calendar_message(phone: str, text: str, media_url: str = "") -> None:
    """Process a WhatsApp message and create a calendar event if applicable.

    Called from main.py when bot_mode="calendar".
    Sends reply via wa_handler._send_reply().
    """
    import wa_handler

    # Step 1: transcribe audio if present
    if media_url:
        transcribed = await wa_handler._transcribe_voice_note(media_url)
        if transcribed:
            text = transcribed
        else:
            await wa_handler._send_reply(phone, "No pude entender el audio. Escríbeme los detalles de la reunión.")
            return

    if not text.strip():
        await wa_handler._send_reply(phone, "Cuéntame los detalles de la reunión: título, fecha, hora y con quién.")
        return

    # Step 2: extract event details
    await wa_handler._send_reply(phone, "📅 Procesando tu reunión...")
    details = await extract_event_details(text)

    if not details:
        await wa_handler._send_reply(
            phone,
            "No detecté una reunión en tu mensaje. "
            "Ejemplo: 'Reunión con Juan mañana a las 3pm sobre el contrato de seguros'"
        )
        return

    # Step 3: create calendar event
    try:
        event = await create_calendar_event(details)
        reply = format_event_reply(event)
        await wa_handler._send_reply(phone, reply)
        logger.info("[Calendar] Event created: %s meet=%s", event["summary"], event["meet_link"])
    except ValueError as e:
        # Missing refresh token
        await wa_handler._send_reply(phone, f"⚠️ Google Calendar no configurado: {e}")
    except Exception as e:
        logger.error("[Calendar] create_calendar_event error: %s", e)
        await wa_handler._send_reply(phone, "Error creando el evento. Intenta de nuevo.")


# ── Tool function (called from wa_handler dispatch_tool_asesor) ───────────────

async def crear_reunion_tool(text: str) -> str:
    """Create a Google Calendar event from text. Used as wa_handler tool.

    Returns WhatsApp-formatted result string.
    """
    details = await extract_event_details(text)
    if not details:
        return (
            "No detecté detalles de reunión en tu mensaje. "
            "Ejemplo: 'Reunión con Juan mañana a las 3pm'"
        )
    try:
        event = await create_calendar_event(details)
        return format_event_reply(event)
    except ValueError as e:
        return f"⚠️ Google Calendar no configurado aún: {e}"
    except Exception as e:
        logger.error("[Calendar] crear_reunion_tool error: %s", e)
        return f"Error creando la reunión: {e}"
