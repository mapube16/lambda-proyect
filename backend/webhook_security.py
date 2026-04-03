"""
webhook_security.py — Security utilities for webhook signature validation.

Implements HMAC-SHA256 signature verification for Vapi webhooks and other
third-party integrations to prevent unauthorized webhook spoofing.
"""
import hmac
import hashlib
import os
from typing import Optional
import logging

logger = logging.getLogger("webhook_security")


def get_vapi_webhook_secret() -> Optional[str]:
    """Retrieve the Vapi webhook secret from environment variables."""
    return os.getenv("VAPI_WEBHOOK_SECRET")


def verify_vapi_webhook_signature(
    payload: bytes,
    signature: str,
    secret: Optional[str] = None
) -> bool:
    """
    Verify HMAC-SHA256 signature for Vapi webhooks.

    Args:
        payload: Raw request body bytes
        signature: The signature from the X-Vapi-Signature header
        secret: The Vapi webhook secret (defaults to env var)

    Returns:
        True if signature is valid, False otherwise

    References:
        https://docs.vapi.ai/understanding-vapi/webhooks#webhook-security
    """
    if secret is None:
        secret = get_vapi_webhook_secret()

    if not secret:
        logger.warning(
            "⚠️  VAPI_WEBHOOK_SECRET not configured. "
            "Webhook signature validation is disabled. "
            "Set VAPI_WEBHOOK_SECRET in .env for production."
        )
        return False

    # Compute expected signature
    expected_signature = hmac.new(
        secret.encode(),
        payload,
        hashlib.sha256
    ).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(expected_signature, signature)


def extract_signature_from_headers(headers: dict) -> Optional[str]:
    """
    Extract the signature from request headers.

    Vapi sends the signature in the X-Vapi-Signature header.

    Args:
        headers: Request headers dict

    Returns:
        The signature string, or None if not found
    """
    # Try different header name variations (case-insensitive)
    for header_name in ["x-vapi-signature", "X-Vapi-Signature", "X-VAPI-SIGNATURE"]:
        if header_name in headers:
            return headers[header_name]

    return None
