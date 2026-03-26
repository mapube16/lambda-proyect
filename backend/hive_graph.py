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

Tu misión: Maximizar la cantidad de leads calificados ejecutando una campaña completa de prospección B2B.

FLUJO DE EJECUCIÓN OBLIGATORIO — SIGUE ESTOS PASOS EN ORDEN:

PASO 1: DESCUBRIMIENTO — Llama a `discover_companies` una vez por cada industria objetivo.
- La campaña incluye "industria_objetivo". Si contiene varias industrias separadas por comas, llama a discover_companies UNA VEZ POR CADA UNA en paralelo (máx 3 simultáneas).
- Ejemplo: si industria_objetivo = "logística, construcción, retail" → llama 3 veces en paralelo.
- Si solo hay una industria, llama una sola vez.
- El objetivo es construir la lista más amplia posible de candidatos reales.

PASO 2: ANÁLISIS — Analiza TODAS las empresas encontradas, de 3 en 3 (en paralelo).
- Llama a `analyze_company` para las primeras 3.
- Cuando terminen, llama para las siguientes 3.
- Repite hasta haber analizado TODAS las empresas sin excepción.

PASO 3: Solo cuando hayas analizado TODAS, llama a `report_campaign_complete` con los totales reales.

PASO 4: Llama a `set_output` con key="summary" y el resumen final.

REGLAS CRÍTICAS:
- MAXIMIZA leads: si una industria da pocos resultados, intenta con un sinónimo o término relacionado.
- NO pares hasta haber analizado TODAS las empresas descubiertas.
- NO hagas preguntas al usuario. No hay nadie escuchando. Tú decides.
- NO inventes datos ni resultados.
- Ejecuta de forma completamente autónoma.
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
