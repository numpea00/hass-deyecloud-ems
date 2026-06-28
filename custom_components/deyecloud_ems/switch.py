"""Switch platform for Deye Cloud EMS."""

from __future__ import annotations

import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DeyeCloudApiError
from .config_helpers import normalize_bool
from .const import DOMAIN
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity
from .sensor_helpers import SOC_KEYS, find_data_value
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
        value = self._get_config_value(
            "solarSellEnable",
            "SolarSellEnable",
            "solarSell",
            "SolarSell",
        )
        if value is None:
            value = self._get_data_value("SolarSell", "solarSell", "SolarSellEnable")
        normalized = normalize_bool(value)
        return normalized if normalized is not None else False

    @property
    def extra_state_attributes(self) -> dict:
        data = self._device_payload().get("data", {})
        soc = find_data_value(data, *SOC_KEYS)
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
            self.coordinator.async_invalidate_config_cache()
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
        value = self._get_config_value(
            "enableGridCharge",
            "gridChargeEnable",
            "gridCharge",
            "GridCharge",
            "BatteryChargeMode",
            "batteryChargeMode",
        )
        if value is None:
            value = self._get_data_value(
                "BatteryChargeMode",
                "GridCharge",
                "gridCharge",
                "enableGridCharge",
            )
        normalized = normalize_bool(value)
        return normalized if normalized is not None else False

    async def async_turn_on(self, **kwargs) -> None:
        await self._set_charge_mode(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set_charge_mode(False)

    async def _set_charge_mode(self, enabled: bool) -> None:
        try:
            await self.coordinator.client.set_battery_mode(
                self._device_sn, enabled, "GRID_CHARGE"
            )
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set battery charge mode for %s: %s", self._device_sn, err)
