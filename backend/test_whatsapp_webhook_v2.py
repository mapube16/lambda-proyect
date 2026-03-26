#!/usr/bin/env python3
"""
Test WhatsApp webhook with valid Twilio signature.
Simulates a Twilio WhatsApp incoming message webhook.
"""

import asyncio
import httpx
import os
from urllib.parse import urlencode

async def test_whatsapp_webhook():
    """Send realistic WhatsApp webhook to local backend."""
    
    # Backend URL
    base_url = "http://localhost:8001"
    webhook_url = f"{base_url}/api/whatsapp/incoming"
    
    # Form data matching Twilio webhook format
    webhook_data = {
        "MessageSid": "SMtest123456789abcdef",
        "AccountSid": "ACtest123456789abcdef",
        "From": "whatsapp:+573123528153",
        "To": "whatsapp:+14155238886",
        "Body": "Hola! Quiero buscar licitaciones de textiles en Bogotá",
        "NumMedia": "0",
    }
    
    # Try to generate valid Twilio signature
    headers = {}
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if twilio_token:
        try:
            from twilio.request_validator import RequestValidator
            validator = RequestValidator(twilio_token)
            # Generate signature
            signature = validator.compute_signature(webhook_url, webhook_data)
            headers["X-Twilio-Signature"] = signature
            print(f"✅ Generated Twilio signature: {signature[:20]}...")
        except Exception as e:
            print(f"⚠️ Could not generate signature: {e}")
            print("   (Backend should fallback to validation=True if creds not set)")
    else:
        print("⚠️ TWILIO_AUTH_TOKEN not set in environment")
        print("   (Backend will skip signature validation)")
    
    # Send webhook
    async with httpx.AsyncClient() as client:
        print(f"\n🚀 Enviando webhook a {webhook_url}")
        print(f"📱 De: {webhook_data['From']}")
        print(f"📝 Mensaje: {webhook_data['Body']}")
        print()
        
        try:
            resp = await client.post(
                webhook_url,
                data=webhook_data,
                headers=headers,
                timeout=10
            )
            
            print(f"✅ Status: {resp.status_code}")
            print(f"📨 Response: {resp.text[:200] if resp.text else '(empty)'}")
            print()
            
            if resp.status_code == 200:
                print("✅ Webhook procesado correctamente")
                print("Verifica el backend logs para detalles de procesamiento")
            else:
                print(f"❌ Error inesperado: {resp.status_code}")
                if resp.text:
                    print(f"   {resp.text}")
                    
        except httpx.ConnectError:
            print("❌ No se pudo conectar al backend")
            print("   ¿Está corriendo 'npm run dev' en backend/?")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_whatsapp_webhook())
