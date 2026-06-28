"""Convert TOU schedules to Deye Cloud OpenAPI format."""

from __future__ import annotations

from typing import Any

DEFAULT_TOU_POWER = 5000


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


def normalize_tou_items_for_api(
    items: list[dict[str, Any]],
    default_power: int = DEFAULT_TOU_POWER,
) -> list[dict[str, Any]]:
    """Convert internal/profile TOU slots to Deye API timeUseSettingItems."""
    if not items:
        raise ValueError("TOU update requires at least one time slot")

    normalized = [normalize_tou_item(item, default_power) for item in items]
    normalized.sort(key=lambda slot: slot["time"])
    return normalized


def apply_soc_to_tou_items(items: list[dict[str, Any]], soc: int) -> list[dict[str, Any]]:
    """Return a copy of TOU items with SOC updated on every slot."""
    updated: list[dict[str, Any]] = []
    for item in items:
        slot = dict(item)
        slot["soc"] = soc
        updated.append(slot)
    return updated
