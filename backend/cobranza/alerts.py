"""
alerts.py — alertas tipadas al equipo DPG (informe §7) + routing por área (§11).

Cada alerta es un documento en db.cobranza_alertas: tipo, contexto del deudor,
área/responsable resuelto contra la tabla §11 (tenant_config.cobranza.alertas,
sembrada en scripts/seed_dpg_f0_config.py), y si "whatsapp_responsable" está en
los canales configurados, se envía DE INMEDIATO por WhatsApp al responsable.

Entrega REAL vía Twilio (services.notifications.send_whatsapp_text) — NO el
sub_agent cobranza/sub_agents/whatsapp_notifier.py, que es un stub muerto:
encola un job ARQ "send_whatsapp_job" que ningún worker registra (confirmado
contra el repo landa-agent-service). Toda la ruta de notify_payment_claim que
pasaba por ahí quedaba silenciosamente sin enviar nada.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger("cobranza.alerts")

COLLECTION = "cobranza_alertas"

# Los 9 tipos del informe §7 (más "sin_contacto_agotado" = 3 intentos sin
# respuesta, que el informe pide notificar a cartera para seguimiento manual,
# y "llamada_entrante_no_identificada" = §9.4, cliente devuelve la llamada
# pero no se pudo resolver un único deudor por su número).
TIPOS = (
    "asesor_humano", "consulta_fuera_alcance", "oportunidad_comercial",
    "pago_reportado", "solicitud_link_cupon", "opt_out",
    "numero_equivocado", "fecha_estimada_pago", "sin_contacto_agotado",
    "llamada_entrante_no_identificada",
)

_TITULOS = {
    "asesor_humano": "Solicita hablar con un asesor",
    "consulta_fuera_alcance": "Consulta fuera del alcance del bot",
    "oportunidad_comercial": "Interés / oportunidad comercial detectada",
    "pago_reportado": "Cliente reporta que ya pagó — validar comprobante",
    "solicitud_link_cupon": "Solicita link/cupón de pago",
    "opt_out": "No desea recibir más llamadas",
    "numero_equivocado": "El número no corresponde al cliente",
    "fecha_estimada_pago": "Informó una fecha estimada de pago",
    "sin_contacto_agotado": "Agotó los 3 intentos sin contacto",
    "llamada_entrante_no_identificada": "Llamada entrante sin identificar — seguimiento manual",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clasificar_area(texto: str, routing: list) -> Optional[dict]:
    """Primera área de la tabla §11 cuyas keywords aparecen en `texto` (case-insensitive)."""
    low = (texto or "").lower()
    for area in routing or []:
        for kw in area.get("keywords", []):
            if kw.lower() in low:
                return area
    return None


def _formatear_mensaje(tipo: str, doc: dict) -> str:
    linea = [
        f"🔔 {_TITULOS.get(tipo, tipo)}",
        f"Cliente: {doc.get('debtor_nombre') or 'N/D'}",
        f"Teléfono: {doc.get('debtor_telefono') or 'N/D'}",
        f"Póliza: {doc.get('numero_poliza') or 'N/D'}",
    ]
    if doc.get("detalle"):
        linea.append(f"Detalle: {doc['detalle']}")
    return "\n".join(linea)


def _alerta_email_html(tipo: str, doc: dict) -> str:
    def _esc(v):
        return (str(v) if v is not None else "N/D").replace("<", "&lt;").replace(">", "&gt;")
    rows = [
        ("Tipo", _TITULOS.get(tipo, tipo)),
        ("Cliente", doc.get("debtor_nombre")),
        ("Teléfono", doc.get("debtor_telefono")),
        ("Póliza", doc.get("numero_poliza")),
        ("Área", doc.get("area")),
        ("Responsable", doc.get("responsable")),
        ("Detalle", doc.get("detalle")),
    ]
    trs = "".join(
        f'<tr><td style="padding:6px 14px 6px 0;color:#667;font-size:13px;white-space:nowrap">{_esc(k)}</td>'
        f'<td style="padding:6px 0;color:#1a1a1a;font-size:13px"><b>{_esc(v)}</b></td></tr>'
        for k, v in rows if v
    )
    return f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;border:1px solid #e3e3ea;border-radius:12px;overflow:hidden">
  <div style="background:#1a7f6e;color:#fff;padding:16px 22px;font-size:16px;font-weight:bold">
    🔔 Alerta de cobranza — ARIA
  </div>
  <div style="padding:20px 22px">
    <table style="border-collapse:collapse;width:100%">{trs}</table>
    <p style="margin:18px 0 0;color:#889;font-size:12px">
      Notificación automática del agente de cobranza. Gestiona esta alerta desde el dashboard de Landa Tech.
    </p>
  </div>
</div>
"""


