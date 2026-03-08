"""Service registration for timekpr."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
import homeassistant.helpers.config_validation as cv

ATTR_ENTRY_ID = "entry_id"

from .adapter import TimekprCommandAdapter, TimekprParseError
from .const import (
    CONF_USERS,
    DOMAIN,
    SERVICE_ADD_TIME,
    SERVICE_LOCK_USER,
    SERVICE_REFRESH_USERS,
    SERVICE_SET_ALLOWED_WINDOWS,
    SERVICE_SET_DAILY_LIMIT,
    SERVICE_UNLOCK_USER,
    WEEKDAYS,
    WEEKDAY_TO_NUMBER,
)
from .coordinator import TimekprCoordinator


def _validate_weekday(value: str) -> str:
    value = value.strip().lower()
    if value not in WEEKDAY_TO_NUMBER:
        raise vol.Invalid(f"Invalid weekday '{value}'")
    return value


def _validate_windows(value: str) -> str:
    value = value.strip()
    try:
        TimekprCommandAdapter.windows_to_hour_spec(value)
    except TimekprParseError as exc:
        raise vol.Invalid(str(exc)) from exc
    return value


SET_DAILY_LIMIT_SCHEMA = vol.Schema(
    {
        vol.Required("user"): cv.string,
        vol.Required("weekday"): _validate_weekday,
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=0, max=24 * 60)),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

SET_ALLOWED_WINDOWS_SCHEMA = vol.Schema(
    {
        vol.Required("user"): cv.string,
        vol.Required("weekday"): _validate_weekday,
        vol.Required("windows"): _validate_windows,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

ADD_TIME_SCHEMA = vol.Schema(
    {
        vol.Required("user"): cv.string,
        vol.Required("minutes"): vol.All(vol.Coerce(int), vol.Range(min=1, max=24 * 60)),
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

LOCK_UNLOCK_SCHEMA = vol.Schema(
    {
        vol.Required("user"): cv.string,
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)

REFRESH_USERS_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_ENTRY_ID): cv.string,
    }
)


def _iter_coordinators(hass: HomeAssistant) -> Iterable[TimekprCoordinator]:
    domain_data = hass.data.get(DOMAIN, {})
    for entry_data in domain_data.values():
        coordinator = getattr(entry_data, "coordinator", None)
        if coordinator is not None:
            yield coordinator


def _get_coordinator_for_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> TimekprCoordinator:
    for coordinator in _iter_coordinators(hass):
        if coordinator.entry.entry_id == entry_id:
            return coordinator
    raise ServiceValidationError(f"No timekpr entry found for entry_id={entry_id}")


def _resolve_user_coordinator(
    hass: HomeAssistant,
    user: str,
    entry_id: str | None,
) -> TimekprCoordinator:
    if entry_id:
        coordinator = _get_coordinator_for_entry(hass, entry_id)
        if user not in coordinator.users:
            raise ServiceValidationError(
                f"User '{user}' is not managed by entry {entry_id}"
            )
        return coordinator

    matches = [coordinator for coordinator in _iter_coordinators(hass) if user in coordinator.users]
    if not matches:
        raise ServiceValidationError(f"User '{user}' is not managed by any timekpr entry")
    if len(matches) > 1:
        raise ServiceValidationError(
            f"User '{user}' is managed by multiple entries; provide entry_id"
        )
    return matches[0]


async def async_register_services(hass: HomeAssistant) -> None:
    """Register all integration services once."""
    if hass.data.setdefault(DOMAIN, {}).get("services_registered"):
        return

    async def _set_daily_limit(call: ServiceCall) -> None:
        user = call.data["user"]
        weekday = call.data["weekday"]
        minutes = call.data["minutes"]
        coordinator = _resolve_user_coordinator(hass, user, call.data.get(ATTR_ENTRY_ID))
        await coordinator.async_set_daily_limit(user, WEEKDAY_TO_NUMBER[weekday], minutes)

    async def _set_allowed_windows(call: ServiceCall) -> None:
        user = call.data["user"]
        weekday = call.data["weekday"]
        windows = call.data["windows"]
        coordinator = _resolve_user_coordinator(hass, user, call.data.get(ATTR_ENTRY_ID))
        await coordinator.async_set_allowed_windows(user, WEEKDAY_TO_NUMBER[weekday], windows)

    async def _add_time(call: ServiceCall) -> None:
        user = call.data["user"]
        minutes = call.data["minutes"]
        coordinator = _resolve_user_coordinator(hass, user, call.data.get(ATTR_ENTRY_ID))
        await coordinator.async_add_time(user, minutes)

    async def _lock_user(call: ServiceCall) -> None:
        user = call.data["user"]
        coordinator = _resolve_user_coordinator(hass, user, call.data.get(ATTR_ENTRY_ID))
        await coordinator.async_lock_user(user)

    async def _unlock_user(call: ServiceCall) -> None:
        user = call.data["user"]
        coordinator = _resolve_user_coordinator(hass, user, call.data.get(ATTR_ENTRY_ID))
        await coordinator.async_unlock_user(user)

    async def _refresh_users(call: ServiceCall) -> None:
        entry_id = call.data.get(ATTR_ENTRY_ID)
        coordinators = (
            [_get_coordinator_for_entry(hass, entry_id)]
            if entry_id
            else list(_iter_coordinators(hass))
        )

        for coordinator in coordinators:
            users = await coordinator.async_discover_users()
            coordinator.users = sorted(set(users))

            options = dict(coordinator.entry.options)
            options[CONF_USERS] = coordinator.users
            hass.config_entries.async_update_entry(coordinator.entry, options=options)

            # Ensure bonus defaults exist for new users.
            for user in coordinator.users:
                coordinator.set_bonus_minutes(user, coordinator.get_bonus_minutes(user))

            await coordinator.async_request_refresh()

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_DAILY_LIMIT,
        _set_daily_limit,
        schema=SET_DAILY_LIMIT_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_ALLOWED_WINDOWS,
        _set_allowed_windows,
        schema=SET_ALLOWED_WINDOWS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_TIME,
        _add_time,
        schema=ADD_TIME_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOCK_USER,
        _lock_user,
        schema=LOCK_UNLOCK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_UNLOCK_USER,
        _unlock_user,
        schema=LOCK_UNLOCK_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH_USERS,
        _refresh_users,
        schema=REFRESH_USERS_SCHEMA,
    )

    hass.data[DOMAIN]["services_registered"] = True


async def async_unregister_services(hass: HomeAssistant) -> None:
    """Unregister integration services when last entry unloads."""
    domain_data = hass.data.get(DOMAIN, {})
    remaining_entries = [
        value for key, value in domain_data.items() if key != "services_registered"
    ]
    if remaining_entries:
        return

    for service in (
        SERVICE_SET_DAILY_LIMIT,
        SERVICE_SET_ALLOWED_WINDOWS,
        SERVICE_ADD_TIME,
        SERVICE_LOCK_USER,
        SERVICE_UNLOCK_USER,
        SERVICE_REFRESH_USERS,
    ):
        if hass.services.has_service(DOMAIN, service):
            hass.services.async_remove(DOMAIN, service)

    domain_data["services_registered"] = False
