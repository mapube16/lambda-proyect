#!/usr/bin/env python
"""
Test WhatsApp webhook de Twilio
Simula un mensaje entrante y verifica que el backend lo procesa correctamente
"""
import asyncio
import httpx
import json
from datetime import datetime

async def test_whatsapp_webhook():
    """Simular un webhook entrante de Twilio WhatsApp"""
    
    # Datos que Twilio envía en el webhook
    webhook_data = {
        "MessageSid": "SMtest123456789",
        "AccountSid": "ACtest123456789",
        "From": "whatsapp:+573123528153",  # Tu número
        "To": "whatsapp:+14155238886",      # Número Twilio
        "Body": "Hola! Quiero buscar licitaciones de textiles en Bogotá",
        "NumMedia": "0",
    }
    
    # Enviar al backend
    url = "http://localhost:8001/api/whatsapp/incoming"
    
    print(f"🚀 Enviando webhook a {url}")
    print(f"📱 De: {webhook_data['From']}")
    print(f"📝 Mensaje: {webhook_data['Body']}")
    print()
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(url, data=webhook_data, timeout=10)
            print(f"✅ Status: {resp.status_code}")
            print(f"📨 Response: {resp.text[:200]}")
            
            if resp.status_code == 200:
                print("\n✅ Webhook procesado correctamente")
                print("Verifica el backend logs para detalles de procesamiento")
                return True
            else:
                print(f"\n❌ Error: {resp.status_code}")
                return False
        except Exception as e:
            print(f"❌ Error: {e}")
            return False

if __name__ == "__main__":
    success = asyncio.run(test_whatsapp_webhook())
    exit(0 if success else 1)