# Referencias fuertes a las tareas de notificación fire-and-forget — sin esto
# el GC puede matar un create_task a mitad de envío.
_notify_tasks: set = set()


async def _notificar_alerta(tipo: str, doc: dict, alertas_cfg: dict, user_id: str) -> None:
    """Envía la alerta ya insertada por WhatsApp/email. Corre en background —
    nunca lanza, nunca bloquea la llamada en curso."""
    if "whatsapp_responsable" in (alertas_cfg.get("canales") or []) and doc.get("responsable_telefono"):
        try:
            from services.notifications import send_whatsapp_text
            await send_whatsapp_text(doc["responsable_telefono"], _formatear_mensaje(tipo, doc))
        except Exception:
            logger.exception("[alerts] envío WhatsApp falló (no fatal) tipo=%s user=%s", tipo, user_id)

    # Canal EMAIL (SMTP Private Email) — canal principal de alertas mientras no
    # haya WhatsApp oficial aprobado. Destinatarios: alertas.email_to del tenant
    # o, si no, la var ALERTAS_EMAIL_TO (coma-separada). Nunca fatal.
    import os as _os
    email_to = alertas_cfg.get("email_to") or _os.getenv("ALERTAS_EMAIL_TO", "")
    if isinstance(email_to, str):
        email_to = [e.strip() for e in email_to.split(",") if e.strip()]
    if email_to:
        import asyncio as _asyncio
        from mailer import send_smtp
        # 3 intentos con backoff: con 20 llamadas/min la ráfaga de alertas hace
        # que Private Email a veces no responda (TimeoutError observado) — un
        # reintento a los 20/60s casi siempre pasa. Corre en background, no
        # afecta la llamada.
        for _intento, _espera in ((1, 0), (2, 20), (3, 60)):
            if _espera:
                await _asyncio.sleep(_espera)
            try:
                await _asyncio.to_thread(
                    send_smtp, email_to,
                    f"[ARIA] {_TITULOS.get(tipo, tipo)} — {doc.get('debtor_nombre') or 'deudor'}",
                    _alerta_email_html(tipo, doc),
                )
                break
            except Exception:
                if _intento == 3:
                    logger.exception("[alerts] envío EMAIL falló 3/3 (no fatal) tipo=%s user=%s", tipo, user_id)
                else:
                    logger.warning("[alerts] envío EMAIL falló (intento %d/3, reintenta) tipo=%s", _intento, tipo)


# Tipos que NO mandan correo en el momento (no spamear): se registran (dashboard)
# y se consolidan en el informe de fin de jornada. Doc DPG 21-jul: "los correos
# solo serán para link/cupón, escalación a humano, o 'ya pagué'". Todo lo demás
# va al consolidado. Se listan en run_fin_jornada_report.
# NOTIFICAN por correo (NO están aquí): solicitud_link_cupon,
# consulta_fuera_alcance + asesor_humano (escalar), pago_reportado.
TIPOS_SOLO_INFORME = {
    "sin_contacto_agotado", "numero_equivocado", "oportunidad_comercial",
    "fecha_estimada_pago", "opt_out", "llamada_entrante_no_identificada",
}


