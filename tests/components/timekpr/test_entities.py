"""Entity behavior tests."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

from homeassistant.exceptions import HomeAssistantError
import pytest

from custom_components.timekpr.button import TimekprApplyBonusButton
from custom_components.timekpr.models import TimekprUserState
from custom_components.timekpr.number import TimekprDailyLimitNumber
from custom_components.timekpr.switch import TimekprLockoutSwitch
from custom_components.timekpr.text import TimekprAllowedWindowsText


def _coordinator_with_user(user: str = "alice"):
    state = TimekprUserState(
        username=user,
        limits_per_weekday_seconds={1: 3600, 2: 3600, 3: 3600, 4: 3600, 5: 3600, 6: 0, 7: 0},
        windows_per_weekday={
            1: "09:00-10:00",
            2: "09:00-10:00",
            3: "09:00-10:00",
            4: "09:00-10:00",
            5: "09:00-10:00",
            6: "",
            7: "",
        },
        actual_time_left_day_seconds=1200,
        lockout_type="lock",
    )

    coordinator = SimpleNamespace(
        entry=SimpleNamespace(entry_id="entry-1", title="timekpr host", data={"ssh_entry_id": "ssh1"}),
        data={user: state},
        users=[user],
        async_set_daily_limit=AsyncMock(),
        async_set_allowed_windows=AsyncMock(),
        async_add_time=AsyncMock(),
        async_lock_user=AsyncMock(),
        async_unlock_user=AsyncMock(),
        get_bonus_minutes=lambda _: 20,
    )
    return coordinator


@pytest.mark.asyncio
async def test_daily_limit_number_writes_to_coordinator() -> None:
    """Daily limit number writes should dispatch to coordinator."""
    coordinator = _coordinator_with_user()
    entity = TimekprDailyLimitNumber(coordinator, "alice", 1)

    assert entity.native_value == 60
    await entity.async_set_native_value(90)
    coordinator.async_set_daily_limit.assert_awaited_once_with("alice", 1, 90)


@pytest.mark.asyncio
async def test_allowed_windows_text_validation_and_write() -> None:
    """Allowed windows text validates format before dispatch."""
    coordinator = _coordinator_with_user()
    entity = TimekprAllowedWindowsText(coordinator, "alice", 1)

    await entity.async_set_value("09:00-11:30")
    coordinator.async_set_allowed_windows.assert_awaited_once_with(
        "alice", 1, "09:00-11:30"
    )

    with pytest.raises(HomeAssistantError):
        await entity.async_set_value("11:00-10:00")


@pytest.mark.asyncio
async def test_apply_bonus_button_uses_staged_minutes() -> None:
    """Button should use staged bonus minutes and add time."""
    coordinator = _coordinator_with_user()
    entity = TimekprApplyBonusButton(coordinator, "alice")

    await entity.async_press()
    coordinator.async_add_time.assert_awaited_once_with("alice", 20)


@pytest.mark.asyncio
async def test_lockout_switch_actions() -> None:
    """Lockout switch should call lock/unlock coordinator methods."""
    coordinator = _coordinator_with_user()
    entity = TimekprLockoutSwitch(coordinator, "alice")

    assert entity.is_on is False
    await entity.async_turn_on()
    await entity.async_turn_off()

    coordinator.async_lock_user.assert_awaited_once_with("alice")
    coordinator.async_unlock_user.assert_awaited_once_with("alice")
