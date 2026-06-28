"""Data update coordinator for Deye Cloud EMS."""

from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeyeCloudApiError, DeyeCloudClient
from .config_helpers import merge_device_config
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

CONFIG_REFRESH_SECONDS = 300


class DeyeCloudEMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fetching Deye Cloud device and station data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DeyeCloudClient,
        scan_interval: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.devices: list[str] = []
        self.device_info: dict[str, dict[str, Any]] = {}
        self.stations: list[dict[str, Any]] = []
        self._device_configs: dict[str, dict[str, Any]] = {}
        self._last_config_fetch = 0.0
        self._force_config_refresh = True

    def async_invalidate_config_cache(self) -> None:
        """Force config endpoints to refresh on the next update."""
        self._force_config_refresh = True

    async def _async_fetch_device_configs(self) -> dict[str, dict[str, Any]]:
        device_configs: dict[str, dict[str, Any]] = {}
        for device_sn in self.devices:
            system_config: dict[str, Any] | None = None
            battery_config: dict[str, Any] | None = None
            tou_config: dict[str, Any] | None = None
            try:
                system_config = await self.client.get_system_config(device_sn)
            except DeyeCloudApiError as err:
                _LOGGER.debug("System config failed for %s: %s", device_sn, err)
            try:
                battery_config = await self.client.get_battery_config(device_sn)
            except DeyeCloudApiError as err:
                _LOGGER.debug("Battery config failed for %s: %s", device_sn, err)
            try:
                tou_config = await self.client.get_tou_config(device_sn)
            except DeyeCloudApiError as err:
                _LOGGER.debug("TOU config failed for %s: %s", device_sn, err)

            merged = merge_device_config(system_config, battery_config, tou_config)
            device_configs[device_sn] = merged
            if merged:
                _LOGGER.debug(
                    "Device %s config keys: %s",
                    device_sn,
                    ", ".join(sorted(key for key in merged if not key.startswith("_"))),
                )
        return device_configs

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            if not self.stations:
                self.stations = await self.client.get_station_list()
                station_ids = [
                    st.get("id") or st.get("stationId")
                    for st in self.stations
                    if st.get("id") or st.get("stationId")
                ]
                inverter_devices = await self.client.get_station_devices(station_ids)
                self.devices = [d["deviceSn"] for d in inverter_devices]
                self.device_info = {d["deviceSn"]: d for d in inverter_devices}
                self._force_config_refresh = True

            device_data = await self.client.get_device_latest_data(self.devices)

            station_data: dict[str, Any] = {}
            for station in self.stations:
                station_id = station.get("id") or station.get("stationId")
                if station_id:
                    try:
                        station_data[str(station_id)] = await self.client.get_station_latest_data(
                            station_id
                        )
                    except DeyeCloudApiError as err:
                        _LOGGER.debug("Station latest failed for %s: %s", station_id, err)

            now = time.monotonic()
            if (
                self._force_config_refresh
                or not self._device_configs
                or now - self._last_config_fetch >= CONFIG_REFRESH_SECONDS
            ):
                self._device_configs = await self._async_fetch_device_configs()
                self._last_config_fetch = now
                self._force_config_refresh = False

            devices_payload: dict[str, Any] = {}
            for device_sn in self.devices:
                latest = device_data.get(device_sn, {})
                if isinstance(latest, dict) and "values" in latest:
                    values = latest.get("values", {})
                    fields = latest.get("fields", {})
                else:
                    values = latest if isinstance(latest, dict) else {}
                    fields = {
                        key: {"value": value, "unit": None, "name": None}
                        for key, value in values.items()
                    }
                devices_payload[device_sn] = {
                    "info": self.device_info.get(device_sn, {}),
                    "data": values,
                    "fields": fields,
                    "config": self._device_configs.get(device_sn, {}),
                }
                if fields:
                    _LOGGER.debug(
                        "Device %s latest keys: %s",
                        device_sn,
                        ", ".join(sorted(fields.keys())),
                    )

            return {
                "stations": self.stations,
                "station_data": station_data,
                "devices": devices_payload,
            }
        except DeyeCloudApiError as err:
            raise UpdateFailed(f"Deye Cloud update failed: {err}") from err
