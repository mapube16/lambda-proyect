import os
import asyncio
import logging
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel

import database as _database
from auth import get_current_user
from database import (
    get_db, get_lead_by_id, get_leads_by_user, update_lead_hitl,
    get_ideal_leads, get_rejected_leads,
)
from services.connection_manager import manager
from services.notifications import notify_user

logger = logging.getLogger(__name__)

router = APIRouter()


class SendEmailRequest(BaseModel):
    subject_index: int = 0


class LeadDecisionRequest(BaseModel):
    decision: str
    canal_elegido: Optional[str] = None
    motivo: Optional[str] = None


class CallReportRequest(BaseModel):
    resultado: str
    detalle: Optional[str] = None
    sub_tipo: Optional[str] = None


DECISION_MAP = {"aprobar": "outreach", "pausar": "pausado", "rechazar": "nurturing"}


def _build_lead_signal(lead: dict) -> str:
    """Derive short signal string from lead.expediente_json. Returns '' if insufficient data."""
    exp = lead.get("expediente_json") or {}
    if not isinstance(exp, dict):
        return ""
    industria = (exp.get("industria") or exp.get("industry") or "").strip()
    ciudad = (exp.get("ciudad") or exp.get("city") or "").strip()
    if not industria and not ciudad:
        return ""  # RESEARCH pitfall 4 — do not append empty/useless signals
    parts = []
    if industria:
        parts.append(f"industria={industria}")
    if ciudad:
        parts.append(f"ciudad={ciudad}")
    tech = exp.get("tech_stack") or exp.get("software_clave")
    if tech:
        if isinstance(tech, list):
            tech = ", ".join(str(t) for t in tech[:3])
        parts.append(f"tech={tech}")
    return " ".join(parts)


@router.get("/api/leads")
async def get_user_leads(current_user: dict = Depends(get_current_user)):
    return await get_leads_by_user(str(current_user["user_id"]))


@router.get("/api/leads/checkpoint")
async def get_checkpoint_leads(current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    db = get_db()
    leads = await db.leads.find({"user_id": user_id, "estado": "checkpoint"}).sort("estado_updated_at", -1).to_list(length=100)
    result = []
    for l in leads:
        l["_id"] = str(l["_id"])
        result.append({
            "id": l["_id"],
            "empresa": l.get("company_name") or l.get("empresa", ""),
            "decisor": l.get("decisor"),
            "puntaje": l.get("puntaje", 0),
            "criterios": l.get("criterios", []),
            "senales": l.get("señales", l.get("senales", [])),
            "canales": l.get("canales", []),
            "canal_elegido": l.get("canal_elegido"),
            "estado": l.get("estado"),
        })
    return result


@router.get("/api/leads/{lead_id}")
async def get_lead_detail(lead_id: str, current_user: dict = Depends(get_current_user)):
    lead = await get_lead_by_id(lead_id, str(current_user["user_id"]))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    return lead


@router.get("/api/leads/{lead_id}/draft")
async def get_lead_draft(lead_id: str, current_user: dict = Depends(get_current_user)):
    lead = await get_lead_by_id(lead_id, str(current_user["user_id"]))
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    exp = lead.get("expediente_json") or {}
    borradores = exp.get("borradores") or {}
    return {
        **lead,
        "email_draft": {
            "asuntos": borradores.get("email_asuntos", []),
            "cuerpo": borradores.get("email_cuerpo", ""),
            "decisor": exp.get("decisor", {}),
        },
    }


@router.post("/api/leads/{lead_id}/send-email")
async def send_lead_email(lead_id: str, request: SendEmailRequest, current_user: dict = Depends(get_current_user)):
    from mailer import send_lead_outreach
    if not os.getenv("MAILERSEND_API_KEY"):
        raise HTTPException(status_code=503, detail="MAILERSEND_API_KEY not configured")
    user_id = str(current_user["user_id"])
    db = get_db()
    lead = await db.leads.find_one({"_id": lead_id, "user_id": user_id})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    exp = lead.get("expediente_json") or {}
    borradores = exp.get("borradores") or {}
    decisor = exp.get("decisor") or {}
    to_email = decisor.get("email") or ""
    if not to_email:
        raise HTTPException(status_code=422, detail="El lead no tiene email del decisor")
    body = borradores.get("email_cuerpo") or ""
    if not body:
        raise HTTPException(status_code=422, detail="El lead no tiene borrador de correo")
    subjects = borradores.get("email_asuntos") or []
    idx = min(request.subject_index, len(subjects) - 1) if subjects else 0
    subject = subjects[idx] if subjects else "Propuesta de colaboracion"
    campaign = await db.campaigns.find_one({"user_id": user_id}, sort=[("created_at", -1)])
    camp = campaign or {}
    try:
        status = await send_lead_outreach(
            to_email=to_email, to_name=decisor.get("nombre") or "",
            subject=subject, body_text=body,
            sender_name=camp.get("nombre_remitente", ""),
            sender_empresa=camp.get("empresa_remitente", ""),
            reply_to_email=camp.get("email_remitente", ""),
            user_id=user_id,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail="Email service temporarily unavailable")
    except Exception as e:
        raise HTTPException(status_code=502, detail="Failed to send email. Please try again later.")
    await db.leads.update_one({"_id": lead_id}, {"$set": {"email_sent": True}})
    return {"ok": True, "to": to_email, "subject": subject, "status": status}


@router.patch("/api/leads/{lead_id}/approve")
async def approve_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "approved")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    leads = await get_leads_by_user(user_id, limit=200)
    lead_data = next((l for l in leads if l["_id"] == lead_id), None)
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key and lead_data:
        from learning import embed_and_store_approved_lead
        asyncio.create_task(embed_and_store_approved_lead(user_id, lead_id, lead_data))
    if lead_data:
        canal = lead_data.get("canal_elegido", "email")
        from landa.agents.outreach import run_outreach
        asyncio.create_task(run_outreach(lead_id, user_id, canal, intento=1))
    return {"status": "approved", "lead_id": lead_id}


