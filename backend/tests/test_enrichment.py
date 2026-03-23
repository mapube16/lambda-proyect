"""
test_enrichment.py — Wave 0 xfail stubs for Phase 15: Pipeline Enrichment + Real Channel Activation.

Requirement areas:
  ENRICH-01: SECOP flag resolution (bridge from secop_radar results to lead flags)
  ENRICH-02: NIT enrichment (async enrichment of leads with Colombian company registry data)
  ENRICH-03: WhatsApp outreach fallback (channel routing when phone present/absent)

All stubs raise NotImplementedError — they will be un-xfailed in Wave 1 plans (15-02, 15-03, 15-04).
"""
import pytest


# ── ENRICH-01: SECOP flag resolution ──────────────────────────────────────────


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_secop_flag_from_company_voice():
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_secop_flag_fallback_to_campaign():
    raise NotImplementedError


# ── ENRICH-02: NIT enrichment ─────────────────────────────────────────────────


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_nit_enrichment_saved_to_lead():
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_nit_enrichment_skipped_when_no_nit():
    raise NotImplementedError


# ── ENRICH-03: WhatsApp outreach fallback ─────────────────────────────────────


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_outreach_whatsapp_sends_with_phone():
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_outreach_whatsapp_fallback_to_email():
    raise NotImplementedError


@pytest.mark.xfail(strict=True, reason="not implemented — Phase 15")
async def test_outreach_no_phone_no_email():
    raise NotImplementedError
