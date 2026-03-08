"""Number entities for timekpr integration."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity
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
    """Set up number entities for configured users."""
    coordinator = entry.runtime_data.coordinator

    entities: list[NumberEntity] = []
    for user in coordinator.users:
        entities.extend(
            TimekprDailyLimitNumber(coordinator, user, weekday)
            for weekday in range(1, 8)
        )
        entities.append(TimekprBonusMinutesNumber(coordinator, user))

    async_add_entities(entities)


class TimekprDailyLimitNumber(TimekprEntity, NumberEntity):
    """Daily limit in minutes for one weekday."""

    _attr_native_min_value = 0
    _attr_native_max_value = 24 * 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:clock-edit-outline"

    def __init__(self, coordinator, user: str, weekday_number: int) -> None:
        self._weekday_number = weekday_number
        weekday = NUMBER_TO_WEEKDAY[weekday_number]
        super().__init__(coordinator, user, f"daily_limit_{weekday}")
        self._attr_name = f"Daily Limit {weekday.upper()}"

    @property
    def native_value(self) -> int | None:
        """Current daily limit for this weekday."""
        state = self.user_state
        if state is None:
            return None
        seconds = state.limits_per_weekday_seconds.get(self._weekday_number)
        if seconds is None:
            return None
        return max(0, int(seconds // 60))

    async def async_set_native_value(self, value: float) -> None:
        """Update daily limit for this weekday."""
        await self.coordinator.async_set_daily_limit(
            self._user,
            self._weekday_number,
            int(value),
        )


class TimekprBonusMinutesNumber(TimekprEntity, NumberEntity):
    """Staged bonus minutes to apply with the add-time button."""

    _attr_native_min_value = 1
    _attr_native_max_value = 24 * 60
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_icon = "mdi:plus-circle-outline"

    def __init__(self, coordinator, user: str) -> None:
        super().__init__(coordinator, user, "bonus_minutes")
        self._attr_name = "Bonus Minutes"

    @property
    def native_value(self) -> int:
        """Current staged bonus minutes."""
        return self.coordinator.get_bonus_minutes(self._user)

    async def async_set_native_value(self, value: float) -> None:
        """Update staged bonus minutes (local value)."""
        self.coordinator.set_bonus_minutes(self._user, int(value))
        self.async_write_ha_state()
