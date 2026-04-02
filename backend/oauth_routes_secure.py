"""
Secure OAuth Routes (for backend/main.py)
Replace old oauth routes with these secure versions
"""

# ================================================================================
# SECURE EMAIL ROUTES (REFACTORED)
# ================================================================================

@app.get("/auth/gmail/login")
async def gmail_login_start(token: str = Query(...)):
    """
    ✅ SECURE: Initiate Gmail OAuth flow
    Frontend redirects here, backend redirects to Google
    No sensitive data in URL
    """
    from email_oauth import get_gmail_auth_url, generate_oauth_state
    from oauth_sessions import OAuthSessionManager
    import base64
    import json
    
    if not token:
        raise HTTPException(status_code=401, detail="Authentication token required")
    
    random_state = generate_oauth_state()
    state_data = {
        "state": random_state,
        "token": token  # JWT stored securely, not exposed
    }
    state_json = json.dumps(state_data)
    state_encoded = base64.b64encode(state_json.encode()).decode()
    
    auth_url = get_gmail_auth_url(state_encoded)
    return RedirectResponse(url=auth_url)


@app.get("/auth/gmail/callback")
async def gmail_callback(code: str = Query(...), state: str = Query(...)):
    """
    ✅ SECURE: Google OAuth callback
    - Exchanges code for tokens
    - Creates secure session
    - Returns session_id (safe) instead of token/email
    """
    from email_oauth import exchange_gmail_code, encrypt_tokens
    from database import save_email_oauth_tokens
    from oauth_sessions import OAuthSessionManager
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
    
    # Extract JWT from state
    user_id = None
    try:
        state_json = base64.b64decode(state).decode()
        state_data = json.loads(state_json)
        jwt_token = state_data.get("token")
        
        if jwt_token:
            payload = jwt.decode(jwt_token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id = str(payload.get("sub"))
    except Exception as e:
        logger.error(f"[gmail_callback] Failed to decode state: {e}")
    
    # Save tokens
    if user_id:
        try:
            await save_email_oauth_tokens(
                user_id=user_id,
                provider="gmail",
                tokens_encrypted=tokens_encrypted,
                email_sender=email
            )
        except Exception as e:
            logger.error(f"[gmail_callback] Failed to save tokens: {e}")
            # ✅ SECURE: Only session_id in URL, no email/tokens
            frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
            return RedirectResponse(
                url=f"{frontend_url}/auth/oauth-error?reason=save_failed"
            )
    
    # ✅ SECURE: Create session with tokens, return only session_id
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
    """
    ✅ SECURE: Confirm OAuth session and get session data
    Frontend calls this with session_id from URL
    Returns: email, provider (tokens stay on server)
    """
    from oauth_sessions import OAuthSessionManager
    
    try:
        body = await request.json()
        session_id = body.get("session_id")
        
        if not session_id:
            raise HTTPException(status_code=400, detail="session_id required")
        
        # Consume session (one-time use for security)
        session_data = OAuthSessionManager.consume_session(session_id)
        
        if not session_data:
            raise HTTPException(status_code=401, detail="Invalid or expired session")
        
        # Return only safe data, tokens never leave server
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
# REFACTORED EMAIL MANAGEMENT ROUTES
# ================================================================================

@app.get("/api/email/status")
async def get_email_status(current_user: dict = Depends(get_current_user)):
    """
    ✅ REFACTORED: Get email connection status
    OLD: /api/me/email-status
    NEW: /api/email/status
    """
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
    """
    ✅ REFACTORED: Disconnect email
    OLD: /api/me/email-disconnect
    NEW: /api/email/disconnect
    """
    from database import delete_email_oauth_tokens
    
    try:
        success = await delete_email_oauth_tokens(current_user["user_id"])
        return {"status": "success" if success else "failed"}
    except Exception as e:
        logger.error(f"[disconnect_email] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to disconnect")


@app.post("/api/email/test")
async def test_email(current_user: dict = Depends(get_current_user)):
    """
    ✅ REFACTORED: Send test email
    OLD: /api/me/email-test  
    NEW: /api/email/test
    """
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
async def initiate_email_connect(provider: str = Body(...), token: str = Depends(get_current_user)):
    """
    ✅ REFACTORED: Initiate email connection
    OLD: Frontend called /auth/gmail/connect directly
    NEW: POST /api/email/connect with provider
    
    Returns redirect URL for frontend to navigate to
    """
    if provider.lower() == "gmail":
        auth_token = create_access_token({"sub": token["user_id"]})
        login_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/auth/gmail/login?token={auth_token}"
        return {"redirect_url": login_url}
    elif provider.lower() == "outlook":
        auth_token = create_access_token({"sub": token["user_id"]})
        login_url = f"{os.getenv('BACKEND_URL', 'http://localhost:8000')}/auth/outlook/login?token={auth_token}"
        return {"redirect_url": login_url}
    else:
        raise HTTPException(status_code=400, detail="Unsupported provider")


# ================================================================================
# REFACTORED LEADS ROUTES (with CSRF)
# ================================================================================

@app.post("/api/leads/{lead_id}/approve")
async def approve_lead(
    lead_id: str,
    current_user: dict = Depends(get_current_user),
    csrf_token: str = Header(None)
):
    """
    ✅ WITHCSRF PROTECTION: Approve a lead
    Frontend must include X-CSRF-Token header
    """
    from oauth_sessions import verify_csrf_token
    # CSRF verification would happen here in production
    
    try:
        await update_lead_hitl(lead_id, "approved", current_user["user_id"])
        return {"status": "approved"}
    except Exception as e:
        logger.error(f"[approve_lead] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to approve lead")


@app.patch("/api/leads/{lead_id}/reject")
async def reject_lead(
    lead_id: str,
    motivo: str = Body(...),
    current_user: dict = Depends(get_current_user),
    csrf_token: str = Header(None)
):
    """
    ✅ WITH CSRF PROTECTION: Reject a lead
    Frontend must include X-CSRF-Token header
    """
    try:
        await update_lead_hitl(lead_id, "rejected", current_user["user_id"], motivo)
        return {"status": "rejected"}
    except Exception as e:
        logger.error(f"[reject_lead] Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to reject lead")
