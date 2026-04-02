# 🔒 Security Audit & OAuth Refactor

## 📋 Problemas Identificados

### 1. **CRITICAL: OAuth URL Exposure**
**Ubicación:** `backend/main.py` líneas 627, 717

```python
# ❌ INSEGURO
redirect_url = f"{frontend_url}/?oauth_success=true&oauth_email={email}&oauth_provider=gmail&oauth_tokens={tokens}"
```

**Riesgos:**
- Email en historial del navegador
- Tokens encriptados pero visibles en URL
- Exposed en server logs
- XSS/CSRF attack surface

---

## ✅ SOLUCIÓN: Secure OAuth Flow

### Backend Changes (`main.py`)

**CAMBIO 1:** Usar sesiones HTTP-only en lugar de URL params

```python
# Después del OAuth callback, crear sesión segura:

from fastapi.responses import RedirectResponse
from itsdangerous import URLSafeTimedSerializer

# En /auth/gmail/callback:
session_id = generate_secure_session(user_id, email, provider)

# ✅ SEGURO - Solo session_id en URL
redirect_url = f"{frontend_url}/auth/oauth-callback?session_id={session_id}"

# El session_id expira en 5 minutos
```

**CAMBIO 2:** Nuevo endpoint para recuperar datos de OAuth

```python
@app.post("/api/auth/oauth-confirm")
async def confirm_oauth(request: Request, token: str = Depends(...)):
    """
    Frontend llama aquí DESPUÉS de recibir session_id
    Backend valida sesión y retorna datos
    """
    session = db.sessions.get(token)
    if not session or session.expired:
        raise HTTPException(status_code=401)
    
    return {
        "email": session.email,
        "provider": session.provider,
        "tokens_encrypted": session.tokens_encrypted
    }
```

---

### Frontend Changes (`ClientDashboard.tsx`)

**CAMBIO 1:** Procesar session_id en lugar de parámetros

```typescript
// ✅ SEGURO - Solo recupera session_id de URL
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  const sessionId = params.get('session_id');
  
  if (sessionId) {
    // Limpiar URL INMEDIATAMENTE
    window.history.replaceState({}, document.title, window.location.pathname);
    
    // Confirmar OAuth vía POST seguro
    apiFetch(`${API}/api/auth/oauth-confirm`, {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId })
    })
      .then(r => r.json())
      .then(data => {
        // Backend maneja tokens, frontend solo actualiza estado
        setEmailConnected(true);
        setEmailAddress(data.email);
      });
  }
}, []);
```

---

## 📁 Problemas de Estructura de Paths

### Paths Caóticos Encontrados:
- `/auth/gmail/connect` — OK
- `/auth/gmail/callback` — OK
- `/api/leads` — OK
- `/api/me/email-status` — OK
- `/?oauth_success=true` — ❌ ROOT PATH (debería limpiarse)
- `/api/cobranza/status` — OK
- `/api/me/email-connect` — Debería ser POST, name confuso

### Solución: Estructura RESTful Coherente

```
✅ SEGURO Y COHERENTE:

Auth:
  GET  /auth/gmail/login      → Redirect a Google
  GET  /auth/gmail/callback   → Process OAuth, return session_id en URL
  POST /api/auth/oauth-confirm → Validar session_id, retornar datos

Email:
  POST /api/email/connect       → Initiate OAuth flow
  GET  /api/email/status        → Get connection status
  DELETE /api/email/disconnect  → Disconnect
  POST /api/email/test          → Send test email

Leads:
  GET  /api/leads              → List all
  PATCH /api/leads/{id}/approve
  PATCH /api/leads/{id}/reject
  GET  /api/leads/{id}/dossier

Cobranza:
  GET  /api/cobranza/status
  POST /api/cobranza/campaign
```

---

## 🔐 Additional Security Improvements

### 1. **HTTP-Only Cookies para Tokens**
```python
from fastapi.responses import JSONResponse

response = JSONResponse({"status": "success"})
response.set_cookie(
    "oauth_refresh_token",
    value=encrypted_token,
    httponly=True,      # No accessible via JS (XSS safe)
    secure=True,        # Only over HTTPS
    samesite="strict",  # CSRF protection
    max_age=7*24*3600   # 7 days
)
return response
```

### 2. **CSRF Protection**
```python
from fastapi_csrf_protect import CsrfProtect

@app.post("/api/email/connect")
async def email_connect(csrf_protect: CsrfProtect = Depends()):
    await csrf_protect.validate_csrf()
    # ... process
```

### 3. **Rate Limiting en OAuth**
```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@app.get("/auth/gmail/callback")
@limiter.limit("5/minute")
async def gmail_callback(code: str):
    # Prevent brute force
    pass
```

### 4. **Session Timeouts**
```python
# Sessions expiran automáticamente en 5 minutos
class OAuthSession:
    created_at: datetime
    
    @property
    def is_expired(self) -> bool:
        return (datetime.utcnow() - self.created_at).seconds > 300
```

---

## 📊 Before vs After

| Aspecto | ANTES ❌ | DESPUÉS ✅ |
|---------|---------|----------|
| **OAuth URL** | `/?oauth_email=user@gmail.com&oauth_tokens=encrypted...` | `/?session_id=abc123` |
| **Token Storage** | URL (exposed) | HTTP-only Cookie (secure) |
| **Session Mgmt** | Stateless (inseguro) | Stateful con timeout (seguro) |
| **API Structure** | Caótica `/api/me/email-*` | RESTful `/api/email/*` |
| **CSRF** | No protegido | Token CSRF requerido |
| **XSS** | Vulnerable (JS ve params) | Mitigado (solo server vé tokens) |

---

## 🚀 Implementation Roadmap

### Phase 1: Backend Refactor (2-3 horas)
- [ ] Crear endpoints OAuth seguros
- [ ] Implementar HTTP-only cookies
- [ ] Agregar session management mit timeout
- [ ] Refactorizar rutas API

### Phase 2: Frontend Refactor (1-2 horas)
- [ ] Usar session_id en lugar de params
- [ ] Limpiar URL después de procesar
- [ ] Agregar CSRF tokens
- [ ] Actualizar apiFetch para cookies

### Phase 3: Testing (1 hora)
- [ ] Verificar flujo OAuth completo
- [ ] XSS prevention tests
- [ ] CSRF protection tests
- [ ] Session expiration tests

---

## ⚠️ CRITICAL: Do Not Commit Sensitive Data

**Ya están en el repo:**
- `google_service_account.json` con credentials
- Email OAuth tokens potentially exposed

**ACCIONES URGENTES:**
1. `git filter-branch` para remover del historio
2. Regenerar credenciales en Google Cloud
3. Agregar `.gitignore` entries
4. Usar `--cached` para file history

```bash
# Remover file del historial:
git filter-repo --invert-paths --path google_service_account.json
git filter-repo --invert-paths --path .env

# Regenerar credenciales en Google Cloud Console
```

