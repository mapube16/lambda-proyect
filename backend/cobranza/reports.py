"""
reports.py — reporte diario/semanal de la operación ARIA (informe §12).

El reporte diario se arma con datos 100% reales de este repo:
  - Cuantitativo (10 puntos, agregación directa de Mongo — sin LLM).
  - Cualitativo (2 secciones, sintetizadas por un modelo barato — OpenAI
    gpt-5.4-nano — a partir de transcripts/alertas reales del día; si no hay
    material real, NO se inventa nada, se devuelve "sin datos suficientes").

Una métrica del informe (comprobantes de pago recibidos) vive en el canal de
WhatsApp — landa-agent-service, otro repo — y NO es visible desde aquí. Se
reporta explícitamente como "no disponible en este canal" en vez de inventar
un número; el equipo la revisa en Chat Landa Tech como ya hace hoy.

Entrega: HTML renderizado en Python (tabla, sin dependencias de Node/React) +
envío por MailerSend (MAILERSEND_API_KEY, mismo cliente que ya usa mailer.py
para el resto de la plataforma). Sin MAILERSEND_API_KEY o sin destinatarios
configurados, el reporte se genera igual (queda en logs) pero no se envía —
no falla el job.
"""
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pytz

from cobranza.alerts import COLLECTION as ALERTS_COLLECTION

logger = logging.getLogger("cobranza.reports")

COLOMBIA_TZ = pytz.timezone("America/Bogota")

# El único hueco real del informe §12 que no podemos ver desde este repo.
_COMPROBANTES_NOTA = "No disponible en este canal — se revisa en Chat Landa Tech (WhatsApp)."


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _dia_utc_range(d: date, tz=COLOMBIA_TZ) -> tuple:
    """[inicio, fin) del día calendario `d` en la tz del tenant, en UTC."""
    start_local = tz.localize(datetime.combine(d, datetime.min.time()))
    end_local = start_local + timedelta(days=1)
    return start_local.astimezone(pytz.utc), end_local.astimezone(pytz.utc)


# ── Cuantitativo (agregación directa, sin LLM) ─────────────────────────────────

