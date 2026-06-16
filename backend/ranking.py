"""
ranking.py — Intent-based ranking for signal leads.
"""
from __future__ import annotations

from datetime import datetime, timezone


def calculate_intent_score(lead: dict, compliance_score: float = 1.0) -> float:
    """Return score 0-100 based on signal metadata."""
    meta = lead.get("metadata", {}) or {}
    now = datetime.now(timezone.utc)

    new_hires = float(meta.get("new_hires") or 0)
    growth_rate = float(meta.get("growth_rate") or 0)
    funding_round = bool(meta.get("funding_round"))

    hiring_intensity = min(100, new_hires * 8)
    growth_score = min(100, (growth_rate / 0.5) * 100) if growth_rate else 0
    funding_score = 80 if funding_round else 0
    hiring_component = max(hiring_intensity, growth_score, funding_score)

    size_score = 0
    tam = str(meta.get("tamano_estimado") or "").lower()
    if tam == "micro":
        size_score = 10
    elif tam == "pequena":
        size_score = 40
    elif tam == "mediana":
        size_score = 80
    elif tam == "grande":
        size_score = 100

    fecha = lead.get("fecha_senal")
    if isinstance(fecha, str):
        try:
            fecha = datetime.fromisoformat(fecha)
        except Exception:
            fecha = None
    days_old = (now - fecha).days if fecha else 999
    recency_score = max(0, 20 - (days_old * 2))

    total = (
        hiring_component * 0.40
        + size_score * 0.25
        + recency_score * 1.0
    )
    total = total * float(compliance_score or 1.0)
    return float(min(100, total))
