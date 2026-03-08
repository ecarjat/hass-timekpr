"""Button entities for timekpr integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import TimekprEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entities for configured users."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(TimekprApplyBonusButton(coordinator, user) for user in coordinator.users)


class TimekprApplyBonusButton(TimekprEntity, ButtonEntity):
    """Apply staged bonus minutes for a user."""

    _attr_icon = "mdi:plus-box"

    def __init__(self, coordinator, user: str) -> None:
        super().__init__(coordinator, user, "apply_bonus")
        self._attr_name = "Apply Bonus Time"

    async def async_press(self) -> None:
        """Apply staged bonus time."""
        minutes = self.coordinator.get_bonus_minutes(self._user)
        await self.coordinator.async_add_time(self._user, minutes)
