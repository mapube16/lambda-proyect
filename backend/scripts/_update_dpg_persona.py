"""Actualiza el voice_persona de DPG (saludo oficial informe §9 + respuesta 'ya pague'
que anuncia el Mensaje 2 de comprobante). Invalida el cache Redis al final."""
import asyncio
import os
import re
import certifi
from motor.motor_asyncio import AsyncIOMotorClient

USER_ID = "69bcd9bb6e35d53880364535"

# Saludo oficial del informe §9 (verbatim) + confirmacion de identidad OBLIGATORIA
# al final (regla del cliente: SIEMPRE validar identidad antes de dar datos). La
# pregunta va DENTRO del saludo verbatim para que se haga el 100% de las veces.
# {saludo_franja} -> Buenos dias / Buenas tardes (render_greeting lo resuelve por
# hora). "senor" por defecto (sin dato de genero confiable; el bot ya asumia senor).
GREETING = "{saludo_franja}, señor {first_name}. Le habla {agent_name}, asistente virtual de {company_brand}. ¿Hablo con el señor {first_name}?"
GREETING_NO_NAME = "{saludo_franja}. Le habla {agent_name}, asistente virtual de {company_brand}. ¿Con quién tengo el gusto?"

# Nueva respuesta verbal para 'ya pague' (anuncia el Mensaje 2).
NUEVA_YA_PAGUE = (
    "- 'Ya pague' / 'ya lo cancele' / 'pague ayer' -> PRIMERO llama la funcion notify_payment_claim "
    "(que ademas le envia por WhatsApp la solicitud del comprobante), y LUEGO di: 'Perfecto, muchas "
    "gracias por la informacion. Le estaremos enviando un mensaje por WhatsApp para que pueda "
    "compartirnos el comprobante de pago y asi actualizar nuestros registros.' NUNCA confirmes tu el "
    "pago, eso lo valida el equipo."
)


async def main():
    db = AsyncIOMotorClient(os.getenv("MONGODB_URI"), tlsCAFile=certifi.where())[
        os.getenv("MONGODB_DB", "hive_office")
    ]
    doc = await db.tenant_configs.find_one({"user_id": USER_ID})
    persona = (doc or {}).get("voice_persona") or {}

    oh = persona.get("objection_handling") or ""
    # Reemplaza el bullet completo de 'Ya pague' (desde el marcador hasta el siguiente
    # bullet '\n- ' o fin de string), robusto ante los chars exactos internos.
    nuevo_oh, n = re.subn(
        r"- 'Ya pague'.*?(?=\n- |\Z)",
        NUEVA_YA_PAGUE.replace("\\", "\\\\"),
        oh,
        count=1,
        flags=re.DOTALL,
    )
    if n != 1:
        print(f"AVISO: no se encontro/reemplazo el bullet 'Ya pague' (n={n}). Reviso a mano.")
    else:
        print("OK: bullet 'Ya pague' reemplazado.")

    update = {
        "voice_persona.greeting_template": GREETING,
        "voice_persona.greeting_template_no_name": GREETING_NO_NAME,
        "voice_persona.objection_handling": nuevo_oh,
    }
    res = await db.tenant_configs.update_one({"user_id": USER_ID}, {"$set": update})
    print(f"tenant_configs actualizado: matched={res.matched_count} modified={res.modified_count}")

    # Invalida cache Redis para hot-reload inmediato
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from cobranza.config_cache import invalidate_tenant_config
        await invalidate_tenant_config(USER_ID)
        print("Cache Redis invalidado.")
    except Exception as exc:
        print(f"AVISO: no se pudo invalidar Redis (TTL 5min igual refresca): {exc}")

    # Verifica lo escrito
    doc2 = await db.tenant_configs.find_one({"user_id": USER_ID})
    p2 = doc2.get("voice_persona") or {}
    print("\n--- greeting_template ---")
    print(p2.get("greeting_template"))
    print("--- objection_handling (bullet ya pague) ---")
    for line in (p2.get("objection_handling") or "").split("\n"):
        if "Ya pague" in line or "notify_payment_claim" in line:
            print(line)
    db.client.close()


asyncio.run(main())
