"""
context.py — Variable template builder and OpenAI wrapper for Landa agents.
Per Documento B Sección 1.4 and 2.x.
"""
import os
import re
import sys
import logging
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

logger = logging.getLogger("landa.context")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")

# Per-agent temperature constants (Documento B Sección 1.4)
TEMP_INVESTIGADOR: float = 0.2
TEMP_OUTREACH:     float = 0.7
TEMP_NURTURING:    float = 0.6

# Regex to find [KEY] placeholders — uppercase letters, digits, underscores
_VAR_PATTERN = re.compile(r"\[([A-Z][A-Z0-9_]*)\]")


def build_system_prompt(template: str, variables: dict) -> str:
    """
    Replace [KEY] placeholders in template with values from variables dict.
    Missing keys are replaced with [inferida — KEY] (not left as [KEY]).

    Examples:
      build_system_prompt("[SECTOR] en [PAIS]", {"SECTOR": "tech", "PAIS": "Colombia"})
      → "tech en Colombia"

      build_system_prompt("[SECTOR] en [PAIS]", {"SECTOR": "tech"})
      → "tech en [inferida — PAIS]"
    """
    def replace_match(m: re.Match) -> str:
        key = m.group(1)
        value = variables.get(key)
        if value is None or str(value).strip() == "":
            return f"[inferida — {key}]"
        return str(value)

    return _VAR_PATTERN.sub(replace_match, template)


async def call_agent(
    system_prompt: str,
    user_message: str,
    temperature: float = 0.5,
    model: Optional[str] = None,
) -> str:
    """
    Wrapper around OpenAI chat completions.
    Returns the assistant's response content as a string.
    Raises RuntimeError if OPENAI_API_KEY is not set.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set — cannot call agent")

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)
    response = await client.chat.completions.create(
        model=model or OPENAI_MODEL,
        temperature=temperature,
        messages=[
            {"role": "system",  "content": system_prompt},
            {"role": "user",    "content": user_message},
        ],
    )
    return response.choices[0].message.content or ""
