"""
setup_bot_flags.py — Auditoría y setup de flags de bot en usuarios.

Propósito:
  1. Identificar qué usuarios deberían tener el bot SECOP
  2. Marcar con has_bot_secop: true/false
  3. Asociar configuración completa del bot al usuario correcto

Ejecución:
  python backend/setup_bot_flags.py --audit          # Solo ver
  python backend/setup_bot_flags.py --apply          # Aplicar cambios
  python backend/setup_bot_flags.py --phone 3123528153  # Specific user
"""
import asyncio
import sys
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
DB_NAME = os.getenv("MONGODB_DB", "hive_office")

# Criterios para determinar si usuario debería tener bot
BOT_INDICATORS = [
    "SENDER_COMPANY",  # Empresa definida
    "wa_phone_number",  # Número WhatsApp
    "onboarding_campaign",  # Tiene campaña
]

# Configuración del bot SECOP para el usuario correcto
BOT_SECOP_CONFIG = {
    "bot_name": "SECOP Pólizas Bot",
    "bot_mode": "legacy",  # legacy = whatsapp_agent.py con todas las herramientas
    "sectors": ["construccion", "servicios", "tecnologia", "transporte", "manufactura"],
    "features": {
        "multi_sector_search": True,
        "nit_enrichment": True,
        "interactive_buttons": True,
        "public_entity_filter": True,
        "auto_retry": True,
    },
    "enabled_at": "2026-03-24T00:00:00Z",
    "last_updated": "2026-03-24T00:00:00Z",
}


async def get_db():
    """Conectar a MongoDB."""
    client = AsyncIOMotorClient(MONGO_URI)
    db = client[DB_NAME]
    return db, client


async def audit_users(phone: Optional[str] = None):
    """Auditar usuarios y mostrar estado de bot flags."""
    print("\n" + "="*80)
    print("AUDITORÍA: Estado de flags de bot en usuarios")
    print("="*80 + "\n")
    
    db, client = await get_db()
    
    try:
        # Construir query
        query = {"role": "client"}
        if phone:
            # Buscar con múltiples variaciones del teléfono
            phone_clean = phone.lstrip('+').strip()
            query["$or"] = [
                {"wa_phone_number": phone_clean},
                {"wa_phone_number": f"+{phone_clean}"},
                {"wa_phone_number": f"whatsapp:{phone_clean}"},
                {"SENDER_PHONE": phone_clean},
            ]
        
        users = await db.users.find(query).to_list(length=None)
        
        print(f"📊 Total de usuarios encontrados: {len(users)}\n")
        
        if len(users) == 0 and phone:
            print(f"❌ No se encontró usuario con teléfono: {phone}")
            print(f"\n💡 Verificando directamente en MongoDB si existe el número...\n")
            # Buscar en cualquier campo
            all_users = await db.users.find({}).to_list(length=None)
            found = False
            for u in all_users:
                wa_phone = u.get("wa_phone_number", "")
                sender_phone = u.get("SENDER_PHONE", "")
                if phone_clean in str(wa_phone) or phone_clean in str(sender_phone):
                    print(f"✓ Encontrado en usuario: {u.get('email')}")
                    print(f"  wa_phone_number: {wa_phone}")
                    print(f"  SENDER_PHONE: {sender_phone}\n")
                    found = True
            if not found:
                print(f"⚠️  El número {phone} NO existe en MongoDB")
                print(f"   Necesitas crear/actualizar el usuario con este teléfono.\n")
            client.close()
            return
        
        for i, user in enumerate(users, 1):
            email = user.get("email", "N/A")
            phone_num = user.get("wa_phone_number", "N/A")
            company = user.get("onboarding_campaign", {}).get("empresa_remitente", "N/A")
            has_bot = user.get("has_bot_secop", "❓ NO DEFINIDO")
            bot_config = user.get("bot_secop_config", {})
            
            print(f"{i}. {email}")
            print(f"   📱 Teléfono: {phone_num}")
            print(f"   🏢 Empresa: {company}")
            print(f"   🤖 has_bot_secop: {has_bot}")
            if bot_config:
                print(f"   ⚙️ Bot mode: {bot_config.get('bot_mode')}")
            print()
    
    finally:
        client.close()