async def _contar_llamadas(db, user_id: str, start: datetime, end: datetime) -> dict:
    """
    Realizadas/contestadas/no-contestadas a partir de historial_llamadas
    (un push por llamada COMPLETADA — voice_router._process_call_ended).
    """
    pipeline = [
        {"$match": {"user_id": user_id, "historial_llamadas.fecha": {"$gte": start, "$lt": end}}},
        {"$unwind": "$historial_llamadas"},
        {"$match": {"historial_llamadas.fecha": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$historial_llamadas.resultado", "n": {"$sum": 1}}},
    ]
    por_resultado = {r["_id"]: r["n"] async for r in db.debtors.aggregate(pipeline)}
    realizadas = sum(por_resultado.values())
    no_contestadas = por_resultado.get("sin_contacto", 0)
    contestadas = realizadas - no_contestadas
    return {
        "realizadas": realizadas,
        "contestadas": contestadas,
        "no_contestadas": no_contestadas,
        "tasa_efectividad": round(contestadas / realizadas, 3) if realizadas else 0.0,
        "por_resultado": por_resultado,
    }


async def _contar_alertas(db, user_id: str, start: datetime, end: datetime) -> dict:
    """Cuenta por tipo + trae detalle de escalados (motivo) para el reporte."""
    q_base = {"user_id": user_id, "created_at": {"$gte": start, "$lt": end}}
    pipeline = [{"$match": q_base}, {"$group": {"_id": "$tipo", "n": {"$sum": 1}}}]
    por_tipo = {r["_id"]: r["n"] async for r in db[ALERTS_COLLECTION].aggregate(pipeline)}

    links = cupones = 0
    async for a in db[ALERTS_COLLECTION].find({**q_base, "tipo": "solicitud_link_cupon"}, {"extra": 1}):
        if (a.get("extra") or {}).get("tipo") == "cupon":
            cupones += 1
        else:
            links += 1

    escalados = []
    async for a in db[ALERTS_COLLECTION].find(
        {**q_base, "tipo": "consulta_fuera_alcance"}, {"debtor_nombre": 1, "detalle": 1}
    ):
        escalados.append({"nombre": a.get("debtor_nombre"), "motivo": a.get("detalle") or ""})

    return {
        "links_solicitados": links,
        "cupones_solicitados": cupones,
        "pago_reportado": por_tipo.get("pago_reportado", 0),
        "opt_outs": por_tipo.get("opt_out", 0),
        "oportunidades_comerciales": por_tipo.get("oportunidad_comercial", 0),
        "numero_equivocado": por_tipo.get("numero_equivocado", 0),
        "sin_contacto_agotado": por_tipo.get("sin_contacto_agotado", 0),
        "escalados": escalados,
    }


async def _contar_programadas(db, user_id: str, fecha: date) -> int:
    """Llamadas que el dispatcher decidió marcar hoy (cobranza_daily_stats)."""
    doc = await db.cobranza_daily_stats.find_one({"user_id": user_id, "fecha": fecha.isoformat()})
    return int((doc or {}).get("llamadas_iniciadas") or 0)


async def _contar_reagendamientos(db, user_id: str, start: datetime, end: datetime) -> int:
    return await db.debtors.count_documents({
        "user_id": user_id, "estado": "reagendado",
        "reagendado_solicitado_por": "cliente", "updated_at": {"$gte": start, "$lt": end},
    })


async def aggregate_metrics(db, user_id: str, start: datetime, end: datetime, fecha_ref: date) -> dict:
    """Los 10 puntos cuantitativos del informe §12 que sí podemos calcular aquí."""
    llamadas = await _contar_llamadas(db, user_id, start, end)
    alertas = await _contar_alertas(db, user_id, start, end)
    return {
        "llamadas_programadas": await _contar_programadas(db, user_id, fecha_ref),
        "llamadas_realizadas": llamadas["realizadas"],
        "llamadas_contestadas": llamadas["contestadas"],
        "llamadas_no_contestadas": llamadas["no_contestadas"],
        "tasa_efectividad": llamadas["tasa_efectividad"],
        "links_solicitados": alertas["links_solicitados"],
        "cupones_solicitados": alertas["cupones_solicitados"],
        "pago_reportado": alertas["pago_reportado"],
        "comprobantes_recibidos": None,  # ver _COMPROBANTES_NOTA
        "reagendamientos": await _contar_reagendamientos(db, user_id, start, end),
        "opt_outs": alertas["opt_outs"],
        "escalados": alertas["escalados"],
        "sin_contacto_agotado": alertas["sin_contacto_agotado"],
        "oportunidades_comerciales": alertas["oportunidades_comerciales"],
    }


# ── Cualitativo: síntesis por LLM barato (solo con material real) ─────────────

async def _muestras_del_dia(db, user_id: str, start: datetime, end: datetime, limit: int = 25) -> list:
    """Transcripts reales (truncados) + detalles de alertas del día — la materia
    prima para sintetizar 'principales consultas' y 'novedades'. Sin invención:
    si no hay nada, la lista vuelve vacía y no se llama al LLM."""
    muestras = []
    pipeline = [
        {"$match": {"user_id": user_id, "historial_llamadas.fecha": {"$gte": start, "$lt": end}}},
        {"$unwind": "$historial_llamadas"},
        {"$match": {"historial_llamadas.fecha": {"$gte": start, "$lt": end},
                    "historial_llamadas.transcript": {"$nin": [None, ""]}}},
        {"$limit": limit},
        {"$project": {"t": {"$substrCP": ["$historial_llamadas.transcript", 0, 400]}}},
    ]
    async for r in db.debtors.aggregate(pipeline):
        muestras.append(r["t"])
    async for a in db[ALERTS_COLLECTION].find(
        {"user_id": user_id, "created_at": {"$gte": start, "$lt": end}, "detalle": {"$nin": [None, ""]}},
        {"detalle": 1, "tipo": 1},
    ).limit(limit):
        muestras.append(f"[{a['tipo']}] {a['detalle']}")
    return muestras


async def synthesize_qualitative(muestras: list) -> dict:
    """
    2-5 bullets de 'principales consultas' + 'incidencias/novedades', vía el
    modelo más barato de OpenAI (gpt-5.4-nano). Sin OPENAI_API_KEY, sin
    muestras, o si el modelo falla: devuelve listas vacías — nunca inventa.
    """
    vacio = {"principales_consultas": [], "incidencias": []}
    if not muestras:
        return vacio
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return vacio

    model = os.getenv("REPORTES_LLM_MODEL", "gpt-5.4-nano")
    prompt = (
        "Eres un analista de cobranza. A partir de estos fragmentos REALES de "
        "llamadas y alertas de hoy, identifica patrones — NO inventes nada que "
        "no esté sugerido por el texto. Responde SOLO un JSON con esta forma: "
        '{"principales_consultas": ["..."], "incidencias": ["..."]}. '
        "Máximo 5 items por lista, cada uno una frase corta. Si no hay patrones "
        "claros en una categoría, deja la lista vacía.\n\nFragmentos:\n"
        + "\n---\n".join(muestras)
    )
    try:
        import httpx
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"},
                    "max_completion_tokens": 500,
                },
            )
            r.raise_for_status()
            import json
            out = json.loads(r.json()["choices"][0]["message"]["content"])
            return {
                "principales_consultas": list(out.get("principales_consultas") or [])[:5],
                "incidencias": list(out.get("incidencias") or [])[:5],
            }
    except Exception:
        logger.exception("[reports] síntesis LLM falló (no fatal) — sección queda vacía")
        return vacio