@router.patch("/api/leads/{lead_id}/reject")
async def reject_lead(lead_id: str, current_user: dict = Depends(get_current_user)):
    user_id = str(current_user["user_id"])
    updated = await update_lead_hitl(lead_id, user_id, "rejected")
    if not updated:
        raise HTTPException(status_code=404, detail="Lead not found or not yours")
    leads = await get_leads_by_user(user_id, limit=200)
    lead_data = next((l for l in leads if l["_id"] == lead_id), None)
    if lead_data:
        from learning import store_rejected_lead
        asyncio.create_task(store_rejected_lead(user_id, lead_id, lead_data))
    db = get_db()
    lead_doc = await db.leads.find_one({"_id": ObjectId(lead_id)})
    if lead_doc and lead_doc.get("estado") == "checkpoint":
        await db.leads.update_one({"_id": ObjectId(lead_id)}, {"$set": {"motivo_nurturing": "rechazado_humano"}})
        try:
            from landa.state_machine import update_lead_estado
            await update_lead_estado(lead_id, user_id, "nurturing")
        except ValueError:
            pass
    return {"status": "rejected", "lead_id": lead_id}


@router.post("/api/leads/{lead_id}/decision")
async def lead_decision(lead_id: str, request: LeadDecisionRequest, current_user: dict = Depends(get_current_user)):
    from landa.state_machine import update_lead_estado
    from landa.agents.outreach import run_outreach as _run_outreach
    user_id = str(current_user["user_id"])
    new_estado = DECISION_MAP.get(request.decision)
    if not new_estado:
        raise HTTPException(status_code=400, detail=f"Unknown decision: {request.decision}")
    db = get_db()
    if request.decision == "rechazar":
        motivo = request.motivo or "rechazado_humano"
        await db.leads.update_one({"_id": ObjectId(lead_id)}, {"$set": {"motivo_nurturing": motivo}})
    try:
        updated = await update_lead_estado(lead_id, user_id, new_estado)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid request data")
    if request.decision == "aprobar":
        canal = request.canal_elegido or updated.get("canal_elegido", "email")
        asyncio.create_task(_run_outreach(lead_id, user_id, canal, intento=1))
        await notify_user(user_id, {"type": "lead_checkpoint", "lead_id": lead_id, "empresa": updated.get("company_name") or updated.get("empresa", ""), "puntaje": updated.get("puntaje", 0), "accion": "aprobado"})
    elif request.decision == "rechazar":
        await notify_user(user_id, {"type": "lead_archived", "lead_id": lead_id, "empresa": updated.get("company_name") or updated.get("empresa", "")})
    else:
        await manager.send_to_user(user_id, {"type": "agent_state", "agent": "investigador", "state": "idle", "message": f"Lead pausado: {updated.get('company_name', lead_id)}"})
    # Phase 23 SIGNAL-FB-01: fire-and-forget feedback to prospecting_knowledge
    if request.decision in ("aprobar", "rechazar"):
        signal_text = _build_lead_signal(updated)
        if signal_text:
            signal_type = "approved" if request.decision == "aprobar" else "rejected"
            asyncio.create_task(_database.append_lead_signal(user_id, signal_text, signal_type))
    return {"status": "ok", "lead_id": lead_id, "nuevo_estado": new_estado}


