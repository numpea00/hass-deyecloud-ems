"""Named TOU profile storage and management."""

from __future__ import annotations

import copy
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DEFAULT_TOU_PROFILES, DOMAIN, MIN_BATTERY_RESERVE_SOC, STORAGE_KEY, STORAGE_VERSION

_LOGGER = logging.getLogger(__name__)


class TouProfileManager:
    """Persist and manage named TOU profiles."""

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self._store = Store(
            hass,
            STORAGE_VERSION,
            f"{STORAGE_KEY}_{entry_id}",
        )
        self._profiles: dict[str, dict[str, Any]] = {}
        self._active_profile: str | None = None

    @property
    def active_profile(self) -> str | None:
        return self._active_profile

    def set_active_profile(self, name: str) -> None:
        self._active_profile = name

    async def async_load(self) -> None:
        stored = await self._store.async_load()
        if stored and isinstance(stored, dict):
            self._profiles = stored.get("profiles", {})
            self._active_profile = stored.get("active_profile")
        else:
            self._profiles = {}

        changed = False
        for name, profile in DEFAULT_TOU_PROFILES.items():
            self._profiles[name] = copy.deepcopy(profile)
            changed = True

        if "ev_night" in self._profiles:
            del self._profiles["ev_night"]
            changed = True
            if self._active_profile == "ev_night":
                self._active_profile = "thai_sunny"

        if changed or not stored:
            await self.async_save()

    async def async_save(self) -> None:
        await self._store.async_save(
            {
                "profiles": self._profiles,
                "active_profile": self._active_profile,
            }
        )

    def list_profiles(self) -> list[str]:
        return sorted(self._profiles.keys())

    def get_profile(self, name: str) -> dict[str, Any] | None:
        profile = self._profiles.get(name)
        return copy.deepcopy(profile) if profile else None

    def get_profile_slots(self, name: str) -> list[dict[str, Any]]:
        profile = self.get_profile(name)
        if not profile:
            return []
        return copy.deepcopy(profile.get("slots", []))

    async def async_save_profile(
        self,
        name: str,
        slots: list[dict[str, Any]],
        description: str = "",
    ) -> None:
        self._profiles[name] = {
            "description": description,
            "slots": copy.deepcopy(slots),
        }
        await self.async_save()

    async def async_delete_profile(self, name: str) -> None:
        if name in DEFAULT_TOU_PROFILES:
            raise ValueError(f"Cannot delete built-in profile: {name}")
        self._profiles.pop(name, None)
        if self._active_profile == name:
            self._active_profile = None
        await self.async_save()

    async def async_reset_builtin(self, name: str) -> None:
        if name not in DEFAULT_TOU_PROFILES:
            raise ValueError(f"Unknown built-in profile: {name}")
        self._profiles[name] = copy.deepcopy(DEFAULT_TOU_PROFILES[name])
        await self.async_save()

    def apply_reserve_to_slots(self, slots: list[dict[str, Any]], soc: int) -> list[dict[str, Any]]:
        """Return slots with SOC updated for the current time window."""
        clamped = max(MIN_BATTERY_RESERVE_SOC, min(100, int(soc)))
        updated = copy.deepcopy(slots)
        for slot in updated:
            slot["soc"] = clamped
        return updated
