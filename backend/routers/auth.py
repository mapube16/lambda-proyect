import os
import json
import base64
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query, Request, Body
from fastapi.responses import JSONResponse, RedirectResponse
from jose import JWTError, jwt
from pymongo.errors import DuplicateKeyError

from auth import (
    hash_password, verify_password, create_access_token,
    get_current_user, SECRET_KEY, ALGORITHM,
)
from database import (
    get_user_by_email, get_user_by_id, create_user, add_phone_to_user,
    create_registration_request, get_all_registration_requests,
    update_registration_request_status,
)
from models import UserCreate, RegistrationRequest
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Auth cookie helper ──────────────────────────────────────────────────────────
# secure=True means the browser only sends the cookie over HTTPS. On HTTP localhost
# (dev) that silently drops the cookie → every request is unauthenticated → 401 loop.
# Gate it on COOKIE_SECURE (default false for dev; set true in production/HTTPS).
_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").strip().lower() in ("1", "true", "yes")


def _set_auth_cookie(response, token: str) -> None:
    response.set_cookie(
        key="hive_token",
        value=token,
        httponly=True,
        secure=_COOKIE_SECURE,
        samesite="lax",
        max_age=int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440")) * 60,
        path="/",
    )


class AddPhoneRequest(BaseModel):
    phone: str


# ── Register / Login ─────────────────────────────────────────────────────────

@router.post("/auth/register", status_code=201)
async def register(user: UserCreate):
    existing = await get_user_by_email(user.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(user.password)
    try:
        created = await create_user(
            user.email, hashed,
            role=user.role or "client",
            full_name=user.full_name,
            company_name=user.company_name,
            phone=user.phone,
            country=user.country,
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=400, detail="Email already registered")
    return {"id": created["id"], "email": created["email"]}


@router.post("/auth/login")
async def login(user: UserCreate, request: Request):
    from rate_limiting import check_login_rate_limit
    check_login_rate_limit(user.email, request)
    db_user = await get_user_by_email(user.email)
    if not db_user or not verify_password(user.password, db_user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password",
                            headers={"WWW-Authenticate": "Bearer"})
    token = create_access_token(data={"sub": str(db_user["id"]), "role": db_user.get("role", "client")})
    response_data = {
        "user_id": str(db_user["id"]),
        "role": db_user.get("role", "client"),
        "email": db_user["email"],
        "authenticated": True,
        "access_token": token,
    }
    response = JSONResponse(content=response_data, status_code=200)
    _set_auth_cookie(response, token)
    return response


@router.post("/auth/dev-token")
async def dev_token():
    """Development endpoint: returns a token for dpg.seguros@gmail.com without rate limiting"""
    from datetime import timedelta
    user_id = "6a1aec6e89dbf2987cef054e"
    role = "client"
    # Token largo para desarrollo/demo (evita expiración a los 15 min mientras se prueba).
    token = create_access_token(data={"sub": user_id, "role": role}, expires_delta=timedelta(hours=12))
    return {
        "user_id": user_id,
        "role": role,
        "email": "dpg.seguros@gmail.com",
        "authenticated": True,
        "access_token": token,
    }


@router.get("/auth/me")
async def auth_me(current_user: dict = Depends(get_current_user)):
    """Validate the httpOnly cookie and return the current user's identity.
    The frontend calls this on load to rehydrate the session after a reload
    (the JWT lives only in the cookie, so there's nothing in JS to read directly).
    Returns 401 if the cookie is missing/expired."""
    user_id = str(current_user["user_id"])
    db_user = await get_user_by_id(user_id)
    if not db_user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "user_id": user_id,
        "role": db_user.get("role", current_user.get("role", "client")),
        "email": db_user.get("email"),
        "authenticated": True,
    }


@router.post("/api/ws-ticket")
async def ws_ticket(current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    ticket = create_access_token(
        data={"sub": str(current_user["user_id"]), "role": current_user.get("role", "client")},
        expires_delta=timedelta(seconds=30),
    )
    return {"ticket": ticket}


@router.post("/auth/google-login")
async def google_login(data: dict):
    import urllib.request
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="Token requerido")
    try:
        url = f"https://www.googleapis.com/oauth2/v1/userinfo?access_token={token}"
        with urllib.request.urlopen(url) as response:
            user_info = json.loads(response.read().decode())
        email = user_info.get("email")
        name = user_info.get("name", "")
        if not email:
            raise HTTPException(status_code=400, detail="Email no disponible en token de Google")
        db_user = await get_user_by_email(email)
        if not db_user:
            hashed_pw = hash_password("google_oauth_no_password_needed")
            try:
                db_user = await create_user(email, hashed_pw, role="client", full_name=name)
            except DuplicateKeyError:
                db_user = await get_user_by_email(email)
        token = create_access_token(data={"sub": str(db_user["id"]), "role": db_user.get("role", "client")})
        response_data = {
            "user_id": str(db_user["id"]),
            "role": db_user.get("role", "client"),
            "email": db_user["email"],
            "authenticated": True,
        }
        response = JSONResponse(content=response_data, status_code=200)
        _set_auth_cookie(response, token)
        return response
    except Exception as e:
        logger.error("[google_login] Authentication error: %s", e)
        raise HTTPException(status_code=401, detail="Invalid authentication token")


