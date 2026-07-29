"""
test_whatsapp_sender.py — Meta WhatsApp Cloud API sender (whatsapp_sender.py).

Cubre los builders puros de payload (texto / plantilla), la normalización de
teléfono a formato Meta y el guard de credenciales.
"""
import pytest

from whatsapp_sender import (
    _build_template_payload,
    _build_text_payload,
    _normalize_phone,
    send_whatsapp_template,
    send_whatsapp_text,
)


def test_normalize_phone_deja_solo_digitos():
    assert _normalize_phone("+57 300 111 2233") == "573001112233"
    assert _normalize_phone("+57-300-111-2233") == "573001112233"
    assert _normalize_phone("573001112233") == "573001112233"
    assert _normalize_phone(None) == ""


def test_build_text_payload():
    p = _build_text_payload("+573001112233", "hola")
    assert p == {
        "messaging_product": "whatsapp",
        "to": "573001112233",
        "type": "text",
        "text": {"body": "hola"},
    }


def test_build_template_payload_con_components_crudos():
    comps = [{"type": "body", "parameters": [{"type": "text", "text": "Juan"}]}]
    p = _build_template_payload("573001112233", "recordatorio_pago", "es_CO", comps)
    assert p["type"] == "template"
    assert p["template"]["name"] == "recordatorio_pago"
    assert p["template"]["language"] == {"code": "es_CO"}
    assert p["template"]["components"] == comps


def test_build_template_payload_sin_components_queda_lista_vacia():
    p = _build_template_payload("573001112233", "hello_world", "en_US", [])
    assert p["template"]["components"] == []


@pytest.mark.asyncio
async def test_send_text_sin_credenciales_devuelve_false(monkeypatch):
    monkeypatch.delenv("WA_TOKEN", raising=False)
    monkeypatch.delenv("WA_PHONE_ID", raising=False)
    assert await send_whatsapp_text("573001112233", "hola") is False


@pytest.mark.asyncio
async def test_send_template_body_params_arma_component_de_body(monkeypatch):
    """body_params se convierte en un component 'body' con parámetros de texto,
    y sin credenciales el envío corta en False sin tocar la red."""
    captured = {}

    async def fake_post(payload):
        captured["payload"] = payload
        return False

    monkeypatch.setattr("whatsapp_sender._post_message", fake_post)
    ok = await send_whatsapp_template(
        "+573001112233", "recordatorio_pago", language_code="es_CO",
        body_params=["Juan", "$150.000"],
    )
    assert ok is False
    comps = captured["payload"]["template"]["components"]
    assert comps == [{
        "type": "body",
        "parameters": [
            {"type": "text", "text": "Juan"},
            {"type": "text", "text": "$150.000"},
        ],
    }]
