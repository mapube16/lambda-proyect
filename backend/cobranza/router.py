"""
router.py — REST endpoints for cobranza debtor management.
All endpoints require authentication and enforce tenant isolation via user_id.
Prefix: /api/cobranza
"""
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from pydantic import BaseModel

from auth import get_current_user
from database import get_db
from cobranza.debtor_crud import (
    bulk_create_debtors,
    create_debtor,
    delete_debtor,
    get_debtor_by_id,
    get_debtors,
    update_debtor,
)
from cobranza.csv_parser import normalize_phone, parse_debtor_csv

router = APIRouter(prefix="/api/cobranza", tags=["cobranza"])


# ── Request / Response Models ─────────────────────────────────────────────────

class DebtorCreate(BaseModel):
    nombre: str
    telefono: str
    monto: float
    vencimiento: str  # "YYYY-MM-DD"
    notas: Optional[str] = None
    max_intentos: int = 5


class DebtorPatch(BaseModel):
    nombre: Optional[str] = None
    telefono: Optional[str] = None
    monto: Optional[float] = None
    vencimiento: Optional[str] = None  # "YYYY-MM-DD"
    notas: Optional[str] = None


# ── CSV Upload ────────────────────────────────────────────────────────────────

@router.post("/debtors/csv", status_code=status.HTTP_201_CREATED)
async def upload_debtors_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a CSV file of debtors. Returns {created: N, errors: [...]}."""
    user_id = str(current_user["user_id"])
    db = get_db()

    file_bytes = await file.read()
    valid_rows, errors = parse_debtor_csv(file_bytes)

    result = await bulk_create_debtors(db, user_id, valid_rows)
    return {"created": result["created"], "errors": errors}


# ── Single Debtor Create ──────────────────────────────────────────────────────

@router.post("/debtors", status_code=status.HTTP_201_CREATED)
async def create_debtor_endpoint(
    body: DebtorCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a single debtor. Returns {debtor: {...}}."""
    user_id = str(current_user["user_id"])
    db = get_db()

    # Normalize phone
    normalized = normalize_phone(body.telefono)
    if normalized is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"telefono inválido '{body.telefono}'",
        )

    # Parse vencimiento
    try:
        vencimiento = datetime.strptime(body.vencimiento.strip(), "%Y-%m-%d")
    except (ValueError, AttributeError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"vencimiento inválido '{body.vencimiento}' (esperado YYYY-MM-DD)",
        )

    data = {
        "nombre": body.nombre,
        "telefono": normalized,
        "monto": body.monto,
        "vencimiento": vencimiento,
        "notas": body.notas,
        "max_intentos": body.max_intentos,
    }

    debtor = await create_debtor(db, user_id, data)
    return {"debtor": debtor}


# ── List Debtors ──────────────────────────────────────────────────────────────

@router.get("/debtors")
async def list_debtors(
    estado: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """List debtors for the authenticated user, optionally filtered by estado."""
    user_id = str(current_user["user_id"])
    db = get_db()
    debtors = await get_debtors(db, user_id, estado)
    return debtors


# ── Get Single Debtor ─────────────────────────────────────────────────────────

@router.get("/debtors/{debtor_id}")
async def get_debtor_endpoint(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get full debtor document including historial_llamadas."""
    user_id = str(current_user["user_id"])
    db = get_db()
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if debtor is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": debtor}


# ── Patch Debtor ──────────────────────────────────────────────────────────────

@router.patch("/debtors/{debtor_id}")
async def patch_debtor_endpoint(
    debtor_id: str,
    body: DebtorPatch,
    current_user: dict = Depends(get_current_user),
):
    """Partially update nombre/telefono/monto/vencimiento/notas."""
    user_id = str(current_user["user_id"])
    db = get_db()

    patch: dict = {}
    if body.nombre is not None:
        patch["nombre"] = body.nombre
    if body.telefono is not None:
        normalized = normalize_phone(body.telefono)
        if normalized is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"telefono inválido '{body.telefono}'",
            )
        patch["telefono"] = normalized
    if body.monto is not None:
        patch["monto"] = body.monto
    if body.vencimiento is not None:
        try:
            patch["vencimiento"] = datetime.strptime(body.vencimiento.strip(), "%Y-%m-%d")
        except (ValueError, AttributeError):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"vencimiento inválido '{body.vencimiento}' (esperado YYYY-MM-DD)",
            )
    if body.notas is not None:
        patch["notas"] = body.notas

    updated = await update_debtor(db, user_id, debtor_id, patch)
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


# ── Delete Debtor ─────────────────────────────────────────────────────────────

@router.delete("/debtors/{debtor_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_debtor_endpoint(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a debtor."""
    user_id = str(current_user["user_id"])
    db = get_db()
    deleted = await delete_debtor(db, user_id, debtor_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Debtor not found")


# ── State Transition Endpoints ────────────────────────────────────────────────

@router.post("/debtors/{debtor_id}/pagar")
async def marcar_pagado(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Mark debtor as pagado."""
    user_id = str(current_user["user_id"])
    db = get_db()
    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pagado"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


@router.post("/debtors/{debtor_id}/pausar")
async def pausar_debtor(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Pause a debtor (sets estado=pausado)."""
    user_id = str(current_user["user_id"])
    db = get_db()
    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pausado"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}


@router.post("/debtors/{debtor_id}/reactivar")
async def reactivar_debtor(
    debtor_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Reactivate a paused debtor (estado=pausado -> pendiente)."""
    user_id = str(current_user["user_id"])
    db = get_db()

    # Only reactivate if currently pausado
    debtor = await get_debtor_by_id(db, user_id, debtor_id)
    if debtor is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    if debtor.get("estado") != "pausado":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reactivate debtor with estado='{debtor.get('estado')}' (must be 'pausado')",
        )

    updated = await update_debtor(db, user_id, debtor_id, {"estado": "pendiente"})
    if updated is None:
        raise HTTPException(status_code=404, detail="Debtor not found")
    return {"debtor": updated}
