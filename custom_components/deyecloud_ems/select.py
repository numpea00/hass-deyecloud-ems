"""Select platform for Deye Cloud EMS."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DeyeCloudApiError
from .const import DOMAIN, ENERGY_PATTERNS, WORK_MODES
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCloudEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SelectEntity] = []
    for device_sn in coordinator.devices:
        entities.extend(
            [
                DeyeCloudEMSWorkModeSelect(coordinator, device_sn),
                DeyeCloudEMSEnergyPatternSelect(coordinator, device_sn),
            ]
        )
    async_add_entities(entities)


class DeyeCloudEMSWorkModeSelect(DeyeCloudEMSDeviceEntity, SelectEntity):
    """System work mode select."""

    _attr_icon = "mdi:cog"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "work_mode", "Work Mode")
        self._attr_options = WORK_MODES

    @property
    def current_option(self) -> str | None:
        value = self._get_data_value("workMode", "WorkMode", "SystemWorkMode")
        if value in WORK_MODES:
            return value
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in WORK_MODES:
            return
        try:
            await self.coordinator.client.set_work_mode(self._device_sn, option)
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set work mode: %s", err)


class DeyeCloudEMSEnergyPatternSelect(DeyeCloudEMSDeviceEntity, SelectEntity):
    """Energy pattern select."""

    _attr_icon = "mdi:battery-arrow-up"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "energy_pattern", "Energy Pattern")
        self._attr_options = ENERGY_PATTERNS

    @property
    def current_option(self) -> str | None:
        value = self._get_data_value("energyPattern", "EnergyPattern", "SystemEnergyPattern")
        if value in ENERGY_PATTERNS:
            return value
        return None

    async def async_select_option(self, option: str) -> None:
        if option not in ENERGY_PATTERNS:
            return
        try:
            await self.coordinator.client.set_energy_pattern(self._device_sn, option)
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set energy pattern: %s", err)
