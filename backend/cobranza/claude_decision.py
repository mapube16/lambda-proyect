"""
claude_decision.py — Claude-powered conversation logic for cobranza calls.

This is the "brain" of the voice orchestrator. It takes:
- estrategia (Queen-generated strategy: tono, guion, etc.)
- call_context (debtor name, monto, vencimiento, max_intentos reached?)
- conversation_history (what's been said so far)
- assembly_ai_transcript (what the debtor just said)

And returns:
- next_action (ask_identity, ask_confirmation, offer_payment, handle_objection, escalate, end)
- response_text (what the agent should say next)
- reasoning (for logging/debugging)

The key to naturalness: this is NOT a rigid state machine. Claude decides dynamically
based on what the debtor actually says, not pre-recorded scripts.
"""
import json
import logging
import os
from datetime import datetime
from typing import Optional

import openai

logger = logging.getLogger("cobranza.claude_decision")


def _build_decision_prompt(
    estrategia: dict,
    debtor: dict,
    transcript_history: list[dict],
    latest_debtor_input: str,
    turn_number: int,
    intentos_used: int,
) -> str:
    """
    Build the system + user prompts for Claude to decide the next action.

    estrategia: {"tono": "...", "guion": {...}, "frecuencia_dias": ..., "max_intentos": ...}
    debtor: {"nombre": "...", "monto": 500000, "vencimiento": "2026-06-01", ...}
    transcript_history: [{"speaker": "agent", "text": "..."}, {"speaker": "debtor", "text": "..."}]
    latest_debtor_input: what the debtor just said
    turn_number: call turn (1-indexed)
    intentos_used: how many times we've failed to reach agreement
    """

    guion = estrategia.get("guion", {})
    tono = estrategia.get("tono", "profesional")

    # Format debtor data for LLM
    debtor_name = debtor.get("nombre", "Cliente")
    monto = debtor.get("monto", 0)
    vencimiento = debtor.get("vencimiento", "desconocida")
    max_intentos = debtor.get("max_intentos", 5)

    # Format conversation history (last 6 exchanges to keep context window reasonable)
    history_text = ""
    for turn in transcript_history[-6:]:
        speaker = "Agente" if turn["speaker"] == "agent" else "Deudor"
        history_text += f"{speaker}: {turn['text']}\n"

    system_prompt = f"""\
Eres un agente de cobranza empático pero firme para {debtor_name}.

ESTRATEGIA DE LLAMADA:
- Tono: {tono}
- Máximo de intentos permitidos antes de escalar: {max_intentos}
- Intentos usados hasta ahora: {intentos_used}

INFORMACIÓN DEL DEUDOR:
- Nombre: {debtor_name}
- Deuda: ${monto:,.0f}
- Vencimiento: {vencimiento}

GUIÓN (usar como referencia, NO como plantilla):
- Saludo inicial: "{guion.get('saludo', '')}"
- Propuesta: "{guion.get('propuesta', '')}"
- Manejo de objeciones: "{guion.get('objeciones', '')}"
- Cierre: "{guion.get('cierre', '')}"

TU OBJETIVO:
1. Confirmar identidad si no está confirmada
2. Confirmar los detalles de la deuda
3. Ofrecer opciones de pago (fecha, monto)
4. Si hay objeciones, manejarlas con empatía pero firmeza
5. Si se alcanza max_intentos, escalar a un supervisor

INSTRUCCIONES DE NATURALIDAD:
- Habla como un colombiano real, NO como robot
- Usa pausas naturales donde sea apropiado
- Responde específicamente a lo que el deudor dijo, NO ignores sus palabras
- Si el deudor dice algo fuera de tema, reconócelo y redirige
- Si el deudor parece cooperativo, sé más amable; si es evasivo, sé más directo
- Máximo 2-3 oraciones por turno (la gente no habla en párrafos)

RESPONDE SIEMPRE CON JSON VÁLIDO:
{{
  "action": "ask_identity" | "ask_confirmation" | "offer_payment" | "handle_objection" | "escalate" | "end",
  "reasoning": "Por qué elegiste esta acción (breve)",
  "response_text": "Lo que debes decir (natural, 2-3 oraciones máximo)",
  "metadata": {{
    "identity_confirmed": bool,
    "debt_confirmed": bool,
    "payment_agreed": bool,
    "objection_type": null | "no_money" | "wrong_person" | "generic_resistance" | "other",
  }}
}}
"""

    user_prompt = f"""\
TURNO {turn_number} DE LA LLAMADA

HISTORIAL HASTA AHORA:
{history_text}

EL DEUDOR ACABA DE DECIR:
"{latest_debtor_input}"

Basándote en:
1. Lo que el deudor acaba de decir
2. El historial de la conversación
3. La estrategia y guión
4. Tu objetivo (lograr un acuerdo de pago)

¿Cuál es tu siguiente paso? Responde con JSON válido.
"""

    return system_prompt, user_prompt


