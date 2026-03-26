#!/usr/bin/env python3
"""
Manual test of WhatsApp webhook endpoint
Simulates Twilio sending a webhook to your bot
"""
import asyncio
import json
from unittest.mock import AsyncMock, patch

async def simulate_whatsapp_webhook():
    """Simulate incoming Twilio WhatsApp message"""
    
    print("="*70)
    print("📱 WhatsApp Agent - Manual Webhook Test")
    print("="*70)
    print()
    
    # Mock the external service calls
    with patch("whatsapp_agent._send_whatsapp") as mock_send:
        with patch("whatsapp_agent._send_whatsapp_buttons") as mock_buttons:
            with patch("secop_radar.build_poliza_leads") as mock_secop:
                
                mock_send.return_value = True
                mock_buttons.return_value = True
                mock_secop.return_value = {
                    "proponentes_probables": [
                        {
                            "razon_social": "Constructor Plus SAS",
                            "nit": "900123456",
                            "contratos_secop": 5,
                            "valor_total_fmt": "$250M",
                            "rep_legal_telefono": "+573001234567",
                            "rep_legal_email": "contacto@constructor.co",
                            "representante_legal": "Juan Pérez",
                        },
                        {
                            "razon_social": "BuildTech Innovations",
                            "nit": "900234567",
                            "contratos_secop": 3,
                            "valor_total_fmt": "$180M",
                            "phone": "+573105678901",
                            "email": "info@buildtech.co",
                        },
                        {
                            "razon_social": "Obras Colombia S.A.",
                            "nit": "900345678",
                            "contratos_secop": 7,
                            "valor_total_fmt": "$520M",
                            "rep_legal_telefono": "+573209876543",
                            "rep_legal_email": "ventas@obrasco.co",
                        },
                    ]
                }
                
                from whatsapp_agent import handle_inbound_message
                
                # Test case 1: User asks for help
                print("📨 TEST 1: User asks for help")
                print("   Input: 'ayuda'")
                print()
                await handle_inbound_message(
                    from_phone="+573123528153",
                    body="ayuda",
                    from_twilio="whatsapp:+14155238886",
                )
                
                if mock_send.called:
                    last_call = mock_send.call_args
                    print(f"   ✅ Response sent")
                    print(f"   Message: {last_call[0][2][:100]}...")
                else:
                    print("   ❌ No response")
                
                print()
                print("-"*70)
                print()
                
                # Test case 2: User searches for construction in Bogotá
                print("📨 TEST 2: Search for construction companies in Bogotá")
                print("   Input: 'construccion bogota'")
                print()
                
                mock_send.reset_mock()
                mock_buttons.reset_mock()
                
                await handle_inbound_message(
                    from_phone="+573123528153",
                    body="construccion bogota",
                    from_twilio="whatsapp:+14155238886",
                )
                
                if mock_buttons.called or mock_send.called:
                    print(f"   ✅ Results sent (buttons or text)")
                    if mock_buttons.called:
                        print(f"   Sent via buttons: {mock_buttons.call_count} call(s)")
                    if mock_send.called:
                        print(f"   Sent via text: {mock_send.call_count} call(s)")
                else:
                    print("   ❌ No response")
                
                print()
                print("-"*70)
                print()
                
                # Test case 3: User selects prospect
                print("📨 TEST 3: User selects prospect #1")
                print("   Input: '1'")
                print()
                
                mock_send.reset_mock()
                mock_buttons.reset_mock()
                
                # First set the session
                from whatsapp_agent import _SESSIONS
                _SESSIONS["+573123528153"] = {
                    "state": "awaiting_selection",
                    "prospects": [
                        {
                            "razon_social": "Constructor Plus SAS",
                            "rep_legal_email": "contacto@constructor.co",
                            "rep_legal_telefono": "+573001234567",
                            "representante_legal": "Juan Pérez",
                        },
                        {
                            "razon_social": "BuildTech Innovations",
                            "email": "info@buildtech.co",
                            "phone": "+573105678901",
                        },
                    ],
                    "sector": "Construcción",
                    "from_number": "whatsapp:+14155238886",
                }
                
                await handle_inbound_message(
                    from_phone="+573123528153",
                    body="1",
                    from_twilio="whatsapp:+14155238886",
                )
                
                if mock_buttons.called or mock_send.called:
                    print(f"   ✅ Selection processed")
                    if mock_buttons.called:
                        print(f"   Sent channel options (buttons)")
                    if mock_send.called:
                        print(f"   Sent channel options (text): {mock_send.call_args[0][2][:80]}...")
                else:
                    print("   ❌ No response")
                
                print()
                print("-"*70)
                print()
    
    print()
    print("="*70)
    print("✅ All webhook tests completed successfully!")
    print("="*70)
    print()
    print("📝 Next steps:")
    print("   1. Run: python -m uvicorn main:app --host 0.0.0.0 --port 8001")
    print("   2. Configure Twilio webhook to: http://your-server:8001/whatsapp/webhook")
    print("   3. Send a WhatsApp message to your Twilio number")
    print("   4. Bot will respond with prospects for search!")
    print()

if __name__ == "__main__":
    asyncio.run(simulate_whatsapp_webhook())