@router.post("/auth/register-request", status_code=202)
async def register_request(req: RegistrationRequest, request: Request):
    from rate_limiting import check_registration_rate_limit
    check_registration_rate_limit(request)
    result = await create_registration_request(
        email=req.email, full_name=req.full_name, company_name=req.company_name,
        phone=req.phone, country=req.country, role=req.role or "user", message=req.message,
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return {"message": "Registration request submitted successfully. Our team will contact you soon.", "status": "pending"}


# ── Admin ─────────────────────────────────────────────────────────────────────

@router.get("/admin/registration-requests")
async def get_registration_requests(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff only")
    requests = await get_all_registration_requests()
    return requests


@router.patch("/admin/registration-requests/{request_id}/status")
async def update_request_status(
    request_id: str,
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user),
):
    if current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="Staff only")
    new_status = body.get("status")
    if new_status not in ("approved", "rejected", "pending"):
        raise HTTPException(status_code=400, detail="Invalid status")
    updated = await update_registration_request_status(request_id, new_status)
    if not updated:
        raise HTTPException(status_code=404, detail="Request not found")
    return {"ok": True, "status": new_status}


# ── Users ─────────────────────────────────────────────────────────────────────

@router.patch("/api/users/{user_id}/phones", status_code=200)
async def api_add_phone_to_user(
    user_id: str,
    req: AddPhoneRequest,
    current_user: dict = Depends(get_current_user),
):
    if current_user["user_id"] != user_id and current_user.get("role") != "staff":
        raise HTTPException(status_code=403, detail="No autorizado")
    ok = await add_phone_to_user(user_id, req.phone)
    if not ok:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"success": True, "added": req.phone}


# ── Email OAuth ───────────────────────────────────────────────────────────────

@router.get("/auth/gmail/connect")
async def gmail_connect_start(current_user: dict = Depends(get_current_user)):
    from email_oauth import get_gmail_auth_url, generate_oauth_state
    try:
        user_data = {"sub": current_user["user_id"], "role": current_user.get("role", "client")}
        token = create_access_token(data=user_data)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")
    random_state = generate_oauth_state()
    state_encoded = base64.b64encode(json.dumps({"state": random_state, "token": token}).encode()).decode()
    return RedirectResponse(url=get_gmail_auth_url(state_encoded))


