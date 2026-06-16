"""
deduplication.py — Lead de-duplication helpers for signal sources.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from database import get_db


def _normalize_domain(url: str) -> str:
    value = (url or "").strip().lower()
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = f"https://{value}"
    try:
        host = (urlparse(value).netloc or "").lower().strip()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host


def _normalize_text(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip().lower())
    return text


class DeduplicationEngine:
    def __init__(self) -> None:
        self._db = get_db()

    async def find_duplicate(self, *, nit: str, empresa: str, url: str, user_id: str) -> dict | None:
        """Return existing lead doc if it matches by NIT, domain, or fuzzy name."""
        nit_norm = re.sub(r"\D", "", nit or "")
        if nit_norm:
            existing = await self._db.leads.find_one({"user_id": user_id, "nit": nit_norm})
            if existing:
                return existing

        domain = _normalize_domain(url)
        if domain:
            existing = await self._db.leads.find_one({"user_id": user_id, "url": {"$regex": domain}})
            if existing:
                return existing

        name_norm = _normalize_text(empresa)
        if not name_norm:
            return None
        cursor = self._db.leads.find({"user_id": user_id, "company_name": {"$exists": True}})
        docs = await cursor.to_list(length=300)
        for lead in docs:
            lead_name = _normalize_text(str(lead.get("company_name") or ""))
            if not lead_name:
                continue
            ratio = SequenceMatcher(None, name_norm, lead_name).ratio()
            if ratio >= 0.92:
                return lead
        return None
