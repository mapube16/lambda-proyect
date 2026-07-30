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
    # El _id puede venir como str (el dict del pipeline de voz viaja
    # serializado): sin coerción a ObjectId el update_one no matchea (no-op
    # silencioso), el case_id nunca se persistía y cada llamada fallida
    # generaba un case NUEVO → WA re-enviaba la plantilla en cada intento
    # (el dedupe por case_id quedaba anulado). Observado 29-jul en el smoke.
    _id = debtor["_id"]
    if isinstance(_id, str):
        try:
            from bson import ObjectId
            _id = ObjectId(_id)
        except Exception:
            pass  # ids no-ObjectId (tests): se intenta tal cual
    await db.debtors.update_one({"_id": _id}, {"$set": {"case_id": new_id}})
    debtor["case_id"] = new_id
    return new_id


async def handoff_no_answer(db, debtor: dict) -> dict:
    """
    D-19: llamada NO contestada → WA abre el caso y envía la plantilla Meta
    voice_no_answer_followup al deudor (re-abre el canal de WhatsApp).
    POST /case/handoff/no_answer. WA es idempotente por case_id: el mismo caso
    solo dispara la plantilla UNA vez aunque haya varios intentos fallidos.
    Nunca lanza — un fallo aquí no puede afectar el callback de Twilio.
    """
    base_url = os.getenv("LAMBDA_PROYECT_BASE_URL", "").rstrip("/")
    token = os.getenv("LAMBDA_PROYECT_INTERNAL_TOKEN", "")
    phone = str(debtor.get("telefono", "")).strip()

    if not phone:
        return {"ok": False, "error": "debtor sin teléfono"}
    if not base_url or not token:
        logger.warning("[wa_bridge] no-answer handoff NO configurado (BASE_URL/TOKEN) — plantilla no enviada")
        return {"ok": False, "error": "puente WA no configurado", "sent": False}

    case_id = await _ensure_case_id(db, debtor)
    body = {
        "case_id": case_id,
        "phone": phone if phone.startswith("+") else f"+{phone}",
        "cliente_nombre": str(debtor.get("nombre") or "Cliente")[:80] or "Cliente",
        "numero_poliza": str(debtor.get("numero_poliza") or "")[:40] or "N/A",
    }
    # Con documento, WA resuelve la póliza en SoftSeguros y siembra el hilo:
    # el cliente que responde a la plantilla entra DIRECTO a respuestas con
    # contexto (nombre + póliza de la llamada) sin que le pidan la cédula.
    # Sin documento, el saludo es genérico + pide identificación (decisión
    # DPG 29-jul: el bot ya debe saber de qué póliza era la llamada).
    documento = str(debtor.get("cliente_documento") or debtor.get("documento") or "").strip()
    if documento:
        body["documento"] = documento
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{base_url}/case/handoff/no_answer",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            r.raise_for_status()
            data = r.json()
            logger.info("[wa_bridge] no_answer handoff case=%s debtor=%s sent=%s",
                        case_id, debtor.get("_id"), data.get("sent"))
            return {"ok": True, "case_id": case_id, "sent": data.get("sent", False)}
    except Exception as exc:
        logger.error("[wa_bridge] no_answer handoff falló case=%s: %s", case_id, exc)
        return {"ok": False, "case_id": case_id, "error": str(exc)[:200]}


async def notify_link_cupon(db, debtor: dict, tipo: str = "link") -> dict:
    """
    El cliente pidió link/cupón en la llamada → WA le manda la confirmación
    escrita (plantilla solicitud_link_cupon). Antes solo se alertaba a cartera
    y el cliente se quedaba esperando sin nada por WhatsApp.

    Nunca lanza: la alerta a cartera ya salió y una llamada en curso no puede
    caerse porque WA falle.
    """
    base_url = os.getenv("LAMBDA_PROYECT_BASE_URL", "").rstrip("/")
    token = os.getenv("LAMBDA_PROYECT_INTERNAL_TOKEN", "")
    phone = str(debtor.get("telefono", "")).strip()

    if not phone:
        return {"ok": False, "error": "debtor sin teléfono"}
    if not base_url or not token:
        logger.warning("[wa_bridge] link/cupón NO confirmado por WhatsApp — puente no configurado")
        return {"ok": False, "error": "puente WA no configurado", "sent": False}

    case_id = await _ensure_case_id(db, debtor)
    body = {
        "case_id": case_id,
        "phone": phone if phone.startswith("+") else f"+{phone}",
        "cliente_nombre": str(debtor.get("nombre") or "Cliente")[:80] or "Cliente",
        "numero_poliza": str(debtor.get("numero_poliza") or "")[:40] or "N/A",
        "tipo": "cupon" if str(tipo).lower().startswith("cup") else "link",
    }
    documento = str(debtor.get("cliente_documento") or debtor.get("documento") or "").strip()
    if documento:
        body["documento"] = documento
    try:
        import httpx
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"{base_url}/case/link_cupon",
                headers={"Authorization": f"Bearer {token}"},
                json=body,
            )
            r.raise_for_status()
            logger.info("[wa_bridge] link/cupón confirmado case=%s tipo=%s debtor=%s",
                        case_id, body["tipo"], debtor.get("_id"))
            return {"ok": True, "case_id": case_id, "sent": True}
    except Exception as exc:
        logger.error("[wa_bridge] confirmación de link/cupón falló case=%s: %s", case_id, exc)
        return {"ok": False, "case_id": case_id, "error": str(exc)[:200]}


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
        "case_id": case_id,
        "debtor_id": str(debtor.get("_id", "")),
        "poliza_number": str(debtor.get("numero_poliza") or "")[:40] or "N/A",
        "call_id": call_id,
        "user_id": user_id,
        "phone": phone if phone.startswith("+") else f"+{phone}",
        "initial_context": initial_context[:500],
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
