"""
shared_models.py — modelos compartidos con landa-agent-service (Fase 6).

Copia deliberada (NO submodule landa-shared) por decisión del contrato
(.planning/contracts/lambda-handoff-contract.md en landa-agent-service,
"Recomendación v1"): un tercer repo con versionado propio es over-engineering
para arrancar con un solo cliente (WhatsApp). Cuando el drift entre las dos
copias empiece a doler, o entre un 2º cliente, se extrae landa-shared — ese
trigger se documenta en un ADR, no antes.

Estos 3 modelos son el contrato congelado v1. Cambios aquí requieren aviso al
otro lado (bump de versión en el doc del contrato).
"""
from typing import Optional

from pydantic import BaseModel


class Policy(BaseModel):
    numero: str                      # "POL-000123" — debtor.numero_poliza
    estado: Optional[str] = None     # vigente | vencida | ... (Softseguros no siempre lo trae)
    ramo: Optional[str] = None       # debtor.ramo_nombre
    aseguradora: Optional[str] = None  # debtor.aseguradora_nombre
    forma_pago: Optional[str] = None   # debtor.forma_pago (Contado/Financiado/...)
    objeto_asegurado: Optional[str] = None  # riesgo — debtor.objeto_asegurado


class Debtor(BaseModel):
    debtor_id: str
    phone: str                       # E.164 — debtor.telefono
    nombre: str
    poliza: Optional[Policy] = None
    promesa_de_pago: bool = False
    fecha_promesa: Optional[str] = None  # YYYY-MM-DD, si promesa_de_pago
    escalado_previo: bool = False
    dias_mora: Optional[int] = None


class ConversationContext(BaseModel):
    case_id: str
    canal_origen: str                # "voice" | "whatsapp"
    initial_context: Optional[str] = None
    call_id: Optional[str] = None


def debtor_to_shared(doc: dict) -> Debtor:
    """db.debtors doc → el Debtor compartido del contrato (subset, tolerante a faltantes)."""
    poliza = None
    if doc.get("numero_poliza"):
        poliza = Policy(
            numero=str(doc["numero_poliza"]),
            estado=doc.get("estado_poliza_nombre"),
            ramo=doc.get("ramo_nombre"),
            aseguradora=doc.get("aseguradora_nombre"),
            forma_pago=doc.get("forma_pago"),
            objeto_asegurado=doc.get("objeto_asegurado"),
        )
    return Debtor(
        debtor_id=str(doc.get("_id", "")),
        phone=str(doc.get("telefono", "")),
        nombre=doc.get("nombre", ""),
        poliza=poliza,
        promesa_de_pago=doc.get("estado") == "promesa_de_pago",
        fecha_promesa=doc.get("fecha_promesa"),
        escalado_previo=doc.get("estado") == "escalado",
        dias_mora=doc.get("dias_mora") or doc.get("edad_cartera"),
    )
