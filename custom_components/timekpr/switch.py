"""Switch entities for timekpr integration."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TimekprEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up timekpr switches."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(TimekprLockoutSwitch(coordinator, user) for user in coordinator.users)


class TimekprLockoutSwitch(TimekprEntity, SwitchEntity):
    """Manual lockout switch for a managed user."""

    _attr_icon = "mdi:lock"

    def __init__(self, coordinator, user: str) -> None:
        super().__init__(coordinator, user, "lockout", "lockout")

    @property
    def is_on(self) -> bool:
        """Return whether the user is currently locked out."""
        state = self.user_state
        if state is None or state.actual_time_left_day_seconds is None:
            return False
        return state.actual_time_left_day_seconds <= 0

    async def async_turn_on(self, **kwargs) -> None:
        """Lock user immediately."""
        await self.coordinator.async_lock_user(self._user)

    async def async_turn_off(self, **kwargs) -> None:
        """Unlock user by restoring time."""
        await self.coordinator.async_unlock_user(self._user)
