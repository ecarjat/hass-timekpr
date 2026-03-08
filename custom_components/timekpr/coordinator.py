"""Coordinator for state and write operations."""

from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adapter import TimekprCommandAdapter, TimekprError
from .const import DEFAULT_SCAN_INTERVAL_SECONDS, DEFAULT_UNLOCK_GRACE_MINUTES
from .models import TimekprUserState

_LOGGER = logging.getLogger(__name__)


class TimekprCoordinator(DataUpdateCoordinator[dict[str, TimekprUserState]]):
    """Coordinate read/write operations for all configured users."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        adapter: TimekprCommandAdapter,
        users: list[str],
        unlock_grace_minutes: int = DEFAULT_UNLOCK_GRACE_MINUTES,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"timekpr_{entry.entry_id}",
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL_SECONDS),
        )
        self.entry = entry
        self.adapter = adapter
        self.users = sorted(set(users))
        self._unlock_grace_seconds = max(1, unlock_grace_minutes * 60)
        self._unlock_restore_seconds: dict[str, int] = {}
        self._bonus_minutes: dict[str, int] = {
            user: unlock_grace_minutes for user in self.users
        }

    async def _async_update_data(self) -> dict[str, TimekprUserState]:
        """Fetch full state for managed users."""
        data: dict[str, TimekprUserState] = {}
        for user in self.users:
            try:
                data[user] = await self.adapter.async_fetch_user_state(user)
            except TimekprError as exc:
                raise UpdateFailed(f"Failed fetching timekpr state for {user}: {exc}") from exc

        return data

    async def async_discover_users(self) -> list[str]:
        """Retrieve controllable users from remote host."""
        return await self.adapter.async_list_users()

    def set_bonus_minutes(self, user: str, minutes: int) -> None:
        """Set staged bonus minutes for button action."""
        self._bonus_minutes[user] = max(1, minutes)

    def get_bonus_minutes(self, user: str) -> int:
        """Get staged bonus minutes for button action."""
        return self._bonus_minutes.get(user, max(1, self._unlock_grace_seconds // 60))

    async def async_set_daily_limit(self, user: str, weekday_number: int, minutes: int) -> None:
        """Set per-day limit then refresh."""
        await self.adapter.async_set_daily_limit(user, weekday_number, minutes)
        await self.async_request_refresh()

    async def async_set_allowed_windows(
        self,
        user: str,
        weekday_number: int,
        windows: str,
    ) -> None:
        """Set per-day allowed windows then refresh."""
        await self.adapter.async_set_allowed_windows(user, weekday_number, windows)
        await self.async_request_refresh()

    async def async_add_time(self, user: str, minutes: int) -> None:
        """Add remaining time for user today then refresh."""
        await self.adapter.async_add_time(user, minutes)
        await self.async_request_refresh()

    async def async_lock_user(self, user: str) -> None:
        """Force lock user by exhausting available time today."""
        current = self.data.get(user) if self.data else None
        restore_seconds = (
            current.actual_time_left_day_seconds
            if current and current.actual_time_left_day_seconds and current.actual_time_left_day_seconds > 0
            else self._unlock_grace_seconds
        )
        self._unlock_restore_seconds[user] = int(restore_seconds)

        await self.adapter.async_lock_user(user)
        await self.async_request_refresh()

    async def async_unlock_user(self, user: str) -> None:
        """Unlock user by restoring the previous/default remaining time."""
        restore_seconds = self._unlock_restore_seconds.get(user, self._unlock_grace_seconds)
        await self.adapter.async_unlock_user(user, restore_seconds)
        await self.async_request_refresh()
