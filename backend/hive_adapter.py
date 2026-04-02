"""
HiveAdapter — single seam between FastAPI and aden-hive/hive framework.

Uses GraphExecutor with a real LLM (OpenRouter) + custom prospecting tools.
The LLM-driven EventLoopNode autonomously calls discover_companies,
analyze_company, and report_campaign_complete based on the campaign prompt.

ARCHITECTURE RULE: Only this file may import from `framework.*`.
"""
import asyncio
import logging
import os
from pathlib import Path
from typing import Callable, Awaitable

from framework.graph.event_loop_node import EventLoopNode, LoopConfig
from framework.graph.executor import GraphExecutor
from framework.runtime.core import Runtime
from framework.runtime.event_bus import EventBus, EventType
from models import AgentState

logger = logging.getLogger(__name__)

# Event → AgentState mapping (for EventBus → WS bridge)
_EVENT_STATE_MAP = {
    EventType.NODE_LOOP_STARTED:      AgentState.THINKING,
    EventType.TOOL_CALL_STARTED:      AgentState.TOOL_USE,
    EventType.TOOL_CALL_COMPLETED:    AgentState.THINKING,
    EventType.NODE_LOOP_COMPLETED:    AgentState.WAITING,
    EventType.CLIENT_INPUT_REQUESTED: AgentState.WAITING,
    EventType.EXECUTION_COMPLETED:    AgentState.IDLE,
    EventType.EXECUTION_FAILED:       AgentState.ERROR,
}


def _event_to_agent_state(event) -> AgentState | None:
    """Map a Hive EventBus event to an AgentState. Returns None if unmapped."""
    return _EVENT_STATE_MAP.get(event.type)


