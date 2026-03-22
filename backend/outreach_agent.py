"""
outreach_agent.py — Re-export shim for outreach agent.

Canonical implementation lives in backend/landa/agents/outreach.py.

Invocado desde:
  - backend/main.py (approve_lead endpoint) via asyncio.create_task
  - backend/landa/scheduler.py (_noop_stub replacement, Phase 13)
"""
from landa.agents.outreach import run_outreach  # noqa: F401

__all__ = ["run_outreach"]
