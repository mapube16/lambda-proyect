"""
entidad_estatal.py — exclusión de entidades estatales de la campaña (informe §2).

"Entidades estatales (hospitales, municipios y demás entidades públicas): no se
gestionan por el bot." Su gestión la hace personal humano, así que el deudor
queda VISIBLE en el dashboard pero el bot nunca lo marca.

Clasificación en 2 capas, cacheada por deudor (se clasifica UNA vez):

  1. REGEX (gratis, determinista): patrones inequívocos de entidad pública
     colombiana (MUNICIPIO, ALCALDÍA, E.S.E., HOSPITAL, PERSONERÍA…).
  2. LLM juez (modelo barato): solo los nombres que el regex no resolvió, en
     lotes. Va por OPENROUTER (mismo gateway que usa landa-agent-service —
     modelo cambiable por env sin deploy) con fallback a Gemini directo
     (GOOGLE_API_KEY, que ya existe en el Railway de voz). Sin ninguna key
     los ambiguos quedan sin clasificar y se reintentan en el siguiente sync.

Resultado en el deudor:
  tipo_entidad: "estatal" | "privada"
  no_llamar: True  + no_llamar_motivo: "entidad_estatal"   (solo estatales)
  clasificado_por: "regex" | "llm" | "manual"

El colaborador puede corregir un falso positivo desde la UI (PATCH no_llamar),
y esa corrección manual NUNCA se re-clasifica (clasificado_por="manual" se salta).
"""
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("cobranza.entidad_estatal")

# Modelo juez barato para la capa 2 — configurable sin deploy. Formato
# OpenRouter (proveedor/modelo); para el fallback Gemini directo se usa lo
# que va después del "/".
LLM_MODEL = os.getenv("ENTIDAD_CLASSIFIER_MODEL", "google/gemini-2.5-flash-lite")
LLM_BATCH = 40

# ── Capa 1: regex de alta precisión (sobre nombre normalizado sin acentos) ─────
# Solo patrones que en Colombia son inequívocamente sector público. Lo dudoso
# (fundaciones, iglesias, JAC, bomberos voluntarios, institutos privados…) se
# deja a la capa LLM — acá preferimos precisión sobre cobertura.
_PATRONES_ESTATAL = [
    r"\bMUNICIPIO\b", r"\bALCALDIA\b", r"\bGOBERNACION\b", r"\bDISTRITO\s",
    r"\bCONCEJO (MUNICIPAL|DE)\b", r"\bASAMBLEA DEPARTAMENTAL\b",
    r"\bPERSONERIA\b", r"\bCONTRALORIA\b", r"\bPROCURADURIA\b",
    r"\bDEFENSORIA DEL PUEBLO\b", r"\bFISCALIA\b", r"\bREGISTRADURIA\b",
    r"\bE\.?\s?S\.?\s?E\b", r"\bEMPRESA SOCIAL DEL ESTADO\b",
    r"\bHOSPITAL\b", r"\bCENTRO DE SALUD\b", r"\bPUESTO DE SALUD\b",
    r"\bSECRETARIA DE\b", r"\bMINISTERIO\b", r"\bSUPERINTENDENCIA\b",
    r"\bUNIDAD ADMINISTRATIVA\b", r"\bCORPORACION AUTONOMA\b",
    r"\bPOLICIA NACIONAL\b", r"\bEJERCITO NACIONAL\b", r"\bARMADA NACIONAL\b",
    r"\bFUERZA AEREA\b", r"\bINPEC\b", r"\bSENA\b", r"\bICBF\b",
    r"\bUNIVERSIDAD (NACIONAL|DEL? [A-Z]+|DISTRITAL|DEPARTAMENTAL)\b",
    r"\bINSTITUTO (NACIONAL|DEPARTAMENTAL|MUNICIPAL|DISTRITAL|COLOMBIANO)\b",
    r"\bEMPRESAS PUBLICAS\b", r"\bLOTERIA DE\b", r"\bCUERPO OFICIAL DE BOMBEROS\b",
]
_RE_ESTATAL = re.compile("|".join(_PATRONES_ESTATAL))