class HiveAdapter:
    """
    Adapter between FastAPI WebSocket layer and aden-hive/hive GraphExecutor.

    Uses an LLM-driven EventLoopNode as the prospecting director.
    The LLM receives the client's campaign data and autonomously calls
    the prospecting tools in whatever order it decides.

    Tenant isolation: one GraphExecutor task per user_id.
    """

    def __init__(self, send_to_user_callback: Callable[[str, dict], Awaitable[None]]):
        self._send_to_user = send_to_user_callback
        self._runs: dict[str, asyncio.Task] = {}   # user_id → running task
        self._runtime_agents: dict[str, list[dict]] = {}

    async def start_run(
        self,
        user_id: str,
        inputs: dict,
        run_id: str | None = None,
        save_lead: Callable | None = None,
    ) -> str:
        """
        Build a real prospect GraphExecutor with LLM + tools and launch async.
        Returns user_id as run identifier.
        """
        from hive_graph import build_prospect_graph, build_prospect_goal
        from hive_llm import OpenRouterProvider
        from hive_tools import make_prospecting_registry

        openai_key = os.getenv("OPENAI_API_KEY", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        gmaps_key  = os.getenv("GOOGLE_MAPS_API_KEY", "")
        campaign          = inputs.get("campaign", {})
        max_results       = int(inputs.get("max_results", 20))
        personality_prompt = inputs.get("personality_prompt", "")
        runtime_agents = inputs.get("runtime_agents", []) or []
        excluded_domains = inputs.get("excluded_domains", []) or []
        source_priority   = inputs.get("source_priority", campaign.get("source_priority", "serper"))

        if not runtime_agents:
            from hive_graph import PIPELINE_AGENTS as DEFAULT_PIPELINE_AGENTS
            runtime_agents = DEFAULT_PIPELINE_AGENTS

        self._runtime_agents[user_id] = runtime_agents

        # LLM provider — OpenAI directly (gpt-4o-mini)
        from hive_llm import OpenRouterProvider

        llm = OpenRouterProvider(
            api_key=openai_key,
            model="gpt-4o-mini",
            base_url="https://api.openai.com/v1",
            max_output_tokens=2000,
        )

        # Per-run tool registry (closures capture campaign/user context)
        # OpenAI-only path for analysis tools.
        use_openrouter_for_tools = False
        tools_api_key = openai_key
        registry = make_prospecting_registry(
            campaign=campaign,
            gmaps_key=gmaps_key,
            openrouter_key=tools_api_key,
            user_id=user_id,
            run_id=run_id or "",
            send_to_user=self._send_to_user,
            save_lead=save_lead,
            max_results=max_results,
            personality_prompt=personality_prompt,
            runtime_agents=runtime_agents,
            excluded_domains=excluded_domains,
            use_openrouter=use_openrouter_for_tools,
            source_priority=source_priority,
        )
        all_tools    = list(registry.get_tools().values())
        tool_executor = registry.get_executor()

        graph = build_prospect_graph()
        goal  = build_prospect_goal()

        # Per-user EventBus
        event_bus = EventBus()
        event_bus.subscribe(
            event_types=list(_EVENT_STATE_MAP.keys()),
            handler=self._make_event_handler(user_id),
            filter_stream=user_id,
        )

        storage_path = Path(f"/tmp/hive_runs/{user_id}")
        storage_path.mkdir(parents=True, exist_ok=True)

        # Build EventLoopNode for the director
        director_node = EventLoopNode(
            event_bus=event_bus,
            config=LoopConfig(
                max_iterations=100,          # enough for large company lists
                max_tool_calls_per_turn=50,
                max_tool_result_chars=15_000,
                max_history_tokens=32_000,
            ),
            tool_executor=tool_executor,
        )

        executor = GraphExecutor(
            runtime=Runtime(storage_path=storage_path),
            llm=llm,
            tools=all_tools,
            tool_executor=tool_executor,
            event_bus=event_bus,
            stream_id=user_id,
        )
        executor.register_node("director", director_node)

        industria = campaign.get("industria_objetivo", "empresas")
        ciudad    = campaign.get("ciudad_objetivo", "Colombia")

        async def _run():
            try:
                logger.info(
                    "[HiveAdapter] Starting LLM run user=%s industria=%s ciudad=%s max=%d",
                    user_id, industria, ciudad, max_results
                )
                await executor.execute(
                    graph=graph,
                    goal=goal,
                    input_data={
                        "task": (
                            f"Ejecuta la campaña de prospección B2B:\n"
                            f"- Industria objetivo: {industria}\n"
                            f"- Ciudad/Región: {ciudad}\n"
                            f"- Máximo de empresas: {max_results}\n"
                            f"- Dolor operativo: {campaign.get('dolor_operativo', 'N/A')}\n"
                            f"- Solución ofrecida: {campaign.get('solucion_ofrecida', 'N/A')}\n"
                            f"- Software clave: {campaign.get('software_clave', 'N/A')}\n"
                            f"- Decisores: {campaign.get('jerarquia_decisores', 'N/A')}\n\n"
                            f"Empieza ahora: busca {max_results} empresas y analiza TODAS sin detenerte ni hacer preguntas. "
                            f"Completa los 4 pasos del flujo de ejecución de forma autónoma."
                        ),
                    },
                )
                logger.info("[HiveAdapter] Run completed user=%s", user_id)
            except Exception as e:
                logger.error("[HiveAdapter] run error user=%s: %s", user_id, e)
                import traceback; traceback.print_exc()
                await self._send_to_user(user_id, {
                    "type": "error", "message": f"Pipeline error: {e}"
                })
            finally:
                self._runs.pop(user_id, None)
                self._runtime_agents.pop(user_id, None)

        # Cancel any in-flight run for this user before starting new one
        existing = self._runs.get(user_id)
        if existing and not existing.done():
            existing.cancel()

        task = asyncio.create_task(_run())
        self._runs[user_id] = task
        return user_id

    def _make_event_handler(self, user_id: str):
        """Returns async handler: Hive EventBus event → agent_update WS message."""
        async def handler(event) -> None:
            node_id  = getattr(event, "node_id", None)
            state    = _event_to_agent_state(event)
            if state:
                agents = self._runtime_agents.get(user_id) or []
                target_agent_id = next(
                    (
                        str(a.get("id") or "")
                        for a in agents
                        if str(a.get("role") or "") == "researcher" and str(a.get("id") or "")
                    ),
                    "",
                )
                if not target_agent_id:
                    target_agent_id = str((agents[0] if agents else {}).get("id") or "buscador-001")
                await self._send_to_user(user_id, {
                    "type":     "agent_update",
                    "agent_id": target_agent_id,
                    "state":    state.value,
                })
        return handler
