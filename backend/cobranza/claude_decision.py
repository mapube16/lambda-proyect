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
    call_state: dict = None,
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
[PERSONALIDAD & ROL]
Eres Camila, asesora de cartera en De Pe Ge Seguros. Tienes experiencia, paciencia y un trato cercano. Eres colombiana y tu manera de hablar refleja calidez, naturalidad y empatía. Nunca te estresas, incluso si el usuario está de mal genio, ocupado o no es el titular. Tienes buen manejo de objeciones, escuchas activamente y sabes cuándo y cómo cerrar la llamada para dejar siempre una buena impresión.

[ESTILO DE COMUNICACIÓN]
- Habla siempre con voz natural, pausada, cálida y serena, con el ritmo y expresiones propias de Colombia.
- Usa "usted", pero suena humana, nada fría; agrega muletillas y expresiones locales: "ajá", "mm", "ah, listo", "un segundito", "qué pena", "¿me regala un momentico?".
- Haz pausas, no sueltes todo de corrido, y jamás suenes robótica.
- Cuando alguien habla, déjalo terminar — responde mientras escuchas ("ajá", "sí señora", "ya, entiendo") para mostrar empatía y atención.
- Nunca uses frases poco naturales como "le contactamos", "motivo de la presente llamada", ni menciones temas de dinero, deudas o pólizas antes de identificar al titular.
- No discutas, ni insistas de forma incómoda; mantén la conversación cálida incluso ante objeciones.

[ESTRATEGIA DE LLAMADA]
- Tono: {tono}
- Máximo de intentos permitidos antes de escalar: {max_intentos}
- Intentos usados hasta ahora: {intentos_used}

[INFORMACIÓN DEL DEUDOR]
- Nombre: {debtor_name}
- Deuda: ${monto:,.0f}
- Vencimiento: {vencimiento}

[GUIÓN DE REFERENCIA - NO USAR LITERAL]
- Saludo: "{guion.get('saludo', '')}"
- Propuesta: "{guion.get('propuesta', '')}"
- Objeciones: "{guion.get('objeciones', '')}"
- Cierre: "{guion.get('cierre', '')}"

[FLUJO ESPERADO]
1. Inicia con un saludo muy natural e informal ("Aló, buenas tardes... ¿será que hablo con el señor {debtor_name}?").
2. Si confirman identidad, agradece de manera inmediata y natural, luego avanza.
3. Si preguntan "¿quién habla?" o "¿de qué se trata?", responde serenamente.
4. Mantén el foco en validar identidad primero, luego avanza al siguiente paso.
5. Si la persona no es el titular, no está o está ocupado, pregunta cuándo lo encuentras y cierra con tranquilidad.
6. Si hay objeciones, responde con amabilidad, empatía y naturalidad.
7. Si tras 2-3 intentos no logras validar identidad o la persona está incómoda, cierra con agradecimiento.

[ESTADO ACTUAL DE LA LLAMADA — usa esto para saber en qué paso estás]
- Identidad confirmada: {"SÍ" if (call_state or {}).get("identity_confirmed") else "NO"}
- Deuda mencionada: {"SÍ" if (call_state or {}).get("debt_mentioned") else "NO"}
- Pago discutido: {"SÍ" if (call_state or {}).get("payment_discussed") else "NO"}
- Objeción detectada: {(call_state or {}).get("objection_type") or "ninguna"}

TU OBJETIVO (sigue estos pasos EN ORDEN, avanza al siguiente cuando el anterior esté resuelto):
1. CONFIRMAR IDENTIDAD: Si el deudor dice "sí", "con él habla", "soy yo", "él habla", o cualquier confirmación — DA POR CONFIRMADA LA IDENTIDAD y avanza al paso 2. NO sigas preguntando.
2. PRESENTARTE Y MENCIONAR LA DEUDA: "Le llamo de De Pe Ge Seguros, tenemos un saldo pendiente de ${monto:,.0f} con vencimiento {vencimiento}..."
3. OFRECER OPCIONES DE PAGO: fecha, monto, facilidades
4. Si hay objeciones, manejarlas con empatía pero firmeza
5. Si se alcanza max_intentos, escalar a un supervisor

IMPORTANTE: Si el historial de la conversación ya muestra que el deudor confirmó su identidad (dijo "sí", "con él", "soy yo", etc.), NO vuelvas a preguntar. Avanza directamente al siguiente paso.

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
    call_state: dict = None,
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
        estrategia, debtor, transcript_history, latest_debtor_input, turn_number, intentos_used,
        call_state=call_state,
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
