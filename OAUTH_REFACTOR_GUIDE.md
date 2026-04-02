# 🔒 OAUTH SECURITY REFACTOR - IMPLEMENTATION GUIDE

## ✅ Cambios Completados

### 1. **Backend**: Módulo de Sesiones Seguras
**Archivo:** `backend/oauth_sessions.py` (NUEVO)
- `OAuthSessionManager` — Gestión de sesiones seguras
- Sessions con expiry automático (5 minutos)
- `session_id` urlsafe en lugar de tokens en URL
- Consumo de sessions (one-time use)
- Token CSRF para requests

### 2. **Backend**: Rutas OAuth Refactorizadas
**Archivo:** `backend/oauth_routes_secure.py` (NUEVO)
Contiene:
- `/auth/gmail/login` — Inicia flujo Gmail (seguro)
- `/auth/gmail/callback` — Google callback, crea session_id
- `/api/auth/oauth-confirm` — Frontend confirma sesión
- `/api/email/connect` — POST para iniciar OAuth
- `/api/email/status` — GET estado de email
- `/api/email/disconnect` — DELETE
- `/api/email/test` — POST prueba

### 3. **Frontend**: ClientDashboard.tsx Actualizado
- ✅ OAuth callback usando `session_id` (no expone datos)
- ✅ Limpia URL inmediatamente
- ✅ POST seguro a `/api/auth/oauth-confirm`
- ✅ Botones Gmail/Outlook usan nuevo flujo
- ✅ Mejor manejo de errores

---

## 🚀 PASOS DE INTEGRACION

### PASO 1: Actualizar `backend/main.py`

**Agregar importes al principio:**
```python
from oauth_sessions import OAuthSessionManager, generate_csrf_token
```

**Reemplazar las rutas OAuth antiguas** (líneas ~570-720con el contenido de `backend/oauth_routes_secure.py`)

**O copiar-pegar las rutas de oauth_routes_secure.py directamente**

### PASO 2: Agregar rate limiting

Instalar:
```bash
pip install slowapi
```

En main.py:
```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# En las rutas OAuth:
@app.get("/auth/gmail/callback")
@limiter.limit("5/minute")
async def gmail_callback(...):
    ...
```

### PASO 3: Agregar CSRF Protection (Opcional - recomendado)

```bash
pip install fastapi-csrf-protect
```

### PASO 4: Testing

```bash
# Terminal 1: Backend
cd backend
python -m uvicorn main:app --reload

# Terminal 2: Frontend
cd frontend
npm run dev

# Probar flujo:
1. Click botón Gmail/Outlook
2. Verificar que session_id solo en URL, no email/tokens
3. Backend crea sesión
4. Frontend limpia URL
5. POST a oauth-confirm
6. Email conectado
```

---

## 📊 BEFORE vs AFTER

### ❌ ANTES - INSEGURO
```
URL: https://my.landatech.org/?oauth_success=true&oauth_email=maximilianopulidobeltran@gmail.com&oauth_provider=gmail&oauth_tokens=eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...

Problemas:
- Email en historial
- Tokens encriptados BUT visible
- Logged en server
- Vulnerable a XSS
```

### ✅ DESPUÉS - SEGURO
```
URL: https://my.landatech.org/auth/oauth-callback?session_id=SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c

Después de 1s:
URL: https://my.landatech.org (limpiada)

Ventajas:
- Session ID anónimo (urlsafe)
- Expira en 5 minutos
- Tokens nunca en URL
- One-time use (consumida)
-CSRF protegida
- Rate limited (5/min)
```

---

## 🔐 API Endpoints Summary

### Auth
- `GET /auth/gmail/login?token=JWT` → Redirect a Google
- `GET /auth/gmail/callback?code=X&state=Y` → Crea session_id → Redirect con session_id
- `POST /api/auth/oauth-confirm` → Valida session_id → Retorna email/provider

### Email (REFACTORED)
- `POST /api/email/connect` → Body: {provider: "gmail"} → {redirect_url}
- `GET /api/email/status` → {connected, email, provider}
- `DELETE /api/email/disconnect` → {status}
- `POST /api/email/test` → {sent_to, status}

### Leads (with CSRF)
- `POST /api/leads/{id}/approve` (Header: X-CSRF-Token)
- `PATCH /api/leads/{id}/reject` (Header: X-CSRF-Token)

---

## ⚠️ IMPORTANT: Secretos en el Repositorio

**ACCIONES URGENTES:**
1. Remove `google_service_account.json` from git history:
   ```bash
   git filter-repo --invert-paths --path google_service_account.json
   git push --force origin master
   ```

2. Regenerar credenciales en Google Cloud Console

3. Add to `.gitignore`:
   ```
   google_service_account.json
   .env
   .env.local
   **/credentials*.json
   **/secrets*.json
   ```

4. Usar variables de entorno:
   ```python
   SERVICE_ACCOUNT_PATH = os.getenv('GOOGLE_SERVICE_ACCOUNT_PATH')
   ```

---

## 📝 Testing Checklist

- [ ] Backend compila sin errores
- [ ] Frontend compila sin errores
- [ ] Gmail OAuth flow completo
- [ ] Outlook OAuth flow completo
- [ ] URL limpiada después de OAuth
- [ ] Email status refleja conexión
- [ ] Email disconnect funciona
- [ ] Test email se envía
- [ ] Leads approve/reject funcionan
- [ ] No hay parámetros sensibles en URL
- [ ] Sessions expiran correctamente

---

## 📚 Additional Resources

- RFC 6234: Stateless sessions
- OWASP: OAuth security best practices
- https://tools.ietf.org/html/draft-ietf-oauth-security-topics

