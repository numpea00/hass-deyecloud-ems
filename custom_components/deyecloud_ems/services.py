"""Service registration for Deye Cloud EMS."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .api import DeyeCloudApiError
from .const import DOMAIN, EVENT_PROFILE_APPLIED, MIN_BATTERY_RESERVE_SOC
from .coordinator import DeyeCloudEMSCoordinator
from .tou_helpers import apply_soc_to_tou_items
from .tou_profile import TouProfileManager

_LOGGER = logging.getLogger(__name__)

SERVICE_SET_TOU = "set_tou"
SERVICE_APPLY_TOU_PROFILE = "apply_tou_profile"
SERVICE_SET_RESERVE = "set_reserve"
SERVICE_SMART_RESERVE = "smart_reserve"
SERVICE_SMART_NIGHT_CHARGE = "smart_night_charge"
SERVICE_SET_BATTERY_PARAMETER = "set_battery_parameter"
SERVICE_SET_WORK_MODE = "set_work_mode"
SERVICE_SET_ENERGY_PATTERN = "set_energy_pattern"
SERVICE_SET_SOLAR_SELL = "set_solar_sell"

TOU_ITEM_SCHEMA = vol.Schema(
    {
        vol.Required("startTime"): cv.string,
        vol.Required("endTime"): cv.string,
        vol.Required("soc"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
        vol.Required("chargeMode"): cv.string,
    }
)


def _get_device_sn(hass: HomeAssistant, call: ServiceCall) -> str | None:
    device_id = call.data.get("device_id")
    if not device_id:
        return call.data.get("device_sn")

    registry = dr.async_get(hass)
    device = registry.async_get(device_id)
    if not device:
        return None

    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            return identifier[1]
    return None


def _get_runtime(hass: HomeAssistant, entry_id: str) -> dict[str, Any] | None:
    return hass.data.get(DOMAIN, {}).get(entry_id)


async def _refresh_after_control(coordinator: DeyeCloudEMSCoordinator) -> None:
    """Refresh live data and invalidate cached inverter config."""
    coordinator.async_invalidate_config_cache()
    await coordinator.async_request_refresh()


async def _resolve_context(
    hass: HomeAssistant, call: ServiceCall
) -> tuple[DeyeCloudEMSCoordinator, TouProfileManager, str] | None:
    device_sn = _get_device_sn(hass, call)
    if not device_sn:
        _LOGGER.error("Device not found for service call")
        return None

    for entry_id, runtime in hass.data.get(DOMAIN, {}).items():
        coordinator: DeyeCloudEMSCoordinator = runtime["coordinator"]
        if device_sn in coordinator.devices:
            profile_manager: TouProfileManager = runtime["profile_manager"]
            return coordinator, profile_manager, device_sn

    _LOGGER.error("No coordinator found for device %s", device_sn)
    return None


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration services once."""

    if hass.services.has_service(DOMAIN, SERVICE_SET_TOU):
        return

    async def handle_set_tou(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, _, device_sn = ctx
        tou_items = call.data.get("tou_items") or call.data.get("time_use_setting_items")
        if not tou_items:
            _LOGGER.error("set_tou requires tou_items")
            return
        try:
            await coordinator.client.set_tou_config(
                device_sn,
                tou_items,
                call.data.get("timeout_seconds", 30),
            )
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("set_tou failed: %s", err)

    async def handle_apply_tou_profile(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, profile_manager, device_sn = ctx
        profile_name = call.data["profile_name"]
        slots = profile_manager.get_profile_slots(profile_name)
        if not slots:
            _LOGGER.error("Unknown profile: %s", profile_name)
            return
        try:
            await coordinator.client.set_tou_config(device_sn, slots)
            profile_manager.set_active_profile(profile_name)
            await profile_manager.async_save()
            hass.bus.async_fire(
                EVENT_PROFILE_APPLIED,
                {"device_sn": device_sn, "profile_name": profile_name},
            )
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("apply_tou_profile failed: %s", err)

    async def handle_set_reserve(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, profile_manager, device_sn = ctx
        soc = int(call.data["soc"])
        tou = coordinator.data.get("devices", {}).get(device_sn, {}).get("config", {}).get("tou") or {}
        existing_items = (
            tou.get("timeUseSettingItems")
            or tou.get("time_use_setting_items")
            or []
        )
        if existing_items:
            items = apply_soc_to_tou_items(existing_items, soc)
        elif profile_manager.active_profile:
            items = profile_manager.apply_reserve_to_slots(
                profile_manager.get_profile_slots(profile_manager.active_profile), soc
            )
        else:
            items = [{"startTime": "00:00", "endTime": "24:00", "soc": soc, "chargeMode": "HOLD"}]
        try:
            await coordinator.client.set_tou_config(device_sn, items)
            await _refresh_after_control(coordinator)
        except (DeyeCloudApiError, ValueError) as err:
            _LOGGER.error("set_reserve failed: %s", err)

    async def handle_smart_reserve(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, profile_manager, device_sn = ctx
        forecast_kwh = float(call.data["forecast_kwh"])
        target_kwh = float(call.data.get("target_kwh", 0))
        battery_capacity = float(call.data.get("battery_capacity_kwh", 10))
        reserve = max(MIN_BATTERY_RESERVE_SOC, min(90, int((target_kwh / battery_capacity) * 100)))
        if forecast_kwh < target_kwh:
            reserve = min(90, reserve + 20)
        active = profile_manager.active_profile or "thai_rainy"
        slots = profile_manager.apply_reserve_to_slots(
            profile_manager.get_profile_slots(active), reserve
        )
        try:
            await coordinator.client.set_tou_config(device_sn, slots)
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("smart_reserve failed: %s", err)

    async def handle_smart_night_charge(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, profile_manager, device_sn = ctx
        forecast_tomorrow = float(call.data["forecast_kwh_tomorrow"])
        daily_consumption = float(call.data.get("daily_consumption_kwh", 15))
        battery_capacity = float(call.data.get("battery_capacity_kwh", 10))
        current_soc = float(call.data.get("current_soc", 50))

        solar_surplus = forecast_tomorrow - daily_consumption
        if solar_surplus > 0.7 * battery_capacity:
            _LOGGER.info(
                "Skipping grid charge for %s; tomorrow solar surplus %.1f kWh",
                device_sn,
                solar_surplus,
            )
            return

        needed_kwh = battery_capacity - (current_soc / 100 * battery_capacity)
        target_soc = min(90, current_soc + (needed_kwh / battery_capacity) * 100)
        profile_name = call.data.get("profile_name", "thai_rainy")
        slots = profile_manager.apply_reserve_to_slots(
            profile_manager.get_profile_slots(profile_name),
            int(target_soc),
        )
        try:
            await coordinator.client.set_tou_config(device_sn, slots)
            await coordinator.client.set_battery_mode(device_sn, True, "GRID_CHARGE")
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("smart_night_charge failed: %s", err)

    async def handle_set_battery_parameter(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, _, device_sn = ctx
        try:
            await coordinator.client.set_battery_parameter(
                device_sn,
                call.data["parameter"],
                call.data["value"],
            )
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("set_battery_parameter failed: %s", err)

    async def handle_set_work_mode(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, _, device_sn = ctx
        try:
            await coordinator.client.set_work_mode(device_sn, call.data["work_mode"])
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("set_work_mode failed: %s", err)

    async def handle_set_energy_pattern(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, _, device_sn = ctx
        try:
            await coordinator.client.set_energy_pattern(
                device_sn, call.data["energy_pattern"]
            )
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("set_energy_pattern failed: %s", err)

    async def handle_set_solar_sell(call: ServiceCall) -> None:
        ctx = await _resolve_context(hass, call)
        if not ctx:
            return
        coordinator, _, device_sn = ctx
        try:
            await coordinator.client.set_solar_sell(device_sn, call.data["enabled"])
            await _refresh_after_control(coordinator)
        except DeyeCloudApiError as err:
            _LOGGER.error("set_solar_sell failed: %s", err)

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_TOU,
        handle_set_tou,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("tou_items"): [TOU_ITEM_SCHEMA],
                vol.Optional("timeout_seconds", default=30): cv.positive_int,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_APPLY_TOU_PROFILE,
        handle_apply_tou_profile,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("profile_name"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_RESERVE,
        handle_set_reserve,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("soc"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SMART_RESERVE,
        handle_smart_reserve,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("forecast_kwh"): vol.Coerce(float),
                vol.Optional("target_kwh", default=0): vol.Coerce(float),
                vol.Optional("battery_capacity_kwh", default=10): vol.Coerce(float),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SMART_NIGHT_CHARGE,
        handle_smart_night_charge,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("forecast_kwh_tomorrow"): vol.Coerce(float),
                vol.Optional("daily_consumption_kwh", default=15): vol.Coerce(float),
                vol.Optional("battery_capacity_kwh", default=10): vol.Coerce(float),
                vol.Optional("current_soc", default=50): vol.Coerce(float),
                vol.Optional("profile_name", default="thai_rainy"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_BATTERY_PARAMETER,
        handle_set_battery_parameter,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("parameter"): cv.string,
                vol.Required("value"): vol.Coerce(float),
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_WORK_MODE,
        handle_set_work_mode,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("work_mode"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ENERGY_PATTERN,
        handle_set_energy_pattern,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("energy_pattern"): cv.string,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_SOLAR_SELL,
        handle_set_solar_sell,
        schema=vol.Schema(
            {
                vol.Exclusive("device_id", "device"): cv.string,
                vol.Exclusive("device_sn", "device"): cv.string,
                vol.Required("enabled"): cv.boolean,
            }
        ),
    )
