"""
Script de prueba — dispara una llamada Vapi directamente.
Uso: python test_vapi_call.py
"""
import asyncio
import os
from dotenv import load_dotenv
from vapi.types import AssistantOverrides

load_dotenv()

async def main():
    from vapi import AsyncVapi

    api_key          = os.getenv("VAPI_API_KEY")
    assistant_id     = os.getenv("VAPI_ASSISTANT_ID")
    phone_number_id  = os.getenv("VAPI_PHONE_NUMBER_ID")

    print(f"API Key:         {api_key[:8]}...")
    print(f"Assistant ID:    {assistant_id}")
    print(f"Phone Number ID: {phone_number_id}")
    print()

    client = AsyncVapi(token=api_key)

    print("Iniciando llamada a +573123528153...")
    call = await client.calls.create(
        assistant_id=assistant_id,
        phone_number_id=phone_number_id,
        customer={"number": "+573123528153", "name": "Maximiliano"},
        assistant_overrides=AssistantOverrides(
            first_message="Buenas Maximiliano, le saluda un asesor de DPG Seguros. Le contactamos porque tiene una obligacion pendiente por 500.000 pesos con vencimiento el 15 de abril de 2026. Tiene un momento para hablar?",
            variable_values={
                "debtor_id":   "test-001",
                "debtor_name": "Maximiliano",
                "monto":       "500.000",
                "vencimiento": "15 de abril de 2026",
            }
        ),
    )

    print(f"Llamada creada - ID: {call.id}")
    print(f"Estado: {call.status}")

asyncio.run(main())
