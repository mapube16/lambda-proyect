"""
call_scheduler.py — Ley 2300 de 2023 compliance engine + daily contact guard.

Ley 2300 rules:
- Mon-Fri: contact allowed 7am-7pm Colombia time
- Saturday: contact allowed 8am-3pm Colombia time
- Sunday: never
- Holidays: never
- Max 1 contact per debtor per day
"""
import pytz
from datetime import datetime, timedelta

COLOMBIA_TZ = pytz.timezone("America/Bogota")

# Colombian public holidays for 2026 (month, day)
COLOMBIA_HOLIDAYS_2026 = {
    (1, 1),   # New Year's Day
    (1, 12),  # Reyes Magos (observed)
    (3, 23),  # San José (observed)
    (4, 2),   # Jueves Santo
    (4, 3),   # Viernes Santo
    (5, 1),   # Labour Day
    (5, 25),  # Ascensión del Señor (observed)
    (6, 15),  # Corpus Christi (observed)
    (6, 22),  # Sagrado Corazón (observed)
    (6, 29),  # San Pedro y San Pablo (observed)
    (7, 20),  # Independence Day
    (8, 7),   # Battle of Boyacá
    (8, 17),  # Asunción de la Virgen (observed)
    (10, 12), # Columbus Day (observed)
    (11, 2),  # All Saints' Day (observed)
    (11, 16), # Independence of Cartagena (observed)
    (12, 8),  # Immaculate Conception
    (12, 25), # Christmas
}
# Expand COLOMBIA_HOLIDAYS_2027 when needed


def is_contact_allowed_now() -> bool:
    """
    Ley 2300 de 2023: Mon-Fri 7am-7pm, Sat 8am-3pm, Sun/holiday never.
    Returns True if it is currently permitted to contact a debtor.
    """
    now_co = datetime.now(COLOMBIA_TZ)
    if (now_co.month, now_co.day) in COLOMBIA_HOLIDAYS_2026:
        return False
    weekday = now_co.weekday()  # 0=Mon, 6=Sun
    hour = now_co.hour
    if weekday == 6:
        return False
    if weekday == 5:
        return 8 <= hour < 15
    return 7 <= hour < 19


def has_been_contacted_today(debtor: dict) -> bool:
    """
    Returns True if debtor was already contacted today (Colombia tz).
    Ley 2300 maximum 1 contact per day.
    """
    last = debtor.get("ultimo_contacto_fecha")
    if not last:
        return False
    now_co = datetime.now(COLOMBIA_TZ)
    # Ensure last is timezone-aware; treat naive datetimes as UTC
    if hasattr(last, "tzinfo") and last.tzinfo is None:
        last = pytz.utc.localize(last)
    last_co = last.astimezone(COLOMBIA_TZ)
    return last_co.date() == now_co.date()


def get_next_allowed_slot() -> datetime:
    """
    Returns the next datetime (UTC, timezone-aware) at which contact is allowed.
    Scans forward minute-by-minute up to 10 days.
    """
    now_co = datetime.now(COLOMBIA_TZ)
    candidate = now_co.replace(second=0, microsecond=0)
    for _ in range(10 * 24 * 60):  # up to 10 days in minutes
        candidate += timedelta(minutes=1)
        if (candidate.month, candidate.day) in COLOMBIA_HOLIDAYS_2026:
            # Skip to end of day to avoid iterating all minutes of a holiday
            candidate = candidate.replace(hour=23, minute=59)
            continue
        wd = candidate.weekday()
        h = candidate.hour
        if wd == 6:
            candidate = candidate.replace(hour=23, minute=59)
            continue
        if wd == 5 and 8 <= h < 15:
            return candidate.astimezone(pytz.utc)
        if wd < 5 and 7 <= h < 19:
            return candidate.astimezone(pytz.utc)
    # Fallback: return candidate as UTC (should never reach here in practice)
    return candidate.astimezone(pytz.utc)
