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
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, PROFILE_MANAGER
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity, thai_tou_device_info
from .sensor_helpers import (
    PV1_POWER_KEYS,
    PV2_POWER_KEYS,
    LOAD_POWER_KEYS,
    SOC_KEYS,
    detect_device_class,
    detect_state_class,
    find_data_value,
    format_sensor_name,
    map_unit,
    parse_numeric,
    should_skip_sensor_key,
)
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
        device_payload = coordinator.data.get("devices", {}).get(device_sn, {})
        fields = device_payload.get("fields", {})
        if not fields:
            data = device_payload.get("data", {})
            fields = {
                key: {"value": value, "unit": None, "name": None}
                for key, value in data.items()
            }

        for field_key, field_meta in fields.items():
            if should_skip_sensor_key(field_key):
                continue
            entities.append(
                DeyeCloudEMSFieldSensor(
                    coordinator,
                    device_sn,
                    field_key,
                    field_meta,
                )
            )

        entities.append(DeyeCloudEMSSocPredictedSensor(coordinator, device_sn))

    entities.extend(
        [
            DeyeCloudEMSThaiRateSensor(entry),
            DeyeCloudEMSThaiPeriodSensor(entry),
            DeyeCloudEMSActiveProfileSensor(entry, profile_manager),
        ]
    )

    async_add_entities(entities)


class DeyeCloudEMSFieldSensor(DeyeCloudEMSDeviceEntity, SensorEntity):
    """Dynamic sensor created from Deye Cloud device/latest dataList."""

    def __init__(
        self,
        coordinator: DeyeCloudEMSCoordinator,
        device_sn: str,
        field_key: str,
        field_meta: dict[str, Any],
    ) -> None:
        api_name = field_meta.get("name")
        super().__init__(
            coordinator,
            device_sn,
            field_key,
            format_sensor_name(field_key, api_name),
        )
        self._field_key = field_key
        self._attr_native_unit_of_measurement = map_unit(field_key, field_meta.get("unit"))
        self._attr_device_class = detect_device_class(field_key, api_name)
        self._attr_state_class = detect_state_class(field_key)

    @property
    def native_value(self) -> StateType:
        fields = self._device_payload().get("fields", {})
        field = fields.get(self._field_key, {})
        value = field.get("value", self._device_payload().get("data", {}).get(self._field_key))
        parsed = parse_numeric(value)
        if isinstance(parsed, float):
            return parsed
        return parsed


class DeyeCloudEMSSocPredictedSensor(DeyeCloudEMSDeviceEntity, SensorEntity):
    """Predicted battery SOC at 17:00."""

    _attr_icon = "mdi:battery-clock"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "battery_soc_predicted_17h", "Battery SOC Predicted 17:00")
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_native_unit_of_measurement = PERCENTAGE

    @property
    def native_value(self) -> StateType:
        data = self._device_payload().get("data", {})
        soc = find_data_value(data, *SOC_KEYS)
        if soc is None:
            return None
        pv1 = find_data_value(data, *PV1_POWER_KEYS) or 0
        pv2 = find_data_value(data, *PV2_POWER_KEYS) or 0
        load_power = find_data_value(data, *LOAD_POWER_KEYS) or 0
        try:
            pv_total = float(pv1) + float(pv2)
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
