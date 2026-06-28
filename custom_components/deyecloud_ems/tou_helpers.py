"""Convert TOU schedules to Deye Cloud OpenAPI format."""

from __future__ import annotations

from typing import Any

# ~0.25C for 51.2V / 314Ah class batteries (~16 kWh); gentle on LiFePO4 cycle life.
DEFAULT_TOU_POWER = 4000
DEYE_TOU_SLOT_COUNT = 6
# Spread used when fewer than 6 profile slots must be expanded for the API.
DEFAULT_TOU_TIMES = ("00:00", "04:00", "08:00", "12:00", "16:00", "20:00")


def charge_mode_to_flags(charge_mode: str) -> tuple[bool, bool]:
    """Map profile chargeMode to enableGridCharge / enableGeneration flags."""
    mode = (charge_mode or "HOLD").upper()
    if mode == "GRID_CHARGE":
        return True, False
    if mode in {"SOLAR_CHARGE", "GEN_CHARGE"}:
        return False, True
    return False, False


def is_api_tou_item(item: dict[str, Any]) -> bool:
    """Return True when the item already uses Deye API point-in-time format."""
    return "time" in item


def normalize_tou_item(item: dict[str, Any], default_power: int = DEFAULT_TOU_POWER) -> dict[str, Any]:
    """Normalize one TOU slot to Deye /order/sys/tou/update format."""
    if is_api_tou_item(item):
        return {
            "time": str(item["time"]),
            "soc": int(item.get("soc", 20)),
            "power": int(item.get("power", default_power)),
            "enableGridCharge": bool(item.get("enableGridCharge", False)),
            "enableGeneration": bool(item.get("enableGeneration", False)),
        }

    if "startTime" in item:
        enable_grid, enable_gen = charge_mode_to_flags(str(item.get("chargeMode", "HOLD")))
        return {
            "time": str(item["startTime"]),
            "soc": int(item.get("soc", 20)),
            "power": int(item.get("power", default_power)),
            "enableGridCharge": enable_grid,
            "enableGeneration": enable_gen,
        }

    raise ValueError(f"Unsupported TOU item format: {item}")


def _time_to_minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def _slot_for_time(slots: list[dict[str, Any]], target_time: str) -> dict[str, Any]:
    """Return the slot active at target_time (last slot whose time <= target)."""
    target_minutes = _time_to_minutes(target_time)
    active = slots[0]
    for slot in slots:
        if _time_to_minutes(slot["time"]) <= target_minutes:
            active = slot
        else:
            break
    return active


def ensure_six_tou_slots(
    items: list[dict[str, Any]],
    default_power: int = DEFAULT_TOU_POWER,
) -> list[dict[str, Any]]:
    """Expand or trim TOU slots to the 6 intervals required by Deye Cloud."""
    normalized = [normalize_tou_item(item, default_power) for item in items]
    normalized.sort(key=lambda slot: slot["time"])

    if len(normalized) == DEYE_TOU_SLOT_COUNT:
        return normalized
    if len(normalized) > DEYE_TOU_SLOT_COUNT:
        return normalized[:DEYE_TOU_SLOT_COUNT]

    if len(normalized) == 1:
        base = normalized[0]
        return [{**base, "time": time_value} for time_value in DEFAULT_TOU_TIMES]

    expanded: list[dict[str, Any]] = []
    for time_value in DEFAULT_TOU_TIMES:
        source = _slot_for_time(normalized, time_value)
        expanded.append({**source, "time": time_value})
    return expanded


def normalize_tou_items_for_api(
    items: list[dict[str, Any]],
    default_power: int = DEFAULT_TOU_POWER,
) -> list[dict[str, Any]]:
    """Convert internal/profile TOU slots to Deye API timeUseSettingItems."""
    if not items:
        raise ValueError("TOU update requires at least one time slot")

    return ensure_six_tou_slots(items, default_power)


def apply_soc_to_tou_items(items: list[dict[str, Any]], soc: int) -> list[dict[str, Any]]:
    """Return a copy of TOU items with SOC updated on every slot."""
    updated: list[dict[str, Any]] = []
    for item in items:
        slot = dict(item)
        slot["soc"] = soc
        updated.append(slot)
    return updated
