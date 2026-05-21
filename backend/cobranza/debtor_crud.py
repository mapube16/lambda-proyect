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
        "source": "manual",
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
            "source": "manual",
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
            "source": "manual",
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
    Return the user's MANUAL / CSV cobranza debtors, optionally filtered by estado.
    Sorted by created_at descending.

    Excludes SOFTSEGUROS-sourced debtors (source="softseguros"): those live in the
    dedicated SOFTSEGUROS tab (/api/debtors) which is paginated. Including them here
    pulled the whole imported cartera (e.g. 16 MB / 12 s for ~900 pólizas) into the
    un-paginated cobranza list and blocked the browser connection pool.
    """
    query: dict = {"user_id": user_id, "source": {"$ne": "softseguros"}}
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


# ── Phase 18: SOFTSEGUROS-aware helpers ───────────────────────────────────────
# Idempotency key: (user_id, softseguros_poliza_id). Phase 17 invariants
# (estado/intentos/historial_llamadas/vapi_call_id/escalado/max_intentos) are only
# ever set on first insert via $setOnInsert — never overwritten by a re-sync.

# Fields that SOFTSEGUROS owns and we always overwrite on each sync.
_SOFTSEGUROS_SET_FIELDS = (
    "nombre", "telefono",
    "monto", "vencimiento",
    "numero_poliza", "softseguros_cliente_id",
    "cliente_documento", "cliente_email", "cliente_celular",
    "aseguradora_nit", "ramo_nombre", "ramo_global_nombre", "vendedores_nombre",
    "estado_poliza_nombre", "estado_cartera",
    "prima", "total", "total_pagado", "recaudado",
    "fecha_inicio", "fecha_fin", "fecha_limite_pago",
    "periodicidad", "comicionada",
    "status_softseguros", "is_active",
)


async def upsert_debtor_by_softseguros_poliza_id(
    db, user_id: str, softseguros_poliza_id: int, doc: dict,
) -> dict:
    """
    Upsert a debtor keyed by (user_id, softseguros_poliza_id).

    On insert: seeds Phase 17 cobranza invariants (estado='pendiente', intentos=0, ...)
    and source='softseguros'. On update: only SOFTSEGUROS-owned fields are touched.

    Returns {"created": bool, "updated": bool}.
    """
    now = _utcnow()
    set_payload = {k: doc[k] for k in _SOFTSEGUROS_SET_FIELDS if k in doc}
    set_payload["last_synced"] = now
    set_payload["updated_at"] = now

    on_insert = {
        "user_id": user_id,
        "source": "softseguros",
        "softseguros_poliza_id": softseguros_poliza_id,
        "estado": "pendiente",
        "intentos": 0,
        "max_intentos": int(doc.get("max_intentos", 5)),
        "historial_llamadas": [],
        "escalado": False,
        "vapi_call_id": None,
        "ultimo_contacto_fecha": None,
        "created_at": now,
    }
    # Avoid Mongo conflict: a key cannot be in both $set and $setOnInsert.
    for k in list(set_payload):
        if k in on_insert:
            on_insert.pop(k, None)

    result = await db.debtors.update_one(
        {"user_id": user_id, "softseguros_poliza_id": softseguros_poliza_id},
        {"$set": set_payload, "$setOnInsert": on_insert},
        upsert=True,
    )
    created = result.upserted_id is not None
    return {"created": created, "updated": not created}


def build_softseguros_upsert_op(user_id: str, softseguros_poliza_id: int, doc: dict) -> dict:
    """
    Build the (filter, update) pair for the same upsert as
    upsert_debtor_by_softseguros_poliza_id, WITHOUT executing it. Returned as a
    plain dict so the caller can batch many of them and turn them into a single
    bulk_write (one Atlas round-trip per chunk instead of one per póliza).

    Returns {"filter": {...}, "update": {...}}.
    """
    now = _utcnow()
    set_payload = {k: doc[k] for k in _SOFTSEGUROS_SET_FIELDS if k in doc}
    set_payload["last_synced"] = now
    set_payload["updated_at"] = now

    on_insert = {
        "user_id": user_id,
        "source": "softseguros",
        "softseguros_poliza_id": softseguros_poliza_id,
        "estado": "pendiente",
        "intentos": 0,
        "max_intentos": int(doc.get("max_intentos", 5)),
        "historial_llamadas": [],
        "escalado": False,
        "vapi_call_id": None,
        "ultimo_contacto_fecha": None,
        "created_at": now,
    }
    for k in list(set_payload):
        if k in on_insert:
            on_insert.pop(k, None)

    return {
        "filter": {"user_id": user_id, "softseguros_poliza_id": softseguros_poliza_id},
        "update": {"$set": set_payload, "$setOnInsert": on_insert},
    }


async def bulk_write_debtor_ops(db, ops: list) -> dict:
    """
    Execute a list of {"filter","update"} upsert specs.

    Fast path: one Mongo bulk_write per call (the whole point of this — turns
    ~5k Atlas round-trips into a few hundred). Falls back to per-op update_one
    only if the driver/mock can't do bulk_write (e.g. mongomock-motor with a
    newer pymongo that injects a 'sort' kwarg the mock doesn't accept). The
    fallback path is correctness-preserving; production always uses the fast path.

    Returns {"created": <upserted>, "updated": <modified>}.
    """
    if not ops:
        return {"created": 0, "updated": 0}

    from pymongo import UpdateOne

    update_ones = [
        UpdateOne(o["filter"], o["update"], upsert=True) for o in ops
    ]
    try:
        res = await db.debtors.bulk_write(update_ones, ordered=False)
        return {"created": res.upserted_count, "updated": res.modified_count}
    except BulkWriteError as bwe:
        details = bwe.details or {}
        return {
            "created": details.get("nUpserted", 0),
            "updated": details.get("nModified", 0),
        }
    except TypeError:
        # bulk_write unsupported by this driver/mock — degrade to update_one.
        created = 0
        updated = 0
        for o in ops:
            r = await db.debtors.update_one(o["filter"], o["update"], upsert=True)
            if r.upserted_id is not None:
                created += 1
            else:
                updated += 1
        return {"created": created, "updated": updated}


async def mark_debtor_paid_by_softseguros_poliza_id(
    db, user_id: str, softseguros_poliza_id: int,
) -> bool:
    """Soft-mark a SOFTSEGUROS debtor as paid (never hard-delete). Returns True if matched."""
    result = await db.debtors.update_one(
        {"user_id": user_id, "softseguros_poliza_id": softseguros_poliza_id},
        {"$set": {
            "status_softseguros": "pagado",
            "is_active": False,
            "comicionada": True,
            "updated_at": _utcnow(),
        }},
    )
    return result.matched_count > 0


async def mark_debtor_deleted_by_softseguros_poliza_id(
    db, user_id: str, softseguros_poliza_id: int,
) -> bool:
    """Soft-mark a SOFTSEGUROS debtor as deleted upstream (never hard-delete). Returns True if matched."""
    result = await db.debtors.update_one(
        {"user_id": user_id, "softseguros_poliza_id": softseguros_poliza_id},
        {"$set": {
            "status_softseguros": "eliminado",
            "is_active": False,
            "updated_at": _utcnow(),
        }},
    )
    return result.matched_count > 0


async def list_active_softseguros_poliza_ids(db, user_id: str) -> set:
    """Return the set of softseguros_poliza_id for this user's active SOFTSEGUROS debtors."""
    cursor = db.debtors.find(
        {"user_id": user_id, "source": "softseguros", "is_active": True},
        {"softseguros_poliza_id": 1},
    )
    docs = await cursor.to_list(length=None)
    return {d["softseguros_poliza_id"] for d in docs if d.get("softseguros_poliza_id") is not None}
