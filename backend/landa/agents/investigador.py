"""
investigador.py — Investigador agent for lead scoring with sector_profile enrichment.

Calls GPT-4o to score a lead 0-100 and return structured output including:
  puntaje, criterios, senales_intencion, recomendacion_agente, canales[]

Uses sector_profile (decisor_primario, senales_compra, ganchos) to enrich
the scoring system prompt.

After scoring, applies post-scoring routing via route_after_scoring.
"""
from __future__ import annotations

import json
import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from landa.core.context import call_agent, TEMP_INVESTIGADOR
from landa.sector_profiles import generate_sector_profile

logger = logging.getLogger("landa.agents.investigador")

_SCORING_SYSTEM_TEMPLATE = """
Eres el Investigador de Landa, un agente experto en calificacion de leads B2B en America Latina.

Contexto del sector:
- Decisor primario tipico: {decisor_primario}
- Senales de compra conocidas: {senales_compra}
- Ganchos de valor para este sector: {ganchos}

Tu tarea: analiza el lead que se te presenta y devuelve un JSON con esta forma EXACTA
(sin campos adicionales, sin markdown):
{{
  "puntaje": <entero 0-100>,
  "criterios": [<lista de strings con razon del puntaje>],
  "senales_intencion": [<lista de senales detectadas, puede estar vacia>],
  "recomendacion_agente": "<string con recomendacion breve>",
  "canales": [
    {{"canal": "<email|whatsapp|linkedin|llamada|instagram>", "probabilidad": <int 0-100>, "razon": "<string>"}},
    ...
  ]
}}

Reglas:
- puntaje entre 0 y 100
- canales debe tener al menos 1 entrada
- Si no hay informacion suficiente, usa puntaje bajo (< 40) y canales con probabilidad baja
- Responde SOLO con el JSON
""".strip()


async def run_investigador(
    lead_id: str,
    user_id: str,
    sector: str = "general",
    pais_region: str = "Colombia",
    tamano: str = "mediana",
    lead_context: str = "",
) -> dict:
    """
    Score a lead using sector_profile enrichment.

    Args:
        lead_id: MongoDB ObjectId string of the lead document.
        user_id: Owner user id.
        sector: Lead's industry sector (e.g. "tecnologia").
        pais_region: Country/region (e.g. "Colombia").
        tamano: Target company size (e.g. "mediana").
        lead_context: Optional additional context string about the lead.

    Returns:
        dict with keys: puntaje (int), criterios (list), senales_intencion (list),
        recomendacion_agente (str), canales (list[{canal, probabilidad, razon}])
    """
    # Fetch sector profile for enriched scoring prompt
    try:
        sector_profile = await generate_sector_profile(sector, pais_region, tamano)
    except Exception as exc:
        logger.warning("Could not load sector_profile for %s/%s: %s", sector, pais_region, exc)
        sector_profile = {}

    decisor_primario = sector_profile.get("decisor_primario", "Gerente General")
    senales_compra_raw = sector_profile.get("senales_compra", [])
    ganchos_raw = sector_profile.get("ganchos", [])

    senales_compra = ", ".join(senales_compra_raw) if isinstance(senales_compra_raw, list) else str(senales_compra_raw)
    ganchos = ", ".join(ganchos_raw) if isinstance(ganchos_raw, list) else str(ganchos_raw)

    system_prompt = _SCORING_SYSTEM_TEMPLATE.format(
        decisor_primario=decisor_primario,
        senales_compra=senales_compra or "no especificadas",
        ganchos=ganchos or "no especificados",
    )

    user_message = lead_context or f"Lead ID: {lead_id} — sin informacion adicional disponible."

    raw = await call_agent(
        system_prompt=system_prompt,
        user_message=user_message,
        temperature=TEMP_INVESTIGADOR,
        model="gpt-4o",
    )

    # Parse LLM response
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Fallback: extract JSON from response if it contains extra text
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start != -1 and end > start:
            result = json.loads(raw[start:end])
        else:
            logger.error("Investigador LLM returned non-JSON: %s", raw[:200])
            result = {
                "puntaje": 0,
                "criterios": ["LLM returned non-JSON"],
                "senales_intencion": [],
                "recomendacion_agente": "error en scoring",
                "canales": [{"canal": "email", "probabilidad": 0, "razon": "error en scoring"}],
            }

    # Normalize puntaje to int
    puntaje = int(result.get("puntaje", 0))
    puntaje = max(0, min(100, puntaje))
    result["puntaje"] = puntaje

    # Ensure canales is a list with at least 1 entry
    canales = result.get("canales", [])
    if not isinstance(canales, list) or len(canales) == 0:
        canales = [{"canal": "email", "probabilidad": 0, "razon": "no determinado"}]
        result["canales"] = canales

    # Persist canales and scoring data to the lead document
    try:
        from database import get_db
        from bson import ObjectId

        db = get_db()
        await db.leads.update_one(
            {"_id": ObjectId(lead_id)},
            {"$set": {
                "puntaje": puntaje,
                "criterios": result.get("criterios", []),
                "senales_intencion": result.get("senales_intencion", []),
                "recomendacion_agente": result.get("recomendacion_agente", ""),
                "canales": canales,
            }},
        )
    except Exception as exc:
        logger.error("Could not persist scoring to lead %s: %s", lead_id, exc)

    # Apply post-scoring routing
    try:
        from landa.agents.router import route_after_scoring
        await route_after_scoring(lead_id, user_id, puntaje=puntaje)
    except Exception as exc:
        logger.error("Routing error for lead %s puntaje=%d: %s", lead_id, puntaje, exc)

    return result
