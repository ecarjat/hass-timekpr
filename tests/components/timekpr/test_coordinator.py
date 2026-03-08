"""Coordinator tests."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.timekpr.coordinator import TimekprCoordinator
from custom_components.timekpr.models import TimekprUserState


@pytest.mark.asyncio
async def test_coordinator_write_methods_refresh(hass) -> None:
    """Write operations should trigger refresh."""
    entry = MockConfigEntry(domain="timekpr", data={}, options={})
    adapter = AsyncMock()
    coordinator = TimekprCoordinator(
        hass,
        entry,
        adapter,
        users=["alice"],
        unlock_grace_minutes=15,
    )

    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_add_time("alice", 10)
    await coordinator.async_set_daily_limit("alice", 1, 60)
    await coordinator.async_set_allowed_windows("alice", 1, "09:00-10:00")

    adapter.async_add_time.assert_awaited_once_with("alice", 10)
    adapter.async_set_daily_limit.assert_awaited_once_with("alice", 1, 60)
    adapter.async_set_allowed_windows.assert_awaited_once_with(
        "alice", 1, "09:00-10:00"
    )
    assert coordinator.async_request_refresh.await_count == 3


@pytest.mark.asyncio
async def test_lock_unlock_uses_cached_restore_seconds(hass) -> None:
    """Unlock should restore cached value after lock."""
    entry = MockConfigEntry(domain="timekpr", data={}, options={})
    adapter = AsyncMock()
    coordinator = TimekprCoordinator(
        hass,
        entry,
        adapter,
        users=["alice"],
        unlock_grace_minutes=15,
    )

    coordinator.data = {
        "alice": TimekprUserState(
            username="alice",
            actual_time_left_day_seconds=1800,
        )
    }
    coordinator.async_request_refresh = AsyncMock()

    await coordinator.async_lock_user("alice")
    await coordinator.async_unlock_user("alice")

    adapter.async_lock_user.assert_awaited_once_with("alice")
    adapter.async_unlock_user.assert_awaited_once_with("alice", 1800)
