"""
Test rápido del pipeline en consola — sin ARQ, sin Redis, sin WebSocket.
Corre la prospección directo y muestra todos los eventos en tiempo real.

Uso:
  cd backend
  python test_pipeline_local.py
"""
import asyncio
import json
import logging
import os
import sys

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
# Subir el nivel de los loggers internos para ver todo
for name in ("hive_adapter", "hive_llm", "hive_tools", "hive_graph",
             "framework.graph.event_loop_node", "framework.graph.executor"):
    logging.getLogger(name).setLevel(logging.DEBUG)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


async def on_event(user_id: str, message: dict) -> None:
    """Callback que imprime cada evento del pipeline."""
    msg_type = message.get("type", "?")
    print(f"\n{'='*60}")
    print(f"[EVENT] type={msg_type}  user={user_id}")
    print(json.dumps(message, ensure_ascii=False, indent=2))
    print(f"{'='*60}\n")


async def main():
    import database
    from hive_adapter import HiveAdapter

    print("Conectando a MongoDB Atlas...")
    import certifi
    from motor.motor_asyncio import AsyncIOMotorClient
    ATLAS_URI = os.getenv("MONGODB_URI_PROD") or os.getenv("MONGODB_URI")
    database._client = AsyncIOMotorClient(ATLAS_URI, tlsCAFile=certifi.where())

    USER_ID = "test-user-local"

    # Campaña de prueba — ajustá según tu caso
    # NOTA: usar "industria_objetivo" (no "industry") — es la clave que lee hive_adapter.py
    campaign = {
        "industria_objetivo": "seguros",
        "target_role": "gerente",
        "location": "Colombia",
        "company_size": "mediana",
        "description": "Buscar empresas medianas de seguros en Colombia con gerentes de ventas",
    }

    print(f"\nIniciando pipeline para user={USER_ID}")
    print(f"Campaña: {json.dumps(campaign, ensure_ascii=False, indent=2)}\n")

    adapter = HiveAdapter(send_to_user_callback=on_event)

    run_id = "test-run-local-001"

    await adapter.start_run(
        user_id=USER_ID,
        inputs={
            "campaign": campaign,
            "max_results": 5,
            "personality_prompt": "",
            "runtime_agents": [],
            "excluded_domains": [],
            "source_priority": "serper",
        },
        run_id=run_id,
        save_lead=database.save_lead,
    )

    # Esperar que el task del pipeline termine
    task = adapter._runs.get(USER_ID)
    if isinstance(task, asyncio.Task):
        print("Pipeline corriendo, esperando resultados...\n")
        await task

    print("\nPipeline finalizado.")


if __name__ == "__main__":
    asyncio.run(main())
