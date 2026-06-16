"""
Script de prueba para el pipeline de prospeccion.
Ejecuta: python run_prospect_test.py
"""
import asyncio
import logging
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

# Logs detallados
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
for logger_name in [
    "hive_adapter", "hive_llm", "hive_tools", "hive_graph",
    "framework.graph.event_loop_node", "framework.graph.executor",
    "httpx",
]:
    logging.getLogger(logger_name).setLevel(logging.DEBUG)

CAMPAIGN = {
    "industria_objetivo": "empresas de construccion",
    "ciudad_objetivo": "Bogota, Colombia",
    "dolor_operativo": "gestion de proyectos y presupuestos",
    "solucion_ofrecida": "software ERP para construccion",
    "software_clave": "SAP, Excel, AutoCAD",
    "jerarquia_decisores": "Gerente General, Director de Operaciones",
    "source_priority": "serper",
}

leads_capturados = []
eventos = []

async def on_message(user_id: str, message: dict):
    eventos.append(message)
    t = message.get("type", "?")
    if t == "agent_update":
        state = message.get("state", "?")
        tool = message.get("current_tool", "")
        status = message.get("tool_status", "")
        print(f"  [WS] {state.upper()}" + (f" → {tool}: {status}" if tool else ""))
    elif t == "lead_saved":
        company = message.get("company_name", "?")
        score = message.get("score", "?")
        leads_capturados.append(message)
        print(f"  [LEAD] ✓ {company}  (score: {score})")
    elif t == "run_complete":
        print(f"  [RUN] Completado. Leads: {message.get('leads_count', '?')}")
    elif t == "error":
        print(f"  [ERROR] {message.get('message', '?')}")
    else:
        print(f"  [MSG] {t}: {str(message)[:120]}")


async def main():
    from hive_adapter import HiveAdapter

    print("=" * 60)
    print("PIPELINE DE PROSPECCION — TEST")
    print(f"Industria: {CAMPAIGN['industria_objetivo']}")
    print(f"Ciudad:    {CAMPAIGN['ciudad_objetivo']}")
    print("=" * 60)

    adapter = HiveAdapter(send_to_user_callback=on_message)

    inputs = {
        "campaign": CAMPAIGN,
        "max_results": 5,   # pocos para la prueba
        "personality_prompt": "Sé directo y profesional.",
        "source_priority": "serper",
    }

    t0 = time.time()
    run_id = await adapter.start_run(
        user_id="test_user",
        inputs=inputs,
        run_id="test-run-001",
    )
    print(f"\nRun iniciado: {run_id}")
    print("Esperando resultados...\n")

    # Esperar hasta que el task termine (máx 3 minutos)
    task = adapter._runs.get("test_user")
    if task:
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=180)
        except asyncio.TimeoutError:
            print("\n[TIMEOUT] El pipeline no terminó en 3 minutos.")
        except Exception as e:
            print(f"\n[EXCEPTION] {e}")

    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print(f"RESUMEN — {elapsed:.1f}s")
    print(f"  Leads capturados : {len(leads_capturados)}")
    print(f"  Eventos WS total : {len(eventos)}")
    if leads_capturados:
        print("\n  Leads encontrados:")
        for l in leads_capturados:
            print(f"    • {l.get('company_name','?')}  score={l.get('score','?')}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
