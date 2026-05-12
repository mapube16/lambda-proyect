"""
softseguros/classifier.py — Pure classification function for SOFTSEGUROS pagopoliza records.

No I/O. No DB. No HTTP. Given a fecha_pago, a comisionada flag, and a reference
"today", returns one of four canonical buckets used by the local debtors model.

Buckets:
    - "pagado"             → comisionada=True (cuota ya cobrada en SOFTSEGUROS)
    - "ya_vencidos"        → fecha_pago < today AND not comisionada
    - "proximos_a_vencer"  → today <= fecha_pago <= today+30 AND not comisionada
    - "futuro"             → fecha_pago > today+30 (NOT synced to local in v1)
"""
from datetime import date, datetime, timedelta
from typing import Union

DateLike = Union[date, datetime]


def _to_date(value: DateLike) -> date:
    """Normalize datetime→date; accept date as-is."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raise TypeError(f"classify_pagopoliza expected date or datetime, got {type(value).__name__}")


def classify_pagopoliza(
    fecha_pago: DateLike,
    comisionada: bool,
    today: DateLike,
) -> str:
    """
    Classify a pagopoliza record into one of:
    "pagado" | "ya_vencidos" | "proximos_a_vencer" | "futuro".

    Pure function — no side effects.
    """
    if comisionada:
        return "pagado"

    fp = _to_date(fecha_pago)
    td = _to_date(today)

    if fp < td:
        return "ya_vencidos"
    if fp <= td + timedelta(days=30):
        return "proximos_a_vencer"
    return "futuro"
