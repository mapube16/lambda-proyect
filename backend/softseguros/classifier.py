"""
softseguros/classifier.py — Pure classification for SOFTSEGUROS póliza records.

No I/O. No DB. No HTTP. Given a póliza's cartera state, fecha_fin/fecha_limite_pago,
and a reference "today", returns one of four canonical buckets used by the local
debtors model.

Buckets:
    - "pagado"             → estado_cartera in {"Pagada","Comisionada"} OR recaudado=True
    - "ya_vencidos"        → cobrable AND fecha_referencia < today
    - "proximos_a_vencer"  → cobrable AND today <= fecha_referencia <= today+30
    - "futuro"             → cobrable AND fecha_referencia > today+30 (NOT synced in v1)

"cobrable" = estado_cartera in {"Pendiente por pagar","Sin pagos Asignados"} and not paid.
fecha_referencia = fecha_limite_pago if not None else fecha_fin.

A póliza that is paid OR has no usable fecha_referencia is "pagado" or excluded
(caller decides — classify returns "pagado" for paid, "futuro" as a safe default
when fecha_referencia is missing on an otherwise-cobrable póliza, so it is not
shown as an active debtor without a due date).
"""
from datetime import date, datetime, timedelta
from typing import Optional, Union

DateLike = Union[date, datetime, str]

_PAID_CARTERA = {"pagada", "comisionada"}
_COBRABLE_CARTERA = {"pendiente por pagar", "sin pagos asignados"}


def _to_date(value: Optional[DateLike]) -> Optional[date]:
    """Normalize datetime/ISO-string → date; accept date as-is; None passes through."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        # Accept "YYYY-MM-DD" or full ISO datetime
        s = value.strip()
        if not s:
            return None
        try:
            return date.fromisoformat(s[:10])
        except ValueError:
            return None
    raise TypeError(f"classify_poliza expected date/datetime/str/None, got {type(value).__name__}")


def classify_poliza(
    estado_cartera: Optional[str],
    fecha_fin: Optional[DateLike],
    fecha_limite_pago: Optional[DateLike],
    recaudado: bool,
    today: DateLike,
) -> str:
    """
    Classify a SOFTSEGUROS póliza into:
    "pagado" | "ya_vencidos" | "proximos_a_vencer" | "futuro".

    Pure function — no side effects.
    """
    ec = (estado_cartera or "").strip().lower()
    if recaudado or ec in _PAID_CARTERA:
        return "pagado"

    td = _to_date(today)
    fref = _to_date(fecha_limite_pago) or _to_date(fecha_fin)
    if fref is None:
        # Cobrable but no due date — keep out of active "vencido"/"por vencer" buckets.
        return "futuro"

    if fref < td:
        return "ya_vencidos"
    if fref <= td + timedelta(days=30):
        return "proximos_a_vencer"
    return "futuro"


def classify_cuota(
    fecha_pago: Optional[DateLike],
    recaudado: bool,
    today: DateLike,
    ventana_dias: int = 30,
) -> str:
    """
    Classify a SOFTSEGUROS cuota (installment) by its OWN due date `fecha_pago`.

    Returns "pagado" | "ya_vencidos" | "proximos_a_vencer" | "futuro".

    This is the cuota-level classifier for the real cartera endpoint
    (list_pagospolizas_filtro_paginados), where each row is one installment with
    its own `fecha_pago`. `ventana_dias` (the "próximos a vencer" horizon) is
    tenant-configurable (cobranza.softseguros_cartera.ventana_proximos_dias).
    Pure function — no side effects.
    """
    if recaudado:
        return "pagado"
    fref = _to_date(fecha_pago)
    if fref is None:
        return "futuro"
    td = _to_date(today)
    if fref < td:
        return "ya_vencidos"
    if fref <= td + timedelta(days=ventana_dias):
        return "proximos_a_vencer"
    return "futuro"


# Backwards-compat shim: earlier 18-03 partial work referenced classify_pagopoliza.
# The SOFTSEGUROS /api/pagopoliza/ endpoint turned out to be broken (504), so the
# real model is the póliza. Keep a thin alias so any straggler import doesn't break,
# but new code MUST use classify_poliza.
def classify_pagopoliza(fecha_pago: DateLike, comisionada: bool, today: DateLike) -> str:  # pragma: no cover
    if comisionada:
        return "pagado"
    return classify_poliza(
        estado_cartera="Pendiente por pagar",
        fecha_fin=fecha_pago,
        fecha_limite_pago=None,
        recaudado=False,
        today=today,
    )