async def crear_alerta(
    db, user_id: str, debtor: dict, tipo: str, *,
    detalle: str = "", extra: Optional[dict] = None, notificar: Optional[bool] = None,
) -> dict:
    """
    Registra la alerta, resuelve el responsable por §11, y la envía por
    email/WhatsApp si el canal está habilitado. Nunca lanza — un fallo de
    notificación no puede tumbar una llamada en curso ni el sync.

    `notificar`: si es False no se manda correo/WhatsApp (la alerta igual se
    inserta y sale en el dashboard + informe de fin de jornada). Por defecto,
    los tipos en TIPOS_SOLO_INFORME no notifican (evita spam).
    """
    if notificar is None:
        notificar = tipo not in TIPOS_SOLO_INFORME
    if tipo not in TIPOS:
        raise ValueError(f"tipo de alerta desconocido: {tipo!r}")

    from cobranza.config_cache import get_tenant_config
    cfg = ((await get_tenant_config(user_id)) or {}).get("cobranza") or {}
    alertas_cfg = cfg.get("alertas") or {}
    routing = alertas_cfg.get("routing") or []
    fallback_key = alertas_cfg.get("fallback_responsable")

    area = _clasificar_area(detalle, routing) if detalle else None
    if area is None:
        area = next((a for a in routing if a.get("area") == fallback_key), None)

    doc = {
        "user_id": user_id,
        "debtor_id": str(debtor.get("_id", "")),
        "debtor_nombre": debtor.get("nombre"),
        "debtor_telefono": debtor.get("telefono"),
        "numero_poliza": debtor.get("numero_poliza"),
        "tipo": tipo,
        "detalle": detalle,
        "extra": extra or {},
        "area": (area or {}).get("area"),
        "responsable": (area or {}).get("responsable"),
        "responsable_telefono": (area or {}).get("telefono"),
        "atendida": False,
        "atendida_at": None,
        "atendida_por": None,
        "created_at": _utcnow(),
    }
    try:
        result = await db[COLLECTION].insert_one(doc)
        doc["_id"] = str(result.inserted_id)
    except Exception:
        logger.exception("[alerts] insert failed tipo=%s user=%s", tipo, user_id)
        return doc

    # Notificaciones EN BACKGROUND (fire-and-forget). Antes se esperaban inline:
    # WhatsApp (bridge Baileys, throttle 5-9s) + SMTP (3-8s) sumaban >10s y
    # pipecat mataba la function call de la llamada en curso por timeout
    # (observado: solicitar_link_cupon "timed out after 10.0 seconds" en
    # CA8f9eb1 — ARIA nunca recibió el resultado). El insert ya está hecho; la
    # alerta existe. El envío no debe retrasar a ARIA.
    if notificar:
        import asyncio as _asyncio
        task = _asyncio.create_task(_notificar_alerta(tipo, doc, alertas_cfg, user_id))
        _notify_tasks.add(task)
        task.add_done_callback(_notify_tasks.discard)

    logger.info(
        "[alerts] tipo=%s area=%s responsable=%s notificar=%s user=%s debtor=%s",
        tipo, doc["area"], doc["responsable"], notificar, user_id, doc["debtor_id"],
    )
    return doc


async def listar_alertas(db, user_id: str, *, solo_pendientes: bool = False, limit: int = 200) -> list:
    query: dict = {"user_id": user_id}
    if solo_pendientes:
        query["atendida"] = False
    cursor = db[COLLECTION].find(query).sort("created_at", -1).limit(limit)
    out = []
    async for d in cursor:
        d["_id"] = str(d["_id"])
        out.append(d)
    return out


async def marcar_atendida(db, user_id: str, alerta_id: str, *, actor: str = "") -> bool:
    from bson import ObjectId
    try:
        oid = ObjectId(alerta_id)
    except Exception:
        return False
    result = await db[COLLECTION].update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": {"atendida": True, "atendida_at": _utcnow(), "atendida_por": actor}},
    )
    return result.matched_count > 0
