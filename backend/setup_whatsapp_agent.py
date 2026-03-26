#!/usr/bin/env python3
"""
Setup: Set bot_mode to legacy and check current data
"""
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def main():
    from database import init_db, get_db
    
    # Initialize DB connection first
    await init_db()
    
    db = get_db()
    if db is None:
        print("❌ Failed to connect to database")
        return
    
    phone = '+573123528153'
    
    # Check current agent config
    agent = await db.whatsapp_agents.find_one({'phone': phone})
    print(f"Current agent config:")
    if agent:
        print(f"  _id: {agent.get('_id')}")
        print(f"  bot_mode: {agent.get('bot_mode', 'undefined')}")
        print(f"  empresa: {agent.get('empresa')}")
        print(f"  nombre_asesor: {agent.get('nombre_asesor')}")
    else:
        print(f"  No agent found")
    
    # Update to legacy mode
    result = await db.whatsapp_agents.update_one(
        {'phone': phone},
        {'$set': {
            'bot_mode': 'legacy',
            'nombre_asesor': 'Maximiliano Pulido Beltran',
            'empresa': 'Seguros',
            'telefono_asesor': '3123528153'
        }},
        upsert=True
    )
    
    print(f"\n✅ Updated bot_mode to 'legacy'")
    
    # Verify
    agent = await db.whatsapp_agents.find_one({'phone': phone})
    print(f"\nAgent config after update:")
    print(f"  bot_mode: {agent.get('bot_mode')}")
    print(f"  nombre_asesor: {agent.get('nombre_asesor')}")
    print(f"  empresa: {agent.get('empresa')}")

if __name__ == "__main__":
    asyncio.run(main())
