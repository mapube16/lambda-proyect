"""
debtor_crud.py — MongoDB CRUD for the debtors collection.
All functions are async and accept `db` (Motor database object) as first argument.
Tenant isolation is enforced by always filtering on user_id.
"""
from datetime import datetime, timezone
from typing import Optional

from bson import ObjectId
from pymongo.errors import BulkWriteError, DuplicateKeyError


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: Optional[dict]) -> Optional[dict]:
    """Convert MongoDB document: _id ObjectId -> str, return None if None."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


async def create_debtor(db, user_id: str, data: dict) -> dict:
    """
    Insert a single debtor document.
    Enforces estado=pendiente, intentos=0 defaults.
    Returns the inserted document with _id as str.
    """
    now = _utcnow()
    doc = {
        "user_id": user_id,
        "nombre": data.get("nombre", ""),
        "telefono": data["telefono"],
        "monto": float(data.get("monto", 0)),
        "vencimiento": data.get("vencimiento"),
        "estado": "pendiente",
        "vapi_call_id": data.get("vapi_call_id"),
        "intentos": 0,
        "max_intentos": data.get("max_intentos", 5),
        "historial_llamadas": data.get("historial_llamadas", []),
        "escalado": False,
        "notas": data.get("notas"),
        "ultimo_contacto_fecha": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.debtors.insert_one(doc)
    doc["_id"] = str(result.inserted_id)
    return doc


async def bulk_create_debtors(db, user_id: str, debtors: list[dict]) -> dict:
    """
    Insert multiple debtor documents. Skips duplicates (same user_id+telefono)
    by using ordered=False with BulkWriteError handling.

    Returns {"created": N, "skipped": M}.
    """
    if not debtors:
        return {"created": 0, "skipped": 0}

    now = _utcnow()
    docs = []
    for data in debtors:
        docs.append({
            "user_id": user_id,
            "nombre": data.get("nombre", ""),
            "telefono": data["telefono"],
            "monto": float(data.get("monto", 0)),
            "vencimiento": data.get("vencimiento"),
            "estado": data.get("estado", "pendiente"),
            "vapi_call_id": data.get("vapi_call_id"),
            "intentos": int(data.get("intentos", 0)),
            "max_intentos": int(data.get("max_intentos", 5)),
            "historial_llamadas": data.get("historial_llamadas", []),
            "escalado": bool(data.get("escalado", False)),
            "notas": data.get("notas"),
            "ultimo_contacto_fecha": None,
            "created_at": now,
            "updated_at": now,
        })

    skipped = 0
    created = 0
    try:
        result = await db.debtors.insert_many(docs, ordered=False)
        created = len(result.inserted_ids)
    except BulkWriteError as bwe:
        # Count successful inserts and duplicates (E11000)
        created = bwe.details.get("nInserted", 0)
        skipped = sum(
            1 for err in bwe.details.get("writeErrors", [])
            if err.get("code") == 11000
        )

    return {"created": created, "skipped": skipped}


async def bulk_upsert_debtors(db, user_id: str, debtors: list[dict]) -> dict:
    """
    Upsert debtors by (user_id, telefono).
    For existing debtors: updates nombre, monto, vencimiento, notas — preserves estado/intentos/historial.
    For new debtors: inserts with estado=pendiente defaults.
    Returns {"updated": N, "created": M}.
    """
    if not debtors:
        return {"updated": 0, "created": 0}

    now = _utcnow()
    updated = 0
    created = 0

    for data in debtors:
        mutable = {
            k: v for k, v in {
                "nombre": data.get("nombre"),
                "monto": float(data.get("monto", 0)),
                "vencimiento": data.get("vencimiento"),
                "notas": data.get("notas"),
                "updated_at": now,
            }.items() if v is not None
        }
        on_insert = {
            "user_id": user_id,
            "telefono": data["telefono"],
            "estado": "pendiente",
            "vapi_call_id": None,
            "intentos": 0,
            "max_intentos": int(data.get("max_intentos", 5)),
            "historial_llamadas": [],
            "escalado": False,
            "ultimo_contacto_fecha": None,
            "created_at": now,
        }
        result = await db.debtors.update_one(
            {"user_id": user_id, "telefono": data["telefono"]},
            {"$set": mutable, "$setOnInsert": on_insert},
            upsert=True,
        )
        if result.upserted_id:
            created += 1
        else:
            updated += 1

    return {"updated": updated, "created": created}


async def get_debtors(db, user_id: str, estado: Optional[str] = None) -> list[dict]:
    """
    Return all debtors for user_id, optionally filtered by estado.
    Sorted by created_at descending.
    """
    query: dict = {"user_id": user_id}
    if estado is not None:
        query["estado"] = estado

    cursor = db.debtors.find(query).sort("created_at", -1)
    docs = await cursor.to_list(length=None)
    return [_serialize(d) for d in docs]


async def get_debtor_by_id(db, user_id: str, debtor_id: str) -> Optional[dict]:
    """
    Fetch a single debtor by _id, enforcing user_id tenant isolation.
    Returns None if not found or user_id mismatch.
    """
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        return None
    doc = await db.debtors.find_one({"_id": oid, "user_id": user_id})
    return _serialize(doc)


async def update_debtor(db, user_id: str, debtor_id: str, patch: dict) -> Optional[dict]:
    """
    Apply a partial update ($set) to a debtor, enforcing user_id.
    Returns updated document or None if not found.
    """
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        return None

    patch["updated_at"] = _utcnow()

    try:
        result = await db.debtors.find_one_and_update(
            {"_id": oid, "user_id": user_id},
            {"$set": patch},
            return_document=True,
        )
    except DuplicateKeyError:
        raise ValueError("telefono_duplicado")

    return _serialize(result)


async def delete_debtor(db, user_id: str, debtor_id: str) -> bool:
    """
    Delete a debtor by _id, enforcing user_id tenant isolation.
    Returns True if deleted, False if not found.
    """
    try:
        oid = ObjectId(debtor_id)
    except Exception:
        return False
    result = await db.debtors.delete_one({"_id": oid, "user_id": user_id})
    return result.deleted_count > 0
