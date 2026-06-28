"""Helpers for mapping Deye Cloud device/latest fields to HA sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)

# Keys that are identifiers or metadata, not measurements.
SKIP_SENSOR_KEYS: frozenset[str] = frozenset(
    {
        "SN",
        "SN1",
        "SN2",
        "deviceSn",
        "deviceId",
        "deviceType",
        "deviceState",
        "collectionTime",
        "requestId",
    }
)

# Aliases for computed / blueprint sensors (API keys vary by model/firmware).
SOC_KEYS = ("SOC", "BMSSOC", "soc", "BmsSoc", "batterySoc")
PV1_POWER_KEYS = ("PV1Power", "DP1", "Pv1Power", "PVPower", "pv1Power")
PV2_POWER_KEYS = ("PV2Power", "DP2", "Pv2Power", "pv2Power")
LOAD_POWER_KEYS = ("LoadPower", "UPSLoadPower", "LoadPowerTotal", "LoadPowerL1")
GRID_POWER_KEYS = ("GridPower", "PG_Pt1", "GridSidePower", "TotalGridPower")


def find_data_value(data: dict[str, Any], *keys: str) -> Any:
    """Return the first matching value from a flat data dict."""
    for key in keys:
        value = data.get(key)
        if value is not None and value != "":
            return value
    return None


def should_skip_sensor_key(key: str) -> bool:
    """Return True if this API key should not become a sensor."""
    if not key or key in SKIP_SENSOR_KEYS:
        return True
    if key.startswith("SN") and key[2:].isdigit():
        return True
    return False


def format_sensor_name(key: str, api_name: str | None = None) -> str:
    """Build a friendly sensor name from API metadata."""
    if api_name and str(api_name).strip():
        return str(api_name).strip()
    return key.replace("_", " ")


def parse_numeric(value: Any) -> float | str | None:
    """Parse API value to float when possible."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return str(value)


def map_unit(key: str, api_unit: str | None) -> str | None:
    """Map API unit string to a Home Assistant unit."""
    if api_unit:
        unit = str(api_unit).strip()
        mapping = {
            "W": UnitOfPower.WATT,
            "kW": UnitOfPower.KILO_WATT,
            "kWh": UnitOfEnergy.KILO_WATT_HOUR,
            "V": UnitOfElectricPotential.VOLT,
            "A": UnitOfElectricCurrent.AMPERE,
            "Hz": UnitOfFrequency.HERTZ,
            "°C": UnitOfTemperature.CELSIUS,
            "℃": UnitOfTemperature.CELSIUS,
            "%": PERCENTAGE,
        }
        if unit in mapping:
            return mapping[unit]
        if unit.lower() in {"w", "kw", "kwh", "v", "a", "hz"}:
            return mapping.get(unit, unit)
        return unit

    key_lower = key.lower()
    if "temp" in key_lower or key.startswith("INV_T"):
        return UnitOfTemperature.CELSIUS
    if "frequency" in key_lower or key.startswith("A_F"):
        return UnitOfFrequency.HERTZ
    if "power" in key_lower and "k" not in key_lower:
        return UnitOfPower.WATT
    if "energy" in key_lower or key.startswith("Et") or "Etdy" in key:
        return UnitOfEnergy.KILO_WATT_HOUR
    if "voltage" in key_lower or key.startswith("DV"):
        return UnitOfElectricPotential.VOLT
    if "current" in key_lower or _looks_like_current_key(key):
        return UnitOfElectricCurrent.AMPERE
    if "soc" in key_lower:
        return PERCENTAGE
    return None


def _looks_like_current_key(key: str) -> bool:
    """Return True when a short AC/DC key likely means current, not temperature etc."""
    if "current" in key.lower():
        return True
    upper = key.upper()
    for prefix in ("DC", "AC"):
        if not upper.startswith(prefix):
            continue
        suffix = upper[len(prefix) :]
        if suffix.isdigit():
            return True
        if suffix.endswith("I") and suffix[:-1].isdigit():
            return True
    return False


def device_class_from_unit(unit: str | None) -> SensorDeviceClass | None:
    """Map a resolved HA unit to the matching sensor device class."""
    if not unit:
        return None
    if unit in {UnitOfFrequency.HERTZ, "Hz"}:
        return SensorDeviceClass.FREQUENCY
    if unit in {UnitOfTemperature.CELSIUS, "°C", "℃"}:
        return SensorDeviceClass.TEMPERATURE
    if unit == UnitOfPower.WATT:
        return SensorDeviceClass.POWER
    if unit == UnitOfElectricPotential.VOLT:
        return SensorDeviceClass.VOLTAGE
    if unit == UnitOfElectricCurrent.AMPERE:
        return SensorDeviceClass.CURRENT
    if unit == UnitOfEnergy.KILO_WATT_HOUR:
        return SensorDeviceClass.ENERGY
    if unit == PERCENTAGE:
        return SensorDeviceClass.BATTERY
    return None


def detect_device_class(
    key: str,
    api_name: str | None = None,
    unit: str | None = None,
) -> SensorDeviceClass | None:
    """Infer sensor device class from API unit, key, and name."""
    from_unit = device_class_from_unit(unit)
    if from_unit is not None:
        return from_unit

    text = f"{key} {api_name or ''}".lower()
    if "soc" in text or ("battery" in text and "%" in text):
        return SensorDeviceClass.BATTERY
    if "energy" in text or key.startswith("Et"):
        return SensorDeviceClass.ENERGY
    if "power" in text and "frequency" not in text:
        return SensorDeviceClass.POWER
    if "voltage" in text or key.startswith("DV"):
        return SensorDeviceClass.VOLTAGE
    if "temp" in text or key.startswith("INV_T"):
        return SensorDeviceClass.TEMPERATURE
    if "frequency" in text or key.startswith("A_F"):
        return SensorDeviceClass.FREQUENCY
    if "current" in text or _looks_like_current_key(key):
        return SensorDeviceClass.CURRENT
    return None


def detect_state_class(key: str) -> SensorStateClass | None:
    """Infer sensor state class from API key."""
    if key.startswith("Et") and "dy" not in key:
        return SensorStateClass.TOTAL
    if "Etdy" in key or "Daily" in key or "daily" in key.lower():
        return SensorStateClass.TOTAL_INCREASING
    if any(token in key for token in ("Power", "Voltage", "Current", "Frequency", "SOC", "Temp")):
        return SensorStateClass.MEASUREMENT
    return None
