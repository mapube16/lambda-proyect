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

import logging
import os
from typing import Optional

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


# ── Private helpers (stubs — implemented in Plans 04-05) ─────────────────────

async def _transcribe_voice_note(media_url: str) -> Optional[str]:
    """Download Twilio MediaUrl and transcribe with OpenAI Whisper. Stub for Plan 04."""
    return None


async def _call_llm_with_tools(
    message: str,
    history: list,
    profile: str,
    user_id: str,
) -> str:
    """Call OpenAI with tool definitions for the given profile. Stub for Plans 04-05."""
    return "Recibí tu mensaje. Esta función se completará en la próxima fase."


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
