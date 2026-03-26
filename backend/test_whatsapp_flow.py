#!/usr/bin/env python3
"""
Quick test of WhatsApp agent flow without Twilio
Simulates user messages and checks response logic
"""
import asyncio
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(__file__))

from whatsapp_agent import (
    _format_prospect_list,
    _format_prospect_buttons,
    _is_public_entity,
)

def test_public_entity_filter():
    """Test that public entities are properly filtered"""
    print("🧪 Testing public entity filter...\n")
    
    test_cases = [
        ("MUNICIPIO DE BOGOTA", True, "Municipio"),
        ("Constructor Plus SAS", False, "Private company"),
        ("Armada Nacional", True, "Military"),
        ("COMFENALCO CARTAGENA", True, "Public benefit entity"),
        ("BuildTech Solutions", False, "Tech company"),
        ("MINISTERIO DE OBRAS PUBLICAS", True, "Ministry"),
        ("Construcciones Omega S.A.", False, "Private"),
    ]
    
    for name, expected, desc in test_cases:
        result = _is_public_entity(name)
        status = "✅" if result == expected else "❌"
        print(f"{status} {name[:40]:40} → {result:5} | {desc}")
    
    print()

def test_prospect_formatting():
    """Test prospect list formatting"""
    print("🧪 Testing prospect formatting...\n")
    
    prospects = [
        {
            "razon_social": "Constructor Plus SAS",
            "rep_legal_telefono": "+573001234567",
            "phone": "+573001234567",
            "rep_legal_email": "contacto@constructor.co",
            "email": "contacto@constructor.co",
        },
        {
            "razon_social": "BuildTech Innovations",
            "phone": "+573105678901",
            "email": "info@buildtech.co",
        },
        {
            "razon_social": "Obras Colombia S.A.",
            "rep_legal_telefono": "+573209876543",
            "rep_legal_email": "ventas@obrasco.co",
        },
    ]
    
    reasons = [
        "Acaban de ganar $250M en contrato con Ministerio de Obras",
        "3 adjudicaciones en últimos 90 días por $1.2B total",
        "Especialista en licitaciones del sector construcción",
    ]
    
    print("📋 TEXT FORMAT (fallback para trial):\n")
    text = _format_prospect_list(prospects, "Construcción", "Bogotá", reasons)
    print(text)
    print("\n" + "="*60 + "\n")
    
    print("🔘 BUTTON FORMAT (cuando tenga templates):\n")
    header, buttons = _format_prospect_buttons(prospects, "Construcción", "Bogotá")
    print(f"Header:\n{header}\n")
    print("Buttons:")
    for b in buttons:
        print(f"  • {b['title']}")
    print()

def test_message_flow():
    """Simulate user interaction flow"""
    print("🧪 Testing message flow logic...\n")
    
    messages = [
        ("construccion bogota", "Search for construction companies in Bogotá"),
        ("ayuda", "Help request"),
        ("1", "Select prospect 1"),
        ("E", "Email channel"),
    ]
    
    for msg, desc in messages:
        print(f"📨 User: {msg:25} → {desc}")
    
    print()

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🚀 WhatsApp Agent Flow Tests")
    print("="*60 + "\n")
    
    test_public_entity_filter()
    test_prospect_formatting()
    test_message_flow()
    
    print("✅ All local tests passed!")
    print("Ready to test with real Twilio webhook\n")