async def get_next_action(
    estrategia: dict,
    debtor: dict,
    transcript_history: list[dict],
    latest_debtor_input: str,
    turn_number: int = 1,
    intentos_used: int = 0,
) -> dict:
    """
    Use Claude to decide the next conversational action.

    Returns:
    {
        "action": "ask_identity" | "ask_confirmation" | "offer_payment" | "handle_objection" | "escalate" | "end",
        "reasoning": str,
        "response_text": str,
        "metadata": {...},
        "error": None | str
    }

    On any error, returns graceful fallback with action="escalate".
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("[Claude Decision] OPENAI_API_KEY not set")
        return {
            "action": "escalate",
            "reasoning": "OpenAI API key not configured",
            "response_text": "Voy a transferirle con un supervisor para resolver esto mejor.",
            "metadata": {},
            "error": "no_api_key",
        }

    system_prompt, user_prompt = _build_decision_prompt(
        estrategia, debtor, transcript_history, latest_debtor_input, turn_number, intentos_used
    )

    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.7,  # Some creativity for natural responses
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=500,
        )

        raw_json = response.choices[0].message.content or "{}"
        decision = json.loads(raw_json)

        # Validate required keys
        required = {"action", "reasoning", "response_text"}
        if not required.issubset(decision.keys()):
            logger.warning(
                "[Claude Decision] Missing required keys. Got: %s", decision.keys()
            )
            return {
                "action": "escalate",
                "reasoning": "Decision format invalid",
                "response_text": "Voy a transferirle con un supervisor.",
                "metadata": {},
                "error": "invalid_format",
            }

        # Ensure action is valid
        valid_actions = {
            "ask_identity",
            "ask_confirmation",
            "offer_payment",
            "handle_objection",
            "escalate",
            "end",
        }
        if decision["action"] not in valid_actions:
            logger.warning(
                "[Claude Decision] Invalid action: %s. Defaulting to escalate.",
                decision["action"],
            )
            decision["action"] = "escalate"

        logger.info(
            "[Claude Decision] Turn %d: action=%s, reasoning=%s",
            turn_number,
            decision["action"],
            decision["reasoning"][:100],
        )

        return decision

    except json.JSONDecodeError as e:
        logger.error("[Claude Decision] JSON parse error: %s", e)
        return {
            "action": "escalate",
            "reasoning": "Failed to parse Claude response",
            "response_text": "Déjeme transferirle con un supervisor.",
            "metadata": {},
            "error": "json_parse_error",
        }
    except Exception as e:
        logger.error("[Claude Decision] Unexpected error: %s", e, exc_info=True)
        return {
            "action": "escalate",
            "reasoning": f"API error: {str(e)[:100]}",
            "response_text": "Disculpe, tengo un inconveniente técnico. Voy a transferirle.",
            "metadata": {},
            "error": "api_error",
        }
