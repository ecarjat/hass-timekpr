"""Base entity for timekpr integration."""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import TimekprCoordinator


class TimekprEntity(CoordinatorEntity[TimekprCoordinator]):
    """Base class for all timekpr entities."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: TimekprCoordinator,
        user: str,
        key: str,
        translation_key: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._user = user
        self._key = key
        if translation_key is not None:
            self._attr_translation_key = translation_key
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{user}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Group entities by config entry and remote host."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.entry.entry_id)},
            name=self.coordinator.entry.title,
            manufacturer="Timekpr",
            model="timekpr-next",
            via_device=("ssh", self.coordinator.entry.data.get("ssh_entry_id", "unknown")),
        )

    @property
    def available(self) -> bool:
        """Entity availability follows coordinator state and user presence."""
        return super().available and bool(self.coordinator.data and self._user in self.coordinator.data)

    @property
    def user_state(self):
        """Shortcut to current user state."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._user)
