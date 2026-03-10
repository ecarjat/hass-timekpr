"""Tests for command adapter."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from custom_components.timekpr.adapter import (
    CommandOutput,
    TimekprCommandAdapter,
    TimekprParseError,
    TimekprSudoRequiredError,
)


@dataclass
class DummyServices:
    """Minimal services stub used by adapter tests."""

    response: dict

    async def async_call(self, domain, service, data, blocking, return_response):
        return self.response


@dataclass
class DummyHass:
    """Minimal hass stub used by adapter tests."""

    services: DummyServices


def test_windows_roundtrip() -> None:
    """Windows text converts to hour spec and back."""
    windows = "09:00-12:30,14:00-17:00"
    spec = TimekprCommandAdapter.windows_to_hour_spec(windows)
    assert spec == "9;10;11;12[00-30];14;15;16"

    back = TimekprCommandAdapter.hour_spec_to_windows(spec)
    assert back == windows


def test_windows_invalid_raises() -> None:
    """Invalid windows format should raise parse error."""
    with pytest.raises(TimekprParseError):
        TimekprCommandAdapter.windows_to_hour_spec("09:00-08:00")


@pytest.mark.asyncio
async def test_async_list_users_filters_noise() -> None:
    """User listing should keep only valid usernames."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "Users total: 2\nalice\nbob\ninvalid user",
                        "stderr": "",
                        "code": 0,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(hass, ssh_device_id="device-1", timekpra_path="/usr/bin/timekpra")

    users = await adapter.async_list_users()
    assert users == ["alice", "bob"]


