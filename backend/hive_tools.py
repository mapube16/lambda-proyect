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

import asyncio
import json
import logging
from typing import Callable, Awaitable

from framework.llm.provider import Tool
from framework.runner.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)

SendFn = Callable[[str, dict], Awaitable[None]]

# Generic Spanish business words excluded from competitor keyword matching
# (exported at module level so tests can import and validate it)
COMPETITOR_GENERIC_WORDS: frozenset[str] = frozenset({
    "agencia", "empresa", "empresas", "servicios", "soluciones", "grupo",
    "digital", "nacional", "colombia", "bogota", "bogotá", "ltda", "sas",
    "corp", "compania", "compañia", "consultora", "consultores", "centro",
})


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
    source_priority: str = "serper",  # "serper" | "bright_data" | "hybrid"
) -> ToolRegistry:
    """
    Build and return a ToolRegistry with two tools:
      - discover_companies: search by industry + city, returns list of company dicts
      - analyze_company:    scrape + LLM-analyze a single company URL

    source_priority: Controls which data source to use:
      - "serper": economical Serper search
      - "bright_data": premium Bright Data Web Scraper (emails, phones, full contact)
      - "hybrid": both sources combined for maximum coverage
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
        "llm_analista": _normalize_model_name(campaign.get("llm_analista", ""), "gpt-5.4-2026-03-05"),
        "llm_redactor": _normalize_model_name(campaign.get("llm_redactor", ""), "gpt-5.4-2026-03-05"),
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
        "discovered": [],        # company list from discover_companies
        "discovery_calls": 0,    # number of times discover_companies was called
        "analyzed":   0,    # total analyze_company calls completed
        "approved":   0,    # total SUCCESS_READY_FOR_REVIEW
        "rejected":   0,    # total REJECTED_BY_AI or error
        # Per-agent decision log — shown when user clicks an agent card
        "agent_logs": {
            "buscador":  [],   # discovery decisions
            "analista":  [],   # per-company analysis decisions
            "redactor":  [],   # scoring + email summary
        },
        "rejection_reasons": {},  # reason_code → count
    }

    def _log(agent: str, msg: str) -> None:
        _state["agent_logs"].setdefault(agent, []).append(msg)

    # ── Tool 1: discover_companies ─────────────────────────────────────────

    async def _discover_companies(industria: str, ciudad: str, max_r: int = 0) -> dict:
        """Discover B2B companies via Google Maps + Bing + DuckDuckGo."""
        from prospector import discover_companies

        # Guard: discovery runs exactly once per pipeline execution.
        if _state["discovery_calls"] > 0:
            n_found = len(_state["discovered"])
            logger.warning(
                "[discover_companies] BLOCKED: discovery already ran (%d calls, %d companies found)",
                _state["discovery_calls"],
                n_found,
            )
            if n_found > 0:
                raise RuntimeError(
                    f"[BLOCKED] discover_companies already ran and found {n_found} companies. "
                    "You MUST NOT call discover_companies again. "
                    f"Call analyze_company for each of the {n_found} companies you already have."
                )
            else:
                raise RuntimeError(
                    "[BLOCKED] discover_companies already ran and found 0 companies. "
                    "Call report_campaign_complete with totals=0 and then set_output to finish."
                )

        # Guard: override generic industria if LLM passed a meaningless term.
        # This is a defense-in-depth fix for the bug where the director LLM calls
        # discover_companies(industria="empresas") instead of the real campaign industry.
        _GENERIC_INDUSTRIA_TERMS = frozenset({
            "empresas", "empresa", "negocios", "negocio", "companies", "company",
            "business", "organizaciones", "organizacion", "",
        })
        campaign_industria = campaign.get("industria_objetivo", "").strip()
        if campaign_industria and industria.lower().strip() in _GENERIC_INDUSTRIA_TERMS:
            logger.warning(
                "[discover_companies] LLM passed generic industria=%r; overriding with campaign=%r",
                industria, campaign_industria,
            )
            industria = campaign_industria

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
        # -- SECOP flags from company_voice (Phase 15) --
        from landa.company_voice import get_or_create_company_voice
        try:
            cv = await get_or_create_company_voice(user_id)
            fuentes = cv.get("fuentes_habilitadas") or []
        except Exception as e:
            logger.warning("[discover_companies] company_voice load failed: %s", e)
            fuentes = []

        if fuentes:
            use_secop       = "secop_adjudicados"  in fuentes
            use_secop_radar = "secop_licitaciones" in fuentes
        else:
            use_secop       = bool(campaign.get("use_secop",       False))
            use_secop_radar = bool(campaign.get("use_secop_radar", False))

        _state["discovery_calls"] += 1
        try:
            companies = await discover_companies(
                industria,
                ciudad,
                n,
                gmaps_key,
                excluded_domains=excluded_set,
                use_secop=use_secop,
                source_priority=source_priority,
            )
        except Exception as exc:
            logger.error("[discover_companies] Exception in prospector: %s", exc, exc_info=True)
            companies = []
        if use_secop_radar:
            try:
                from secop_radar import fetch_open_processes
                radar_leads = await fetch_open_processes(sector=industria)
                # Merge radar leads into companies list (deduplicate by domain)
                from urllib.parse import urlparse
                existing_domains = {
                    urlparse(c.get("url", "")).netloc.lower().lstrip("www.")
                    for c in companies
                    if c.get("url")
                }
                for rl in radar_leads:
                    rl_domain = urlparse(rl.get("url", "")).netloc.lower().lstrip("www.")
                    if rl_domain and rl_domain not in existing_domains:
                        companies.append(rl)
                        existing_domains.add(rl_domain)
                logger.info("[discover_companies] secop_radar added %d leads", len(radar_leads))
            except Exception as e:
                logger.warning("[discover_companies] secop_radar error: %s", e)
        _state["discovered"] = companies
        # ── Log buscador decisions ─────────────────────────────────────────
        _log("buscador", f"Consulta: '{industria}' en {ciudad}")
        _log("buscador", f"Empresas encontradas: {len(companies)}")
        if excluded_set:
            _log("buscador", f"Dominios excluidos por historial de campaña: {len(excluded_set)}")
        if companies:
            for c in companies[:3]:
                _log("buscador", f"  • {c.get('title','?')[:45]}  ({c.get('source','ddg')})")
            if len(companies) > 3:
                _log("buscador", f"  … y {len(companies) - 3} más")
        else:
            _log("buscador", "  Sin resultados — verifica la industria o la ciudad")
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

    # Build competitor keyword set once (from sector_propio_cliente campaign field)
    _sector_propio_raw = str(campaign.get("sector_propio_cliente") or "").strip()
    _competitor_keywords: list[str] = [
        w.strip().lower()
        for token in _sector_propio_raw.replace(",", " ").split()
        for w in [token.strip()]
        if len(w) >= 5 and w.strip().lower() not in COMPETITOR_GENERIC_WORDS
    ] if _sector_propio_raw else []

    def _is_competitor_by_name(url: str, title: str) -> bool:
        """Pre-filter: keyword match on name+URL before any scraping or LLM call."""
        if not _competitor_keywords:
            return False
        text = f"{title} {url}".lower()
        return any(kw in text for kw in _competitor_keywords)

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

        # Pre-filter: skip obvious competitors without scraping or LLM
        if _is_competitor_by_name(url, title):
            logger.info("[analyze_company] pre-filter competitor: %s — %s", title, url)
            return {
                "url": url, "title": title, "phone": phone, "address": address,
                "status": "rejected",
                "json_payload": {"motivo_descalificacion": "KILL_DIRECT_COMPETITOR"},
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

        # Silently discard — don't show or save them
        jp = result.get("json_payload") or {}
        motivo = jp.get("motivo_descalificacion", "")
        if motivo in ("KILL_DIRECT_COMPETITOR", "SCRAPING_BLOCKED"):
            logger.info("[analyze_company] silently discarded (%s): %s", motivo, url)
            _log("buscador", f"  [descartado silenciosamente] {title[:45]} — {motivo}")
            return result

        # Track real counts
        _state["analyzed"] += 1
        is_approved = result.get("status") == "success"
        if is_approved:
            _state["approved"] += 1
        else:
            _state["rejected"] += 1
            # Track rejection reasons for summary
            if motivo:
                _state["rejection_reasons"][motivo] = _state["rejection_reasons"].get(motivo, 0) + 1

        # ── Log analista decision ──────────────────────────────────────────
        score  = jp.get("score") or 0
        sector = "✓ sector correcto" if (jp.get("es_sector_correcto") or result.get("status") == "success") else "✗ sector incorrecto"
        tamano = jp.get("tamano_estimado") or "desconocido"
        dolor  = "✓ dolor detectado" if jp.get("sintomas_de_dolor") else "sin dolor claro"
        nombre = jp.get("empresa") or title[:35]
        if is_approved:
            email_ok = bool((jp.get("borradores") or {}).get("email_cuerpo"))
            decisor_nombre = (jp.get("decisor") or {}).get("nombre") or "sin nombre"
            _log("analista", f"APROBADO [{score}]  {nombre}  |  {sector}  |  {tamano}  |  {dolor}")
            _log("redactor", f"  Email generado: {nombre}  |  decisor: {decisor_nombre}  |  score: {score}")
        else:
            motivo_short = motivo or "LOW_SCORE"
            _log("analista", f"RECHAZADO         {nombre[:35]}  |  {motivo_short}")

        # Persist lead to DB if configured
        if save_lead and run_id:
            try:
                lead_id = await save_lead(run_id, user_id, {
                    "company_name":        company.get("title", ""),
                    "url":                 result.get("url", url),
                    "phone":               phone,
                    "address":             address,
                    "score":               jp.get("score"),
                    "system_state":        jp.get("system_state", "REJECTED_BY_AI"),
                    "expediente_markdown": result.get("markdown"),
                    "expediente_json":     jp,
                })
                result["lead_id"] = lead_id
                # NIT enrichment - non-blocking (Phase 15)
                nit_raw = (
                    jp.get("nit")
                    or jp.get("decisor", {}).get("nit")
                    or company.get("nit", "")
                )
                if nit_raw:
                    async def _enrich_and_save(nit: str, lid: str) -> None:
                        try:
                            from nit_enricher import enrich_nit
                            from database import update_lead_nit_data
                            enriched = await enrich_nit(nit)
                            await update_lead_nit_data(lid, enriched)
                            logger.info(
                                "[analyze_company] NIT enrichment saved for lead %s", lid
                            )
                        except Exception as exc:
                            logger.warning(
                                "[analyze_company] NIT enrichment failed for lead %s: %s",
                                lid, exc,
                            )
                    _nit_task = asyncio.create_task(_enrich_and_save(nit_raw, lead_id))
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
        # ── Build redactor summary entry ──────────────────────────────────
        approval_pct = int(real_approved / real_analyzed * 100) if real_analyzed else 0
        _log("redactor", f"")
        _log("redactor", f"RESUMEN FINAL")
        _log("redactor", f"  Analizadas: {real_analyzed}  |  Aprobadas: {real_approved}  |  Tasa: {approval_pct}%")
        if _state["rejection_reasons"]:
            reasons = ", ".join(f"{v}× {k}" for k, v in sorted(_state["rejection_reasons"].items(), key=lambda x: -x[1]))
            _log("redactor", f"  Rechazadas: {real_rejected}  ({reasons})")
        # ── Build buscador summary entry ──────────────────────────────────
        _log("buscador", f"")
        _log("buscador", f"RESULTADO FINAL: {len(_state['discovered'])} descubiertas → {real_analyzed} analizadas → {real_approved} aprobadas")

        agent_logs = _state["agent_logs"]
        await send_to_user(user_id, {
            "type": "campaign_complete",
            "total_analyzed": real_analyzed,
            "total_approved": real_approved,
            "total_rejected": real_rejected,
            "agent_logs": agent_logs,
        })
        for aid in (all_agent_ids or ["buscador-001", "scraper-001", "analista-001", "redactor-001"]):
            await send_to_user(user_id, {
                "type": "agent_update", "agent_id": aid,
                "state": "idle", "tool_status": None,
            })
        return {"status": "sent", "total_analyzed": real_analyzed, "agent_logs": agent_logs}

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
