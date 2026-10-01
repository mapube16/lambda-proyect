"""
wa_bridge.py — puente VOICE→WA (Fase 6, Contrato A del contrato de handoff:
lambda-proyect/.planning no vive aquí, la fuente de verdad es
landa-agent-service/.planning/contracts/lambda-handoff-contract.md).

Reemplaza el entregable #8 del contrato: cobranza/sub_agents/whatsapp_notifier.py
encolaba un job ARQ "send_whatsapp_job" que NINGÚN worker registra (confirmado
contra landa-agent-service) — cada mensaje al deudor por WhatsApp se perdía en
silencio. Ahora POST real a WA's /case/handoff, con retry-safe idempotencia
por case_id (WA lo deduplica; ver contrato).

case_id: "VOICE lo crea (UUID v4) al iniciar la llamada". En la práctica lo
generamos LAZY — la primera vez que de verdad hace falta un handoff (no antes,
para no gastar un id en llamadas que nunca hablan con WhatsApp) — y se
persiste en el deudor para reusarlo en handoffs futuros del mismo caso.
"""
import logging
import os
import uuid
from typing import Optional

logger = logging.getLogger("cobranza.wa_bridge")


async def _ensure_case_id(db, debtor: dict) -> str:
    """Reusa debtor.case_id si ya existe; si no, genera uno y lo persiste."""
    existing = debtor.get("case_id")
    if existing:
        return existing
    new_id = str(uuid.uuid4())
    await db.debtors.update_one({"_id": debtor["_id"]}, {"$set": {"case_id": new_id}})
    debtor["case_id"] = new_id
    return new_id


def _motivo_llamada(debtor: dict) -> str:
    """Por qué se llamó al deudor, para que ARIA en WhatsApp lo sepa (antes le
    llegaba vacío y sonaba plana). Sin montos: WA consulta el saldo en vivo."""
    partes = ["Llamada de cobranza de DPG Seguros por cuota pendiente"]
    if debtor.get("ramo_nombre"):
        partes.append(f"ramo {debtor['ramo_nombre']}")
    if debtor.get("objeto_asegurado"):
        partes.append(f"riesgo asegurado {debtor['objeto_asegurado']}")
    if debtor.get("dias_mora"):
        partes.append(f"{debtor['dias_mora']} dias de mora")
    if debtor.get("estado"):
        partes.append(f"resultado de gestion: {debtor['estado']}")
    return ", ".join(partes) + "."


async def handoff_to_wa(
    db, user_id: str, debtor: dict, *,
    message: str = "", initial_context: str = "", call_id: str = "",
) -> dict:
    """
    Contrato A: POST /case/handoff en WA. Cede (o abre) el caso del deudor al
    canal WhatsApp — con `message`, WA lo envía de inmediato al cliente
    (plantilla si la ventana de 24h está cerrada, libre si está abierta).

    Nunca lanza: un fallo de red/WA no puede tumbar una llamada en curso. Con
    LAMBDA_PROYECT_BASE_URL o el teléfono del deudor ausentes, se registra y
    se devuelve {"ok": False, ...} sin reintentar (el llamador decide).
    """
    base_url = os.getenv("LAMBDA_PROYECT_BASE_URL", "").rstrip("/")
    token = os.getenv("LAMBDA_PROYECT_INTERNAL_TOKEN", "")
    phone = str(debtor.get("telefono", "")).strip()

    if not phone:
        return {"ok": False, "error": "debtor sin teléfono"}
    if not base_url or not token:
        logger.warning(
            "[wa_bridge] LAMBDA_PROYECT_BASE_URL/INTERNAL_TOKEN no configurados — "
            "handoff a WA NO enviado (mensaje perdido): %s", message[:80],
        )
        return {"ok": False, "error": "puente WA no configurado", "sent": False}

    case_id = await _ensure_case_id(db, debtor)
    body = {
        # Sin documento WA no puede fijar la póliza llamada: pedía la cédula o
        # listaba TODAS las pólizas del cliente. Con documento + poliza_number
        # entra directo a ESTA póliza.
        "documento": str(debtor.get("cliente_documento") or "")[:20] or None,
        "cliente_nombre": str(debtor.get("nombre") or "")[:80] or None,
        "case_id": case_id,
        "debtor_id": str(debtor.get("_id", "")),
        "poliza_number": str(debtor.get("numero_poliza") or "")[:40] or "N/A",
        "call_id": call_id,
        "user_id": user_id,
        "phone": phone if phone.startswith("+") else f"+{phone}",
        "initial_context": (initial_context or _motivo_llamada(debtor))[:500],
        "message": message,
    }
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{base_url}/case/handoff",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            logger.info("[wa_bridge] handoff case=%s debtor=%s sent=%s", case_id, body["debtor_id"], data.get("sent"))
            return {"ok": True, "case_id": case_id, "sent": data.get("sent", False)}
    except Exception as exc:
        logger.error("[wa_bridge] handoff a WA falló case=%s: %s", case_id, exc)
        return {"ok": False, "case_id": case_id, "error": str(exc)[:200]}
