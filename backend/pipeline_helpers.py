"""Helper functions for pipeline agent configuration — extracted from main.py."""
from typing import Optional


def _resolve_agent_model(role: str, campaign: dict) -> str:
    if role == "reviewer":
        return str(campaign.get("llm_analista") or "openai/gpt-4.1-nano")
    if role == "writer":
        return str(campaign.get("llm_redactor") or "openai/gpt-4.1-nano")
    return "tooling-only"


def _normalize_agent_configs(agents: list, campaign: dict, personality_prompt: str) -> list[dict]:
    role_to_responsibility = {
        "researcher": "Descubrir empresas objetivo por industria y ciudad",
        "planner": "Extraer señales clave del sitio web y preparar contexto",
        "reviewer": "Calificar fit B2B y decidir aprobación/rechazo",
        "writer": "Redactar outreach personalizado según hallazgos",
        "whatsapp_sender": "Enviar y gestionar outreach por WhatsApp",
    }
    normalized: list[dict] = []
    for agent in agents or []:
        role = str(agent.get("role") or "")
        persona = str(agent.get("persona") or "")
        if role == "reviewer":
            prompt_text = personality_prompt or persona
            prompt_source = "onboarding.system_prompt_analista"
        elif role == "writer":
            prompt_text = "backend/prospector.py::_motor_scoring_prompt"
            prompt_source = "backend.prospector"
        else:
            prompt_text = persona
            prompt_source = "onboarding.agent.persona"
        normalized.append({
            "id": str(agent.get("id") or ""),
            "name": str(agent.get("name") or ""),
            "role": role,
            "channel": str(agent.get("channel") or "email"),
            "model": _resolve_agent_model(role, campaign),
            "responsibility": role_to_responsibility.get(role, "Responsabilidad definida por onboarding"),
            "persona": persona,
            "prompt": prompt_text,
            "prompt_source": prompt_source,
        })
    return normalized


def _build_runtime_agents(profile: Optional[dict]) -> list[dict]:
    from hive_graph import PIPELINE_AGENTS as DEFAULT_PIPELINE_AGENTS
    agents = (profile or {}).get("agents") or []
    if not agents:
        return DEFAULT_PIPELINE_AGENTS
    allowed_roles = {"coder", "researcher", "writer", "reviewer", "planner"}
    role_alias = {"whatsapp_sender": "writer"}
    runtime_agents: list[dict] = []
    for idx, agent in enumerate(agents):
        raw_role = str(agent.get("role") or "").strip().lower()
        normalized_role = role_alias.get(raw_role, raw_role)
        if normalized_role not in allowed_roles:
            normalized_role = "reviewer"
        runtime_agents.append({
            "id": str(agent.get("id") or f"agent-{idx + 1:03d}"),
            "name": str(agent.get("name") or f"Agente {idx + 1}"),
            "role": normalized_role,
            "state": "idle",
            "palette": idx % 6,
            "current_tool": None,
            "tool_status": None,
            "seat_id": None,
            "is_subagent": False,
            "parent_agent_id": None,
        })
    return runtime_agents or DEFAULT_PIPELINE_AGENTS