def _normalizar(nombre: str) -> str:
    s = unicodedata.normalize("NFD", str(nombre or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    return s.upper().strip()


def clasificar_regex(nombre: str) -> Optional[str]:
    """'estatal' si un patrón inequívoco matchea; None = ambiguo (va al LLM)."""
    if not nombre:
        return None
    return "estatal" if _RE_ESTATAL.search(_normalizar(nombre)) else None


# ── Capa 2: Gemini Flash para los ambiguos (batch, JSON estricto) ──────────────

def _prompt(nombres: list) -> str:
    return (
        "Eres un clasificador de razones sociales colombianas. Para CADA nombre "
        "responde si es una ENTIDAD ESTATAL/PÚBLICA colombiana (municipio, alcaldía, "
        "gobernación, hospital público/E.S.E., ministerio, entidad descentralizada, "
        "fuerza pública, universidad pública, empresa industrial y comercial del "
        "Estado, empresa de servicios públicos oficial, etc.). Empresas privadas, "
        "SAS, personas naturales, iglesias, fundaciones privadas, colegios privados "
        "y copropiedades NO son estatales. Si un nombre es GENUINAMENTE ambiguo, "
        "responde true (es más seguro no llamar a una entidad pública; un humano "
        "lo revisa después).\n\n"
        "Responde ÚNICAMENTE un array JSON de booleanos, uno por nombre, en el "
        "mismo orden, sin texto adicional.\n\nNombres:\n"
        + "\n".join(f"{i+1}. {n}" for i, n in enumerate(nombres))
    )


def _parse_bools(text: str, n: int) -> Optional[list]:
    """Array JSON de n booleanos; tolera fences ```json ...```."""
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-z]*\s*|\s*```$", "", t, flags=re.I).strip()
    try:
        out = json.loads(t)
    except json.JSONDecodeError:
        return None
    if isinstance(out, list) and len(out) == n:
        return [bool(v) for v in out]
    return None


async def clasificar_lote_llm(nombres: list) -> Optional[list]:
    """
    Clasifica un lote de nombres → lista de bool (True = entidad estatal).
    OpenRouter primero (OPENROUTER_API_KEY); fallback Gemini directo
    (GOOGLE_API_KEY). Devuelve None sin key o si el request falla (los
    deudores quedan sin clasificar y se reintentan en el siguiente sync).
    """
    if not nombres:
        return None
    import httpx

    prompt = _prompt(nombres)

    # ── Vía 1: OpenRouter (mismo gateway que landa-agent-service) ──────────────
    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {or_key}"},
                    json={
                        "model": LLM_MODEL,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0,
                    },
                )
                r.raise_for_status()
                out = _parse_bools(r.json()["choices"][0]["message"]["content"], len(nombres))
                if out is not None:
                    return out
                logger.warning("[estatal] OpenRouter devolvió JSON inválido — probando fallback")
        except Exception as exc:  # noqa: BLE001 — clasificar no puede tumbar el sync
            logger.warning("[estatal] OpenRouter failed: %s — probando fallback Gemini", exc)

    # ── Vía 2: Gemini directo (key ya presente en el Railway de voz) ───────────
    g_key = os.getenv("GOOGLE_API_KEY")
    if not g_key:
        return None
    gemini_model = LLM_MODEL.split("/", 1)[-1]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/{gemini_model}"
                f":generateContent?key={g_key}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "responseMimeType": "application/json",
                        "responseSchema": {"type": "ARRAY", "items": {"type": "BOOLEAN"}},
                        "temperature": 0,
                    },
                },
            )
            r.raise_for_status()
            return _parse_bools(
                r.json()["candidates"][0]["content"]["parts"][0]["text"], len(nombres)
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[estatal] Gemini fallback failed: %s", exc)
        return None


# ── Orquestación: clasifica lo pendiente y marca no_llamar ─────────────────────

async def run_clasificacion(db, user_id: str) -> dict:
    """
    Clasifica los deudores activos SIN tipo_entidad (idempotente, incremental).
    Nunca toca clasificaciones manuales. Devuelve conteos.
    """
    cursor = db.debtors.find(
        {
            "user_id": user_id,
            "is_active": {"$ne": False},
            "tipo_entidad": None,  # missing o null — manual/previos se saltan
        },
        {"nombre": 1},
    )
    pendientes = await cursor.to_list(length=None)
    if not pendientes:
        return {"clasificados": 0, "estatales": 0, "pendientes_llm": 0}

    now = datetime.now(timezone.utc)
    estatales = clasificados = 0
    ambiguos: list = []

    async def _marcar(doc_id, tipo: str, por: str):
        nonlocal estatales, clasificados
        update = {"tipo_entidad": tipo, "clasificado_por": por, "clasificado_at": now}
        if tipo == "estatal":
            update["no_llamar"] = True
            update["no_llamar_motivo"] = "entidad_estatal"
            estatales += 1
        await db.debtors.update_one({"_id": doc_id}, {"$set": update})
        clasificados += 1

    # Capa 1 — regex
    for d in pendientes:
        if clasificar_regex(d.get("nombre", "")) == "estatal":
            await _marcar(d["_id"], "estatal", "regex")
        else:
            ambiguos.append(d)

    # Capa 2 — LLM en lotes (solo si hay key; si no, quedan para el próximo sync)
    sin_clasificar = 0
    for i in range(0, len(ambiguos), LLM_BATCH):
        lote = ambiguos[i:i + LLM_BATCH]
        veredictos = await clasificar_lote_llm([d.get("nombre", "") for d in lote])
        if veredictos is None:
            sin_clasificar += len(ambiguos) - i
            break
        for d, es_estatal in zip(lote, veredictos):
            await _marcar(d["_id"], "estatal" if es_estatal else "privada", "llm")

    logger.info(
        "[estatal] user=%s clasificados=%d estatales=%d pendientes_llm=%d",
        user_id, clasificados, estatales, sin_clasificar,
    )
    return {"clasificados": clasificados, "estatales": estatales, "pendientes_llm": sin_clasificar}
