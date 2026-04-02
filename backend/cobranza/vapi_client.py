"""
vapi_client.py — AsyncVapi wrapper for outbound Vapi call creation.

Provides initiate_call() and cancel_call() using lazy import of AsyncVapi
so the SDK is optional at startup (consistent with Phase 16 WhatsApp lazy import pattern).
"""
import os
import logging
from datetime import datetime

logger = logging.getLogger("cobranza.vapi")


async def initiate_call(debtor: dict, config: dict) -> str:
    """
    Create an outbound Vapi call for the debtor.

    config must have: vapi_api_key, vapi_assistant_id, vapi_phone_number_id.
    Falls back to environment variables VAPI_API_KEY, VAPI_ASSISTANT_ID,
    VAPI_PHONE_NUMBER_ID if config keys are absent.

    Returns Vapi call_id string.
    Raises ValueError if VAPI_API_KEY missing from both config and env.
    Raises RuntimeError on Vapi API error.
    """
    from vapi import AsyncVapi  # lazy import — SDK optional at startup

    api_key = config.get("vapi_api_key") or os.getenv("VAPI_API_KEY")
    if not api_key:
        logger.error("[Vapi] VAPI_API_KEY not found in config or environment")
        raise ValueError("VAPI_API_KEY not configured")

    assistant_id = config.get("vapi_assistant_id") or os.getenv("VAPI_ASSISTANT_ID")
    phone_number_id = config.get("vapi_phone_number_id") or os.getenv("VAPI_PHONE_NUMBER_ID")

    if not assistant_id:
        logger.error("[Vapi] VAPI_ASSISTANT_ID not found in config or environment")
        raise ValueError("VAPI_ASSISTANT_ID not configured")
    if not phone_number_id:
        logger.error("[Vapi] VAPI_PHONE_NUMBER_ID not found in config or environment")
        raise ValueError("VAPI_PHONE_NUMBER_ID not configured")

    vencimiento_str = ""
    if isinstance(debtor.get("vencimiento"), datetime):
        vencimiento_str = debtor["vencimiento"].strftime("%d de %B de %Y")
    elif debtor.get("vencimiento"):
        vencimiento_str = str(debtor["vencimiento"])

    client = AsyncVapi(token=api_key)
    try:
        nombre = debtor.get("nombre", "")
        monto = debtor.get('monto', 0)
        # Format amount in a natural way for speech (e.g., "quinientos mil" not "500,000")
        if monto >= 1_000_000:
            monto_fmt = f"{monto / 1_000_000:.0f} millones" if monto % 1_000_000 == 0 else f"{monto / 1_000_000:.1f} millones".rstrip('0').rstrip('.')
        elif monto >= 1_000:
            monto_fmt = f"{monto / 1_000:.0f} mil" if monto % 1_000 == 0 else f"{monto / 1_000:.1f} mil".rstrip('0').rstrip('.')
        else:
            monto_fmt = f"{monto:.0f}"

        # STRICT GATE: first_message only validates identity, NO mention of debt/obligation/amount
        # Use natural, conversational Colombian Spanish (Camila persona)
        # This forces the deudor to confirm "yes, it's me" before agent reveals purpose
        import random

        if nombre:
            # With debtor name: natural openings
            greetings = [
                f"Aló, buenas tardes... ¿será que hablo con {nombre}?",
                f"Buenas tardes... ¿estoy hablando con {nombre}?",
                f"Hola, ¿con el señor {nombre.split()[-1]}?",
            ]
            first_message = random.choice(greetings)
        else:
            # Without name: ask who we're talking to
            greetings = [
                "Aló, buenas tardes... ¿con quién tengo el gusto?",
                "Buenas tardes... ¿puedo hablar con el titular de la línea?",
                "Hola, ¿quién es?",
            ]
            first_message = random.choice(greetings)

        call = await client.calls.create(
            assistant_id=assistant_id,
            phone_number_id=phone_number_id,
            customer={"number": debtor["telefono"], "name": nombre},
            assistant_overrides={
                "first_message": first_message,
                "variable_values": {
                    "debtor_id": str(debtor["_id"]),
                    "debtor_name": nombre,
                    "monto": monto_fmt,
                    "vencimiento": vencimiento_str,
                },
            },
        )
        logger.info("[Vapi] Call created: %s → debtor %s", call.id, debtor["_id"])
        return call.id
    except Exception as e:
        logger.error("[Vapi] Call creation failed: %s", e)
        raise RuntimeError(f"Vapi call creation failed: {e}") from e


async def cancel_call(call_id: str) -> bool:
    """Cancel an in-progress Vapi call. Returns True on success, False on failure."""
    from vapi import AsyncVapi  # lazy import

    api_key = os.getenv("VAPI_API_KEY")
    if not api_key:
        logger.warning("[Vapi] VAPI_API_KEY not set — cannot cancel call %s", call_id)
        return False
    client = AsyncVapi(token=api_key)
    try:
        await client.calls.delete(call_id)
        logger.info("[Vapi] Call cancelled: %s", call_id)
        return True
    except Exception as e:
        logger.warning("[Vapi] Cancel failed for %s: %s", call_id, e)
        return False