async def apply_flags(phone: Optional[str] = None, apply: bool = False):
    """Aplicar flags de bot a usuarios."""
    print("\n" + "="*80)
    print("APLICACIÓN: Configurando flags de bot")
    print("="*80 + "\n")
    
    db, client = await get_db()
    
    try:
        # Construir query
        query = {"role": "client"}
        if phone:
            query["wa_phone_number"] = f"+{phone.lstrip('+')}"
        
        users = await db.users.find(query).to_list(length=None)
        
        updates_needed = []
        
        for user in users:
            user_id = user.get("_id")
            email = user.get("email", "N/A")
            phone_num = user.get("wa_phone_number", "N/A")
            company = user.get("onboarding_campaign", {}).get("empresa_remitente", "N/A")
            
            # Criterios para determinar si debería tener bot
            should_have_bot = (
                phone_num and 
                phone_num not in ("N/A", "") and
                company and 
                company.lower() in ("seguros", "pólizas", "seguros de cumplimiento")
            )
            
            current_flag = user.get("has_bot_secop")
            
            # Solo actualizar si el flag no está definido o está incorrecto
            if current_flag != should_have_bot:
                updates_needed.append({
                    "user_id": user_id,
                    "email": email,
                    "phone": phone_num,
                    "company": company,
                    "old_flag": current_flag,
                    "new_flag": should_have_bot,
                    "action": "UPDATE" if current_flag is not None else "CREATE"
                })
        
        if not updates_needed:
            print("✅ Todos los usuarios tienen flags correctos. No hay cambios necesarios.\n")
            client.close()
            return
        
        print(f"⚠️  Cambios necesarios: {len(updates_needed)}\n")
        
        for i, update in enumerate(updates_needed, 1):
            action = "✏️ " if update["action"] == "UPDATE" else "➕"
            flag_arrow = "✓" if update["new_flag"] else "✗"
            print(f"{i}. {action} {update['email']}")
            print(f"   📱 {update['phone']} | 🏢 {update['company']}")
            print(f"   🚩 {update['old_flag']} → {flag_arrow} {update['new_flag']}")
            print()
        
        if not apply:
            print("\n💡 Para aplicar estos cambios, ejecuta con --apply\n")
            client.close()
            return
        
        # Aplicar cambios
        print("\n🔄 Aplicando cambios...\n")
        
        for update in updates_needed:
            user_id = update["user_id"]
            
            if update["new_flag"]:
                # Agregar configuración completa del bot
                result = await db.users.update_one(
                    {"_id": user_id},
                    {
                        "$set": {
                            "has_bot_secop": True,
                            "bot_secop_config": BOT_SECOP_CONFIG,
                            "bot_mode": "legacy",
                            "bot_updated_at": "2026-03-24T00:00:00Z",
                        }
                    }
                )
                status = "✓ UPDATED" if result.modified_count > 0 else "- NO CHANGE"
            else:
                # Marcar como sin bot pero preservar config anterior
                result = await db.users.update_one(
                    {"_id": user_id},
                    {
                        "$set": {
                            "has_bot_secop": False,
                            "bot_disabled_at": "2026-03-24T00:00:00Z",
                        }
                    }
                )
                status = "✓ MARKED" if result.modified_count > 0 else "- NO CHANGE"
            
            print(f"{status}: {update['email']} → {update['new_flag']}")
        
        print("\n✅ Cambios aplicados exitosamente.\n")
    
    finally:
        client.close()


async def show_bot_user():
    """Mostrar SOLO el usuario que tiene el bot activo."""
    print("\n" + "="*80)
    print("BOT USER: Usuario asociado al bot SECOP")
    print("="*80 + "\n")
    
    db, client = await get_db()
    
    try:
        bot_user = await db.users.find_one({
            "has_bot_secop": True,
            "wa_phone_number": {"$ne": None}
        })
        
        if not bot_user:
            print("❌ No se encontró usuario con bot activo.\n")
            client.close()
            return
        
        print("✅ Usuario con bot SECOP activo:\n")
        print(f"📧 Email: {bot_user.get('email')}")
        print(f"📱 WhatsApp: {bot_user.get('wa_phone_number')}")
        print(f"🏢 Empresa: {bot_user.get('onboarding_campaign', {}).get('empresa_remitente')}")
        print(f"🤖 Bot Mode: {bot_user.get('bot_mode')}")
        
        config = bot_user.get("bot_secop_config", {})
        if config:
            print(f"\n⚙️  Configuración del Bot:")
            print(f"   • Nombre: {config.get('bot_name')}")
            print(f"   • Sectores: {', '.join(config.get('sectors', []))}")
            print(f"   • Features habilitadas:")
            for feature, enabled in config.get("features", {}).items():
                status = "✓" if enabled else "✗"
                print(f"     {status} {feature}")
        
        print()
    
    finally:
        client.close()


def main():
    """CLI principal."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Auditoría y setup de flags de bot SECOP en MongoDB"
    )
    parser.add_argument("--audit", action="store_true", help="Solo auditar (no aplicar cambios)")
    parser.add_argument("--apply", action="store_true", help="Aplicar cambios")
    parser.add_argument("--phone", type=str, help="Filtrar por número de teléfono")
    parser.add_argument("--show-bot-user", action="store_true", help="Mostrar usuario con bot activo")
    
    args = parser.parse_args()
    
    if args.show_bot_user:
        asyncio.run(show_bot_user())
    elif args.apply:
        asyncio.run(apply_flags(phone=args.phone, apply=True))
    else:
        # Default: audit mode
        asyncio.run(audit_users(phone=args.phone))


if __name__ == "__main__":
    main()
