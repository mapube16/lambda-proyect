"""
nurturing_agent.py — Top-level re-export shim for LANDA-08 nurturing agent.

The implementation lives in backend/landa/agents/nurturing.py.
This module re-exports run_nurturing for callers that prefer the flat backend/ layout.
"""
from landa.agents.nurturing import run_nurturing  # noqa: F401

__all__ = ["run_nurturing"]