@router.get("/api/leads/{lead_id}/handover")
async def get_handover(lead_id: str, current_user: dict = Depends(get_current_user)):
    from landa.core.context import call_agent as _call_agent
    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        lead = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    lead["_id"] = str(lead["_id"])
    hilo = lead.get("historial_conversacion", [])
    calificacion = {"puntaje": lead.get("puntaje", 0), "criterios": lead.get("criterios", []), "canales": lead.get("canales", [])}
    empresa = lead.get("company_name") or lead.get("empresa", "empresa desconocida")
    decisor = lead.get("decisor", "el decisor")
    try:
        sugerencia = await _call_agent("Eres un experto en ventas B2B colombianas.", f"Genera una sugerencia de cierre concisa (2-3 oraciones) para llamar a {decisor} de {empresa}. Contexto del hilo: {str(hilo)[-500:]}")
    except Exception:
        sugerencia = ""
    return {"lead": lead, "hilo_conversacion": hilo, "calificacion_original": calificacion, "sugerencia_cierre": sugerencia}


@router.post("/api/leads/{lead_id}/handover/tomar")
async def handover_tomar(lead_id: str, current_user: dict = Depends(get_current_user)):
    from landa.state_machine import update_lead_estado
    from landa.scheduler import cancel_lead_actions, schedule_retry
    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        lead = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    await cancel_lead_actions(lead_id)
    try:
        updated = await update_lead_estado(lead_id, user_id, "handover")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid request data")
    await schedule_retry(lead_id, canal="notificacion_48h", days=2)
    await notify_user(user_id, {"type": "lead_handover", "lead_id": lead_id, "empresa": updated.get("company_name") or updated.get("empresa", ""), "canal": lead.get("canal_elegido", "email")})
    return {"status": "ok", "lead_id": lead_id, "estado": "handover"}


@router.post("/api/leads/{lead_id}/reporte-llamada")
async def reporte_llamada(lead_id: str, request: CallReportRequest, current_user: dict = Depends(get_current_user)):
    from landa.state_machine import update_lead_estado
    from landa.scheduler import schedule_retry
    from landa.core.context import call_agent as _call_agent
    user_id = str(current_user["user_id"])
    db = get_db()
    try:
        lead = await db.leads.find_one({"_id": ObjectId(lead_id), "user_id": user_id})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    resultado = request.resultado
    detalle = request.detalle or ""
    sub_tipo = request.sub_tipo or ""
    if resultado == "mal":
        await db.leads.update_one({"_id": ObjectId(lead_id)}, {"$set": {"motivo_nurturing": detalle or "llamada_mal"}})
        try:
            await update_lead_estado(lead_id, user_id, "nurturing")
        except ValueError:
            pass
    elif resultado == "no_pude":
        if sub_tipo in ("ocupado", "apagado"):
            await schedule_retry(lead_id, canal=lead.get("canal_elegido", "telefono"), days=1)
        elif sub_tipo == "incorrecto":
            await db.leads.update_one({"_id": ObjectId(lead_id)}, {"$set": {"buscar_numero_alternativo": True}})
        elif sub_tipo == "corto":
            await schedule_retry(lead_id, canal=lead.get("canal_elegido", "telefono"), days=7)
    elif resultado in ("bien", "mas_o_menos"):
        async def _interpret_and_act():
            empresa_ia = lead.get("company_name") or lead.get("empresa", "empresa")
            try:
                decision_ia = (await _call_agent("Eres un coordinador de ventas B2B.", f"Resultado de llamada '{resultado}' con {empresa_ia}. Detalle: '{detalle}'. Decide: nurturing | reintento_3d | handover_completo")).strip().lower()
                if "nurturing" in decision_ia:
                    await update_lead_estado(lead_id, user_id, "nurturing")
                elif "reintento" in decision_ia:
                    await schedule_retry(lead_id, canal=lead.get("canal_elegido", "email"), days=3)
            except Exception:
                pass
        asyncio.create_task(_interpret_and_act())
    empresa = lead.get("company_name") or lead.get("empresa", "")
    await manager.send_to_user(user_id, {"type": "agent_state", "agent": "outreach", "state": "idle", "message": f"Reporte registrado para {empresa}"})
    return {"status": "ok", "lead_id": lead_id, "resultado": resultado}
