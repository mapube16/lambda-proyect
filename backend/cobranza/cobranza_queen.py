"""
cobranza_queen.py — Queen intelligence for cobranza strategy onboarding.

Reads the user's portfolio description and produces a structured collection
strategy proposal: tono, frecuencia, max_intentos, and a 4-section guion.

Pattern mirrors queen_proposal.py exactly:
  openai.AsyncOpenAI + response_format={"type": "json_object"}
"""
import json
import logging
import os

import openai

logger = logging.getLogger("cobranza.queen")

# ── System prompt template (empresa_nombre interpolated at call time) ─────────

_COBRANZA_QUEEN_SYSTEM_PROMPT_TEMPLATE = """\
Eres la estratega de cobranza de Landa. Tu misión es analizar la descripción \
de la cartera de un cliente y proponer la estrategia ÓPTIMA de llamadas de cobranza.

El cliente usa la empresa: {empresa_nombre}. El agente de voz siempre se \
identificará como representante de {empresa_nombre}.

Propón:
- tono: el tono apropiado para las llamadas (profesional/empático/firme/amigable)
- frecuencia_dias: cada cuántos días hábiles llamar post-vencimiento (1, 2 o 3)
- max_intentos: máximo de intentos fallidos antes de marcar como agotado (1-10, default 5)
- guion: 4 secciones editables con frases concretas y naturales en español colombiano

IMPORTANTE: responde ÚNICAMENTE con JSON válido, sin texto adicional.\
"""


def _safe_defaults(empresa_nombre: str) -> dict:
    """Return safe fallback strategy dict when OpenAI is unavailable."""
    return {
        "tono": "profesional y empático",
        "frecuencia_dias": 2,
        "max_intentos": 5,
        "guion": {
            "saludo": f"Buenos días, mi nombre es Agente de {empresa_nombre}...",
            "propuesta": "Le contactamos sobre una obligación pendiente...",
            "objeciones": "Entiendo su situación, ¿podríamos acordar una fecha de pago?",
            "cierre": "Muchas gracias por su tiempo. Que tenga un buen día.",
        },
    }


async def generate_cobranza_proposal(
    user_description: str,
    empresa_nombre: str = "la empresa",
) -> dict:
    """
    Ask the Queen to propose a cobranza strategy based on the user's portfolio
    description.

    Returns a dict with keys: tono, frecuencia_dias, max_intentos, guion.
    guion has sub-keys: saludo, propuesta, objeciones, cierre.

    On missing OPENAI_API_KEY or any exception returns safe fallback dict
    without raising.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.warning(
            "[CobranzaQueen] OPENAI_API_KEY not set — using fallback defaults"
        )
        return _safe_defaults(empresa_nombre)

    system_prompt = _COBRANZA_QUEEN_SYSTEM_PROMPT_TEMPLATE.format(
        empresa_nombre=empresa_nombre
    )

    try:
        client = openai.AsyncOpenAI(api_key=api_key)
        response = await client.chat.completions.create(
            model="gpt-4o",
            temperature=0.4,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_description},
            ],
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
    except Exception as e:
        logger.warning("[CobranzaQueen] Using defaults: %s", e)
        return _safe_defaults(empresa_nombre)

    # ── Validate and clamp ────────────────────────────────────────────────────
    # Ensure required top-level keys exist; fall back to safe defaults if missing
    required_keys = {"tono", "frecuencia_dias", "max_intentos", "guion"}
    if not required_keys.issubset(data.keys()):
        logger.warning(
            "[CobranzaQueen] Response missing required keys — using defaults"
        )
        return _safe_defaults(empresa_nombre)

    guion = data.get("guion", {})
    required_guion_keys = {"saludo", "propuesta", "objeciones", "cierre"}
    if not required_guion_keys.issubset(guion.keys()):
        logger.warning(
            "[CobranzaQueen] guion missing required keys — using defaults"
        )
        return _safe_defaults(empresa_nombre)

    # Clamp numeric fields
    try:
        data["frecuencia_dias"] = max(1, min(3, int(data["frecuencia_dias"])))
        data["max_intentos"] = max(1, min(10, int(data["max_intentos"])))
    except (TypeError, ValueError) as e:
        logger.warning("[CobranzaQueen] Numeric clamping error — using defaults: %s", e)
        return _safe_defaults(empresa_nombre)

    return data
