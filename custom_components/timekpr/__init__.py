"""Home Assistant integration for managing timekpr through SSH."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .adapter import TimekprCommandAdapter, TimekprError
from .const import (
    CONF_SSH_DEVICE_ID,
    CONF_TIMEKPRA_PATH,
    CONF_UNLOCK_GRACE_MINUTES,
    CONF_USERS,
    DEFAULT_TIMEKPRA_PATH,
    DEFAULT_UNLOCK_GRACE_MINUTES,
    DOMAIN,
    PLATFORMS,
)
from .coordinator import TimekprCoordinator
from .models import TimekprRuntimeData
from .services import async_register_services, async_unregister_services


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up the integration from YAML (not used)."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up timekpr from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    users = list(entry.options.get(CONF_USERS, entry.data.get(CONF_USERS, [])))
    if not users:
        raise ConfigEntryNotReady("No managed users configured for this entry")

    ssh_device_id = entry.data.get(CONF_SSH_DEVICE_ID)
    if not ssh_device_id:
        raise ConfigEntryNotReady("Missing linked SSH device ID")

    timekpra_path = entry.options.get(
        CONF_TIMEKPRA_PATH,
        entry.data.get(CONF_TIMEKPRA_PATH, DEFAULT_TIMEKPRA_PATH),
    )
    unlock_grace_minutes = int(
        entry.options.get(
            CONF_UNLOCK_GRACE_MINUTES,
            entry.data.get(CONF_UNLOCK_GRACE_MINUTES, DEFAULT_UNLOCK_GRACE_MINUTES),
        )
    )

    adapter = TimekprCommandAdapter(hass, ssh_device_id=ssh_device_id, timekpra_path=timekpra_path)
    coordinator = TimekprCoordinator(
        hass,
        entry,
        adapter,
        users=users,
        unlock_grace_minutes=unlock_grace_minutes,
    )

    try:
        await adapter.async_validate_sudo()
        await coordinator.async_config_entry_first_refresh()
    except TimekprError as exc:
        raise ConfigEntryNotReady(
            f"timekpr validation failed for host {entry.data.get(CONF_HOST, 'unknown')}: {exc}"
        ) from exc

    runtime_data = TimekprRuntimeData(coordinator=coordinator)
    hass.data[DOMAIN][entry.entry_id] = runtime_data
    entry.runtime_data = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_register_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
        await async_unregister_services(hass)
    return unload_ok
