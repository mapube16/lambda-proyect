"""
test_reports_wa_metrics.py — métricas del canal WhatsApp en el reporte diario.

Lo que importa: el reporte NUNCA se cae si el WA service no responde
(fail-open) y muestra el número real cuando sí responde.
"""
from datetime import date

import pytest

from cobranza.reports import _fetch_wa_metrics, render_daily_html

FECHA = date(2026, 7, 29)

_BASE = {
    "llamadas_programadas": 700, "llamadas_realizadas": 141,
    "llamadas_contestadas": 60, "llamadas_no_contestadas": 81,
    "tasa_efectividad": 0.42, "links_solicitados": 3, "cupones_solicitados": 1,
    "pago_reportado": 2, "reagendamientos": 4, "opt_outs": 0, "escalados": [],
    "sin_contacto_agotado": 12, "oportunidades_comerciales": 1,
}
_QUAL = {"principales_consultas": [], "incidencias": []}

_WA = {
    "comprobantes_recibidos": 5, "escalaciones": 3, "respuestas_a_plantilla": 9,
    "handoffs_de_voz": 2, "pagos_aprobados": 1, "conv_sin_respuesta": 16,
    "conv_en_conversacion": 4, "conv_escaladas": 2, "conv_con_comprobante": 2,
    "conv_promesa_pago": 1, "conversaciones_total": 25,
    "tasa_respuesta_plantilla": 0.36,
}


@pytest.mark.asyncio
async def test_fetch_sin_config_devuelve_none(monkeypatch):
    """Sin BASE_URL/TOKEN no se intenta la llamada — no revienta."""
    monkeypatch.delenv("LAMBDA_PROYECT_BASE_URL", raising=False)
    monkeypatch.delenv("LAMBDA_PROYECT_INTERNAL_TOKEN", raising=False)
    assert await _fetch_wa_metrics(FECHA) is None


@pytest.mark.asyncio
async def test_fetch_con_wa_caido_devuelve_none(monkeypatch):
    """Timeout/5xx del WA service → None (el reporte de voz sigue saliendo)."""
    monkeypatch.setenv("LAMBDA_PROYECT_BASE_URL", "http://127.0.0.1:1")  # puerto muerto
    monkeypatch.setenv("LAMBDA_PROYECT_INTERNAL_TOKEN", "x")
    assert await _fetch_wa_metrics(FECHA) is None


def test_render_con_metricas_wa_muestra_numero_real():
    m = dict(_BASE, wa=_WA, comprobantes_recibidos=_WA["comprobantes_recibidos"])
    html = render_daily_html(m, _QUAL, FECHA)
    assert "Canal WhatsApp" in html
    assert ">5<" in html                              # comprobantes reales
    assert "No disponible en este canal" not in html  # ya no aplica la nota


def test_render_sin_wa_cae_a_la_nota_y_omite_seccion():
    """WA caído: nota explícita en vez de un 0 engañoso, y sin tabla de ceros."""
    m = dict(_BASE, wa=None, comprobantes_recibidos=None)
    html = render_daily_html(m, _QUAL, FECHA)
    assert "No disponible en este canal" in html
    assert "Canal WhatsApp" not in html
