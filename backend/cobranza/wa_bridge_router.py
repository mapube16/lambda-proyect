"""
wa_bridge_router.py — endpoints WA→VOICE (Contrato B del contrato de handoff:
landa-agent-service/.planning/contracts/lambda-handoff-contract.md).

Los expone VOICE; WA los llama cuando una tool suya muta estado del deudor.
Auth: Bearer token comparado con hmac.compare_digest (tiempo constante) contra
WA_TO_VOICE_TOKEN — un token DISTINTO al que usa VOICE→WA
(LAMBDA_PROYECT_INTERNAL_TOKEN), como recomienda el contrato, para poder
rotar cada dirección sin romper la otra.

B1 y B2 buscan por case_id/debtor_id SIN filtrar por user_id: el contrato no
incluye tenant info en el body (WA solo reenvía el case_id/debtor_id que
recibió del handoff original) — ambos son ObjectId/UUID efectivamente únicos
globalmente, así que la búsqueda es segura sin ese filtro adicional.
"""
import hmac
import logging
import os
from typing import Optional

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("cobranza.wa_bridge_router")

router = APIRouter(prefix="/cobranza", tags=["wa-bridge"])


def _check_token(authorization: str = Header(None)) -> None:
    expected = os.getenv("WA_TO_VOICE_TOKEN", "")
    if not expected:
        # Sin token configurado, el puente está deliberadamente deshabilitado
        # (fail-closed) — mejor que aceptar llamadas sin autenticar.
        raise HTTPException(503, "puente WA→VOICE no configurado")
    got = (authorization or "").removeprefix("Bearer ").strip()
    if not got or not hmac.compare_digest(got, expected):
        raise HTTPException(401, "invalid bearer")


class EscalateBody(BaseModel):
    reason: str
    channel: str = "whatsapp"
    note: str = ""


class DebtorUpdateBody(BaseModel):
    estado: Optional[str] = None
    promesa_de_pago: Optional[bool] = None
    promesa_fecha: Optional[str] = None
    ultima_interaccion_wa: Optional[str] = None
    intentos: Optional[int] = None


@router.post("/case/{case_id}/escalate")
async def wa_escalate(case_id: str, body: EscalateBody, authorization: str = Header(None)):
    """B1: WA escala un caso (rechazo de cartera, firewall, etc.)."""
    _check_token(authorization)
    from database import get_db
    db = get_db()

    debtor = await db.debtors.find_one({"case_id": case_id})
    if debtor is None:
        raise HTTPException(404, "case_id no encontrado")

    from cobranza.sub_agents.escalation_handler import escalate
    reason = f"[WA/{body.channel}] {body.reason}" + (f" — {body.note}" if body.note else "")
    await escalate(db, debtor["user_id"], str(debtor["_id"]), reason)

    # Misma clasificación por área (informe §11) que usa el escalate de voz.
    try:
        from cobranza.alerts import crear_alerta
        await crear_alerta(db, debtor["user_id"], debtor, "consulta_fuera_alcance", detalle=reason)
    except Exception:
        logger.exception("[wa_bridge_router] alerta de escalate (WA) falló (no fatal)")

    return {"case_id": case_id, "status": "escalated"}


@router.post("/debtor/{debtor_id}/update")
async def wa_update_debtor(debtor_id: str, body: DebtorUpdateBody, authorization: str = Header(None)):
    """B2: WA propaga flags del deudor (última escritura gana, por campo)."""
    _check_token(authorization)
    try:
        oid = ObjectId(debtor_id)
    except InvalidId:
        raise HTTPException(422, "debtor_id inválido")

    patch = {k: v for k, v in body.model_dump().items() if v is not None}
    if not patch:
        return {"debtor_id": debtor_id, "updated": False}

    from database import get_db
    db = get_db()
    result = await db.debtors.update_one({"_id": oid}, {"$set": patch})
    if result.matched_count == 0:
        raise HTTPException(404, "debtor_id no encontrado")

    logger.info("[wa_bridge_router] debtor=%s actualizado por WA: %s", debtor_id, list(patch.keys()))
    return {"debtor_id": debtor_id, "updated": True}
