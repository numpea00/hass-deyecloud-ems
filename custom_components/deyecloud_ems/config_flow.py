"""Config flow for Deye Cloud EMS."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlowResult
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DeyeCloudApiError, DeyeCloudClient
from .const import (
    CONF_APP_ID,
    CONF_APP_SECRET,
    CONF_BASE_URL,
    CONF_COMPANY_ID,
    CONF_SCAN_INTERVAL,
    DEFAULT_BASE_URL_EU,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_APP_ID): str,
        vol.Required(CONF_APP_SECRET): str,
        vol.Required(CONF_BASE_URL, default=DEFAULT_BASE_URL_EU): str,
        vol.Optional(CONF_COMPANY_ID, default=""): str,
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)
        ),
    }
)


class NoStationsFound(Exception):
    """Raised when credentials work but no stations are accessible."""


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    for key in (
        CONF_USERNAME,
        CONF_PASSWORD,
        CONF_APP_ID,
        CONF_APP_SECRET,
        CONF_BASE_URL,
        CONF_COMPANY_ID,
    ):
        if key in normalized and isinstance(normalized[key], str):
            normalized[key] = normalized[key].strip()
    if not normalized.get(CONF_COMPANY_ID):
        normalized.pop(CONF_COMPANY_ID, None)
    return normalized


async def _validate(hass: HomeAssistant, data: dict[str, Any]) -> None:
    session = async_get_clientsession(hass)
    client = DeyeCloudClient(
        base_url=data[CONF_BASE_URL],
        app_id=data[CONF_APP_ID],
        app_secret=data[CONF_APP_SECRET],
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        company_id=data.get(CONF_COMPANY_ID),
        session=session,
    )
    try:
        if not await client.test_connection():
            stations = await client.get_station_list()
            if not stations:
                raise NoStationsFound
            raise DeyeCloudApiError("Connection test failed")
    finally:
        await client.close()


class DeyeCloudEMSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Deye Cloud EMS."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            user_input = _normalize(user_input)
            unique_id = (
                f"{user_input[CONF_USERNAME]}:"
                f"{user_input.get(CONF_COMPANY_ID) or 'personal'}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                await _validate(self.hass, user_input)
            except NoStationsFound:
                errors["base"] = "no_stations"
            except DeyeCloudApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(
                    title=f"Deye Cloud EMS ({user_input[CONF_USERNAME]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle reauthentication."""
        self.context["title_placeholders"] = {
            "name": entry_data.get(CONF_USERNAME, DOMAIN),
        }
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauthentication with updated credentials."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            user_input = _normalize(user_input)
            data = {
                **reauth_entry.data,
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_APP_ID: user_input[CONF_APP_ID],
                CONF_APP_SECRET: user_input[CONF_APP_SECRET],
                CONF_BASE_URL: user_input[CONF_BASE_URL],
            }
            if user_input.get(CONF_COMPANY_ID):
                data[CONF_COMPANY_ID] = user_input[CONF_COMPANY_ID]
            else:
                data.pop(CONF_COMPANY_ID, None)
            if CONF_SCAN_INTERVAL in user_input:
                data[CONF_SCAN_INTERVAL] = user_input[CONF_SCAN_INTERVAL]

            try:
                await _validate(self.hass, data)
            except NoStationsFound:
                errors["base"] = "no_stations"
            except DeyeCloudApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    reauth_entry,
                    data=data,
                    title=f"Deye Cloud EMS ({data[CONF_USERNAME]})",
                )
                await self.hass.config_entries.async_reload(reauth_entry.entry_id)
                return self.async_abort(reason="reauth_successful")

        current = dict(reauth_entry.data)
        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD): str,
                vol.Required(CONF_APP_ID, default=current.get(CONF_APP_ID, "")): str,
                vol.Required(CONF_APP_SECRET): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL_EU),
                ): str,
                vol.Optional(CONF_COMPANY_ID, default=current.get(CONF_COMPANY_ID, "")): str,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry):
        return DeyeCloudEMSOptionsFlowHandler(config_entry)


class DeyeCloudEMSOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        current = dict(self.config_entry.data)

        if user_input is not None:
            user_input = _normalize(user_input)
            try:
                await _validate(self.hass, user_input)
            except NoStationsFound:
                errors["base"] = "no_stations"
            except DeyeCloudApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                errors["base"] = "unknown"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                    title=f"Deye Cloud EMS ({user_input[CONF_USERNAME]})",
                )
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME, default=current.get(CONF_USERNAME, "")): str,
                vol.Required(CONF_PASSWORD, default=current.get(CONF_PASSWORD, "")): str,
                vol.Required(CONF_APP_ID, default=current.get(CONF_APP_ID, "")): str,
                vol.Required(CONF_APP_SECRET, default=current.get(CONF_APP_SECRET, "")): str,
                vol.Required(
                    CONF_BASE_URL,
                    default=current.get(CONF_BASE_URL, DEFAULT_BASE_URL_EU),
                ): str,
                vol.Optional(CONF_COMPANY_ID, default=current.get(CONF_COMPANY_ID, "")): str,
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=current.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.All(int, vol.Range(min=MIN_SCAN_INTERVAL, max=MAX_SCAN_INTERVAL)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
