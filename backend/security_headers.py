"""
security_headers.py — HTTP Security Headers Middleware

Adds security-related headers to all HTTP responses to protect against
common web vulnerabilities like XSS, clickjacking, and other attacks.
"""
from fastapi import Request
from fastapi.responses import Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds security headers to all responses.

    Headers Added:
    - Strict-Transport-Security: Force HTTPS for 1 year
    - X-Content-Type-Options: Prevent MIME sniffing
    - X-Frame-Options: Prevent clickjacking
    - X-XSS-Protection: Enable XSS filters in older browsers
    - Referrer-Policy: Control referrer information
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        # Strict-Transport-Security: Force HTTPS for 1 year
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        # X-Content-Type-Options: Prevent MIME type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: Prevent clickjacking
        # DENY is most restrictive; use SAMEORIGIN if iframe is needed
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection: Enable XSS filters (for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: Minimize referrer leakage
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy: Restrict API access
        # Disable dangerous features by default
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "accelerometer=()"
        )

        return response
