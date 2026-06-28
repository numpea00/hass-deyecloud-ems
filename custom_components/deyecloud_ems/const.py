"""Constants for the Deye Cloud EMS integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "deyecloud_ems"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_APP_ID = "app_id"
CONF_APP_SECRET = "app_secret"
CONF_BASE_URL = "base_url"
CONF_COMPANY_ID = "company_id"
CONF_SCAN_INTERVAL = "scan_interval"

DEFAULT_BASE_URL_EU = "https://eu1-developer.deyecloud.com/v1.0"
DEFAULT_BASE_URL_US = "https://us1-developer.deyecloud.com/v1.0"
DEFAULT_SCAN_INTERVAL = 60
MIN_SCAN_INTERVAL = 30
MAX_SCAN_INTERVAL = 300

COORDINATOR = "coordinator"
CLIENT = "client"
PROFILE_MANAGER = "profile_manager"

# Thai TOU rates (2026, Type 3-4 at 69 kV+, before Ft and VAT)
THAI_TOU_PEAK_RATE: Final = 4.1025
THAI_TOU_OFFPEAK_RATE: Final = 2.5849
THAI_TOU_FT_RATE: Final = 0.1623
THAI_TOU_VAT: Final = 0.07
THAI_TOU_ARBITRAGE: Final = THAI_TOU_PEAK_RATE - THAI_TOU_OFFPEAK_RATE

WORK_MODES: Final = [
    "SELLING_FIRST",
    "ZERO_EXPORT_TO_LOAD",
    "ZERO_EXPORT_TO_CT",
]

ENERGY_PATTERNS: Final = [
    "BATTERY_FIRST",
    "LOAD_FIRST",
]

BATTERY_CHARGE_MODES: Final = [
    "GRID_CHARGE",
    "GEN_CHARGE",
]

TOU_CHARGE_MODES: Final = [
    "GRID_CHARGE",
    "SOLAR_CHARGE",
    "DISCHARGE",
    "HOLD",
]

# Built-in TOU profile presets
DEFAULT_TOU_PROFILES: Final = {
    "thai_sunny": {
        "description": "Sunny day — low reserve during solar, discharge during peak",
        "slots": [
            {"startTime": "00:00", "endTime": "09:00", "soc": 20, "chargeMode": "GRID_CHARGE"},
            {"startTime": "09:00", "endTime": "17:00", "soc": 5, "chargeMode": "SOLAR_CHARGE"},
            {"startTime": "17:00", "endTime": "22:00", "soc": 5, "chargeMode": "DISCHARGE"},
            {"startTime": "22:00", "endTime": "24:00", "soc": 20, "chargeMode": "GRID_CHARGE"},
        ],
    },
    "thai_rainy": {
        "description": "Rainy day — grid charge at night, hold reserve during day",
        "slots": [
            {"startTime": "00:00", "endTime": "09:00", "soc": 70, "chargeMode": "GRID_CHARGE"},
            {"startTime": "09:00", "endTime": "17:00", "soc": 50, "chargeMode": "HOLD"},
            {"startTime": "17:00", "endTime": "22:00", "soc": 30, "chargeMode": "DISCHARGE"},
            {"startTime": "22:00", "endTime": "24:00", "soc": 70, "chargeMode": "GRID_CHARGE"},
        ],
    },
    "thai_holiday": {
        "description": "Public holiday — off-peak all day, moderate reserve",
        "slots": [
            {"startTime": "00:00", "endTime": "24:00", "soc": 30, "chargeMode": "HOLD"},
        ],
    },
    "ev_night": {
        "description": "EV night charging — high off-peak reserve for EV + battery",
        "slots": [
            {"startTime": "00:00", "endTime": "09:00", "soc": 90, "chargeMode": "GRID_CHARGE"},
            {"startTime": "09:00", "endTime": "22:00", "soc": 40, "chargeMode": "HOLD"},
            {"startTime": "22:00", "endTime": "24:00", "soc": 90, "chargeMode": "GRID_CHARGE"},
        ],
    },
}

# Device data keys from /device/latest
SENSOR_DEFINITIONS: Final = {
    "battery_soc": {"key": "SOC", "name": "Battery SOC", "unit": "%", "device_class": "battery", "state_class": "measurement"},
    "battery_power": {"key": "BatteryPower", "name": "Battery Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "battery_voltage": {"key": "BatteryVoltage", "name": "Battery Voltage", "unit": "V", "device_class": "voltage", "state_class": "measurement"},
    "pv1_power": {"key": "PV1Power", "name": "PV1 Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "pv2_power": {"key": "PV2Power", "name": "PV2 Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "grid_power": {"key": "GridPower", "name": "Grid Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "load_power": {"key": "LoadPower", "name": "Load Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "ac_power": {"key": "ACPower", "name": "AC Power", "unit": "W", "device_class": "power", "state_class": "measurement"},
    "inverter_temperature": {"key": "InverterTemperature", "name": "Inverter Temperature", "unit": "°C", "device_class": "temperature", "state_class": "measurement"},
    "daily_energy": {"key": "DailyEnergy", "name": "Daily Energy", "unit": "kWh", "device_class": "energy", "state_class": "total_increasing"},
    "total_energy": {"key": "TotalEnergy", "name": "Total Energy", "unit": "kWh", "device_class": "energy", "state_class": "total_increasing"},
}

EVENT_PROFILE_APPLIED = "deyecloud_ems_profile_applied"

STORAGE_KEY = "deyecloud_ems_profiles"
STORAGE_VERSION = 1
