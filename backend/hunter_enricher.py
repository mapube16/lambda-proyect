"""
hunter_enricher.py — Hunter email enrichment helpers.

Requires env:
- HUNTER_API_KEY
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class HunterClient:
    def __init__(self, api_key: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("HUNTER_API_KEY", "")

    async def find_email(
        self,
        domain: str,
        first_name: str,
        last_name: str,
        user_id: Optional[str] = None,
    ) -> dict:
        if not self.api_key:
            logger.warning("[hunter] missing api key")
            return {}

        params = {
            "domain": domain,
            "first_name": first_name,
            "last_name": last_name,
            "api_key": self.api_key,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://api.hunter.io/v2/email-finder", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("[hunter] email finder failed: %s", exc)
            return {}

        if user_id:
            await _record_cost_event(user_id, "hunter", 0.05, {"domain": domain})
        return data

    async def domain_search(self, domain: str, user_id: Optional[str] = None) -> dict:
        if not self.api_key:
            logger.warning("[hunter] missing api key")
            return {}

        params = {"domain": domain, "api_key": self.api_key}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get("https://api.hunter.io/v2/domain-search", params=params)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("[hunter] domain search failed: %s", exc)
            return {}

        if user_id:
            await _record_cost_event(user_id, "hunter", 0.01, {"domain": domain})
        return data


async def _record_cost_event(user_id: str, source: str, cost_usd: float, metadata: dict) -> None:
    try:
        from database import record_cost_event

        await record_cost_event(user_id, source, cost_usd, metadata=metadata)
    except Exception as exc:
        logger.warning("[hunter] cost event failed: %s", exc)
