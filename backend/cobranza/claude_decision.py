"""
claude_decision.py — LLM conversation logic for cobranza calls.

Two modes:
1. get_next_action() — traditional (wait for full response). Used as fallback.
2. stream_next_action() — streaming (yield sentences as they arrive). Used for low-latency.
"""
import json
import logging
import os
import time
from typing import AsyncGenerator, Optional

import openai

logger = logging.getLogger("cobranza.claude_decision")

# Reuse client across calls
_client: Optional[openai.AsyncOpenAI] = None


def _get_client() -> openai.AsyncOpenAI:
    global _client
    if _client is None:
        _client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _client


def _build_system_prompt(
    estrategia: dict,
    debtor: dict,
    intentos_used: int,
    call_state: dict = None,
) -> str:
    guion = estrategia.get("guion", {})
    tono = estrategia.get("tono", "profesional")
    debtor_name = debtor.get("nombre", "Cliente")
    monto = debtor.get("monto", 0)
    vencimiento = debtor.get("vencimiento", "desconocida")
    max_intentos = debtor.get("max_intentos", 5)
    cs = call_state or {}

    return f"""\
Eres Camila, asesora de cartera en De Pe Ge Seguros. Colombiana, cálida, empática, natural. Nunca robótica.

[Style] Usa "usted", muletillas colombianas ("ajá", "qué pena", "un momentico"). Máximo 2-3 frases cortas.

[Datos] Deudor: {debtor_name} | Deuda: ${monto:,.0f} | Vence: {vencimiento} | Tono: {tono}

[Estado] identidad:{"SÍ" if cs.get("identity_confirmed") else "NO"} | deuda:{"SÍ" if cs.get("debt_mentioned") else "NO"} | pago:{"SÍ" if cs.get("payment_discussed") else "NO"}

[Flujo — avanza EN ORDEN, NO repitas pasos completados]
1. identidad=NO → confirma quién es. "sí"/"con él"/"soy yo" = confirmado, avanza.
2. identidad=SÍ, deuda=NO → preséntate, menciona la deuda.
3. deuda=SÍ → ofrece opciones de pago.
4. Objeciones → empatía, no insistas.
5. No es titular/no está → pregunta cuándo llamar, cierra.
6. 2-3 intentos sin avance → cierra amablemente.

FORMATO DE RESPUESTA — IMPORTANTE:
Primero escribe EXACTAMENTE lo que Camila dice (texto plano, sin comillas).
Luego en una línea nueva escribe: META|action|identity_confirmed|debt_confirmed

Ejemplo:
Ah, qué pena señor Juan. Le llamo de De Pe Ge Seguros, tenemos un saldo pendiente.
META|ask_confirmation|true|true

Otro ejemplo:
Será que hablo con el señor Juan?
META|ask_identity|false|false"""


def _build_user_prompt(
    transcript_history: list[dict],
    latest_debtor_input: str,
    turn_number: int,
) -> str:
    history = ""
    for t in transcript_history[-6:]:
        speaker = "Agente" if t["speaker"] == "agent" else "Deudor"
        history += f"{speaker}: {t['text']}\n"

    return f"Turno {turn_number}.\n{history}Deudor: \"{latest_debtor_input}\"\nJSON:"


async def stream_next_action(
    estrategia: dict,
    debtor: dict,
    transcript_history: list[dict],
    latest_debtor_input: str,
    turn_number: int = 1,
    call_state: dict = None,
) -> AsyncGenerator[dict, None]:
    """
    Stream LLM response. Yields partial results as sentences are completed.

    First yield: {"type": "sentence", "text": "Primera oración."}
    ...more sentences...
    Final yield: {"type": "complete", "action": "...", "response_text": "full text", "metadata": {...}}
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        yield {"type": "complete", "action": "escalate", "response_text": "Disculpe, tengo un problema técnico.", "metadata": {}}
        return

    system_prompt = _build_system_prompt(estrategia, debtor, 0, call_state)
    user_prompt = _build_user_prompt(transcript_history, latest_debtor_input, turn_number)

    logger.info("[LLM] Turn %d streaming | state=%s | input: %s", turn_number, call_state, latest_debtor_input[:60])

    t0 = time.time()
    ttft = None
    full_response = ""
    sentence_buffer = ""
    sentences_yielded = 0

    try:
        client = _get_client()
        stream = await client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.7,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=200,
            stream=True,
        )

        async for chunk in stream:
            token = chunk.choices[0].delta.content or ""
            if not token:
                continue

            if ttft is None:
                ttft = time.time() - t0
                logger.info("[LLM] TTFT: %.0fms", ttft * 1000)

            full_response += token

            # Stop accumulating if we hit the META line
            if "META|" in full_response:
                # Flush any remaining sentence buffer
                remaining = full_response.split("META|")[0].strip()
                if remaining and remaining != sentence_buffer:
                    leftover = remaining[len(sentence_buffer):].strip()
                    if leftover:
                        sentences_yielded += 1
                        logger.info("[LLM] Sentence %d (%.0fms): %s", sentences_yielded, (time.time() - t0) * 1000, leftover[:80])
                        yield {"type": "sentence", "text": leftover}
                continue

            sentence_buffer += token

            # Yield complete sentences (split on . ! ?)
            for end_char in [".", "!", "?"]:
                if end_char in sentence_buffer:
                    idx = sentence_buffer.index(end_char)
                    sentence = sentence_buffer[:idx + 1].strip()
                    sentence_buffer = sentence_buffer[idx + 1:].strip()

                    if len(sentence) > 3:
                        sentences_yielded += 1
                        logger.info("[LLM] Sentence %d (%.0fms): %s", sentences_yielded, (time.time() - t0) * 1000, sentence[:80])
                        yield {"type": "sentence", "text": sentence}
                    break

        t_total = time.time() - t0
        logger.info("[LLM] Done %.1fs (TTFT %.0fms, %d sentences)", t_total, (ttft or 0) * 1000, sentences_yielded)

        # Parse META line
        action = "continue"
        metadata = {}
        if "META|" in full_response:
            try:
                meta_line = full_response.split("META|")[1].strip().split("\n")[0]
                parts = meta_line.split("|")
                action = parts[0] if parts else "continue"
                metadata["identity_confirmed"] = parts[1].lower() == "true" if len(parts) > 1 else False
                metadata["debt_confirmed"] = parts[2].lower() == "true" if len(parts) > 2 else False
                metadata["payment_agreed"] = parts[3].lower() == "true" if len(parts) > 3 else False
            except Exception as e:
                logger.warning("[LLM] META parse error: %s", e)

        speech_text = full_response.split("META|")[0].strip() if "META|" in full_response else full_response.strip()
        logger.info("[LLM] Action=%s meta=%s", action, metadata)

        yield {
            "type": "complete",
            "action": action,
            "response_text": speech_text,
            "metadata": metadata,
        }

    except Exception as e:
        logger.error("[LLM] Stream error: %s", e)
        yield {"type": "complete", "action": "escalate", "response_text": "Disculpe, un momento.", "metadata": {}}


async def get_next_action(
    estrategia: dict,
    debtor: dict,
    transcript_history: list[dict],
    latest_debtor_input: str,
    turn_number: int = 1,
    intentos_used: int = 0,
    call_state: dict = None,
) -> dict:
    """Non-streaming fallback. Collects full response."""
    result = {"action": "escalate", "response_text": "Un momento.", "metadata": {}}
    async for event in stream_next_action(
        estrategia, debtor, transcript_history, latest_debtor_input, turn_number, call_state
    ):
        if event["type"] == "complete":
            result = event
    return result
