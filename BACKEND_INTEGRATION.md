# 🔧 BACKEND INTEGRATION INSTRUCTIONS

## Step 1: Import New Modules

Add these imports to the top of `backend/main.py` (around line 40):

```python
from oauth_sessions import OAuthSessionManager, generate_csrf_token, verify_csrf_token
```

## Step 2: Replace OAuth Routes

**FIND AND DELETE** these old routes in `backend/main.py`:
- Lines ~555-635: `@app.get("/auth/gmail/connect")` → `async def gmail_connect_start(...)`
- Lines ~640-730: `@app.get("/auth/outlook/connect")` → `async def outlook_connect_start(...)`
- Lines ~735-760: Related helper routes

**COPY-PASTE THIS INSTEAD** (all the routes from `oauth_routes_secure.py`):

---

## SECURE OAUTH ROUTES (Copy this into main.py)

```python
# ================================================================================
# ✅ SECURE EMAIL OAUTH ROUTES (REFACTORED)
# ================================================================================

@app.get("/auth/gmail/login")
async def gmail_login_start(token: str = Query(...)):
    """Initiate Gmail OAuth - token validated for security"""
    from email_oauth import get_gmail_auth_url, generate_oauth_state
    import base64
    import json
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    random_state = generate_oauth_state()
    state_data = {
        "state": random_state,
        "token": token
    }
    state_json = json.dumps(state_data)
    state_encoded = base64.b64encode(state_json.encode()).decode()
    
    auth_url = get_gmail_auth_url(state_encoded)
    return RedirectResponse(url=auth_url)


@app.get("/auth/gmail/callback")
async def gmail_callback(code: str = Query(...), state: str = Query(...)):
    """✅ SECURE: Google OAuth callback - creates session_id instead of exposing data"""
    from email_oauth import exchange_gmail_code, encrypt_tokens
    from database import save_email_oauth_tokens
    import base64
    import json
    
    if not code:
        raise HTTPException(status_code=400, detail="Authorization code not provided")
    
    tokens = await exchange_gmail_code(code)
    if not tokens:
        raise HTTPException(status_code=400, detail="Failed to exchange authorization code")
    
    email = tokens.get("email", "unknown@gmail.com")
    tokens_encrypted = encrypt_tokens({
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
    })
    
    user_id = None
    try:
        state_json = base64.b64decode(state).decode()
        state_data = json.loads(state_json)
        jwt_token = state_data.get("token")
        
        if jwt_token:
            payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub"))
            logger.info(f"[gmail_callback] Decoded JWT, user_id={user_id}")
    except Exception as e:
        logger.error(f"[gmail_callback] Failed to decode state: {e}")
    
    if user_id:
        try:
            await save_email_oauth_tokens(
                user_id=user_id,
                provider="gmail",
                tokens_encrypted=tokens_encrypted,
                email_sender=email
            )
            logger.info(f"[gmail_callback] Saved OAuth tokens for user {user_id} with email {email}")
        except Exception as e:
            logger.error(f"[gmail_callback] Failed to save tokens: {e}")
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
            return RedirectResponse(
                url=f"{frontend_url}/auth/oauth-error?reason=save_failed"
            )
    
    # ✅ SECURE: Create session_id, don't expose email/tokens in URL
    session_id = OAuthSessionManager.create_session(
        user_id=user_id or "unknown",
        email=email,
        provider="gmail",
        tokens_encrypted=tokens_encrypted
    )
    
    frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
    redirect_url = f"{frontend_url}/auth/oauth-callback?session_id={session_id}"
    return RedirectResponse(url=redirect_url)


@app.post("/api/auth/oauth-confirm")
async def oauth_confirm(request: Request):
    """✅ SECURE: Confirm OAuth session and get session data (one-time use)"""
    try:
        body = await request.json()
        session_id = body.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")
        
        # Consume session (delete after use - one-time)
        session_data = OAuthSessionManager.consume_session(session_id)
        
        if not session_data:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        return {
            "email": session_data["email"],
            "provider": session_data["provider"],
            "user_id": session_data["user_id"],
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[oauth_confirm] Error: {e}")
        raise HTTPException(status_code=500, detail="oauth_confirm failed")


# ================================================================================
# ✅ REFACTORED EMAIL ROUTES (update /api/me/email-* → /api/email/*)
# ================================================================================

@app.get("/api/email/status")
async def get_email_status(current_user: dict = Depends(get_current_user)):
    """Get email connection status"""
    from database import get_email_oauth_tokens
    
    try:
        tokens_info = await get_email_oauth_tokens(current_user["user_id"])
        
        if not tokens_info:
            return {"connected": False, "email": None}
        
        return {
            "connected": True,
            "email": tokens_info.get("email"),
            "provider": tokens_info.get("provider"),
        }
    except Exception as e:
        logger.error(f"[get_email_status] Error: {e}")
        return {"connected": False, "email": None}


@app.delete("/api/email/disconnect")
async def disconnect_email(current_user: dict = Depends(get_current_user)):
    """Disconnect email account"""
    from database import delete_email_oauth_tokens
    
    try:
        success = await delete_email_oauth_tokens(current_user["user_id"])
        return {"status": "success" if success else "failed"}
    except Exception as e:
        logger.error(f"[disconnect_email] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect")


@app.post("/api/email/test")
async def test_email(current_user: dict = Depends(get_current_user)):
    """Send test email"""
    from database import get_email_oauth_tokens
    from mailer import send_email_oauth
    
    try:
        tokens_info = await get_email_oauth_tokens(current_user["user_id"])
        if not tokens_info:
            raise HTTPException(status_code=400, detail="Email not configured")
        
        email = tokens_info["email"]
        result = await send_email_oauth(
            user_id=current_user["user_id"],
            to_email=email,
            subject="Test Email from Landa",
            html="<p>✅ Your email integration is working correctly!</p>"
        )
        
        return {"sent_to": email, "status": "success" if result else "failed"}
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[test_email] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send test email")


@app.post("/api/email/connect")
async def initiate_email_connect(
    body: dict = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Initiate email connection with provider"""
    provider = body.get("provider", "").lower()
    
    if provider == "gmail":
        auth_token = create_access_token({"sub": current_user["user_id"]})
        login_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/auth/gmail/login?token={auth_token}"
        return {"redirect_url": login_url}
    elif provider == "outlook":
        auth_token = create_access_token({"sub": current_user["user_id"]})
        login_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/auth/outlook/login?token={auth_token}"
        return {"redirect_url": login_url}
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")
```

