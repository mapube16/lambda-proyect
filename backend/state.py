"""
Shared mutable singletons initialized during lifespan.
Always import the module and access via state.orchestrator / state.hive_adapter
— do NOT use `from state import orchestrator` (captures None at import time).
"""
from typing import Dict, Optional
from datetime import datetime, timezone

orchestrator = None
hive_adapter = None
arq_pool = None

_agent_state_cache: Dict[str, Dict[str, dict]] = {}


def update_agent_state_cache(user_id: str, agent_id: str, state_data: dict):
    if user_id not in _agent_state_cache:
        _agent_state_cache[user_id] = {}
    _agent_state_cache[user_id][agent_id] = {
        **state_data,
        "updated_at": datetime.now(timezone.utc),
    }
