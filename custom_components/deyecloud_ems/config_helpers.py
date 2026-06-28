"""Helpers for reading and normalizing Deye Cloud config values."""

from __future__ import annotations

from datetime import datetime, time
from typing import Any

from .const import ENERGY_PATTERNS, WORK_MODES

# Common wrapper keys in /config/* API responses.
_CONFIG_WRAPPER_KEYS = (
    "systemConfig",
    "batteryConfig",
    "config",
    "data",
    "result",
)

WORK_MODE_ALIASES: dict[Any, str] = {
    0: "SELLING_FIRST",
    1: "ZERO_EXPORT_TO_LOAD",
    2: "ZERO_EXPORT_TO_CT",
    "0": "SELLING_FIRST",
    "1": "ZERO_EXPORT_TO_LOAD",
    "2": "ZERO_EXPORT_TO_CT",
    "SELLING_FIRST": "SELLING_FIRST",
    "ZERO_EXPORT_TO_LOAD": "ZERO_EXPORT_TO_LOAD",
    "ZERO_EXPORT_TO_CT": "ZERO_EXPORT_TO_CT",
    "selling_first": "SELLING_FIRST",
    "zero_export_to_load": "ZERO_EXPORT_TO_LOAD",
    "zero_export_to_ct": "ZERO_EXPORT_TO_CT",
    "Selling First": "SELLING_FIRST",
    "Zero Export To Load": "ZERO_EXPORT_TO_LOAD",
    "Zero Export To CT": "ZERO_EXPORT_TO_CT",
    "Zero Export to Load": "ZERO_EXPORT_TO_LOAD",
    "Zero Export to CT": "ZERO_EXPORT_TO_CT",
}

ENERGY_PATTERN_ALIASES: dict[Any, str] = {
    0: "LOAD_FIRST",
    1: "BATTERY_FIRST",
    "0": "LOAD_FIRST",
    "1": "BATTERY_FIRST",
    "LOAD_FIRST": "LOAD_FIRST",
    "BATTERY_FIRST": "BATTERY_FIRST",
    "load_first": "LOAD_FIRST",
    "battery_first": "BATTERY_FIRST",
    "Load First": "LOAD_FIRST",
    "Battery First": "BATTERY_FIRST",
}


def merge_device_config(
    system: dict[str, Any] | None,
    battery: dict[str, Any] | None,
    tou: dict[str, Any] | None,
) -> dict[str, Any]:
    """Merge system/battery config responses into one flat lookup dict."""
    merged: dict[str, Any] = {}
    if isinstance(system, dict):
        merged.update(system)
        merged["_system"] = system
    if isinstance(battery, dict):
        merged.update(battery)
        merged["_battery"] = battery
    if tou is not None:
        merged["tou"] = tou
    return merged


def _sections_to_search(config: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = [config]
    for key in ("_system", "_battery", "system", "battery", "tou"):
        section = config.get(key)
        if isinstance(section, dict):
            sections.append(section)
    for section in list(sections):
        for wrapper in _CONFIG_WRAPPER_KEYS:
            nested = section.get(wrapper)
            if isinstance(nested, dict):
                sections.append(nested)
    return sections


def find_config_value(config: dict[str, Any], *keys: str) -> Any:
    """Find a config value across flat and nested API response shapes."""
    if not config:
        return None

    for section in _sections_to_search(config):
        for key in keys:
            value = section.get(key)
            if value is not None and value != "":
                return value
    return None


def normalize_work_mode(value: Any) -> str | None:
    """Normalize work mode values from API to WORK_MODES enum strings."""
    if value is None or value == "":
        return None
    if value in WORK_MODES:
        return value
    normalized = WORK_MODE_ALIASES.get(value)
    if normalized in WORK_MODES:
        return normalized
    if isinstance(value, str):
        upper = value.strip().upper().replace(" ", "_")
        if upper in WORK_MODES:
            return upper
    return None


def normalize_energy_pattern(value: Any) -> str | None:
    """Normalize energy pattern values from API to ENERGY_PATTERNS enum strings."""
    if value is None or value == "":
        return None
    if value in ENERGY_PATTERNS:
        return value
    normalized = ENERGY_PATTERN_ALIASES.get(value)
    if normalized in ENERGY_PATTERNS:
        return normalized
    if isinstance(value, str):
        upper = value.strip().upper().replace(" ", "_")
        if upper in ENERGY_PATTERNS:
            return upper
    return None


def normalize_bool(value: Any) -> bool | None:
    """Normalize API boolean-ish values."""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"on", "true", "1", "yes", "enabled", "enable"}:
            return True
        if lowered in {"off", "false", "0", "no", "disabled", "disable"}:
            return False
        if lowered in {"grid_charge", "gridcharge"}:
            return True
    return None


def normalize_number(value: Any) -> float | None:
    """Parse numeric config values."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_hhmm(value: str) -> time | None:
    try:
        hour, minute = value.strip().split(":", 1)
        return time(int(hour), int(minute))
    except (TypeError, ValueError):
        return None


def get_current_tou_soc(tou_config: dict[str, Any] | None, now: datetime | None = None) -> float | None:
    """Return SOC for the active TOU slot at the given time."""
    if not tou_config:
        return None

    items = (
        tou_config.get("timeUseSettingItems")
        or tou_config.get("time_use_setting_items")
        or []
    )
    if not items:
        return None

    now = now or datetime.now()
    current = now.time().replace(second=0, microsecond=0)

    # Range-based slots: startTime / endTime
    if any("startTime" in item for item in items):
        for item in items:
            start = _parse_hhmm(str(item.get("startTime", "")))
            end = _parse_hhmm(str(item.get("endTime", "")))
            if start is None or end is None:
                continue
            if start <= end:
                in_slot = start <= current < end
            else:
                in_slot = current >= start or current < end
            if in_slot:
                soc = normalize_number(item.get("soc"))
                if soc is not None:
                    return soc
        return normalize_number(items[0].get("soc"))

    # Point-in-time slots: time (official dynamicControl format)
    timed_items: list[tuple[time, dict[str, Any]]] = []
    for item in items:
        slot_time = _parse_hhmm(str(item.get("time", "")))
        if slot_time is not None:
            timed_items.append((slot_time, item))
    if not timed_items:
        return normalize_number(items[0].get("soc"))

    timed_items.sort(key=lambda pair: pair[0])
    active = timed_items[0][1]
    for slot_time, item in timed_items:
        if slot_time <= current:
            active = item
        else:
            break
    return normalize_number(active.get("soc"))
