"""
test_call_scheduler.py — TDD RED phase for call_scheduler.py (Plan 17-03 Task 1).

Tests Ley 2300 de 2023 compliance:
- Mon-Fri 7am-7pm Colombia allowed
- Saturday 8am-3pm allowed
- Sunday never
- Holidays never
- Daily contact guard
- get_next_allowed_slot
"""
import pytest
from unittest.mock import patch
from datetime import datetime, timezone, timedelta
import pytz

COLOMBIA_TZ = pytz.timezone("America/Bogota")


# ── is_contact_allowed_now ─────────────────────────────────────────────────────

def _make_dt(year, month, day, hour, minute=0, tz=COLOMBIA_TZ):
    """Helper: create a timezone-aware datetime in Colombia tz."""
    return tz.localize(datetime(year, month, day, hour, minute))


def test_monday_2am_not_allowed():
    """Monday 2am Colombia → not allowed (outside 7am-7pm)."""
    from cobranza.call_scheduler import is_contact_allowed_now
    # 2026-03-30 is Monday (not a holiday)
    fake_now = _make_dt(2026, 3, 30, 2, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is False


def test_monday_10am_allowed():
    """Monday 10am Colombia → allowed."""
    from cobranza.call_scheduler import is_contact_allowed_now
    # 2026-03-30 is Monday (not a holiday)
    fake_now = _make_dt(2026, 3, 30, 10, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is True


def test_sunday_not_allowed():
    """Sunday (any time) → not allowed."""
    from cobranza.call_scheduler import is_contact_allowed_now
    # 2026-03-22 is Sunday
    fake_now = _make_dt(2026, 3, 22, 10, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is False


def test_saturday_10am_allowed():
    """Saturday 10am Colombia → allowed (8am-3pm)."""
    from cobranza.call_scheduler import is_contact_allowed_now
    # 2026-03-21 is Saturday
    fake_now = _make_dt(2026, 3, 21, 10, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is True


def test_saturday_4pm_not_allowed():
    """Saturday 4pm Colombia → not allowed (after 3pm)."""
    from cobranza.call_scheduler import is_contact_allowed_now
    fake_now = _make_dt(2026, 3, 21, 16, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is False


def test_holiday_new_year_not_allowed():
    """2026-01-01 (New Year) → not allowed (holiday)."""
    from cobranza.call_scheduler import is_contact_allowed_now
    # 2026-01-01 is a Thursday, but it's a holiday
    fake_now = _make_dt(2026, 1, 1, 10, 0)
    with patch("cobranza.call_scheduler.datetime") as mock_dt:
        mock_dt.now.return_value = fake_now
        assert is_contact_allowed_now() is False


# ── has_been_contacted_today ───────────────────────────────────────────────────

def test_contacted_today_returns_true():
    """debtor with ultimo_contacto_fecha = today (Colombia tz) → True."""
    from cobranza.call_scheduler import has_been_contacted_today
    # Make today in Colombia tz
    today_co = datetime.now(COLOMBIA_TZ).replace(hour=9, minute=0, second=0, microsecond=0)
    debtor = {"ultimo_contacto_fecha": today_co}
    assert has_been_contacted_today(debtor) is True


def test_contacted_yesterday_returns_false():
    """debtor with ultimo_contacto_fecha = yesterday → False."""
    from cobranza.call_scheduler import has_been_contacted_today
    yesterday_co = (datetime.now(COLOMBIA_TZ) - timedelta(days=1)).replace(
        hour=9, minute=0, second=0, microsecond=0
    )
    debtor = {"ultimo_contacto_fecha": yesterday_co}
    assert has_been_contacted_today(debtor) is False


def test_contacted_none_returns_false():
    """debtor with ultimo_contacto_fecha = None → False."""
    from cobranza.call_scheduler import has_been_contacted_today
    debtor = {"ultimo_contacto_fecha": None}
    assert has_been_contacted_today(debtor) is False


def test_contacted_missing_field_returns_false():
    """debtor with no ultimo_contacto_fecha key → False."""
    from cobranza.call_scheduler import has_been_contacted_today
    debtor = {}
    assert has_been_contacted_today(debtor) is False


# ── get_next_allowed_slot ──────────────────────────────────────────────────────

def test_next_allowed_slot_is_future():
    """get_next_allowed_slot() returns a datetime in the future."""
    from cobranza.call_scheduler import get_next_allowed_slot
    now_utc = datetime.now(timezone.utc)
    slot = get_next_allowed_slot()
    assert slot > now_utc, f"Expected future slot, got {slot} (now={now_utc})"


def test_next_allowed_slot_returns_datetime():
    """get_next_allowed_slot() returns a datetime object."""
    from cobranza.call_scheduler import get_next_allowed_slot
    slot = get_next_allowed_slot()
    assert isinstance(slot, datetime)
