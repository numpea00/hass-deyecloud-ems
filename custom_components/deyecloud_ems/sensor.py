"""Sensor platform for Deye Cloud EMS."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, PROFILE_MANAGER, SENSOR_DEFINITIONS
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity, thai_tou_device_info
from .thai_tou import current_period, current_rate_thb, predict_soc_at_hour

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCloudEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    profile_manager = hass.data[DOMAIN][entry.entry_id][PROFILE_MANAGER]

    entities: list[SensorEntity] = []

    for device_sn in coordinator.devices:
        for sensor_key, definition in SENSOR_DEFINITIONS.items():
            entities.append(
                DeyeCloudEMSSensor(
                    coordinator,
                    device_sn,
                    sensor_key,
                    definition["name"],
                    definition.get("unit"),
                    definition.get("device_class"),
                    definition.get("state_class"),
                    definition["key"],
                )
            )
        entities.append(DeyeCloudEMSTotalPvPowerSensor(coordinator, device_sn))
        entities.append(DeyeCloudEMSSocPredictedSensor(coordinator, device_sn))

    entities.extend(
        [
            DeyeCloudEMSThaiRateSensor(entry),
            DeyeCloudEMSThaiPeriodSensor(entry),
            DeyeCloudEMSActiveProfileSensor(entry, profile_manager),
        ]
    )

    async_add_entities(entities)


class DeyeCloudEMSSensor(DeyeCloudEMSDeviceEntity, SensorEntity):
    """Generic Deye monitoring sensor."""

    def __init__(
        self,
        coordinator: DeyeCloudEMSCoordinator,
        device_sn: str,
        key: str,
        name: str,
        unit: str | None,
        device_class: str | None,
        state_class: str | None,
        data_key: str,
    ) -> None:
        super().__init__(coordinator, device_sn, key, name)
        self._data_key = data_key
        self._attr_native_unit_of_measurement = unit
        if device_class:
            self._attr_device_class = getattr(SensorDeviceClass, device_class.upper(), None) or device_class
        if state_class:
            self._attr_state_class = getattr(SensorStateClass, state_class.upper(), None) or state_class

    @property
    def native_value(self) -> StateType:
        value = self._get_data_value(self._data_key)
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value


class DeyeCloudEMSTotalPvPowerSensor(DeyeCloudEMSDeviceEntity, SensorEntity):
    """Total PV power (PV1 + PV2)."""

    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "W"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "total_pv_power", "Total PV Power")

    @property
    def native_value(self) -> StateType:
        pv1 = self._get_data_value("PV1Power")
        pv2 = self._get_data_value("PV2Power")
        total = 0.0
        found = False
        for value in (pv1, pv2):
            if value is not None:
                try:
                    total += float(value)
                    found = True
                except (TypeError, ValueError):
                    pass
        return total if found else None


class DeyeCloudEMSSocPredictedSensor(DeyeCloudEMSDeviceEntity, SensorEntity):
    """Predicted battery SOC at 17:00."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "battery_soc_predicted_17h", "Battery SOC Predicted 17:00")

    @property
    def native_value(self) -> StateType:
        soc = self._get_data_value("SOC")
        if soc is None:
            return None
        pv_power = self._get_data_value("PV1Power") or 0
        pv2 = self._get_data_value("PV2Power") or 0
        load_power = self._get_data_value("LoadPower") or 0
        try:
            pv_total = float(pv_power) + float(pv2)
            load = float(load_power)
            current_soc = float(soc)
        except (TypeError, ValueError):
            return None
        now = datetime.now()
        return predict_soc_at_hour(
            current_soc=current_soc,
            current_hour=now.hour,
            target_hour=17,
            pv_power_w=pv_total,
            load_power_w=load,
            battery_capacity_kwh=10.0,
        )


class DeyeCloudEMSThaiRateSensor(SensorEntity):
    """Current Thai TOU electricity rate."""

    _attr_name = "Thai TOU Rate Now"
    _attr_icon = "mdi:currency-thb"
    _attr_native_unit_of_measurement = "THB/kWh"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_thai_tou_rate"
        self._attr_device_info = thai_tou_device_info(entry)

    @property
    def native_value(self) -> StateType:
        return current_rate_thb()


class DeyeCloudEMSThaiPeriodSensor(SensorEntity):
    """Current Thai TOU period label."""

    _attr_name = "Thai TOU Period"
    _attr_icon = "mdi:clock-outline"

    def __init__(self, entry: ConfigEntry) -> None:
        self._attr_unique_id = f"{entry.entry_id}_thai_tou_period"
        self._attr_device_info = thai_tou_device_info(entry)

    @property
    def native_value(self) -> StateType:
        return current_period()


class DeyeCloudEMSActiveProfileSensor(SensorEntity):
    """Last applied TOU profile name."""

    _attr_name = "Active TOU Profile"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, entry: ConfigEntry, profile_manager: Any) -> None:
        self._profile_manager = profile_manager
        self._attr_unique_id = f"{entry.entry_id}_active_tou_profile"
        self._attr_device_info = thai_tou_device_info(entry)

    @property
    def native_value(self) -> StateType:
        return self._profile_manager.active_profile or "none"