@pytest.mark.asyncio
async def test_async_list_users_falls_back_to_stderr() -> None:
    """User listing should parse stderr when stdout is empty."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "",
                        "stderr": "3 users in total:\nemmanuel\nhadrien\njosephine",
                        "code": 0,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(
        hass,
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    users = await adapter.async_list_users()
    assert users == ["emmanuel", "hadrien", "josephine"]


@pytest.mark.asyncio
async def test_async_list_users_parses_bullets_and_bytes_repr() -> None:
    """User listing should support additional textual wrappers."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "- emmanuel\nb'hadrien'\n* josephine\n",
                        "stderr": "",
                        "code": 0,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(
        hass,
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    users = await adapter.async_list_users()
    assert users == ["emmanuel", "hadrien", "josephine"]


@pytest.mark.asyncio
async def test_async_list_users_parses_literal_list_output() -> None:
    """User listing should parse when output is a serialized list."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "['3 users in total:', 'emmanuel', 'hadrien', 'josephine']",
                        "stderr": "",
                        "code": 0,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(
        hass,
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    users = await adapter.async_list_users()
    assert users == ["emmanuel", "hadrien", "josephine"]


@pytest.mark.asyncio
async def test_async_list_users_unparsable_output_raises_parse_error() -> None:
    """Non-empty non-user output should produce detailed parse error."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "Users total: 2\ninvalid user",
                        "stderr": "",
                        "code": 0,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(
        hass,
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    with pytest.raises(TimekprParseError):
        await adapter.async_list_users()


@pytest.mark.asyncio
async def test_sudo_error_is_mapped() -> None:
    """Sudo-related failures should raise dedicated error type."""
    hass = DummyHass(
        services=DummyServices(
            response={
                "results": [
                    {
                        "success": True,
                        "command": "cmd",
                        "stdout": "",
                        "stderr": "sudo: a password is required",
                        "code": 1,
                    }
                ]
            }
        )
    )
    adapter = TimekprCommandAdapter(hass, ssh_device_id="device-1", timekpra_path="/usr/bin/timekpra")

    with pytest.raises(TimekprSudoRequiredError):
        await adapter.async_validate_sudo()


@pytest.mark.asyncio
async def test_fetch_user_state_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Adapter should parse userinfo output into structured state."""
    adapter = TimekprCommandAdapter(
        hass=DummyHass(services=DummyServices(response={})),
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    stdout = "\n".join(
        [
            "ALLOWED_WEEKDAYS: 1;2;3;4;5;6;7",
            "LIMITS_PER_WEEKDAYS: 3600;7200;7200;7200;7200;10800;10800",
            "ALLOWED_HOURS_1: 9;10;11[00-30]",
            "ALLOWED_HOURS_2: 8;9;10",
            "ALLOWED_HOURS_3: 8;9;10",
            "ALLOWED_HOURS_4: 8;9;10",
            "ALLOWED_HOURS_5: 8;9;10",
            "ALLOWED_HOURS_6: 10;11",
            "ALLOWED_HOURS_7: 10;11",
            "ACTUAL_TIME_LEFT_DAY: 1800",
            "LOCKOUT_TYPE: lock",
        ]
    )

    async def _fake_run(*args: str) -> CommandOutput:
        return CommandOutput(command="x", stdout=stdout, stderr="", code=0)

    monkeypatch.setattr(adapter, "_async_run_timekpra", _fake_run)

    state = await adapter.async_fetch_user_state("alice")

    assert state.username == "alice"
    assert state.limits_per_weekday_seconds[1] == 3600
    assert state.limits_per_weekday_seconds[6] == 10800
    assert state.windows_per_weekday[1] == "09:00-11:30"
    assert state.actual_time_left_day_seconds == 1800
    assert state.lockout_type == "lock"


@pytest.mark.asyncio
async def test_fetch_user_state_uses_stderr_when_stdout_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User state parsing should fall back to stderr channel."""
    adapter = TimekprCommandAdapter(
        hass=DummyHass(services=DummyServices(response={})),
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    stderr = "\n".join(
        [
            "ALLOWED_WEEKDAYS: 1;2;3;4;5;6;7",
            "LIMITS_PER_WEEKDAYS: 3600;3600;3600;3600;3600;3600;3600",
            "ALLOWED_HOURS_1: 9;10",
            "ALLOWED_HOURS_2: 9;10",
            "ALLOWED_HOURS_3: 9;10",
            "ALLOWED_HOURS_4: 9;10",
            "ALLOWED_HOURS_5: 9;10",
            "ALLOWED_HOURS_6: 9;10",
            "ALLOWED_HOURS_7: 9;10",
            "TIME_LEFT_DAY: 1200",
            "LOCKOUT_TYPE: none",
        ]
    )

    async def _fake_run(*args: str) -> CommandOutput:
        return CommandOutput(command="x", stdout="", stderr=stderr, code=0)

    monkeypatch.setattr(adapter, "_async_run_timekpra", _fake_run)

    state = await adapter.async_fetch_user_state("alice")

    assert state.username == "alice"
    assert state.actual_time_left_day_seconds == 1200


@pytest.mark.asyncio
async def test_fetch_user_state_parses_literal_list_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User state parsing should support serialized list output."""
    adapter = TimekprCommandAdapter(
        hass=DummyHass(services=DummyServices(response={})),
        ssh_device_id="device-1",
        timekpra_path="/usr/bin/timekpra",
    )

    stdout = (
        "['ALLOWED_WEEKDAYS: 1;2;3;4;5;6;7',"
        " 'LIMITS_PER_WEEKDAYS: 3600;3600;3600;3600;3600;3600;3600',"
        " 'ALLOWED_HOURS_1: 9;10',"
        " 'ALLOWED_HOURS_2: 9;10',"
        " 'ALLOWED_HOURS_3: 9;10',"
        " 'ALLOWED_HOURS_4: 9;10',"
        " 'ALLOWED_HOURS_5: 9;10',"
        " 'ALLOWED_HOURS_6: 9;10',"
        " 'ALLOWED_HOURS_7: 9;10',"
        " 'TIME_LEFT_DAY: 1200',"
        " 'LOCKOUT_TYPE: none']"
    )

    async def _fake_run(*args: str) -> CommandOutput:
        return CommandOutput(command="x", stdout=stdout, stderr="", code=0)

    monkeypatch.setattr(adapter, "_async_run_timekpra", _fake_run)

    state = await adapter.async_fetch_user_state("alice")

    assert state.username == "alice"
    assert state.actual_time_left_day_seconds == 1200