@router.get("/auth/gmail/callback")
async def gmail_callback(code: str = Query(...), state: str = Query(...)):
    from email_oauth import exchange_gmail_code, encrypt_tokens
    from database import save_email_oauth_tokens
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    tokens = await exchange_gmail_code(code)
    if not tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
    email = tokens.get("email", "unknown@gmail.com")
    tokens_encrypted = encrypt_tokens({"access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"]})
    user_id = None
    try:
        state_data = json.loads(base64.b64decode(state).decode())
        jwt_token = state_data.get("token")
        if jwt_token:
            payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub"))
    except Exception as e:
        logger.error("[gmail_callback] Failed to decode state: %s", e)
    if user_id:
        try:
            await save_email_oauth_tokens(user_id=user_id, provider="gmail", tokens_encrypted=tokens_encrypted, email_sender=email)
        except Exception as e:
            logger.error("[gmail_callback] Failed to save tokens: %s", e)
            return RedirectResponse(url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}?oauth_success=false&error=save_failed")
    return RedirectResponse(url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/?oauth_success={'true' if user_id else 'false'}&oauth_provider=gmail")


@router.get("/auth/outlook/connect")
async def outlook_connect_start(current_user: dict = Depends(get_current_user)):
    from email_oauth import get_outlook_auth_url, generate_oauth_state
    try:
        user_data = {"sub": current_user["user_id"], "role": current_user.get("role", "client")}
        token = create_access_token(data=user_data)
    except Exception as e:
        raise HTTPException(status_code=401, detail="Authentication failed")
    random_state = generate_oauth_state()
    state_encoded = base64.b64encode(json.dumps({"state": random_state, "token": token}).encode()).decode()
    return RedirectResponse(url=get_outlook_auth_url(state_encoded))


@router.get("/auth/outlook/callback")
async def outlook_callback(code: str = Query(...), state: str = Query(...)):
    from email_oauth import exchange_outlook_code, encrypt_tokens
    from database import save_email_oauth_tokens
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    tokens = await exchange_outlook_code(code)
    if not tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
    email = tokens.get("email", "unknown@outlook.com")
    tokens_encrypted = encrypt_tokens({"access_token": tokens["access_token"], "refresh_token": tokens["refresh_token"]})
    user_id = None
    try:
        state_data = json.loads(base64.b64decode(state).decode())
        jwt_token = state_data.get("token")
        if jwt_token:
            payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub"))
    except Exception as e:
        logger.error("[outlook_callback] Failed to decode state: %s", e)
    if user_id:
        try:
            await save_email_oauth_tokens(user_id=user_id, provider="outlook", tokens_encrypted=tokens_encrypted, email_sender=email)
        except Exception as e:
            return RedirectResponse(url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}?oauth_success=false&error=save_failed")
    return RedirectResponse(url=f"{os.getenv('FRONTEND_URL', 'http://localhost:5173')}/?oauth_success={'true' if user_id else 'false'}&oauth_provider=outlook")


# ── Me / Email ────────────────────────────────────────────────────────────────

@router.get("/api/me/email-status")
async def email_status(current_user: dict = Depends(get_current_user)):
    from database import get_email_oauth_tokens
    tokens_info = await get_email_oauth_tokens(current_user.get("user_id"))
    if not tokens_info:
        return {"connected": False, "provider": None, "email": None}
    return {"connected": True, "provider": tokens_info["provider"], "email": tokens_info["email_sender_address"]}


@router.delete("/api/me/email-disconnect")
async def email_disconnect(current_user: dict = Depends(get_current_user)):
    from database import delete_email_oauth_tokens
    success = await delete_email_oauth_tokens(current_user.get("user_id"))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to disconnect email")
    return {"message": "Email account disconnected", "connected": False}


@router.get("/api/me/email-stats")
async def email_stats(current_user: dict = Depends(get_current_user)):
    from database import get_email_stats
    return await get_email_stats(current_user.get("user_id"))


@router.post("/api/mailersend/webhook")
async def mailersend_webhook(request: Request):
    from database import save_email_event
    import hmac, hashlib
    body = await request.body()
    webhook_secret = os.getenv("MAILERSEND_WEBHOOK_SECRET", "")
    if webhook_secret:
        signature = request.headers.get("X-MailerSend-Signature", "")
        expected_sig = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
        if signature != expected_sig:
            raise HTTPException(status_code=401, detail="Invalid signature")
    data = await request.json()
    event_type = data.get("type", "")
    event_data = data.get("data", {})
    message_id = event_data.get("message_id") or event_data.get("id")
    if message_id:
        await save_email_event(lead_id=event_data.get("lead_id", ""), event_type=event_type, message_id=message_id)
    return {"status": "ok"}


@router.post("/api/me/email-connect")
async def email_connect_finalize(
    current_user: dict = Depends(get_current_user),
    email: str = Body(...),
    provider: str = Body(...),
    tokens_encrypted: str = Body(...),
):
    from database import save_email_oauth_tokens
    if provider not in ("gmail", "outlook"):
        raise HTTPException(status_code=400, detail="Invalid provider")
    success = await save_email_oauth_tokens(user_id=current_user.get("user_id"), provider=provider, tokens_encrypted=tokens_encrypted, email_sender=email)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save email configuration")
    return {"message": "Email connected successfully", "provider": provider, "email": email}


@router.post("/api/me/smtp-config")
async def save_smtp_config(
    current_user: dict = Depends(get_current_user),
    email: str = Body(...),
    password: str = Body(...),
    smtp_host: str = Body(...),
    smtp_port: int = Body(...),
):
    from database import save_smtp_config as _save_smtp
    from email_oauth import encrypt_tokens
    if not all([email, password, smtp_host, smtp_port]):
        raise HTTPException(status_code=400, detail="Missing required fields")
    config_encrypted = encrypt_tokens({"email": email, "password": password, "smtp_host": smtp_host, "smtp_port": smtp_port})
    success = await _save_smtp(current_user.get("user_id"), config_encrypted)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save SMTP configuration")
    return {"message": "SMTP configuration saved successfully", "email": email, "configured": True}


@router.get("/api/me/smtp-status")
async def get_smtp_status(current_user: dict = Depends(get_current_user)):
    from database import get_smtp_status as _get_smtp_status
    return await _get_smtp_status(current_user.get("user_id"))


@router.delete("/api/me/smtp-disconnect")
async def smtp_disconnect(current_user: dict = Depends(get_current_user)):
    from database import delete_smtp_config
    success = await delete_smtp_config(current_user.get("user_id"))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to disconnect SMTP")
    return {"message": "SMTP configuration removed", "configured": False}


@router.get("/api/me/email-template")
async def get_email_template(current_user: dict = Depends(get_current_user)):
    from database import get_email_template as _get_tpl
    return await _get_tpl(current_user.get("user_id")) or {}


@router.post("/api/me/email-template")
async def save_email_template(current_user: dict = Depends(get_current_user), template: dict = Body(...)):
    from database import save_email_template as _save_tpl
    success = await _save_tpl(current_user.get("user_id"), template)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save email template")
    return {"message": "Template saved successfully", "template": template}


@router.post("/api/me/email-test")
async def send_test_email(
    current_user: dict = Depends(get_current_user),
    to: Optional[str] = Body(None, embed=True),
):
    """Envía un correo de prueba (a la dirección 'to' o, si no, al propio remitente).
    Soporta buzón OAuth (Gmail/Outlook) y SMTP — lo que esté configurado."""
    from database import get_email_oauth_tokens, get_smtp_config
    from email_oauth import decrypt_tokens
    user_id = current_user.get("user_id")
    subject = "Correo de prueba - Landa"

    # 1) OAuth (Gmail/Outlook)
    tokens_info = await get_email_oauth_tokens(user_id)
    if tokens_info:
        from email_sender_oauth import send_email_oauth
        provider = tokens_info.get("provider")
        sender_email = tokens_info.get("email_sender_address")
        dest = (to or "").strip() or sender_email
        body = f"""<h2>¡Funciona! ✅</h2><p>Tu conexión con {provider.title()} está bien configurada. Enviado desde <strong>{sender_email}</strong>.</p><hr><p style="font-size:12px;color:#999;">Landa — correo de prueba.</p>"""
        try:
            tokens = decrypt_tokens(tokens_info.get("encrypted_tokens"))
            ok = await send_email_oauth(provider=provider, access_token=tokens.get("access_token"), to_email=dest, to_name=dest.split("@")[0], subject=subject, html_body=body, sender_email=sender_email, sender_name="Landa")
            if not ok:
                raise HTTPException(status_code=502, detail="El proveedor rechazó el envío de prueba.")
            return {"message": f"Correo de prueba enviado a {dest}", "sent_to": dest, "via": provider}
        except HTTPException:
            raise
        except Exception as e:
            logger.error("[test_email oauth] %s", e)
            raise HTTPException(status_code=502, detail="No se pudo enviar la prueba (OAuth).")

    # 2) SMTP
    smtp_enc = await get_smtp_config(user_id)
    if smtp_enc:
        try:
            cfg = decrypt_tokens(smtp_enc)
        except Exception:
            raise HTTPException(status_code=500, detail="No se pudo leer la configuración SMTP.")
        sender_email = cfg.get("email")
        dest = (to or "").strip() or sender_email
        from email_sender import send_email
        try:
            ok = await send_email(
                to=dest, subject=subject,
                body="¡Funciona! ✅ Tu conexión SMTP está bien configurada. — Landa (correo de prueba)",
                sender_name="Landa", sender_email=sender_email,
                smtp_host=cfg.get("smtp_host"), smtp_port=int(cfg.get("smtp_port") or 587),
                smtp_user=cfg.get("email"), smtp_password=cfg.get("password"),
            )
        except Exception as e:
            logger.error("[test_email smtp] %s", e)
            raise HTTPException(status_code=502, detail="Error enviando por SMTP.")
        if not ok:
            host = (cfg.get("smtp_host") or "").lower()
            if "gmail" in host:
                detail = ("Gmail rechazó la conexión. Casi siempre es la contraseña: Gmail exige una "
                          "App Password (no tu contraseña normal). Actívala en Cuenta de Google → "
                          "Seguridad → Contraseñas de aplicaciones, y pégala aquí.")
            else:
                detail = "El servidor SMTP rechazó el envío. Revisa host, puerto, usuario y contraseña."
            raise HTTPException(status_code=502, detail=detail)
        return {"message": f"Correo de prueba enviado a {dest}", "sent_to": dest, "via": "smtp"}

    raise HTTPException(status_code=400, detail="No hay buzón configurado. Conecta Gmail/Outlook o configura SMTP primero.")
