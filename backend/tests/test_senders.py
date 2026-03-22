"""
test_senders.py — Unit tests for email_sender and whatsapp_sender.
Transport layer is fully mocked — no real SMTP or HTTP calls.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


async def test_send_email_returns_true_on_success():
    """send_email returns True when SMTP sendmail succeeds."""
    with patch.dict("os.environ", {
        "SMTP_HOST": "smtp.test.com", "SMTP_PORT": "587",
        "SMTP_USER": "user@test.com", "SMTP_PASS": "secret",
    }):
        with patch("email_sender.asyncio.to_thread", new_callable=AsyncMock) as mock_thread:
            mock_thread.return_value = True
            from email_sender import send_email
            result = await send_email("to@test.com", "Subject", "Body", "Sender", "from@test.com")
            assert result is True


async def test_send_email_returns_false_when_creds_missing():
    """send_email returns False when SMTP_HOST is not configured."""
    with patch.dict("os.environ", {"SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASS": ""}):
        from email_sender import send_email
        result = await send_email("to@test.com", "Subject", "Body", "Sender", "from@test.com")
        assert result is False


async def test_send_whatsapp_returns_true_on_success():
    """send_whatsapp_text returns True when Meta Graph API responds 201."""
    with patch.dict("os.environ", {"WA_TOKEN": "tok123", "WA_PHONE_ID": "12345"}):
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_post = AsyncMock(return_value=mock_response)
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = mock_post
            mock_client_cls.return_value = mock_client
            from whatsapp_sender import send_whatsapp_text
            result = await send_whatsapp_text("+573001234567", "Hola!")
            assert result is True


async def test_send_whatsapp_returns_false_when_creds_missing():
    """send_whatsapp_text returns False when WA_TOKEN is not configured."""
    with patch.dict("os.environ", {"WA_TOKEN": "", "WA_PHONE_ID": ""}):
        from whatsapp_sender import send_whatsapp_text
        result = await send_whatsapp_text("+573001234567", "Hola!")
        assert result is False
