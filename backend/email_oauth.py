"""
email_oauth.py — OAuth flows para Gmail y Outlook (Microsoft)
Permite que cada usuario conecte su cuenta de email personal para enviar correos.

Env vars requeridas:
  - GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
  - MICROSOFT_CLIENT_ID, MICROSOFT_CLIENT_SECRET
  - OAUTH_REDIRECT_BASE_URL (ej: https://tudominio.com)
  - FERNET_KEY (encriptación de tokens)
"""

import os
import json
import logging
from typing import Optional, Dict
from cryptography.fernet import Fernet
import secrets

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Encriptación de tokens
# ─────────────────────────────────────────────────────────────────────────────

def get_fernet_cipher() -> Fernet:
    """Obtiene la cipher de Fernet usando FERNET_KEY del env."""
    key = os.getenv("FERNET_KEY")
    if not key:
        raise RuntimeError("FERNET_KEY not configured in environment")
    return Fernet(key.encode())


def encrypt_tokens(tokens: Dict) -> str:
    """Encripta un diccionario de tokens a string seguro."""
    cipher = get_fernet_cipher()
    json_str = json.dumps(tokens)
    encrypted = cipher.encrypt(json_str.encode())
    return encrypted.decode()


def decrypt_tokens(encrypted: str) -> Dict:
    """Desencripta un string de tokens a diccionario."""
    cipher = get_fernet_cipher()
    try:
        decrypted = cipher.decrypt(encrypted.encode())
        return json.loads(decrypted.decode())
    except Exception as e:
        logger.error(f"[email_oauth] Token decryption failed: {e}")
        return {}


# ─────────────────────────────────────────────────────────────────────────────
# Google OAuth (Gmail)
# ─────────────────────────────────────────────────────────────────────────────

def get_gmail_auth_url(state: str) -> str:
    """Genera la URL de autorización de Google OAuth."""
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    redirect_uri = os.getenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8001") + "/auth/gmail/callback"

    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID not configured")

    scope = "https://www.googleapis.com/auth/gmail.send"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"


async def exchange_gmail_code(code: str) -> Optional[Dict]:
    """
    Intercambia el authorization code por access_token y refresh_token.
    Retorna { access_token, refresh_token, email } o None si falla.
    """
    import httpx

    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    redirect_uri = os.getenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8001") + "/auth/gmail/callback"

    if not client_id or not client_secret:
        logger.error("[email_oauth] GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET not configured")
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data=payload, timeout=10)
            data = resp.json()

            if "error" in data:
                logger.error(f"[email_oauth] Google token error: {data.get('error_description')}")
                return None

            # Decodificar el id_token para obtener el email
            id_token = data.get("id_token", "")
            email = None
            if id_token:
                import base64
                parts = id_token.split(".")
                if len(parts) == 3:
                    # Padding puede ser incorrecto
                    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
                    try:
                        payload_json = base64.urlsafe_b64decode(payload_b64)
                        payload_dict = json.loads(payload_json)
                        email = payload_dict.get("email")
                    except Exception as e:
                        logger.error(f"[email_oauth] Could not decode id_token: {e}")

            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "email": email or "unknown@gmail.com",
            }
    except Exception as e:
        logger.error(f"[email_oauth] Gmail token exchange failed: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Microsoft OAuth (Outlook)
# ─────────────────────────────────────────────────────────────────────────────

def get_outlook_auth_url(state: str) -> str:
    """Genera la URL de autorización de Microsoft OAuth."""
    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    redirect_uri = os.getenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8001") + "/auth/outlook/callback"

    if not client_id:
        raise RuntimeError("MICROSOFT_CLIENT_ID not configured")

    scope = "Mail.Send offline_access"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "prompt": "select_account",
    }

    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{query_string}"


async def exchange_outlook_code(code: str) -> Optional[Dict]:
    """
    Intercambia el authorization code por access_token y refresh_token (Outlook).
    Retorna { access_token, refresh_token, email } o None si falla.
    """
    import httpx

    client_id = os.getenv("MICROSOFT_CLIENT_ID")
    client_secret = os.getenv("MICROSOFT_CLIENT_SECRET")
    redirect_uri = os.getenv("OAUTH_REDIRECT_BASE_URL", "http://localhost:8001") + "/auth/outlook/callback"

    if not client_id or not client_secret:
        logger.error("[email_oauth] MICROSOFT_CLIENT_ID or MICROSOFT_CLIENT_SECRET not configured")
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": redirect_uri,
        "scope": "Mail.Send offline_access",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post("https://login.microsoftonline.com/common/oauth2/v2.0/token", data=payload, timeout=10)
            data = resp.json()

            if "error" in data:
                logger.error(f"[email_oauth] Outlook token error: {data.get('error_description')}")
                return None

            # Obtener el email del usuario (necesita otro request a Graph API)
            access_token = data.get("access_token")
            email = "unknown@outlook.com"
            if access_token:
                email = await _get_outlook_email(access_token)

            return {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token"),
                "email": email,
            }
    except Exception as e:
        logger.error(f"[email_oauth] Outlook token exchange failed: {e}")
        return None


async def _get_outlook_email(access_token: str) -> str:
    """Obtiene el email del usuario logueado en Outlook vía Microsoft Graph."""
    import httpx

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10
            )
            data = resp.json()
            return data.get("userPrincipalName", "unknown@outlook.com")
    except Exception as e:
        logger.error(f"[email_oauth] Could not fetch Outlook email: {e}")
        return "unknown@outlook.com"


# ─────────────────────────────────────────────────────────────────────────────
# Utilitarios
# ─────────────────────────────────────────────────────────────────────────────

def generate_oauth_state() -> str:
    """Genera un state random para CSRF protection en OAuth."""
    return secrets.token_urlsafe(32)
