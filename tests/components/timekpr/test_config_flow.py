"""Config and options flow tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_USERNAME
import pytest

pytest.importorskip("pytest_homeassistant_custom_component")
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.timekpr.adapter import TimekprNoUsersError, TimekprSudoRequiredError
from custom_components.timekpr.const import (
    CONF_SSH_DEVICE_ID,
    CONF_SSH_ENTRY_ID,
    CONF_SSH_KEY,
    CONF_TIMEKPRA_PATH,
    CONF_UNLOCK_GRACE_MINUTES,
    CONF_USERS,
    DEFAULT_TIMEKPRA_PATH,
    DEFAULT_UNLOCK_GRACE_MINUTES,
    DOMAIN,
)


@pytest.mark.asyncio
async def test_config_flow_success(hass) -> None:
    """Config flow should create entry after user selection."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"

    user_input = {
        CONF_HOST: "192.168.1.20",
        CONF_PORT: 22,
        CONF_USERNAME: "ha_ssh",
        CONF_SSH_KEY: "-----BEGIN PRIVATE KEY-----\nKEY\n-----END PRIVATE KEY-----",
        "ssh_key_passphrase": "",
        CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
        CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
    }

    with (
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._async_ensure_ssh_entry",
            AsyncMock(return_value="ssh-entry-1"),
        ),
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._get_ssh_device_id",
            return_value="device-1",
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_validate_sudo",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_list_users",
            AsyncMock(return_value=["alice", "bob"]),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "select_users"

    result3 = await hass.config_entries.flow.async_configure(
        result2["flow_id"],
        {CONF_USERS: ["alice"]},
    )

    assert result3["type"] == "create_entry"
    assert result3["data"][CONF_USERS] == ["alice"]
    assert result3["data"][CONF_SSH_ENTRY_ID] == "ssh-entry-1"
    assert result3["data"][CONF_SSH_DEVICE_ID] == "device-1"


@pytest.mark.asyncio
async def test_config_flow_sudo_failure(hass) -> None:
    """Config flow should show sudo-specific error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    user_input = {
        CONF_HOST: "192.168.1.20",
        CONF_PORT: 22,
        CONF_USERNAME: "ha_ssh",
        CONF_SSH_KEY: "KEY",
        "ssh_key_passphrase": "",
        CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
        CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
    }

    with (
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._async_ensure_ssh_entry",
            AsyncMock(return_value="ssh-entry-1"),
        ),
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._get_ssh_device_id",
            return_value="device-1",
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_validate_sudo",
            AsyncMock(side_effect=TimekprSudoRequiredError("password required")),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "sudo_password_required"}


@pytest.mark.asyncio
async def test_config_flow_no_users(hass) -> None:
    """Config flow should block if user list is empty."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    user_input = {
        CONF_HOST: "192.168.1.20",
        CONF_PORT: 22,
        CONF_USERNAME: "ha_ssh",
        CONF_SSH_KEY: "KEY",
        "ssh_key_passphrase": "",
        CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
        CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
    }

    with (
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._async_ensure_ssh_entry",
            AsyncMock(return_value="ssh-entry-1"),
        ),
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._get_ssh_device_id",
            return_value="device-1",
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_validate_sudo",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_list_users",
            AsyncMock(return_value=[]),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "no_users_found"}


@pytest.mark.asyncio
async def test_config_flow_no_users_surfaces_details(hass) -> None:
    """Config flow should include no-users details in placeholders."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    user_input = {
        CONF_HOST: "192.168.1.20",
        CONF_PORT: 22,
        CONF_USERNAME: "ha_ssh",
        CONF_SSH_KEY: "KEY",
        "ssh_key_passphrase": "",
        CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
        CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
    }

    with (
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._async_ensure_ssh_entry",
            AsyncMock(return_value="ssh-entry-1"),
        ),
        patch(
            "custom_components.timekpr.config_flow.TimekprConfigFlow._get_ssh_device_id",
            return_value="device-1",
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_validate_sudo",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_list_users",
            AsyncMock(side_effect=TimekprNoUsersError("0 users in total:\\n")),
        ),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            user_input,
        )

    assert result2["type"] == "form"
    assert result2["step_id"] == "user"
    assert result2["errors"] == {"base": "no_users_found"}
    assert result2["description_placeholders"]["details"] == "0 users in total:\n"


@pytest.mark.asyncio
async def test_options_flow_refresh_and_update_users(hass) -> None:
    """Options flow should refresh users and update managed list."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="timekpr host",
        data={
            CONF_HOST: "192.168.1.20",
            CONF_PORT: 22,
            CONF_USERNAME: "ha_ssh",
            CONF_SSH_ENTRY_ID: "ssh-entry-1",
            CONF_SSH_DEVICE_ID: "device-1",
            CONF_USERS: ["alice"],
            CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
            CONF_UNLOCK_GRACE_MINUTES: DEFAULT_UNLOCK_GRACE_MINUTES,
        },
    )
    entry.add_to_hass(hass)

    with (
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_validate_sudo",
            AsyncMock(return_value=None),
        ),
        patch(
            "custom_components.timekpr.adapter.TimekprCommandAdapter.async_list_users",
            AsyncMock(return_value=["alice", "bob"]),
        ),
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result2 = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_USERS: ["alice", "bob"],
            CONF_TIMEKPRA_PATH: DEFAULT_TIMEKPRA_PATH,
            CONF_UNLOCK_GRACE_MINUTES: 20,
        },
    )

    assert result2["type"] == "create_entry"
    assert result2["data"][CONF_USERS] == ["alice", "bob"]
    assert result2["data"][CONF_UNLOCK_GRACE_MINUTES] == 20