# ── Render HTML (sin dependencias de Node) ─────────────────────────────────────

def _fmt_pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def render_daily_html(metrics: dict, qualitative: dict, fecha: date, tenant_nombre: str = "DPG Seguros") -> str:
    filas = [
        ("Llamadas programadas", metrics["llamadas_programadas"]),
        ("Llamadas realizadas", metrics["llamadas_realizadas"]),
        ("Contestadas", metrics["llamadas_contestadas"]),
        ("No contestadas", metrics["llamadas_no_contestadas"]),
        ("Tasa de efectividad", _fmt_pct(metrics["tasa_efectividad"])),
        ("Solicitaron link de pago", metrics["links_solicitados"]),
        ("Solicitaron cupón de pago", metrics["cupones_solicitados"]),
        ("Informaron que ya pagaron", metrics["pago_reportado"]),
        ("Comprobantes recibidos", _COMPROBANTES_NOTA),
        ("Pidieron ser recontactados después", metrics["reagendamientos"]),
        ("No desean más llamadas", metrics["opt_outs"]),
        ("Casos escalados", len(metrics["escalados"])),
        ("Agotaron intentos sin contacto", metrics["sin_contacto_agotado"]),
        ("Oportunidades comerciales detectadas", metrics["oportunidades_comerciales"]),
    ]
    filas_html = "".join(
        f'<tr><td style="padding:8px 12px;border-bottom:1px solid #E7E6E2;color:#4B5563">{k}</td>'
        f'<td style="padding:8px 12px;border-bottom:1px solid #E7E6E2;font-weight:700;color:#16161D;text-align:right">{v}</td></tr>'
        for k, v in filas
    )
    escalados_html = "".join(
        f'<li style="margin-bottom:4px"><b>{e["nombre"] or "N/D"}</b>: {e["motivo"] or "sin detalle"}</li>'
        for e in metrics["escalados"]
    ) or "<li>Ninguno hoy.</li>"
    consultas_html = "".join(f"<li>{c}</li>" for c in qualitative["principales_consultas"]) \
        or "<li>Sin datos suficientes para identificar patrones hoy.</li>"
    incidencias_html = "".join(f"<li>{c}</li>" for c in qualitative["incidencias"]) \
        or "<li>Sin incidencias reportadas hoy.</li>"

    return f"""<!DOCTYPE html><html><body style="margin:0;background:#F6F6FB;font-family:-apple-system,Segoe UI,Roboto,sans-serif">
<div style="max-width:640px;margin:0 auto;padding:24px 16px">
  <div style="background:#234876;border-radius:12px 12px 0 0;padding:20px 24px">
    <div style="color:#AEC2DA;font-size:11px;font-weight:700;letter-spacing:.1em;text-transform:uppercase">Reporte diario · ARIA</div>
    <div style="color:#fff;font-size:20px;font-weight:800;margin-top:4px">{tenant_nombre} — {fecha.strftime('%d de %B de %Y')}</div>
  </div>
  <div style="background:#fff;border:1px solid #E7E6E2;border-top:none;border-radius:0 0 12px 12px;padding:20px 24px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">{filas_html}</table>

    <h3 style="color:#234876;font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:22px 0 8px">Casos escalados y motivo</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#374151">{escalados_html}</ul>

    <h3 style="color:#234876;font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:22px 0 8px">Principales consultas de los clientes</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#374151">{consultas_html}</ul>

    <h3 style="color:#234876;font-size:13px;text-transform:uppercase;letter-spacing:.06em;margin:22px 0 8px">Incidencias / novedades de la operación</h3>
    <ul style="margin:0;padding-left:18px;font-size:13px;color:#374151">{incidencias_html}</ul>

    <p style="margin-top:24px;font-size:11px;color:#9CA3AF">Generado automáticamente por ARIA (Landa Tech) — {_utcnow().astimezone(COLOMBIA_TZ).strftime('%Y-%m-%d %H:%M')} hora Colombia.</p>
  </div>
</div>
</body></html>"""


