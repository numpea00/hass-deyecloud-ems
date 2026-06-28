"""Data update coordinator for Deye Cloud EMS."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import DeyeCloudApiError, DeyeCloudClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class DeyeCloudEMSCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fetching Deye device and station data."""

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

            device_configs: dict[str, dict[str, Any]] = {}
            for device_sn in self.devices:
                config: dict[str, Any] = {}
                try:
                    config["battery"] = await self.client.get_battery_config(device_sn)
                except DeyeCloudApiError:
                    pass
                try:
                    config["system"] = await self.client.get_system_config(device_sn)
                except DeyeCloudApiError:
                    pass
                try:
                    config["tou"] = await self.client.get_tou_config(device_sn)
                except DeyeCloudApiError:
                    pass
                device_configs[device_sn] = config

            devices_payload: dict[str, Any] = {}
            for device_sn in self.devices:
                devices_payload[device_sn] = {
                    "info": self.device_info.get(device_sn, {}),
                    "data": device_data.get(device_sn, {}),
                    "config": device_configs.get(device_sn, {}),
                }

            return {
                "stations": self.stations,
                "station_data": station_data,
                "devices": devices_payload,
            }
        except DeyeCloudApiError as err:
            raise UpdateFailed(f"Deye Cloud update failed: {err}") from err
