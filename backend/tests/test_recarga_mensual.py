"""test_recarga_mensual.py — cron de recarga mensual de minutos (día >= 15).

Corre recarga_mensual_job contra el mongomock del conftest; solo se mockea
get_tenant_config (Redis). El ledger y get_saldo son los reales.
"""
import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

import database
from cobranza import minutes
from cobranza.report_scheduler import recarga_mensual_job

DPG = "69bcd9bb6e35d53880364535"
CFG = {"cobranza": {"facturacion": {
    "recarga_mensual_minutos": 1500, "recarga_mensual_desde": "2026-09",
}}}


async def _run(hoy: date, cfg: dict = CFG):
    db = database.get_db()
    await db.company_voice.update_one(
        {"user_id": DPG}, {"$set": {"cobranza_enabled": True}}, upsert=True
    )
    with patch("cobranza.config_cache.get_tenant_config", AsyncMock(return_value=cfg)):
        await recarga_mensual_job(hoy=hoy)
    return db


@pytest.mark.asyncio
async def test_antes_del_15_no_carga():
    db = await _run(date(2026, 9, 14))
    assert (await minutes.get_saldo(db, DPG))["minutos_comprados"] == 0


@pytest.mark.asyncio
async def test_el_15_carga_y_el_catchup_no_duplica():
    db = await _run(date(2026, 9, 15))
    await _run(date(2026, 9, 16))  # chequeo diario del mismo mes: idempotente
    saldo = await minutes.get_saldo(db, DPG)
    assert saldo["minutos_comprados"] == 1500
    compra = await db[minutes.COLLECTION].find_one({"tipo": "compra"})
    assert compra["nota"] == "Recarga mensual 2026-09"
    assert compra["actor"] == "cron_recarga"


@pytest.mark.asyncio
async def test_mes_siguiente_suma_otra_recarga():
    db = await _run(date(2026, 9, 15))
    await _run(date(2026, 10, 15))
    assert (await minutes.get_saldo(db, DPG))["minutos_comprados"] == 3000


@pytest.mark.asyncio
async def test_no_retro_carga_antes_del_desde():
    # desde=2026-09 y hoy 30-ago (>= 15): agosto NO se retro-carga
    db = await _run(date(2026, 8, 30))
    assert (await minutes.get_saldo(db, DPG))["minutos_comprados"] == 0


@pytest.mark.asyncio
async def test_sin_config_no_carga():
    db = await _run(date(2026, 9, 15), cfg={})
    assert (await minutes.get_saldo(db, DPG))["minutos_comprados"] == 0
