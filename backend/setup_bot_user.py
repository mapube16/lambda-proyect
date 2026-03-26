"""
setup_bot_user.py — Configurar usuario para bot SECOP.

Actualiza maximilianopulidobeltran@gmail.com con:
  - wa_phone_number: +573123528153
  - onboarding_campaign actualizado a "Seguros"
  - has_bot_secop: true
  - bot_secop_config completo
  - bot_mode: legacy

Ejecución:
  python backend/setup_bot_user.py --show     # Ver usuario actual
  python backend/setup_bot_user.py --setup    # Configurar bot
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB", "hive_office")

BOT_USER_EMAIL = "maximilianopulidobeltran@gmail.com"
BOT_USER_PHONE = "+573123528153"

BOT_SECOP_CONFIG = {
    "bot_name": "SECOP Pólizas Bot",
    "bot_mode": "legacy",
    "sectors": ["construccion", "servicios", "tecnologia", "transporte", "manufactura"],
    "features": {
        "multi_sector_search": True,
        "nit_enrichment": True,
        "interactive_buttons": True,
        "public_entity_filter": True,
        "auto_retry": True,
    },
    "enabled_at": datetime.utcnow().isoformat() + "Z",
    "last_updated": datetime.utcnow().isoformat() + "Z",
}

ONBOARDING_SECOP = {
    "nombre_remitente": "Maximiliano",
    "empresa_remitente": "Seguros",
    "industria_objetivo": "Seguros de Cumplimiento",
    "ciudad_objetivo": "Bogota",
    "dolor_operativo": "Empresas que participan en licitaciones públicas sin póliza de cumplimiento",
    "solucion_ofrecida": "Pólizas de cumplimiento expedidas rápidamente para empresas del SECOP",
    "software_clave": "SECOP II",
    "jerarquia_decisores": "Gerente de Cumplimiento, Gerente Legal, Representante Legal",
}


async def get_db():
    """Conectar a MongoDB."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    return db, client


async def show_user():
    """Mostrar estado actual del usuario."""
    print("\n" + "="*80)
    print("ESTADO ACTUAL: Usuario para bot SECOP")
    print("="*80 + "\n")
    
    db, client = await get_db()
    
    try:
        user = await db.users.find_one({"email": BOT_USER_EMAIL})
        
        if not user:
            print(f"❌ Usuario NO encontrado: {BOT_USER_EMAIL}\n")
            client.close()
            return
        
        print(f"✅ Usuario encontrado:\n")
        print(f"📧 Email: {user.get('email')}")
        print(f"📱 WhatsApp: {user.get('wa_phone_number', '❌ NO DEFINIDO')}")
        print(f"🏢 Empresa (actual): {user.get('onboarding_campaign', {}).get('empresa_remitente', 'N/A')}")
        print(f"🤖 has_bot_secop: {user.get('has_bot_secop', '❌ NO DEFINIDO')}")
        print(f"🔧 bot_mode: {user.get('bot_mode', '❌ NO DEFINIDO')}")
        
        if user.get("bot_secop_config"):
            print(f"\n⚙️  Bot ya está configurado:")
            config = user.get("bot_secop_config")
            print(f"   📛 Bot name: {config.get('bot_name')}")
            print(f"   🎯 Sectores: {', '.join(config.get('sectors', []))}")
        else:
            print(f"\n❌ Bot NO está configurado")
        
        print()
    
    finally:
        client.close()


async def setup_bot_user():
    """Configurar usuario con bot SECOP."""
    print("\n" + "="*80)
    print("SETUP: Configurando usuario para bot SECOP")
    print("="*80 + "\n")
    
    db, client = await get_db()
    
    try:
        user = await db.users.find_one({"email": BOT_USER_EMAIL})
        
        if not user:
            print(f"❌ Usuario NO encontrado: {BOT_USER_EMAIL}\n")
            client.close()
            return
        
        # Preparar actualización
        update = {
            "$set": {
                "wa_phone_number": BOT_USER_PHONE,
                "onboarding_campaign": ONBOARDING_SECOP,
                "has_bot_secop": True,
                "bot_secop_config": BOT_SECOP_CONFIG,
                "bot_mode": "legacy",
                "bot_enabled_at": datetime.utcnow().isoformat() + "Z",
                "bot_updated_at": datetime.utcnow().isoformat() + "Z",
            }
        }
        
        # Mostrar cambios a aplicar
        print("📝 Cambios a aplicar:\n")
        print(f"   ✏️  wa_phone_number: {user.get('wa_phone_number', 'N/A')} → {BOT_USER_PHONE}")
        print(f"   ✏️  empresa_remitente: {user.get('onboarding_campaign', {}).get('empresa_remitente', 'N/A')} → Seguros")
        print(f"   ✏️  has_bot_secop: {user.get('has_bot_secop', 'N/A')} → true")
        print(f"   ✏️  bot_mode: {user.get('bot_mode', 'N/A')} → legacy")
        print(f"   ✏️  bot_secop_config: {'NUEVA' if not user.get('bot_secop_config') else 'ACTUALIZADA'}")
        print()
        
        # Aplicar actualización
        result = await db.users.update_one(
            {"email": BOT_USER_EMAIL},
            update
        )
        
        if result.modified_count > 0:
            print(f"✅ Usuario actualizado exitosamente!\n")
            
            # Mostrar nuevo estado
            updated_user = await db.users.find_one({"email": BOT_USER_EMAIL})
            print("📊 NUEVO ESTADO:\n")
            print(f"📧 Email: {updated_user.get('email')}")
            print(f"📱 WhatsApp: {updated_user.get('wa_phone_number')}")
            print(f"🏢 Empresa: {updated_user.get('onboarding_campaign', {}).get('empresa_remitente')}")
            print(f"🤖 has_bot_secop: {updated_user.get('has_bot_secop')}")
            print(f"🔧 bot_mode: {updated_user.get('bot_mode')}")
            print(f"🎯 Sectores: {', '.join(updated_user.get('bot_secop_config', {}).get('sectors', []))}")
            print()
        else:
            print(f"⚠️  No se realizaron cambios. El usuario ya está configurado.\n")
    
    finally:
        client.close()


def main():
    """CLI principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Configurar usuario para bot SECOP"
    )
    parser.add_argument("--show", action="store_true", help="Ver estado actual del usuario")
    parser.add_argument("--setup", action="store_true", help="Configurar bot en el usuario")
    
    args = parser.parse_args()
    
    if args.setup:
        asyncio.run(setup_bot_user())
    else:
        # Default: show
        asyncio.run(show_user())


if __name__ == "__main__":
    main()
