"""
bright_data_linkedin.py — Bright Data LinkedIn hiring signals.

Requires env:
- BRIGHT_DATA_API_KEY
- BRIGHT_DATA_DATASET_ID
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


class BrightDataLinkedInSource:
    name = "bright_data"

    def __init__(self, api_key: Optional[str] = None, dataset_id: Optional[str] = None) -> None:
        self.api_key = api_key or os.getenv("BRIGHT_DATA_API_KEY", "")
        self.dataset_id = dataset_id or os.getenv("BRIGHT_DATA_DATASET_ID", "")

    async def search(
        self,
        sector: str,
        country: str = "CO",
        ciudad: Optional[str] = None,
        max_results: int = 100,
    ) -> list[dict]:
        if not self.api_key or not self.dataset_id:
            logger.warning("[bright_data] missing api key or dataset id")
            return []

        url = f"https://api.brightdata.com/datasets/{self.dataset_id}/download"
        payload = {
            "query": {
                "sector": sector,
                "country": country,
            }
        }
        if ciudad:
            payload["query"]["city"] = ciudad

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.error("[bright_data] request failed: %s", exc)
            return []

        rows = data.get("data") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            logger.warning("[bright_data] unexpected response type: %s", type(rows))
            return []

        signals: list[dict] = []
        for row in rows[:max_results]:
            company = (row.get("company") or row.get("company_name") or "").strip()
            if not company:
                continue
            url_value = row.get("company_url") or row.get("url") or ""
            signals.append(
                {
                    "source": self.name,
                    "empresa": company,
                    "nit": "",
                    "sector": sector or row.get("industry") or "",
                    "ciudad": ciudad or row.get("city") or "",
                    "fecha_senal": datetime.now(timezone.utc),
                    "confianza": 0.7,
                    "metadata": {
                        "url": url_value,
                        "domain": row.get("domain") or "",
                        "new_hires": row.get("new_hires") or row.get("hiring") or 0,
                        "growth_rate": row.get("growth_rate") or 0,
                        "raw": row,
                    },
                }
            )
        return signals
