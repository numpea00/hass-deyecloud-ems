"""Deye Cloud API client."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from typing import Any

import aiohttp

_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 30
SUCCESS_CODES = {0, 1000000, 1106000, "0", "1000000", "1106000"}
AUTH_ERROR_CODES = {1001, 1002, 1003, "1001", "1002", "1003", 2101017, "2101017"}


class DeyeCloudApiError(Exception):
    """Base exception for Deye Cloud API errors."""


class DeyeCloudAuthError(DeyeCloudApiError):
    """Authentication error."""


def _sha256(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest().lower()


def _build_login_payload(login: str) -> dict[str, str]:
    login = login.strip()
    if "@" in login:
        return {"email": login}
    return {"username": login}


class DeyeCloudClient:
    """Async client for Deye Cloud OpenAPI v1."""

    def __init__(
        self,
        base_url: str,
        app_id: str,
        app_secret: str,
        username: str,
        password: str,
        company_id: str | None = None,
        session: aiohttp.ClientSession | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.app_id = app_id
        self.app_secret = app_secret
        self.username = username
        self.password = password
        self.company_id = company_id
        self._session = session
        self._close_session = False
        self._access_token: str | None = None
        self._token_expiry = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession()
            self._close_session = True
        return self._session

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: dict[str, Any] | None = None,
        require_auth: bool = True,
    ) -> dict[str, Any]:
        session = await self._get_session()
        url = f"{self.base_url}{endpoint}"
        payload = data or {}
        headers = {"Content-Type": "application/json"}

        if require_auth:
            if not self._access_token or time.time() >= self._token_expiry:
                await self.obtain_token()
            headers["Authorization"] = f"Bearer {self._access_token}"

        try:
            async with asyncio.timeout(API_TIMEOUT):
                if method.upper() == "GET":
                    async with session.get(url, params=payload, headers=headers) as response:
                        if response.status >= 400:
                            body = await response.text()
                            raise DeyeCloudApiError(
                                f"HTTP {response.status}: {body or response.reason}"
                            )
                        result = await response.json(content_type=None)
                else:
                    async with session.post(url, json=payload, headers=headers) as response:
                        if response.status >= 400:
                            body = await response.text()
                            raise DeyeCloudApiError(
                                f"HTTP {response.status}: {body or response.reason}"
                            )
                        result = await response.json(content_type=None)
        except aiohttp.ClientError as err:
            raise DeyeCloudApiError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            raise DeyeCloudApiError("Request timeout") from err

        code = result.get("code")
        if code not in SUCCESS_CODES and not result.get("success", False):
            error_msg = result.get("msg", "Unknown error")
            if code in AUTH_ERROR_CODES:
                raise DeyeCloudAuthError(error_msg)
            raise DeyeCloudApiError(f"{error_msg} (code: {code})")

        data_field = result.get("data")
        if data_field is not None:
            return data_field
        return result

    async def obtain_token(self) -> str:
        """Obtain and cache access token."""
        url = f"{self.base_url}/account/token?appId={self.app_id}"
        payload: dict[str, Any] = {
            "appSecret": self.app_secret,
            **_build_login_payload(self.username),
            "password": _sha256(self.password),
        }
        if self.company_id:
            payload["companyId"] = str(self.company_id).strip()

        session = await self._get_session()
        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with session.post(
                    url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                ) as response:
                    response.raise_for_status()
                    result = await response.json()
        except aiohttp.ClientError as err:
            raise DeyeCloudApiError(f"Connection error: {err}") from err
        except asyncio.TimeoutError as err:
            raise DeyeCloudApiError("Request timeout") from err

        code = result.get("code")
        if code not in SUCCESS_CODES and not result.get("success", False):
            raise DeyeCloudAuthError(result.get("msg", "Token request failed"))

        token = result.get("accessToken")
        if not token:
            raise DeyeCloudAuthError("No access token in response")

        self._access_token = token
        # Token valid ~60 days; refresh 1 day early
        self._token_expiry = time.time() + (60 * 24 * 60 * 60) - 86400
        return token

    async def get_station_list(self) -> list[dict[str, Any]]:
        result = await self._request("POST", "/station/list", {})
        return result.get("stationList") or []

    async def get_station_devices(self, station_ids: list[int | str]) -> list[dict[str, Any]]:
        if not station_ids:
            return []

        devices: list[dict[str, Any]] = []
        page = 1
        size = 100

        while True:
            payload = {"page": page, "size": size, "stationIds": station_ids}
            result = await self._request("POST", "/station/device", payload)
            page_items = result.get("deviceListItems") or []
            devices.extend(page_items)

            total = result.get("total") or result.get("totalCount")
            if total is not None and len(devices) >= int(total):
                break
            if len(page_items) < size:
                break
            page += 1

        return [
            device
            for device in devices
            if device.get("deviceType") == "INVERTER" and device.get("deviceSn")
        ]

    async def get_device_latest_data(self, device_sns: list[str]) -> dict[str, dict[str, Any]]:
        """Return latest device data with values and field metadata."""
        if not device_sns:
            return {}

        parsed: dict[str, dict[str, Any]] = {}
        for i in range(0, len(device_sns), 10):
            batch = device_sns[i : i + 10]
            result = await self._request("POST", "/device/latest", {"deviceList": batch})
            for device_data in result.get("deviceDataList") or []:
                device_sn = device_data.get("deviceSn")
                if not device_sn:
                    continue
                values: dict[str, Any] = {}
                fields: dict[str, dict[str, Any]] = {}
                for item in device_data.get("dataList") or []:
                    key = item.get("key")
                    if not key:
                        continue
                    value = item.get("value")
                    values[key] = value
                    fields[key] = {
                        "value": value,
                        "unit": item.get("unit"),
                        "name": item.get("name"),
                    }
                parsed[device_sn] = {"values": values, "fields": fields}
        return parsed

    async def get_station_latest_data(self, station_id: str | int) -> dict[str, Any]:
        return await self._request("POST", "/station/latest", {"stationId": station_id})

    async def get_battery_config(self, device_sn: str) -> dict[str, Any]:
        return await self._request("POST", "/config/battery", {"deviceSn": device_sn})

    async def get_system_config(self, device_sn: str) -> dict[str, Any]:
        return await self._request("POST", "/config/system", {"deviceSn": device_sn})

    async def get_tou_config(self, device_sn: str) -> dict[str, Any]:
        return await self._request("POST", "/config/tou", {"deviceSn": device_sn})

    async def set_battery_mode(
        self,
        device_sn: str,
        charge_mode: bool,
        mode_type: str = "GRID_CHARGE",
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/battery/modeControl",
            {
                "action": "on" if charge_mode else "off",
                "batteryModeType": mode_type,
                "deviceSn": device_sn,
            },
        )

    async def set_work_mode(self, device_sn: str, work_mode: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/sys/workMode/update",
            {"deviceSn": device_sn, "workMode": work_mode},
        )

    async def set_energy_pattern(self, device_sn: str, energy_pattern: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/sys/energyPattern/update",
            {"deviceSn": device_sn, "energyPattern": energy_pattern},
        )

    async def set_battery_parameter(
        self,
        device_sn: str,
        parameter: str,
        value: int | float,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/battery/parameter/update",
            {
                "deviceSn": device_sn,
                "parameterName": parameter,
                "parameterValue": value,
            },
        )

    async def set_tou_config(
        self,
        device_sn: str,
        tou_items: list[dict[str, Any]],
        timeout_seconds: int = 30,
    ) -> dict[str, Any]:
        from .tou_helpers import normalize_tou_items_for_api

        normalized_items = normalize_tou_items_for_api(tou_items)
        _LOGGER.debug(
            "TOU update for %s: %s",
            device_sn,
            normalized_items,
        )
        return await self._request(
            "POST",
            "/order/sys/tou/update",
            {
                "deviceSn": device_sn,
                "timeUseSettingItems": normalized_items,
                "timeoutSeconds": timeout_seconds,
            },
        )

    async def set_solar_sell(self, device_sn: str, enabled: bool) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/sys/solarSell/control",
            {"action": "on" if enabled else "off", "deviceSn": device_sn},
        )

    async def set_max_sell_power(self, device_sn: str, power: int) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/order/sys/power/update",
            {"deviceSn": device_sn, "maxSellPower": power},
        )

    async def test_connection(self) -> bool:
        try:
            await self.obtain_token()
            stations = await self.get_station_list()
            return bool(stations)
        except DeyeCloudApiError as err:
            _LOGGER.error("Connection test failed: %s", err)
            return False

    async def close(self) -> None:
        if self._close_session and self._session:
            await self._session.close()
            self._session = None
