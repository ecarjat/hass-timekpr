"""Sensors for timekpr integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import NUMBER_TO_WEEKDAY
from .entity import TimekprEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up timekpr sensors for each configured user."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        TimekprRemainingTimeSensor(coordinator, user) for user in coordinator.users
    )


class TimekprRemainingTimeSensor(TimekprEntity, SensorEntity):
    """Remaining daily time for a managed user."""

    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:timer-outline"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, user: str) -> None:
        super().__init__(coordinator, user, "remaining_minutes", "remaining_minutes")

    @property
    def native_value(self) -> int | None:
        """Return remaining minutes for current day."""
        state = self.user_state
        if state is None or state.actual_time_left_day_seconds is None:
            return None
        return max(0, state.actual_time_left_day_seconds // 60)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Expose status summary and raw effective settings."""
        state = self.user_state
        if state is None:
            return {}

        limits_minutes = {
            NUMBER_TO_WEEKDAY[day]: seconds // 60
            for day, seconds in sorted(state.limits_per_weekday_seconds.items())
        }
        windows = {
            NUMBER_TO_WEEKDAY[day]: state.windows_per_weekday.get(day, "")
            for day in range(1, 8)
        }

        return {
            "username": state.username,
            "locked": bool(
                state.actual_time_left_day_seconds is not None
                and state.actual_time_left_day_seconds <= 0
            ),
            "lockout_type": state.lockout_type,
            "daily_limits_minutes": limits_minutes,
            "allowed_windows": windows,
        }
