"""Switch platform for Deye Cloud EMS."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DeyeCloudApiError
from .const import DOMAIN
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity
from .thai_tou import is_peak

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCloudEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    entities: list[SwitchEntity] = []
    for device_sn in coordinator.devices:
        entities.extend(
            [
                DeyeCloudEMSSolarSellSwitch(coordinator, device_sn),
                DeyeCloudEMSBatteryChargeSwitch(coordinator, device_sn),
            ]
        )
    async_add_entities(entities)


class DeyeCloudEMSSolarSellSwitch(DeyeCloudEMSDeviceEntity, SwitchEntity):
    """Solar sell control with optional smart peak/SOC awareness."""

    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "solar_sell", "Solar Sell")

    @property
    def is_on(self) -> bool:
        value = self._get_data_value("SolarSell", "solarSell", "SolarSellEnable")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"on", "true", "1", "enabled"}
        if value is not None:
            try:
                return float(value) > 0
            except (TypeError, ValueError):
                return False
        return False

    @property
    def extra_state_attributes(self) -> dict:
        soc = self._get_data_value("SOC")
        return {
            "smart_sell_recommended": (
                soc is not None
                and float(soc) > 90
                and is_peak()
            ),
            "smart_sell_block_recommended": (
                soc is not None and float(soc) < 50
            ),
        }

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_solar_sell(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_solar_sell(False)

    async def _set_solar_sell(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_solar_sell(self._device_sn, enabled)
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set solar sell for %s: %s", self._device_sn, err)


class DeyeCloudEMSBatteryChargeSwitch(DeyeCloudEMSDeviceEntity, SwitchEntity):
    """Battery grid charge mode."""

    _attr_icon = "mdi:battery-charging"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "battery_charge_mode", "Battery Charge Mode")

    @property
    def is_on(self) -> bool:
        value = self._get_data_value("BatteryChargeMode", "GridCharge", "gridCharge")
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"on", "true", "1", "enabled", "grid_charge"}
        return False

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_charge_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_charge_mode(False)

    async def _set_charge_mode(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_battery_mode(
                self._device_sn, enabled, "GRID_CHARGE"
            )
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set battery charge mode for %s: %s", self._device_sn, err)