---

## Step 3: Update Outlook Routes (Similar to Gmail)

Replace old `/auth/outlook/connect` and `/auth/outlook/callback` with:

```python
@app.get("/auth/outlook/login")
async def outlook_login_start(token: str = Query(...)):
    """Initiate Outlook OAuth"""
    from email_oauth import get_outlook_auth_url, generate_oauth_state
    import base64
    import json
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    random_state = generate_oauth_state()
    state_data = {"state": random_state, "token": token}
    state_json = json.dumps(state_data)
    state_encoded = base64.b64encode(state_json.encode()).decode()
    
    auth_url = get_outlook_auth_url(state_encoded)
    return RedirectResponse(url=auth_url)


@app.get("/auth/outlook/callback")
async def outlook_callback(code: str = Query(...), state: str = Query(...)):
    """✅ SECURE: Outlook OAuth callback"""
    from email_oauth import exchange_outlook_code, encrypt_tokens
    from database import save_email_oauth_tokens
    import base64
    import json
    
    # Same pattern as gmail_callback
    # ...exchange tokens...
    # ...save via OAuthSessionManager...
    # ...return session_id...
```

---

## Step 4: Remove Old Routes

Delete these if they exist:
- ❌ `/api/me/email-status`
- ❌ `/api/me/email-disconnect`
- ❌ `/api/me/email-test`
- ❌ `/api/me/email-connect`

---

## Step 5: Testing

```bash
# Backend
cd backend
python -m uvicorn main:app --reload

# Frontend (in another terminal)
cd frontend
npm run dev

# Test flow:
1. Click Gmail/Outlook
2. Verify URL only has ?session_id=...
3. After OAuth, URL cleans to no params
4. Email shows as connected
```

---

## ✅ Verification Checklist

- [ ] oauth_sessions.py is in backend/
- [ ] New routes added to main.py
- [ ] Old routes removed from main.py
- [ ] Frontend builds without errors
- [ ] Backend starts without errors
- [ ] Gmail OAuth flow works
- [ ] Outlook OAuth flow works
- [ ] URL is clean after OAuth
- [ ] Email status shows connected

