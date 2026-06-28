"""Binary sensor platform for Deye Cloud EMS."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .thai_tou import is_holiday, is_peak


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        [
            DeyeCloudEMSIsPeakSensor(entry.entry_id),
            DeyeCloudEMSIsThaiHolidaySensor(entry.entry_id),
        ]
    )


class DeyeCloudEMSIsPeakSensor(BinarySensorEntity):
    """True during MEA/PEA TOU peak hours."""

    _attr_name = "Is Peak Now"
    _attr_device_class = BinarySensorDeviceClass.POWER
    _attr_icon = "mdi:flash-alert"

    def __init__(self, entry_id: str) -> None:
        self._attr_unique_id = f"{entry_id}_is_peak_now"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    @property
    def is_on(self) -> bool:
        return is_peak()


class DeyeCloudEMSIsThaiHolidaySensor(BinarySensorEntity):
    """True on Thai public holidays (off-peak all day)."""

    _attr_name = "Is Thai Holiday"
    _attr_icon = "mdi:calendar-star"

    def __init__(self, entry_id: str) -> None:
        self._attr_unique_id = f"{entry_id}_is_thai_holiday"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry_id)}}

    @property
    def is_on(self) -> bool:
        return is_holiday()
