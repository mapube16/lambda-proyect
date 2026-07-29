"""
chatwoot_contacts.py — upsert de contactos de Chatwoot desde la cartera.

El equipo ve las conversaciones de WhatsApp en Chatwoot, pero los contactos
los crea el WA service "pelados" (solo teléfono). Con la cartera ya
sincronizada desde SoftSeguros (db.debtors) este módulo puebla nombre,
documento y pólizas en el contacto para que el equipo sepa QUIÉN escribe.

Config por env (mismas credenciales que usa el WA service):
  CHATWOOT_URL         p.ej. https://chat.landatech.org
  CHATWOOT_API_KEY     api_access_token de un usuario admin
  CHATWOOT_ACCOUNT_ID  default "1"

Sin config → skip silencioso (otros tenants/entornos no se ven afectados).
Se engancha best-effort al final de run_cartera_sync (5x/día) y existe el
wrapper scripts/sync_chatwoot_contacts.py para la carga manual completa.
"""
import asyncio
import logging
import os
import re

logger = logging.getLogger("softseguros.chatwoot_contacts")

_PHONE_RE = re.compile(r"^\+57\d{10}$")  # mismo criterio que el marcador


def _cfg() -> tuple:
    url = os.getenv("CHATWOOT_URL", "").rstrip("/")
    key = os.getenv("CHATWOOT_API_KEY", "")
    acc = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    return url, key, acc


async def sync_chatwoot_contacts(db, user_id: str, *, limit: int = 5000) -> dict:
    """Upsert de contactos en Chatwoot desde db.debtors del tenant.

    Agrupa por teléfono (una persona puede tener varias pólizas), busca el
    contacto por teléfono y lo crea o actualiza con nombre + atributos.
    Nunca lanza — devuelve contadores {ok, created, updated, skipped, failed}.
    """
    url, key, acc = _cfg()
    if not url or not key:
        logger.info("[chatwoot_contacts] sin CHATWOOT_URL/API_KEY — skip")
        return {"ok": False, "reason": "sin_config"}

    import httpx

    # Agrupar cartera por teléfono válido.
    por_tel: dict = {}
    cursor = db.debtors.find(
        {"user_id": user_id, "is_active": {"$ne": False}, "is_test": {"$ne": True}},
        {"nombre": 1, "telefono": 1, "cliente_documento": 1, "numero_poliza": 1, "ramo_nombre": 1},
    ).limit(limit)
    async for d in cursor:
        tel = str(d.get("telefono") or "").strip()
        if not _PHONE_RE.match(tel):
            continue
        g = por_tel.setdefault(tel, {"nombre": "", "documento": "", "polizas": []})
        if not g["nombre"] and d.get("nombre"):
            g["nombre"] = str(d["nombre"])[:255]
        if not g["documento"] and d.get("cliente_documento"):
            g["documento"] = str(d["cliente_documento"])
        pol = str(d.get("numero_poliza") or "")
        if pol:
            ramo = str(d.get("ramo_nombre") or "").strip()
            g["polizas"].append(f"{pol} ({ramo})" if ramo else pol)

    headers = {"api_access_token": key}
    base = f"{url}/api/v1/accounts/{acc}"
    created = updated = failed = 0

    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        for tel, g in por_tel.items():
            attrs = {
                "documento": g["documento"],
                "polizas": ", ".join(g["polizas"][:10]),
                "fuente": "softseguros",
            }
            try:
                r = await client.get(f"{base}/contacts/search", params={"q": tel})
                payload = (r.json() or {}).get("payload") or []
                existing = next(
                    (c for c in payload if (c.get("phone_number") or "") == tel), None
                )
                if existing:
                    body: dict = {"custom_attributes": attrs}
                    # No pisar un nombre puesto a mano: solo completar si el
                    # contacto quedó "pelado" (sin nombre o nombre = teléfono).
                    cur_name = (existing.get("name") or "").strip()
                    if g["nombre"] and (not cur_name or cur_name.lstrip("+").isdigit()):
                        body["name"] = g["nombre"]
                    await client.put(f"{base}/contacts/{existing['id']}", json=body)
                    updated += 1
                else:
                    r = await client.post(
                        f"{base}/contacts",
                        json={
                            "name": g["nombre"] or tel,
                            "phone_number": tel,
                            "identifier": g["documento"] or None,
                            "custom_attributes": attrs,
                        },
                    )
                    if r.status_code == 422:
                        # identifier tomado por otro contacto → reintentar sin él
                        r = await client.post(
                            f"{base}/contacts",
                            json={"name": g["nombre"] or tel, "phone_number": tel,
                                  "custom_attributes": attrs},
                        )
                    created += 1 if r.status_code < 400 else 0
                    failed += 1 if r.status_code >= 400 else 0
            except Exception:
                failed += 1
                logger.warning("[chatwoot_contacts] fallo con %s (no fatal)", tel[-4:])
            await asyncio.sleep(0.1)  # ponytail: rate-limit fijo; batch API si crece

    out = {"ok": True, "contactos": len(por_tel), "created": created,
           "updated": updated, "failed": failed}
    logger.info("[chatwoot_contacts] user=%s %s", user_id, out)
    return out
