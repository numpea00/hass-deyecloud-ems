"""Data update coordinator for Deye Cloud EMS."""

from __future__ import annotations

import asyncio
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

    async def _async_fetch_device_config(self, device_sn: str) -> dict[str, Any]:
        """Fetch and merge config for one device (API calls run in parallel)."""

        async def _load(fetch, label: str) -> dict[str, Any] | None:
            try:
                return await fetch(device_sn)
            except DeyeCloudApiError as err:
                _LOGGER.debug("%s config failed for %s: %s", label, device_sn, err)
                return None

        system_config, battery_config, tou_config = await asyncio.gather(
            _load(self.client.get_system_config, "System"),
            _load(self.client.get_battery_config, "Battery"),
            _load(self.client.get_tou_config, "TOU"),
        )
        merged = merge_device_config(system_config, battery_config, tou_config)
        if merged:
            _LOGGER.debug(
                "Device %s config keys: %s",
                device_sn,
                ", ".join(sorted(key for key in merged if not key.startswith("_"))),
            )
        return merged

    async def _async_fetch_device_configs(self) -> dict[str, dict[str, Any]]:
        if not self.devices:
            return {}

        results = await asyncio.gather(
            *[self._async_fetch_device_config(device_sn) for device_sn in self.devices]
        )
        return dict(zip(self.devices, results, strict=True))

    def _cached_device_payload(self, device_sn: str) -> dict[str, Any]:
        if not self.data:
            return {}
        return self.data.get("devices", {}).get(device_sn, {})

    def _build_device_payload(
        self,
        device_sn: str,
        latest: dict[str, Any],
        config: dict[str, Any],
    ) -> dict[str, Any]:
        if isinstance(latest, dict) and "values" in latest:
            values = latest.get("values", {})
            fields = latest.get("fields", {})
        else:
            values = latest if isinstance(latest, dict) else {}
            fields = {
                key: {"value": value, "unit": None, "name": None}
                for key, value in values.items()
            }

        if fields:
            _LOGGER.debug(
                "Device %s latest keys: %s",
                device_sn,
                ", ".join(sorted(fields.keys())),
            )

        return {
            "info": self.device_info.get(device_sn, {}),
            "data": values,
            "fields": fields,
            "config": config,
        }

    async def _async_update_data(self) -> dict[str, Any]:
        previous_devices = (self.data or {}).get("devices", {})
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

            try:
                device_data = await self.client.get_device_latest_data(self.devices)
            except DeyeCloudApiError as err:
                if previous_devices:
                    _LOGGER.warning(
                        "Device latest failed, using cached telemetry: %s", err
                    )
                    device_data = {
                        device_sn: {
                            "values": previous_devices.get(device_sn, {}).get("data", {}),
                            "fields": previous_devices.get(device_sn, {}).get("fields", {}),
                        }
                        for device_sn in self.devices
                    }
                else:
                    raise

            station_data: dict[str, Any] = {}
            previous_station_data = (self.data or {}).get("station_data", {})
            for station in self.stations:
                station_id = station.get("id") or station.get("stationId")
                if not station_id:
                    continue
                try:
                    station_data[str(station_id)] = await self.client.get_station_latest_data(
                        station_id
                    )
                except DeyeCloudApiError as err:
                    _LOGGER.debug("Station latest failed for %s: %s", station_id, err)
                    if str(station_id) in previous_station_data:
                        station_data[str(station_id)] = previous_station_data[str(station_id)]

            now = time.monotonic()
            if (
                self._force_config_refresh
                or not self._device_configs
                or now - self._last_config_fetch >= CONFIG_REFRESH_SECONDS
            ):
                fetched_configs = await self._async_fetch_device_configs()
                for device_sn, config in fetched_configs.items():
                    if config:
                        self._device_configs[device_sn] = config
                    elif device_sn not in self._device_configs:
                        cached = self._cached_device_payload(device_sn).get("config", {})
                        if cached:
                            self._device_configs[device_sn] = cached
                self._last_config_fetch = now
                self._force_config_refresh = False

            devices_payload: dict[str, Any] = {}
            for device_sn in self.devices:
                cached = self._cached_device_payload(device_sn)
                config = self._device_configs.get(device_sn) or cached.get("config", {})
                devices_payload[device_sn] = self._build_device_payload(
                    device_sn,
                    device_data.get(device_sn, {}),
                    config,
                )

            return {
                "stations": self.stations,
                "station_data": station_data,
                "devices": devices_payload,
            }
        except DeyeCloudApiError as err:
            if previous_devices:
                _LOGGER.warning(
                    "Deye Cloud update failed, keeping previous device data: %s", err
                )
                return {
                    "stations": self.stations,
                    "station_data": (self.data or {}).get("station_data", {}),
                    "devices": previous_devices,
                }
            raise UpdateFailed(f"Deye Cloud update failed: {err}") from err
