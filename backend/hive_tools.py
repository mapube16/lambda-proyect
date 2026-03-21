"""
hive_tools.py — Tool factory for the B2B prospecting pipeline.

Wraps prospector.py async functions as Hive Tool objects with closures
that capture per-run context (user_id, campaign, send_to_user, etc.).

Usage:
    registry = make_prospecting_registry(
        campaign=..., gmaps_key=..., openrouter_key=...,
        user_id=..., run_id=..., send_to_user=..., save_lead=...,
    )
    tools    = list(registry.get_tools().values())
    executor = registry.get_executor()
"""
from __future__ import annotations

import json
import logging
from typing import Callable, Awaitable

from framework.llm.provider import Tool
from framework.runner.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

SendFn = Callable[[str, dict], Awaitable[None]]


def make_prospecting_registry(
    campaign: dict,
    gmaps_key: str,
    openrouter_key: str,
    user_id: str,
    run_id: str,
    send_to_user: SendFn,
    save_lead: Callable | None,
    max_results: int = 20,
    personality_prompt: str = "",
    runtime_agents: list[dict] | None = None,
    excluded_domains: list[str] | None = None,
    use_openrouter: bool = False,
) -> ToolRegistry:
    """
    Build and return a ToolRegistry with two tools:
      - discover_companies: search by industry + city, returns list of company dicts
      - analyze_company:    scrape + LLM-analyze a single company URL
    """
    from openai import AsyncOpenAI

    openai_client = AsyncOpenAI(
        api_key=openrouter_key,
        base_url="https://openrouter.ai/api/v1" if use_openrouter else "https://api.openai.com/v1",
    )

    def _normalize_model_name(model_name: str, fallback: str) -> str:
        value = str(model_name or "").strip()
        if not value:
            return fallback
        if use_openrouter:
            return value
        if value.startswith("openai/"):
            return value.split("/", 1)[1]
        if value.startswith("openrouter/"):
            candidate = value.split("/", 1)[1]
            if candidate.startswith("gpt-"):
                return candidate
            return fallback
        if value.startswith("anthropic/") or value.startswith("google/") or value.startswith("meta/"):
            return fallback
        return value

    campaign_models = {
        **campaign,
        "llm_analista": _normalize_model_name(campaign.get("llm_analista", ""), "gpt-4o-mini"),
        "llm_redactor": _normalize_model_name(campaign.get("llm_redactor", ""), "gpt-4o-mini"),
    }

    runtime_agents = runtime_agents or [
        {"id": "buscador-001", "role": "researcher"},
        {"id": "scraper-001", "role": "planner"},
        {"id": "analista-001", "role": "reviewer"},
        {"id": "redactor-001", "role": "writer"},
    ]
    excluded_domains = [str(d).lower().strip() for d in (excluded_domains or []) if str(d).strip()]
    excluded_set = set(excluded_domains)

    def _agent_ids_for_role(role: str, fallback: str) -> list[str]:
        ids: list[str] = []
        for agent in runtime_agents:
            agent_id = str(agent.get("id") or "")
            agent_role = str(agent.get("role") or "")
            if agent_id and agent_role == role and agent_id not in ids:
                ids.append(agent_id)
        return ids or [fallback]

    all_agent_ids: list[str] = []
    for agent in runtime_agents:
        agent_id = str(agent.get("id") or "")
        if agent_id and agent_id not in all_agent_ids:
            all_agent_ids.append(agent_id)

    # ── Shared run state (tracks real counts across tool calls) ────────────
    _state: dict = {
        "discovered": [],   # company list from discover_companies
        "analyzed":   0,    # total analyze_company calls completed
        "approved":   0,    # total SUCCESS_READY_FOR_REVIEW
        "rejected":   0,    # total REJECTED_BY_AI or error
    }

    # ── Tool 1: discover_companies ─────────────────────────────────────────

    async def _discover_companies(industria: str, ciudad: str, max_r: int = 0) -> dict:
        """Discover B2B companies via Google Maps + Bing + DuckDuckGo."""
        from prospector import discover_companies

        n = int(max_r) if max_r else max_results
        logger.info(
            "[discover_companies] user=%s industria=%s ciudad=%s max=%d",
            user_id, industria, ciudad, n
        )
        for aid in _agent_ids_for_role("researcher", "buscador-001"):
            await send_to_user(user_id, {
                "type": "agent_update", "agent_id": aid,
                "state": "thinking",
                "tool_status": f"Buscando {industria} en {ciudad}...",
            })
        companies = await discover_companies(
            industria,
            ciudad,
            n,
            gmaps_key,
            excluded_domains=excluded_set,
            use_secop=bool(campaign.get("use_secop", False)),
        )
        _state["discovered"] = companies
        await send_to_user(user_id, {
            "type": "discovery_complete", "count": len(companies),
        })
        if excluded_set:
            await send_to_user(user_id, {
                "type": "discovery_filtering",
                "excluded_domains": len(excluded_set),
            })
        for aid in _agent_ids_for_role("researcher", "buscador-001"):
            await send_to_user(user_id, {
                "type": "agent_update", "agent_id": aid,
                "state": "waiting",
                "tool_status": f"✓ {len(companies)} empresas encontradas",
            })
        return {"companies": companies, "total": len(companies)}

    discover_tool = Tool(
        name="discover_companies",
        description=(
            "Search for B2B companies in a given industry and city using Google Maps,"
            " Bing and DuckDuckGo. Returns a list of companies with their URLs, phone"
            " numbers and addresses."
        ),
        parameters={
            "type": "object",
            "properties": {
                "industria": {
                    "type": "string",
                    "description": "Industry or business type to search for (e.g. 'transporte de carga')",
                },
                "ciudad": {
                    "type": "string",
                    "description": "City or region to search in (e.g. 'Bogotá')",
                },
                "max_r": {
                    "type": "integer",
                    "description": "Maximum number of companies to return (default uses run setting)",
                },
            },
            "required": ["industria", "ciudad"],
        },
    )

    # ── Tool 2: analyze_company ────────────────────────────────────────────

    async def _analyze_company(
        url: str,
        title: str,
        phone: str = "",
        address: str = "",
    ) -> dict:
        """Scrape a company's website and run the 3-stage LLM analysis pipeline."""
        from prospector import analyze_company

        company = {
            "url": url, "title": title,
            "phone": phone, "address": address,
        }
        logger.info("[analyze_company] user=%s url=%s", user_id, url)

        async def on_stage(stage: str, status: str):
            _state = {
                "scraper":  "tool_use",
                "analista": "thinking",
                "redactor": "tool_use",
            }.get(stage, "thinking")
            role = {
                "scraper": "planner",
                "analista": "reviewer",
                "redactor": "writer",
            }.get(stage, "reviewer")
            fallback = {
                "scraper": "scraper-001",
                "analista": "analista-001",
                "redactor": "redactor-001",
            }.get(stage, "analista-001")
            for aid in _agent_ids_for_role(role, fallback):
                await send_to_user(user_id, {
                    "type": "agent_update", "agent_id": aid,
                    "state": _state, "tool_status": status,
                })

        idx = _state["analyzed"]
        total = len(_state["discovered"]) or 1
        result = await analyze_company(
            company,
            campaign_models,
            openai_client,
            on_stage,
            personality_prompt=personality_prompt,
        )
        result["index"] = idx
        result["total"] = total

        # Track real counts
        _state["analyzed"] += 1
        if result.get("status") == "success":
            _state["approved"] += 1
        else:
            _state["rejected"] += 1

        # Persist lead to DB if configured
        if save_lead and run_id:
            json_payload = result.get("json_payload") or {}
            try:
                lead_id = await save_lead(run_id, user_id, {
                    "company_name":        company.get("title", ""),
                    "url":                 result.get("url", url),
                    "phone":               phone,
                    "address":             address,
                    "score":               json_payload.get("score"),
                    "system_state":        json_payload.get("system_state", "REJECTED_BY_AI"),
                    "expediente_markdown": result.get("markdown"),
                    "expediente_json":     json_payload,
                })
                result["lead_id"] = lead_id
            except Exception as e:
                logger.error("[analyze_company] save_lead error: %s", e)

        # Broadcast lead result
        await send_to_user(user_id, {"type": "lead_result", **result})
        return result

    analyze_tool = Tool(
        name="analyze_company",
        description=(
            "Scrape a company's website and run a 3-stage analysis pipeline: "
            "scrape → LLM analyst → LLM scorer/writer. Returns qualification score, "
            "system_state (SUCCESS_READY_FOR_REVIEW or REJECTED_BY_AI), and a draft email."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Full URL of the company's website",
                },
                "title": {
                    "type": "string",
                    "description": "Company name",
                },
                "phone": {
                    "type": "string",
                    "description": "Phone number if available (optional)",
                },
                "address": {
                    "type": "string",
                    "description": "Physical address if available (optional)",
                },
            },
            "required": ["url", "title"],
        },
    )

    # ── Tool 3: report_campaign_complete ───────────────────────────────────

    async def _report_campaign_complete(
        total_analyzed: int,
        total_approved: int,
        total_rejected: int,
    ) -> dict:
        """Send the campaign_complete summary to the frontend (uses real tracked counts)."""
        real_analyzed = _state["analyzed"]
        real_approved = _state["approved"]
        real_rejected = _state["rejected"]
        logger.info(
            "[report_campaign_complete] user=%s llm_claimed=(%d/%d/%d) actual=(%d/%d/%d)",
            user_id, total_analyzed, total_approved, total_rejected,
            real_analyzed, real_approved, real_rejected,
        )
        await send_to_user(user_id, {
            "type": "campaign_complete",
            "total_analyzed": real_analyzed,
            "total_approved": real_approved,
            "total_rejected": real_rejected,
        })
        for aid in (all_agent_ids or ["buscador-001", "scraper-001", "analista-001", "redactor-001"]):
            await send_to_user(user_id, {
                "type": "agent_update", "agent_id": aid,
                "state": "idle", "tool_status": None,
            })
        return {"status": "sent", "total_analyzed": real_analyzed}

    complete_tool = Tool(
        name="report_campaign_complete",
        description=(
            "Send the final campaign summary to the user. Call this ONCE after all"
            " companies have been analyzed. Resets all agent states to idle."
        ),
        parameters={
            "type": "object",
            "properties": {
                "total_analyzed": {"type": "integer"},
                "total_approved": {"type": "integer"},
                "total_rejected": {"type": "integer"},
            },
            "required": ["total_analyzed", "total_approved", "total_rejected"],
        },
    )

    # ── Register all tools ─────────────────────────────────────────────────

    registry = ToolRegistry()
    registry.register("discover_companies",      discover_tool,  lambda i: _discover_companies(**i))
    registry.register("analyze_company",         analyze_tool,   lambda i: _analyze_company(**i))
    registry.register("report_campaign_complete", complete_tool,  lambda i: _report_campaign_complete(**i))

    return registry
