"""
signal_sources.py — Registry and helpers for external signal sources.

Wave 1 builds the data capture layer; pipeline integration happens later.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SignalSourceRegistry:
    def __init__(self) -> None:
        self._sources: dict[str, Any] = {}

    def register(self, name: str, source: Any) -> None:
        self._sources[name] = source

    def get(self, name: str) -> Any:
        return self._sources.get(name)

    async def search(self, name: str, **kwargs) -> list[dict]:
        source = self.get(name)
        if not source:
            raise ValueError(f"Unknown signal source: {name}")
        return await source.search(**kwargs)


def _normalize_nit(raw: str | None) -> str:
    return re.sub(r"\D", "", raw or "")


def build_signal_key(empresa: str, domain: str, nit: str) -> str:
    if nit:
        return f"nit:{nit}"
    base = f"{(empresa or '').strip().lower()}|{(domain or '').strip().lower()}"
    base = re.sub(r"\s+", " ", base).strip()
    return f"name:{base}" if base else ""


def build_signal_doc(
    *,
    user_id: str,
    source: str,
    empresa: str,
    nit: str,
    sector: str,
    ciudad: str,
    fecha_senal: Optional[datetime],
    confianza: float,
    metadata: dict,
) -> dict:
    nit_norm = _normalize_nit(nit)
    domain = str(metadata.get("domain") or "")
    signal_key = build_signal_key(empresa, domain, nit_norm)
    return {
        "user_id": user_id,
        "source": source,
        "empresa": empresa,
        "nit": nit_norm,
        "sector": sector,
        "ciudad": ciudad,
        "fecha_senal": fecha_senal or datetime.now(timezone.utc),
        "confianza": float(confianza or 0),
        "metadata": metadata or {},
        "signal_key": signal_key,
        "processed": False,
        "created_at": datetime.now(timezone.utc),
    }


class RuesSignalSource:
    name = "rues"

    async def search(
        self,
        industria: str,
        ciudad: Optional[str] = None,
        max_results: int = 50,
        dias_recientes: int = 180,
    ) -> list[dict]:
        from rues import fetch_rues_companies

        rows = await fetch_rues_companies(
            industria=industria,
            ciudad=ciudad,
            max_results=max_results,
            dias_recientes=dias_recientes,
        )
        signals: list[dict] = []
        for row in rows:
            signals.append(
                {
                    "source": self.name,
                    "empresa": row.get("razon_social") or "",
                    "nit": row.get("numero_id") or "",
                    "sector": row.get("ciiu") or "",
                    "ciudad": row.get("camara_comercio") or (ciudad or ""),
                    "fecha_senal": row.get("fecha_matricula"),
                    "confianza": 0.85,
                    "metadata": {
                        "camara_comercio": row.get("camara_comercio"),
                        "organizacion": row.get("organizacion"),
                        "estado": row.get("estado"),
                        "dias_desde_registro": row.get("dias_desde_registro"),
                    },
                }
            )
        return signals


registry = SignalSourceRegistry()
registry.register("rues", RuesSignalSource())


async def store_signals(user_id: str, signals: list[dict]) -> dict:
    from database import upsert_signal_lead

    inserted = 0
    skipped = 0
    for sig in signals:
        if not sig.get("signal_key"):
            nit = _normalize_nit(str(sig.get("nit") or ""))
            meta = sig.get("metadata") or {}
            domain = str(meta.get("domain") or "")
            sig["signal_key"] = build_signal_key(str(sig.get("empresa") or ""), domain, nit)
        try:
            ok = await upsert_signal_lead(user_id, sig)
            inserted += 1 if ok else 0
            skipped += 0 if ok else 1
        except Exception as exc:
            logger.warning("[signals] failed to store %s: %s", sig.get("source"), exc)
            skipped += 1
    return {"inserted": inserted, "skipped": skipped}
