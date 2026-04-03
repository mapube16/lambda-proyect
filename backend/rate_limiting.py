"""
rate_limiting.py — Rate Limiting for Authentication Endpoints

Implements rate limiting to prevent brute force attacks on sensitive
endpoints like login, registration, and OAuth.

Uses in-memory store for simplicity. For production, use Redis-based
implementation like slowapi + redis.
"""
import time
from typing import Dict, Tuple
from fastapi import HTTPException, status, Request
import logging

logger = logging.getLogger("rate_limiting")

# In-memory store: {key: [(timestamp, count), ...]}
# Key format: "ip:endpoint" or "email:endpoint"
_rate_limit_store: Dict[str, list] = {}

# Configuration
DEFAULT_WINDOW_SECONDS = 900  # 15 minutes
DEFAULT_MAX_ATTEMPTS = 5
CLEANUP_INTERVAL = 3600  # Clean old entries every hour
_last_cleanup = time.time()


def _cleanup_old_entries():
    """Remove expired entries from the rate limit store."""
    global _last_cleanup
    now = time.time()

    # Only cleanup every hour to avoid overhead
    if now - _last_cleanup < CLEANUP_INTERVAL:
        return

    _last_cleanup = now
    to_delete = []

    for key, entries in _rate_limit_store.items():
        # Keep only recent entries
        recent = [(ts, cnt) for ts, cnt in entries if now - ts < DEFAULT_WINDOW_SECONDS * 2]
        if not recent:
            to_delete.append(key)
        else:
            _rate_limit_store[key] = recent

    for key in to_delete:
        del _rate_limit_store[key]

    logger.debug(f"[rate_limiting] Cleaned up {len(to_delete)} expired entries")


def check_rate_limit(
    identifier: str,
    endpoint: str,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    window_seconds: int = DEFAULT_WINDOW_SECONDS,
) -> bool:
    """
    Check if a request exceeds the rate limit.

    Args:
        identifier: Unique identifier (IP address, email, user_id, etc.)
        endpoint: Endpoint name/path (for logging and metrics)
        max_attempts: Maximum attempts within the window
        window_seconds: Time window in seconds

    Returns:
        True if the request is allowed, False if rate limited

    Raises:
        HTTPException: If rate limit is exceeded
    """
    _cleanup_old_entries()

    now = time.time()
    key = f"{identifier}:{endpoint}"

    # Get or create entry list
    if key not in _rate_limit_store:
        _rate_limit_store[key] = []

    entries = _rate_limit_store[key]

    # Remove old entries outside the window
    recent_entries = [(ts, cnt) for ts, cnt in entries if now - ts < window_seconds]

    # Count total attempts in recent window
    total_attempts = sum(cnt for _, cnt in recent_entries)

    if total_attempts >= max_attempts:
        logger.warning(
            f"[rate_limiting] Rate limit exceeded for {identifier} on {endpoint}: "
            f"{total_attempts} attempts in {window_seconds}s"
        )
        # Return 429 Too Many Requests (Retry-After: calculate seconds until next window)
        oldest_entry = recent_entries[0][0] if recent_entries else now
        retry_after = int(window_seconds - (now - oldest_entry)) + 1
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )

    # Record this attempt
    if recent_entries:
        _rate_limit_store[key] = recent_entries + [(now, 1)]
    else:
        _rate_limit_store[key] = [(now, 1)]

    return True


def get_client_ip(request: Request) -> str:
    """
    Extract client IP address from request.

    Checks X-Forwarded-For header (for proxies) before falling back to
    remote client address.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # X-Forwarded-For can contain multiple IPs; take the first
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# Convenience functions for specific endpoints
def check_login_rate_limit(identifier: str, request: Request) -> bool:
    """Check rate limit for login endpoint (5 attempts per 15 minutes)."""
    ip = get_client_ip(request)
    check_rate_limit(f"{ip}:{identifier}", "login", max_attempts=5, window_seconds=900)
    return True


def check_registration_rate_limit(request: Request) -> bool:
    """Check rate limit for registration endpoint (3 requests per 1 hour per IP)."""
    ip = get_client_ip(request)
    check_rate_limit(ip, "registration", max_attempts=3, window_seconds=3600)
    return True


def check_websocket_rate_limit(ip: str) -> bool:
    """Check rate limit for WebSocket connections (10 per minute per IP)."""
    check_rate_limit(ip, "websocket", max_attempts=10, window_seconds=60)
    return True


def check_oauth_rate_limit(identifier: str, request: Request) -> bool:
    """Check rate limit for OAuth endpoints (10 attempts per 10 minutes)."""
    ip = get_client_ip(request)
    check_rate_limit(f"{ip}:{identifier}", "oauth", max_attempts=10, window_seconds=600)
    return True
