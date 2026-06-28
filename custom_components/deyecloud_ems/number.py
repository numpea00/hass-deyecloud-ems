"""Number platform for Deye Cloud EMS."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import DeyeCloudApiError
from .config_helpers import get_current_tou_soc, normalize_number
from .const import DOMAIN, MIN_BATTERY_RESERVE_SOC, PROFILE_MANAGER
from .tou_helpers import apply_soc_to_tou_items
from .coordinator import DeyeCloudEMSCoordinator
from .entity import DeyeCloudEMSDeviceEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: DeyeCloudEMSCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    profile_manager = hass.data[DOMAIN][entry.entry_id][PROFILE_MANAGER]
    entities: list[NumberEntity] = []
    for device_sn in coordinator.devices:
        entities.extend(
            [
                DeyeCloudEMSMaxChargeCurrentNumber(coordinator, device_sn),
                DeyeCloudEMSMaxDischargeCurrentNumber(coordinator, device_sn),
                DeyeCloudEMSMaxSellPowerNumber(coordinator, device_sn),
                DeyeCloudEMSBatteryReserveNumber(coordinator, device_sn, profile_manager),
            ]
        )
    async_add_entities(entities)


class DeyeCloudEMSMaxChargeCurrentNumber(DeyeCloudEMSDeviceEntity, NumberEntity):
    """Max battery charge current."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "A"
    _attr_icon = "mdi:current-dc"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "max_charge_current", "Max Charge Current")

    @property
    def native_value(self) -> float | None:
        value = self._get_config_value(
            "maxChargeCurrent",
            "MaxChargeCurrent",
            "chargeCurrentLimit",
        )
        if value is None:
            value = self._get_data_value(
                "maxChargeCurrent",
                "MaxChargeCurrent",
                "chargeCurrentLimit",
            )
        return normalize_number(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_battery_parameter(
                self._device_sn, "maxChargeCurrent", int(value)
            )
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set max charge current: %s", err)


class DeyeCloudEMSMaxDischargeCurrentNumber(DeyeCloudEMSDeviceEntity, NumberEntity):
    """Max battery discharge current."""

    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "A"
    _attr_icon = "mdi:current-dc"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "max_discharge_current", "Max Discharge Current")

    @property
    def native_value(self) -> float | None:
        value = self._get_config_value(
            "maxDischargeCurrent",
            "MaxDischargeCurrent",
            "dischargeCurrentLimit",
        )
        if value is None:
            value = self._get_data_value(
                "maxDischargeCurrent",
                "MaxDischargeCurrent",
                "dischargeCurrentLimit",
            )
        return normalize_number(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_battery_parameter(
                self._device_sn, "maxDischargeCurrent", int(value)
            )
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set max discharge current: %s", err)


class DeyeCloudEMSMaxSellPowerNumber(DeyeCloudEMSDeviceEntity, NumberEntity):
    """Max sell power."""

    _attr_native_min_value = 0
    _attr_native_max_value = 10000
    _attr_native_step = 100
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "W"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: DeyeCloudEMSCoordinator, device_sn: str) -> None:
        super().__init__(coordinator, device_sn, "max_sell_power", "Max Sell Power")

    @property
    def native_value(self) -> float | None:
        value = self._get_config_value("maxSellPower", "MaxSellPower")
        if value is None:
            value = self._get_data_value("maxSellPower", "MaxSellPower")
        return normalize_number(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.client.set_max_sell_power(self._device_sn, int(value))
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except DeyeCloudApiError as err:
            _LOGGER.error("Failed to set max sell power: %s", err)


class DeyeCloudEMSBatteryReserveNumber(DeyeCloudEMSDeviceEntity, NumberEntity):
    """Battery reserve SOC applied via TOU update."""

    _attr_native_min_value = MIN_BATTERY_RESERVE_SOC
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX
    _attr_native_unit_of_measurement = "%"
    _attr_icon = "mdi:battery-low"

    def __init__(
        self,
        coordinator: DeyeCloudEMSCoordinator,
        device_sn: str,
        profile_manager,
    ) -> None:
        super().__init__(coordinator, device_sn, "battery_reserve_soc", "Battery Reserve SOC")
        self._profile_manager = profile_manager

    @property
    def native_value(self) -> float | None:
        tou = self._device_payload().get("config", {}).get("tou") or {}
        soc = get_current_tou_soc(tou)
        return soc if soc is not None else 20.0

    async def async_set_native_value(self, value: float) -> None:
        tou = self._device_payload().get("config", {}).get("tou") or {}
        existing_items = (
            tou.get("timeUseSettingItems")
            or tou.get("time_use_setting_items")
            or []
        )
        if existing_items:
            items = apply_soc_to_tou_items(
                existing_items,
                max(MIN_BATTERY_RESERVE_SOC, int(value)),
            )
        else:
            active = self._profile_manager.active_profile or "thai_sunny"
            items = self._profile_manager.apply_reserve_to_slots(
                self._profile_manager.get_profile_slots(active),
                int(value),
            )
        try:
            await self.coordinator.client.set_tou_config(self._device_sn, items)
            self.coordinator.async_invalidate_config_cache()
            await self.coordinator.async_request_refresh()
        except (DeyeCloudApiError, ValueError) as err:
            _LOGGER.error("Failed to set battery reserve SOC: %s", err)