# ── Envío (MailerSend — mismo proveedor/cliente que mailer.py, el resto de la
# plataforma ya lo usa; Resend nunca tuvo una key configurada en ningún lado) ──

async def send_via_resend(to: list, subject: str, html: str) -> dict:
    """Nombre histórico (Resend); envía por MailerSend, ver comentario arriba."""
    import asyncio
    api_key = os.getenv("MAILERSEND_API_KEY")
    from_addr = os.getenv("MAILERSEND_FROM_EMAIL", "noreply@isomorph.co")
    if not api_key or not to:
        logger.warning("[reports] sin MAILERSEND_API_KEY o destinatarios — reporte generado pero NO enviado")
        return {"ok": False, "sent": False, "reason": "sin_key_o_destinatarios"}
    from mailer import _send as _mailersend_send
    enviados, fallidos = [], []
    for to_email in to:
        try:
            # _send es síncrono (llamada bloqueante al SDK de MailerSend) — se
            # corre en un thread para no congelar el event loop. Por destinatario:
            # un fallo (ej. límite de cuenta trial) no debe tumbar a los demás.
            await asyncio.to_thread(
                _mailersend_send, from_addr, "ARIA — Landa Tech", to_email, "", subject, html,
            )
            enviados.append(to_email)
        except Exception as exc:
            logger.exception("[reports] envío por MailerSend falló para %s", to_email)
            fallidos.append({"to": to_email, "error": str(exc)[:200]})
    return {"ok": bool(enviados), "sent": bool(enviados), "enviados": enviados, "fallidos": fallidos}


# ── Orquestación ────────────────────────────────────────────────────────────────

async def run_daily_report(db, user_id: str, fecha: Optional[date] = None) -> dict:
    """Genera + envía el reporte diario (informe §12: 1:00pm hora Colombia)."""
    fecha = fecha or datetime.now(COLOMBIA_TZ).date()
    start, end = _dia_utc_range(fecha)

    from cobranza.config_cache import get_tenant_config
    cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
    reportes_cfg = cfg.get("reportes") or {}
    destinatarios = reportes_cfg.get("destinatarios") or []
    tenant_nombre = reportes_cfg.get("nombre_empresa") or "la operación"

    metrics = await aggregate_metrics(db, user_id, start, end, fecha)
    muestras = await _muestras_del_dia(db, user_id, start, end)
    qualitative = await synthesize_qualitative(muestras)
    html = render_daily_html(metrics, qualitative, fecha, tenant_nombre)

    envio = await send_via_resend(
        destinatarios, f"Reporte diario de cobranza — {fecha.strftime('%d/%m/%Y')}", html,
    )
    logger.info("[reports] diario user=%s fecha=%s enviado=%s", user_id, fecha.isoformat(), envio.get("sent"))
    return {"metrics": metrics, "qualitative": qualitative, "envio": envio, "fecha": fecha.isoformat()}


