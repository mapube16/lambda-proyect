"""
Secure OAuth Session Management
Session IDs en lugar de URL parameters
Token storage seguro con HTTP-only cookies
"""

import os
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from functools import lru_cache

# Session storage (en producción usar Redis)
_OAUTH_SESSIONS: Dict[str, Dict[str, Any]] = {}

SESSION_TIMEOUT = 300  # 5 minutes
MAX_SESSIONS = 1000  # Prevent memory leaks


class OAuthSession:
    """Secure OAuth session with auto-expiry"""
    
    def __init__(self, user_id: str, email: str, provider: str, tokens_encrypted: str):
        self.session_id = secrets.token_urlsafe(32)
        self.user_id = user_id
        self.email = email
        self.provider = provider
        self.tokens_encrypted = tokens_encrypted
        self.created_at = datetime.utcnow()
        self.expires_at = self.created_at + timedelta(seconds=SESSION_TIMEOUT)
    
    def is_expired(self) -> bool:
        """Check if session has expired"""
        return datetime.utcnow() > self.expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """Return session data (but not session_id - for validation)"""
        if self.is_expired():
            return {}
        return {
            "user_id": self.user_id,
            "email": self.email,
            "provider": self.provider,
            "tokens_encrypted": self.tokens_encrypted,
        }


class OAuthSessionManager:
    """Manage OAuth sessions securely"""
    
    @staticmethod
    def create_session(user_id: str, email: str, provider: str, tokens_encrypted: str) -> str:
        """
        Create a new OAuth session
        Returns: session_id (safe to include in URL)
        """
        # Cleanup expired sessions
        OAuthSessionManager._cleanup_expired()
        
        # Prevent memory leaks
        if len(_OAUTH_SESSIONS) >= MAX_SESSIONS:
            oldest_id = min(_OAUTH_SESSIONS.keys(), 
                          key=lambda k: _OAUTH_SESSIONS[k]["created_at"])
            del _OAUTH_SESSIONS[oldest_id]
        
        session = OAuthSession(user_id, email, provider, tokens_encrypted)
        _OAUTH_SESSIONS[session.session_id] = {
            "user_id": session.user_id,
            "email": session.email,
            "provider": session.provider,
            "tokens_encrypted": session.tokens_encrypted,
            "created_at": session.created_at,
            "expires_at": session.expires_at,
        }
        
        return session.session_id
    
    @staticmethod
    def get_session(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve and validate session
        Returns: session data if valid, None if expired/not found
        """
        if session_id not in _OAUTH_SESSIONS:
            return None
        
        session_data = _OAUTH_SESSIONS[session_id]
        
        # Check expiry
        if datetime.utcnow() > session_data["expires_at"]:
            del _OAUTH_SESSIONS[session_id]
            return None
        
        return session_data
    
    @staticmethod
    def consume_session(session_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve session and delete it
        (Sessions are one-time use for security)
        """
        session_data = OAuthSessionManager.get_session(session_id)
        if session_data and session_id in _OAUTH_SESSIONS:
            del _OAUTH_SESSIONS[session_id]
        return session_data
    
    @staticmethod
    def _cleanup_expired():
        """Remove expired sessions"""
        expired_ids = [
            sid for sid, data in _OAUTH_SESSIONS.items()
            if datetime.utcnow() > data["expires_at"]
        ]
        for sid in expired_ids:
            del _OAUTH_SESSIONS[sid]


def generate_csrf_token() -> str:
    """Generate CSRF token for form submissions"""
    return secrets.token_urlsafe(32)


def verify_csrf_token(token: str, stored_token: str) -> bool:
    """Verify CSRF token matches"""
    return secrets.compare_digest(token, stored_token)
