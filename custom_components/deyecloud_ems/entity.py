"""Shared entity helpers."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import DeyeCloudEMSCoordinator
from .sensor_helpers import find_data_value


def thai_tou_device_info(entry: ConfigEntry) -> dict[str, Any]:
    """Device info for account-level Thai TOU helper entities."""
    return {
        "identifiers": {(DOMAIN, entry.entry_id)},
        "name": "Thai TOU",
        "manufacturer": "Deye",
        "model": "Cloud EMS",
    }


class DeyeCloudEMSDeviceEntity(CoordinatorEntity[DeyeCloudEMSCoordinator]):
    """Base entity for a Deye inverter device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: DeyeCloudEMSCoordinator,
        device_sn: str,
        key: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self._device_sn = device_sn
        self._key = key
        self._attr_unique_id = f"{device_sn}_{key}"
        self._attr_name = name

    def _device_payload(self) -> dict[str, Any]:
        return self.coordinator.data.get("devices", {}).get(self._device_sn, {})

    def _get_device_name(self) -> str:
        info = self._device_payload().get("info", {})
        return info.get("deviceName") or f"Deye Inverter {self._device_sn}"

    @property
    def device_info(self) -> dict[str, Any]:
        info = self._device_payload().get("info", {})
        return {
            "identifiers": {(DOMAIN, self._device_sn)},
            "name": self._get_device_name(),
            "manufacturer": "Deye",
            "model": info.get("deviceModel") or info.get("model") or "Inverter",
            "serial_number": self._device_sn,
            "sw_version": info.get("firmwareVersion"),
        }

    @property
    def available(self) -> bool:
        return (
            self.coordinator.last_update_success
            and self._device_sn in self.coordinator.data.get("devices", {})
        )

    def _get_data_value(self, *keys: str) -> Any:
        data = self._device_payload().get("data", {})
        value = find_data_value(data, *keys)
        if value is not None:
            return value

        config = self._device_payload().get("config", {})
        for key in keys:
            if key in config and config[key] is not None:
                return config[key]
            system = config.get("system") or {}
            battery = config.get("battery") or {}
            if key in system and system[key] is not None:
                return system[key]
            if key in battery and battery[key] is not None:
                return battery[key]
        return None
