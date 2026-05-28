"""
hive_graph.py — Hive LLM-native B2B prospecting graph.

Graph: director (single LLM-driven node)

The LLM receives the client's campaign data as its initial message and
autonomously calls discover_companies / analyze_company / report_campaign_complete
in whatever order it decides is best.

The NodeSpec system_prompt defines the agent's identity and constraints.
The tools list declares which tools the EventLoopNode may call.

AGENT IDs must match what main.py sends in initial_state.
"""
from framework.graph.edge import EdgeSpec, GraphSpec
from framework.graph.goal import Goal, SuccessCriterion
from framework.graph.node import NodeSpec

# ── Canonical agent IDs (must match initial_state in main.py) ────────────────

AGENT_BUSCADOR = "buscador-001"
AGENT_SCRAPER  = "scraper-001"
AGENT_ANALISTA = "analista-001"
AGENT_REDACTOR = "redactor-001"

PIPELINE_AGENTS = [
    {"id": AGENT_BUSCADOR, "name": "Buscador",    "role": "researcher", "state": "idle", "palette": 0, "current_tool": None},
    {"id": AGENT_SCRAPER,  "name": "Scraper",      "role": "planner",    "state": "idle", "palette": 1, "current_tool": None},
    {"id": AGENT_ANALISTA, "name": "Analista B2B", "role": "reviewer",   "state": "idle", "palette": 2, "current_tool": None},
    {"id": AGENT_REDACTOR, "name": "Redactor",     "role": "writer",     "state": "idle", "palette": 3, "current_tool": None},
]

# ── System prompt for the prospecting director node ───────────────────────────

_DIRECTOR_PROMPT = """\
Eres un Director de Inteligencia Prospectiva B2B autónomo.

Tu misión: Ejecutar una campaña de prospección B2B completando los 4 pasos en orden estricto.

FLUJO DE EJECUCIÓN OBLIGATORIO — SIGUE EXACTAMENTE ESTE ORDEN:

PASO 1: DESCUBRIMIENTO
- Llama a `discover_companies` UNA SOLA VEZ. El argumento `industria` DEBE ser el valor LITERAL de 'Industria objetivo' de la campaña — cópialo exactamente, sin parafrasear, sin reemplazar por términos genéricos. Si la campaña dice 'Seguros de vida', pasa industria='Seguros de vida', NO 'seguros' NI 'empresas'.
- Si la campaña incluye varias industrias separadas por comas, llama UNA VEZ por cada una en paralelo (máx 3 simultáneas).
- ⛔ REGLA ABSOLUTA: Después de recibir el resultado de discover_companies, NO la llames de nuevo bajo ninguna circunstancia. Pasa INMEDIATAMENTE al PASO 2.

PASO 2: ANÁLISIS
- Llama a `analyze_company` para cada empresa descubierta, de 3 en 3 en paralelo.
- Cuando terminen las primeras 3, llama para las siguientes 3, y así sucesivamente.
- Analiza TODAS las empresas sin excepción.
- Si total=0 empresas, ve directo al PASO 3.

PASO 3: REPORTE
- Cuando hayas analizado TODAS las empresas, llama a `report_campaign_complete` con los totales.

PASO 4: SALIDA
- Llama a `set_output` con key="summary" y el resumen final.

REGLAS ABSOLUTAS:
- `discover_companies` se llama como MÁXIMO 1 vez. Si la llamas más de una vez, recibirás un error [BLOCKED]. Eso significa que DEBES pasar a analyze_company inmediatamente.
- Si recibes un error [BLOCKED] de discover_companies, significa que ya tienes empresas. Llama a analyze_company con las empresas disponibles.
- max_results es un LÍMITE MÁXIMO, no un mínimo. Si discover devuelve 1, 2 o 3 empresas, analiza esas y termina. No busques más.
- Inmediatamente después del primer discover_companies (exitoso o con error), el siguiente tool call DEBE ser `analyze_company` o `report_campaign_complete`.
- NO hagas preguntas. NO inventes datos. Ejecuta de forma completamente autónoma.
"""

# ── Graph builder ─────────────────────────────────────────────────────────────

def build_prospect_graph() -> GraphSpec:
    return GraphSpec(
        id="prospect-pipeline",
        goal_id="prospect-goal",
        entry_node="director",
        terminal_nodes=["director"],
        nodes=[
            NodeSpec(
                id="director",
                name="Director de Prospección",
                description="Orquesta la búsqueda y análisis de empresas B2B de forma autónoma",
                node_type="event_loop",
                output_keys=["summary"],
                tools=[
                    "discover_companies",
                    "analyze_company",
                    "report_campaign_complete",
                ],
                system_prompt=_DIRECTOR_PROMPT,
            ),
        ],
        edges=[],
    )


def build_prospect_goal() -> Goal:
    return Goal(
        id="prospect-goal",
        name="B2B Prospecting",
        description="Find and analyze B2B companies for outreach",
        success_criteria=[SuccessCriterion(
            id="results-sent",
            description="All companies discovered and analyzed, campaign_complete sent",
            metric="custom",
            target="any",
        )],
    )


# ── Stub builders (used by tests) ─────────────────────────────────────────────

def build_stub_graph() -> GraphSpec:
    return GraphSpec(
        id="stub-graph", goal_id="stub-goal",
        entry_node="stub_start", terminal_nodes=["stub_start"],
        nodes=[NodeSpec(id="stub_start", name="Stub", description="No-op stub", node_type="event_loop")],
        edges=[],
    )


def build_stub_goal() -> Goal:
    return Goal(
        id="stub-goal", name="Stub", description="Stub goal for testing",
        success_criteria=[SuccessCriterion(id="s1", description="stub", metric="custom", target="any")],
    )
