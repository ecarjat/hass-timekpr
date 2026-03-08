"""Text entities for allowed windows configuration."""

from __future__ import annotations

from homeassistant.components.text import TextEntity, TextMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .adapter import TimekprCommandAdapter, TimekprParseError
from .const import NUMBER_TO_WEEKDAY
from .entity import TimekprEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up text entities for configured users."""
    coordinator = entry.runtime_data.coordinator

    entities: list[TextEntity] = []
    for user in coordinator.users:
        entities.extend(
            TimekprAllowedWindowsText(coordinator, user, weekday)
            for weekday in range(1, 8)
        )

    async_add_entities(entities)


class TimekprAllowedWindowsText(TimekprEntity, TextEntity):
    """Allowed windows text entity for one weekday."""

    _attr_mode = TextMode.TEXT
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator, user: str, weekday_number: int) -> None:
        self._weekday_number = weekday_number
        weekday = NUMBER_TO_WEEKDAY[weekday_number]
        super().__init__(coordinator, user, f"allowed_windows_{weekday}")
        self._attr_name = f"Allowed Windows {weekday.upper()}"

    @property
    def native_value(self) -> str:
        """Current allowed windows for this weekday."""
        state = self.user_state
        if state is None:
            return ""
        return state.windows_per_weekday.get(self._weekday_number, "")

    async def async_set_value(self, value: str) -> None:
        """Update allowed windows for this weekday."""
        try:
            canonical = TimekprCommandAdapter.hour_spec_to_windows(
                TimekprCommandAdapter.windows_to_hour_spec(value)
            )
        except TimekprParseError as exc:
            raise HomeAssistantError(str(exc)) from exc

        await self.coordinator.async_set_allowed_windows(
            self._user,
            self._weekday_number,
            canonical,
        )