async def run_weekly_report(db, user_id: str, semana_fin: Optional[date] = None) -> dict:
    """Reporte semanal (informe §12): mismo cálculo, ventana de 7 días + franja
    de mayor tasa de contacto (informe: 'horarios con mayor tasa de contacto')."""
    semana_fin = semana_fin or datetime.now(COLOMBIA_TZ).date()
    semana_inicio = semana_fin - timedelta(days=6)
    start, _ = _dia_utc_range(semana_inicio)
    _, end = _dia_utc_range(semana_fin)

    from cobranza.config_cache import get_tenant_config
    cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
    reportes_cfg = cfg.get("reportes") or {}
    destinatarios = reportes_cfg.get("destinatarios") or []
    tenant_nombre = reportes_cfg.get("nombre_empresa") or "la operación"

    metrics = await aggregate_metrics(db, user_id, start, end, semana_fin)
    mejor_franja = await _mejor_franja_contacto(db, user_id, start, end)
    muestras = await _muestras_del_dia(db, user_id, start, end, limit=60)
    qualitative = await synthesize_qualitative(muestras)

    html = render_daily_html(metrics, qualitative, semana_fin, tenant_nombre).replace(
        "Reporte diario · ARIA", "Reporte semanal · ARIA",
    )
    if mejor_franja:
        html = html.replace(
            "</table>",
            f"</table><p style='margin-top:14px;font-size:12px;color:#4B5563'>"
            f"<b>Franja con mayor tasa de contacto:</b> {mejor_franja}</p>",
        )

    envio = await send_via_resend(
        destinatarios,
        f"Reporte semanal de cobranza — {semana_inicio.strftime('%d/%m')} al {semana_fin.strftime('%d/%m/%Y')}",
        html,
    )
    logger.info("[reports] semanal user=%s hasta=%s enviado=%s", user_id, semana_fin.isoformat(), envio.get("sent"))
    return {"metrics": metrics, "qualitative": qualitative, "mejor_franja": mejor_franja, "envio": envio}


async def _mejor_franja_contacto(db, user_id: str, start: datetime, end: datetime) -> Optional[str]:
    """Hora del día (0-23, en tz del tenant) con mejor tasa contestada/realizada."""
    pipeline = [
        {"$match": {"user_id": user_id, "historial_llamadas.fecha": {"$gte": start, "$lt": end}}},
        {"$unwind": "$historial_llamadas"},
        {"$match": {"historial_llamadas.fecha": {"$gte": start, "$lt": end}}},
        {"$project": {
            "hora": {"$hour": {"date": "$historial_llamadas.fecha", "timezone": "America/Bogota"}},
            "contactado": {"$cond": [{"$ne": ["$historial_llamadas.resultado", "sin_contacto"]}, 1, 0]},
        }},
        {"$group": {"_id": "$hora", "total": {"$sum": 1}, "contactados": {"$sum": "$contactado"}}},
    ]
    mejor, mejor_tasa = None, -1.0
    async for r in db.debtors.aggregate(pipeline):
        if r["total"] < 3:  # evita que 1 llamada aislada gane por ruido
            continue
        tasa = r["contactados"] / r["total"]
        if tasa > mejor_tasa:
            mejor, mejor_tasa = r["_id"], tasa
    if mejor is None:
        return None
    return f"{mejor:02d}:00–{(mejor + 1) % 24:02d}:00 ({_fmt_pct(mejor_tasa)} de contacto)"
