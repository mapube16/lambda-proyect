"""Crea las cuentas de equipo de DPG (acts_for -> tenant DPG) con contraseña
temporal y les envía el correo de bienvenida con sus credenciales.

- Idempotente: si la cuenta ya existe, solo re-genera la contraseña temporal y
  re-marca must_change_password (útil para reenviar credenciales).
- Las contraseñas temporales NUNCA se imprimen — solo viajan en el correo al
  destinatario. La salida muestra únicamente OK/FALLO por cuenta.

Correr vía: railway run --service lambda-proyect <venv-python> scripts/create_dpg_team.py
"""
import asyncio
import os
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import certifi
from motor.motor_asyncio import AsyncIOMotorClient

from auth import hash_password

DPG_TENANT_ID = "69bcd9bb6e35d53880364535"
DASHBOARD_URL = "https://my.landatech.org"

TEAM = [
    "administracion@dpgseguros.com",
    "auxiliar.cartera@dpgseguros.com",
    "gerencia@dpgseguros.com",
    "proyectos@dpgseguros.com",
    "innovaciondpg@gmail.com",
]


def _email_html(email: str, temp_password: str) -> str:
    return f"""
<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#222">
  <h2 style="color:#1a7f6e">Bienvenido al dashboard de cobranza de DPG Seguros</h2>
  <p>Hola,</p>
  <p>Se creó tu cuenta de acceso al dashboard de <b>Landa Tech</b>, donde puedes
  hacer seguimiento a la gestión de cobranza de ARIA (llamadas, alertas,
  deudores y reportes, sincronizado con SoftSeguros).</p>
  <table style="border-collapse:collapse;margin:18px 0">
    <tr><td style="padding:6px 14px 6px 0;color:#666">URL:</td>
        <td><a href="{DASHBOARD_URL}">{DASHBOARD_URL}</a></td></tr>
    <tr><td style="padding:6px 14px 6px 0;color:#666">Usuario:</td>
        <td><b>{email}</b></td></tr>
    <tr><td style="padding:6px 14px 6px 0;color:#666">Contraseña temporal:</td>
        <td><b style="font-family:monospace">{temp_password}</b></td></tr>
  </table>
  <p><b>Al entrar por primera vez, el sistema te pedirá crear tu propia
  contraseña.</b> La temporal deja de servir en ese momento.</p>
  <p style="color:#666;font-size:13px">Si tienes problemas para entrar, responde
  a este correo y te ayudamos.</p>
  <p style="margin-top:24px">— Equipo Landa Tech</p>
</div>
"""


async def main():
    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]

    tenant = await db.users.find_one({"_id": __import__("bson").ObjectId(DPG_TENANT_ID)})
    if not tenant:
        raise SystemExit(f"Tenant DPG {DPG_TENANT_ID} no existe — abortando")

    from mailer import _send as mailersend_send
    from_addr = os.getenv("MAILERSEND_FROM_EMAIL", "reportes@landatech.org")

    from datetime import datetime, timezone
    for email in TEAM:
        temp = secrets.token_urlsafe(9)
        existing = await db.users.find_one({"email": email})
        if existing:
            await db.users.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "hashed_password": hash_password(temp),
                    "acts_for_user_id": DPG_TENANT_ID,
                    "must_change_password": True,
                }},
            )
            accion = "actualizada"
        else:
            await db.users.insert_one({
                "email": email,
                "hashed_password": hash_password(temp),
                "role": "client",
                "company_name": "DPG Seguros",
                "acts_for_user_id": DPG_TENANT_ID,
                "must_change_password": True,
                "created_at": datetime.now(timezone.utc),
            })
            accion = "creada"

        try:
            await asyncio.to_thread(
                mailersend_send,
                from_addr, "Landa Tech", email, "",
                "Tu acceso al dashboard de cobranza DPG — Landa Tech",
                _email_html(email, temp),
            )
            print(f"{email}: cuenta {accion}, correo ENVIADO")
        except Exception as exc:
            print(f"{email}: cuenta {accion}, correo FALLO -> {str(exc)[:150]}")

    db.client.close()


asyncio.run(main())
