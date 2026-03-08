"""Service tests for timekpr integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.exceptions import ServiceValidationError

from custom_components.timekpr.const import (
    CONF_TIMEKPRA_PATH,
    CONF_UNLOCK_GRACE_MINUTES,
    CONF_USERS,
    DEFAULT_TIMEKPRA_PATH,
    DEFAULT_UNLOCK_GRACE_MINUTES,
    DOMAIN,
    SERVICE_ADD_TIME,
    SERVICE_LOCK_USER,
    SERVICE_REFRESH_USERS,
    SERVICE_SET_ALLOWED_WINDOWS,
    SERVICE_SET_DAILY_LIMIT,
    SERVICE_UNLOCK_USER,
)
from custom_components.timekpr.services import async_register_services

ATTR_ENTRY_ID = "entry_id"


@pytest.mark.asyncio
async def test_set_daily_limit_service_dispatches(hass) -> None:
    """set_daily_limit service should dispatch to coordinator with day mapping."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    coordinator = SimpleNamespace(
        entry=entry,
        users=["alice"],
        async_set_daily_limit=AsyncMock(),
        async_set_allowed_windows=AsyncMock(),
        async_add_time=AsyncMock(),
        async_lock_user=AsyncMock(),
        async_unlock_user=AsyncMock(),
        async_discover_users=AsyncMock(return_value=["alice"]),
        async_request_refresh=AsyncMock(),
        set_bonus_minutes=lambda user, minutes: None,
        get_bonus_minutes=lambda user: 15,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = SimpleNamespace(coordinator=coordinator)
    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SET_DAILY_LIMIT,
        {"user": "alice", "weekday": "mon", "minutes": 120, ATTR_ENTRY_ID: entry.entry_id},
        blocking=True,
    )

    coordinator.async_set_daily_limit.assert_awaited_once_with("alice", 1, 120)


@pytest.mark.asyncio
async def test_set_allowed_windows_schema_validation(hass) -> None:
    """set_allowed_windows should reject malformed windows."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    coordinator = SimpleNamespace(
        entry=entry,
        users=["alice"],
        async_set_daily_limit=AsyncMock(),
        async_set_allowed_windows=AsyncMock(),
        async_add_time=AsyncMock(),
        async_lock_user=AsyncMock(),
        async_unlock_user=AsyncMock(),
        async_discover_users=AsyncMock(return_value=["alice"]),
        async_request_refresh=AsyncMock(),
        set_bonus_minutes=lambda user, minutes: None,
        get_bonus_minutes=lambda user: 15,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = SimpleNamespace(coordinator=coordinator)
    await async_register_services(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_ALLOWED_WINDOWS,
            {
                "user": "alice",
                "weekday": "mon",
                "windows": "09:00-08:00",
                ATTR_ENTRY_ID: entry.entry_id,
            },
            blocking=True,
        )


@pytest.mark.asyncio
async def test_refresh_users_updates_options(hass) -> None:
    """refresh_users service should refresh list and persist options."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERS: ["alice"],
            CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
            CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
        },
        options={
            CONF_USERS: ["alice"],
            CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
            CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
        },
    )
    entry.add_to_hass(hass)

    coordinator = SimpleNamespace(
        entry=entry,
        users=["alice"],
        async_set_daily_limit=AsyncMock(),
        async_set_allowed_windows=AsyncMock(),
        async_add_time=AsyncMock(),
        async_lock_user=AsyncMock(),
        async_unlock_user=AsyncMock(),
        async_discover_users=AsyncMock(return_value=["alice", "bob"]),
        async_request_refresh=AsyncMock(),
        set_bonus_minutes=lambda user, minutes: None,
        get_bonus_minutes=lambda user: 15,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = SimpleNamespace(coordinator=coordinator)
    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_REFRESH_USERS,
        {ATTR_ENTRY_ID: entry.entry_id},
        blocking=True,
    )

    assert set(entry.options[CONF_USERS]) == {"alice", "bob"}
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_lock_unlock_and_add_time_services(hass) -> None:
    """lock/unlock/add services should dispatch to coordinator."""
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    coordinator = SimpleNamespace(
        entry=entry,
        users=["alice"],
        async_set_daily_limit=AsyncMock(),
        async_set_allowed_windows=AsyncMock(),
        async_add_time=AsyncMock(),
        async_lock_user=AsyncMock(),
        async_unlock_user=AsyncMock(),
        async_discover_users=AsyncMock(return_value=["alice"]),
        async_request_refresh=AsyncMock(),
        set_bonus_minutes=lambda user, minutes: None,
        get_bonus_minutes=lambda user: 15,
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = SimpleNamespace(coordinator=coordinator)
    await async_register_services(hass)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_ADD_TIME,
        {"user": "alice", "minutes": 10, ATTR_ENTRY_ID: entry.entry_id},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_LOCK_USER,
        {"user": "alice", ATTR_ENTRY_ID: entry.entry_id},
        blocking=True,
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_UNLOCK_USER,
        {"user": "alice", ATTR_ENTRY_ID: entry.entry_id},
        blocking=True,
    )

    coordinator.async_add_time.assert_awaited_once_with("alice", 10)
    coordinator.async_lock_user.assert_awaited_once_with("alice")
    coordinator.async_unlock_user.assert_awaited_once_with("alice")
