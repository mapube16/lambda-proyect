"""
learning.py — Continuous Learning Loop (Phase 11).

Every HITL decision teaches the system:
  - Approved leads → embedded + stored in `ideal_leads` corpus
  - Rejected leads → stored in `rejected_leads` with reason

After 3+ campaigns the system can:
  - Surface top-3 recurring patterns in approved leads ("tu cliente ideal")
  - Compute semantic similarity for new companies vs the ideal corpus
  - Give a +15 score bonus to companies above 0.75 cosine similarity
"""

import logging
import json
import os

logger = logging.getLogger("learning")


# ── Store approved lead embedding ──────────────────────────────────────────────

async def embed_and_store_approved_lead(
    user_id: str,
    lead_id: str,
    lead_data: dict,
) -> None:
    """
    Build a rich text representation of an approved lead, embed it,
    and store in `ideal_leads` corpus.
    """
    from rag import embed_text
    from database import save_ideal_lead

    ejson = lead_data.get("expediente_json") or {}
    decisor = ejson.get("decisor") or {}
    dt = ejson.get("datos_tecnicos") or {}

    # Build a compact company profile for embedding
    profile_parts = [
        f"Empresa: {lead_data.get('company_name', '')}",
        f"URL: {lead_data.get('url', '')}",
        f"Score: {ejson.get('score', '')}",
        f"Perfil: {dt.get('perfil', '')}",
        f"Tech stack: {dt.get('tech_stack', '')}",
        f"Sector: {ejson.get('sector', '')}",
        f"Ciudad: {ejson.get('ciudad', '')}",
        f"Decisor cargo: {decisor.get('cargo', '')}",
    ]
    profile_text = " | ".join(p for p in profile_parts if p.split(': ')[1])

    try:
        embedding = await embed_text(profile_text)
        await save_ideal_lead(
            user_id=user_id,
            lead_id=lead_id,
            company_name=lead_data.get("company_name", ""),
            url=lead_data.get("url", ""),
            embedding=embedding,
            profile_text=profile_text,
            score=ejson.get("score"),
        )
        logger.info(f"[learning] Stored ideal lead {lead_id} for user {user_id}")
    except Exception as e:
        logger.warning(f"[learning] Could not embed approved lead {lead_id}: {e}")


# ── Store rejected lead ────────────────────────────────────────────────────────

async def store_rejected_lead(
    user_id: str,
    lead_id: str,
    lead_data: dict,
) -> None:
    """Store rejection data in `rejected_leads` for pattern learning."""
    from database import save_rejected_lead as _save

    ejson = lead_data.get("expediente_json") or {}
    reason = ejson.get("motivo_descalificacion") or ejson.get("motivo") or "unknown"

    try:
        await _save(
            user_id=user_id,
            lead_id=lead_id,
            company_name=lead_data.get("company_name", ""),
            url=lead_data.get("url", ""),
            reason=reason,
        )
    except Exception as e:
        logger.warning(f"[learning] Could not store rejected lead {lead_id}: {e}")


# ── Similarity scoring ─────────────────────────────────────────────────────────

async def get_similarity_to_ideal(user_id: str, company_text: str) -> float:
    """
    Embed company_text and compute max cosine similarity to ideal_leads corpus.
    Returns 0.0 if no ideal leads exist yet.
    """
    from rag import embed_text, cosine_similarity
    from database import get_ideal_leads

    ideal = await get_ideal_leads(user_id)
    if not ideal:
        return 0.0

    query_vec = await embed_text(company_text)
    sims = [
        cosine_similarity(query_vec, doc["embedding"])
        for doc in ideal
        if doc.get("embedding")
    ]
    return max(sims) if sims else 0.0


# ── Pattern detection ──────────────────────────────────────────────────────────

PATTERNS_SYSTEM = """Eres un analista de ventas B2B. Recibirás una lista de empresas que un cliente aprobó como buenos prospectos.

Tu tarea: identifica los 3 patrones más recurrentes que definen al "cliente ideal" de este vendedor.

Ejemplos de patrones:
- "Medianas empresas (50-200 empleados) del sector logístico en Bogotá"
- "Empresas con flota propia mencionada explícitamente en su web"
- "Director de Operaciones o Gerente General como decisor principal"

Responde ÚNICAMENTE en JSON con este formato exacto:
{"patterns": [{"description": "...", "confidence": "alta|media", "evidence_count": N}, ...]}

Incluye exactamente 3 patrones. Si hay pocos datos, estima con lo que tienes."""

async def detect_patterns(user_id: str, openai_api_key: str) -> list[dict]:
    """
    Analyze ideal_leads corpus and return top-3 recurring patterns.
    Returns empty list if fewer than 3 approved leads exist.
    """
    from database import get_ideal_leads
    from openai import AsyncOpenAI

    ideal = await get_ideal_leads(user_id)
    if len(ideal) < 3:
        return []

    # Format leads as context
    lines = []
    for lead in ideal[:30]:  # cap at 30 for context window
        lines.append(f"• {lead['company_name']} ({lead['url']}) — {lead.get('profile_text', '')}")
    context = "\n".join(lines)

    client = AsyncOpenAI(api_key=openai_api_key)
    try:
        response = await client.chat.completions.create(
            model="gpt-5.4-2026-03-05",
            messages=[
                {"role": "system", "content": PATTERNS_SYSTEM},
                {"role": "user", "content": f"Leads aprobados:\n{context}"},
            ],
            temperature=0.3,
            extra_body={"max_completion_tokens": 500},
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        data = json.loads(raw)
        return data.get("patterns", [])
    except Exception as e:
        logger.error(f"[learning] Pattern detection failed: {e}")
        return []
