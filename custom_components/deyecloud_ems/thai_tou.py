"""Thai MEA/PEA TOU schedule utilities."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .const import THAI_TOU_OFFPEAK_RATE, THAI_TOU_PEAK_RATE

# MEA/PEA public holidays 2026 (Off-Peak all day)
# Excludes substitution holidays per ERC rules.
THAI_PUBLIC_HOLIDAYS_2026: frozenset[date] = frozenset(
    {
        date(2026, 1, 1),
        date(2026, 3, 3),
        date(2026, 4, 6),
        date(2026, 4, 13),
        date(2026, 4, 14),
        date(2026, 4, 15),
        date(2026, 5, 1),
        date(2026, 5, 4),
        date(2026, 5, 5),
        date(2026, 6, 3),
        date(2026, 7, 10),
        date(2026, 7, 28),
        date(2026, 8, 12),
        date(2026, 10, 13),
        date(2026, 10, 23),
        date(2026, 12, 5),
        date(2026, 12, 10),
        date(2026, 12, 31),
    }
)

DEFAULT_TIMEZONE = ZoneInfo("Asia/Bangkok")

PEAK_START = time(9, 0)
PEAK_END = time(22, 0)


def is_holiday(day: date | None = None) -> bool:
    """Return True if the given date is a Thai public holiday."""
    day = day or datetime.now(DEFAULT_TIMEZONE).date()
    return day in THAI_PUBLIC_HOLAYS_2026


def is_weekend(day: date | None = None) -> bool:
    """Return True if Saturday or Sunday."""
    day = day or datetime.now(DEFAULT_TIMEZONE).date()
    return day.weekday() >= 5


def is_peak(dt: datetime | None = None, tz: ZoneInfo | None = None) -> bool:
    """Return True during MEA/PEA TOU peak hours."""
    tz = tz or DEFAULT_TIMEZONE
    dt = dt or datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    day = dt.date()
    if is_holiday(day) or is_weekend(day):
        return False

    current = dt.time()
    return PEAK_START <= current < PEAK_END


def current_rate_thb(dt: datetime | None = None, include_ft: bool = False, include_vat: bool = False) -> float:
    """Return current TOU energy rate in THB/kWh."""
    rate = THAI_TOU_PEAK_RATE if is_peak(dt) else THAI_TOU_OFFPEAK_RATE
    if include_ft:
        rate += 0.1623
    if include_vat:
        rate *= 1.07
    return round(rate, 4)


def current_period(dt: datetime | None = None) -> str:
    """Return 'Peak' or 'Off-Peak'."""
    return "Peak" if is_peak(dt) else "Off-Peak"


def minutes_to_next_transition(dt: datetime | None = None, tz: ZoneInfo | None = None) -> int:
    """Minutes until the next peak/off-peak transition."""
    tz = tz or DEFAULT_TIMEZONE
    dt = dt or datetime.now(tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    else:
        dt = dt.astimezone(tz)

    if is_peak(dt):
        next_transition = datetime.combine(dt.date(), PEAK_END, tzinfo=tz)
        if dt.time() >= PEAK_END:
            next_transition += timedelta(days=1)
    else:
        day = dt.date()
        if is_holiday(day) or is_weekend(day):
            # Next transition is Monday 09:00 if weekend/holiday
            next_day = day + timedelta(days=1)
            while is_holiday(next_day) or is_weekend(next_day):
                next_day += timedelta(days=1)
            next_transition = datetime.combine(next_day, PEAK_START, tzinfo=tz)
        elif dt.time() < PEAK_START:
            next_transition = datetime.combine(day, PEAK_START, tzinfo=tz)
        else:
            next_transition = datetime.combine(day + timedelta(days=1), PEAK_START, tzinfo=tz)
            while is_holiday(next_transition.date()) or is_weekend(next_transition.date()):
                next_transition += timedelta(days=1)

    delta = next_transition - dt
    return max(0, int(delta.total_seconds() // 60))


def predict_soc_at_hour(
    current_soc: float,
    current_hour: int,
    target_hour: int,
    pv_power_w: float,
    load_power_w: float,
    battery_capacity_kwh: float,
    efficiency: float = 0.92,
) -> float:
    """Estimate battery SOC at target hour today."""
    if battery_capacity_kwh <= 0:
        return current_soc

    hours = target_hour - current_hour
    if hours <= 0:
        return current_soc

    net_power_kw = (pv_power_w - load_power_w) / 1000.0
    soc_delta = (net_power_kw * hours * efficiency / battery_capacity_kwh) * 100
    predicted = current_soc + soc_delta
    return round(max(0.0, min(100.0, predicted)), 1)
