"""
sector_profiles.py — GPT-4o generation of sector intelligence profiles.
Implements 30-day cache in MongoDB (sector_profiles collection).
"""
import os
import sys
import json
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db

logger = logging.getLogger("landa.sector_profiles")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL   = os.getenv("OPENAI_MODEL", "gpt-4o")
CACHE_DAYS = 30

SECTOR_PROFILE_KEYS = [
    "decisor_primario", "influenciador", "bloqueador",
    "canal_principal", "canal_respaldo", "tono", "ciclo_venta",
    "ganchos", "objeciones", "senales_compra", "senales_reentrada",
    "consideraciones_legales",
]

_SYSTEM_PROMPT = """
Eres un experto en ventas B2B en América Latina. Genera un perfil de sector en JSON
con los siguientes campos exactos (sin campos adicionales):
{
  "decisor_primario": "cargo típico del decisor principal",
  "influenciador": "cargo del influenciador",
  "bloqueador": "cargo del bloqueador típico",
  "canal_principal": "email|linkedin|whatsapp|llamada|instagram",
  "canal_respaldo": "canal secundario",
  "tono": "formal|semiformal|informal",
  "ciclo_venta": "dias estimados como número entero",
  "ganchos": ["gancho1", "gancho2", "gancho3"],
  "objeciones": ["obj1","obj2","obj3","obj4","obj5"],
  "senales_compra": ["senal1","senal2","senal3"],
  "senales_reentrada": ["senal1","senal2","senal3"],
  "consideraciones_legales": "texto libre sobre regulaciones relevantes"
}
Responde SOLO con el JSON, sin explicaciones ni markdown.
""".strip()


async def generate_sector_profile(
    sector: str,
    pais_region: str,
    tamano: str = "mediana",
) -> dict:
    """
    Returns a sector intelligence profile. Uses 30-day cache from MongoDB.
    Calls GPT-4o (temp=0.2) on cache miss. Saves result to sector_profiles collection.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not set — cannot generate sector profile")

    db = get_db()
    cutoff = datetime.now(timezone.utc) - timedelta(days=CACHE_DAYS)

    # Cache lookup
    cached = await db.sector_profiles.find_one({
        "sector": sector,
        "pais_region": pais_region,
        "created_at": {"$gte": cutoff},
    })
    if cached:
        cached["_id"] = str(cached["_id"])
        logger.info("sector_profile cache hit: %s / %s", sector, pais_region)
        return cached

    logger.info("sector_profile cache miss — calling GPT-4o: %s / %s", sector, pais_region)

    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=OPENAI_API_KEY)

    user_message = (
        f"Sector: {sector}\n"
        f"País/Región: {pais_region}\n"
        f"Tamaño típico de empresa objetivo: {tamano}"
    )
    response = await client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.2,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user",   "content": user_message},
        ],
        response_format={"type": "json_object"},
    )
    raw = response.choices[0].message.content
    profile_data = json.loads(raw)

    now = datetime.now(timezone.utc)
    doc = {
        **profile_data,
        "sector": sector,
        "pais_region": pais_region,
        "tamano": tamano,
        "created_at": now,
    }
    result = await db.sector_profiles.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    logger.info("sector_profile saved: %s", doc["_id"])
    return doc
