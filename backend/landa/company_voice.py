"""
company_voice.py — Company voice configuration for Landa outreach.
Syncs from existing client_profiles collection (Phase 9 onboarding data).
Stored in company_voice collection (separate from client_profiles).
"""
import os
import sys
import logging
from datetime import datetime, timezone
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from database import get_db

logger = logging.getLogger("landa.company_voice")

# Schema field names for company_voice (Documento B Sección 3.3)
COMPANY_VOICE_KEYS = [
    "remitentes",           # list[{nombre, cargo, correo, telefono}]
    "web",                  # str
    "tratamiento",          # "tuteo" | "ustedeo"
    "tono_empresa",         # str
    "largo_mensajes",       # "corto" | "medio" | "largo"
    "usa_emojis",           # bool
    "formato",              # "texto plano" | "html" | "markdown"
    "palabras_clave",       # list[str] (max 3)
    "palabras_prohibidas",  # list[str] (max 3)
    "frase_apertura",       # str
    "frase_cierre",         # str
    "ejemplo_comunicacion", # str
    "estilos_canal",        # dict {email, whatsapp, linkedin, instagram, tiktok}
]


def _map_from_client_profile(profile: dict) -> dict:
    """Map fields from client_profiles to company_voice schema."""
    campaign = profile.get("campaign") or {}
    agents = profile.get("agents") or []

    remitentes = [
        {
            "nombre": str(a.get("name") or ""),
            "cargo": str(a.get("role") or ""),
            "correo": "",
            "telefono": "",
        }
        for a in agents
    ] or [{"nombre": "", "cargo": "", "correo": "", "telefono": ""}]

    return {
        "remitentes":           remitentes,
        "web":                  campaign.get("web_empresa", ""),
        "tratamiento":          campaign.get("tratamiento", "ustedeo"),
        "tono_empresa":         campaign.get("tono_empresa") or profile.get("personality_prompt", "")[:200],
        "largo_mensajes":       campaign.get("largo_mensajes", "medio"),
        "usa_emojis":           bool(campaign.get("usa_emojis", False)),
        "formato":              campaign.get("formato", "texto plano"),
        "palabras_clave":       campaign.get("palabras_clave", []),
        "palabras_prohibidas":  campaign.get("palabras_prohibidas", []),
        "frase_apertura":       campaign.get("frase_apertura", ""),
        "frase_cierre":         campaign.get("frase_cierre", ""),
        "ejemplo_comunicacion": campaign.get("ejemplo_comunicacion", ""),
        "estilos_canal": {
            "email":     campaign.get("estilo_email", ""),
            "whatsapp":  campaign.get("estilo_wa", ""),
            "linkedin":  campaign.get("estilo_li", ""),
            "instagram": campaign.get("estilo_ig", ""),
            "tiktok":    campaign.get("estilo_tk", ""),
        },
    }


async def get_or_create_company_voice(user_id: str) -> dict:
    """
    Returns the company_voice document for user_id.
    Creates it from client_profiles if it doesn't exist yet.
    Returns a doc with all COMPANY_VOICE_KEYS regardless of source data completeness.
    """
    db = get_db()
    existing = await db.company_voice.find_one({"user_id": user_id})
    if existing:
        existing["_id"] = str(existing["_id"])
        return existing

    # Build from client_profiles
    profile = await db.client_profiles.find_one({"user_id": user_id})
    if profile:
        voice_data = _map_from_client_profile(profile)
        logger.info("company_voice: syncing from client_profiles for user %s", user_id)
    else:
        logger.info("company_voice: no client_profile found, creating empty voice for user %s", user_id)
        voice_data = {k: [] if k in ("remitentes", "palabras_clave", "palabras_prohibidas") else
                        {} if k == "estilos_canal" else
                        False if k == "usa_emojis" else ""
                      for k in COMPANY_VOICE_KEYS}

    now = datetime.now(timezone.utc)
    doc = {
        "user_id": user_id,
        **voice_data,
        "synced_from_profile": profile is not None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.company_voice.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc
