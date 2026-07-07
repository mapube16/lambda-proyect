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


async def crear_alerta(
    db, user_id: str, debtor: dict, tipo: str, *,
    detalle: str = "", extra: Optional[dict] = None,
) -> dict:
    """
    Registra la alerta, resuelve el responsable por §11, y la envía por
    WhatsApp si el canal está habilitado. Nunca lanza — un fallo de
    notificación no puede tumbar una llamada en curso ni el sync.
    """
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

    if "whatsapp_responsable" in (alertas_cfg.get("canales") or []) and doc["responsable_telefono"]:
        try:
            from services.notifications import send_whatsapp_text
            await send_whatsapp_text(doc["responsable_telefono"], _formatear_mensaje(tipo, doc))
        except Exception:
            logger.exception("[alerts] envío WhatsApp falló (no fatal) tipo=%s user=%s", tipo, user_id)

    logger.info(
        "[alerts] tipo=%s area=%s responsable=%s user=%s debtor=%s",
        tipo, doc["area"], doc["responsable"], user_id, doc["debtor_id"],
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
