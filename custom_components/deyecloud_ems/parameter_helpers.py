"""Normalize Deye Cloud order API parameter names."""

from __future__ import annotations

# Official sample uses paramterType (missing 'e') and SCREAMING_SNAKE values.
BATTERY_PARAMETER_ALIASES: dict[str, str] = {
    "maxchargecurrent": "MAX_CHARGE_CURRENT",
    "maxdischargecurrent": "MAX_DISCHARGE_CURRENT",
    "chargecurrentlimit": "MAX_CHARGE_CURRENT",
    "dischargecurrentlimit": "MAX_DISCHARGE_CURRENT",
    "max_charge_current": "MAX_CHARGE_CURRENT",
    "max_discharge_current": "MAX_DISCHARGE_CURRENT",
}


def normalize_battery_paramter_type(parameter: str) -> str:
    """Map friendly names to Deye paramterType values."""
    key = parameter.replace("-", "_").replace(" ", "_")
    alias = BATTERY_PARAMETER_ALIASES.get(key.lower().replace("_", ""))
    if alias:
        return alias
    upper = key.upper()
    if upper in {"MAX_CHARGE_CURRENT", "MAX_DISCHARGE_CURRENT"}:
        return upper
    return upper
