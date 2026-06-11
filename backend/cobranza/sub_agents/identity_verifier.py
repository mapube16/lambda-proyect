"""
identity_verifier.py — Sub-agent for NIT/identity verification.

Strategy:
1. Regex short-circuit: confirm/deny patterns resolved in <1ms (confidence="high").
2. LLM fallback (gpt-4o-mini, NOT realtime): used only when utterance is ambiguous.
   Returns confidence="low" or "medium" — never blocks >3s.

Threat: T-25-04 — only utterance + debtor_name sent to LLM; no PII beyond call scope.
"""
import logging
import os
import re
from typing import Optional

import openai

logger = logging.getLogger("cobranza.sub_agents.identity_verifier")

# ── Compiled patterns (module-level for zero-overhead reuse) ─────────────────

_CONFIRM_PATTERNS = re.compile(
    r"\b(si|s[ií]|soy|claro|correcto|eso es|afirmativo|con gusto|exacto|así es|efectivamente)\b",
    re.I,
)
_DENY_PATTERNS = re.compile(
    r"\b(no|incorrecto|equivocado|otro numero|no es aqui|no soy|se equivoc[oó]|número incorrecto)\b",
    re.I,
)

# LLM client (lazy singleton)
_openai_client: Optional[openai.AsyncOpenAI] = None


def _get_llm_client() -> openai.AsyncOpenAI:
    global _openai_client
    if _openai_client is None:
        _openai_client = openai.AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    return _openai_client


async def _llm_verify(utterance: str, debtor_name: str) -> dict:
    """
    LLM fallback for ambiguous utterances. Uses gpt-4o-mini (NOT realtime).
    Returns {"confirmed": bool, "confidence": "low" | "medium"}.
    """
    prompt = (
        f"El agente de cobro preguntó si está hablando con {debtor_name}. "
        f"La respuesta del usuario fue: \"{utterance}\". "
        "Responde SOLO con 'confirm' o 'deny'."
    )
    try:
        client = _get_llm_client()
        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            temperature=0,
        )
        answer = response.choices[0].message.content.strip().lower()
        if "confirm" in answer:
            return {"confirmed": True, "confidence": "medium"}
        elif "deny" in answer:
            return {"confirmed": False, "confidence": "medium"}
        else:
            logger.warning("[identity_verifier] unexpected LLM answer: %s", answer)
            return {"confirmed": False, "confidence": "low"}
    except Exception as e:
        logger.error("[identity_verifier] LLM fallback failed: %s", e)
        return {"confirmed": False, "confidence": "low"}


async def verify_identity(utterance: str, debtor_name: str) -> dict:
    """
    Verify whether the utterance confirms or denies that the debtor is on the line.

    Resolution order:
    1. Regex confirm pattern → {"confirmed": True, "confidence": "high"}
    2. Regex deny pattern   → {"confirmed": False, "confidence": "high"}
    3. LLM fallback         → {"confirmed": bool, "confidence": "low"|"medium"}

    Args:
        utterance: What the called party said.
        debtor_name: Expected debtor name (used in LLM fallback prompt).

    Returns:
        {"confirmed": bool, "confidence": "high" | "medium" | "low"}
    """
    # Fast path: regex (sub-100ms, no external call)
    if _CONFIRM_PATTERNS.search(utterance):
        logger.debug("[identity_verifier] regex confirm for utterance='%s'", utterance[:50])
        return {"confirmed": True, "confidence": "high"}

    if _DENY_PATTERNS.search(utterance):
        logger.debug("[identity_verifier] regex deny for utterance='%s'", utterance[:50])
        return {"confirmed": False, "confidence": "high"}

    # Ambiguous — LLM fallback
    logger.info("[identity_verifier] regex inconclusive, using LLM fallback")
    return await _llm_verify(utterance, debtor_name)
