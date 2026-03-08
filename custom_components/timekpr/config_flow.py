"""Config flow for the timekpr integration."""

from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_NAME,
    CONF_PASSWORD,
    CONF_PORT,
    CONF_USERNAME,
)
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult, UnknownHandler
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .adapter import TimekprCommandAdapter, TimekprError, TimekprSudoRequiredError
from .const import (
    CONF_SSH_DEVICE_ID,
    CONF_SSH_ENTRY_ID,
    CONF_SSH_KEY,
    CONF_SSH_KEY_PASSPHRASE,
    CONF_SSH_KEY_PATH,
    CONF_TIMEKPRA_PATH,
    CONF_UNLOCK_GRACE_MINUTES,
    CONF_USERS,
    DEFAULT_TIMEKPRA_PATH,
    DEFAULT_UNLOCK_GRACE_MINUTES,
    DOMAIN,
    SSH_CONF_ADD_HOST_KEYS,
    SSH_CONF_DEFAULT_COMMANDS,
    SSH_CONF_HOST_KEYS_FILENAME,
    SSH_CONF_INVOKE_SHELL,
    SSH_CONF_KEY_FILENAME,
    SSH_CONF_LOAD_SYSTEM_HOST_KEYS,
)

SSH_DOMAIN = "ssh"
CONF_MAC = "mac"


def _managed_users_selector(users: list[str]) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            mode=SelectSelectorMode.LIST,
            multiple=True,
            options=[SelectOptionDict(value=user, label=user) for user in users],
        )
    )


class TimekprConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for timekpr."""

    VERSION = 1
    MINOR_VERSION = 0

    _data: dict[str, Any]
    _available_users: list[str]

    def __init__(self) -> None:
        self._data = {}
        self._available_users = []

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "TimekprOptionsFlow":
        """Create options flow."""
        return TimekprOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Collect SSH and timekpr connection details."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._data = dict(user_input)
            host = user_input[CONF_HOST]
            port = int(user_input[CONF_PORT])
            username = user_input[CONF_USERNAME]
            unique = f"{host}:{port}:{username}"

            await self.async_set_unique_id(unique)
            self._abort_if_unique_id_configured()

            try:
                ssh_entry_id = await self._async_ensure_ssh_entry(user_input)
                ssh_device_id = self._get_ssh_device_id(ssh_entry_id)

                adapter = TimekprCommandAdapter(
                    self.hass,
                    ssh_device_id=ssh_device_id,
                    timekpra_path=user_input[CONF_TIMEKPRA_PATH],
                )
                await adapter.async_validate_sudo()

                users = await adapter.async_list_users()
                if not users:
                    errors["base"] = "no_users_found"
                else:
                    self._available_users = users
                    self._data[CONF_SSH_ENTRY_ID] = ssh_entry_id
                    self._data[CONF_SSH_DEVICE_ID] = ssh_device_id
                    return await self.async_step_select_users()

            except TimekprSudoRequiredError:
                errors["base"] = "sudo_password_required"
            except MissingSSHIntegrationError:
                errors["base"] = "missing_ssh_integration"
            except TimekprError:
                errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "unknown"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._data.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=self._data.get(CONF_PORT, 22)): int,
                vol.Required(CONF_USERNAME, default=self._data.get(CONF_USERNAME, "")): str,
                vol.Required(
                    CONF_SSH_KEY,
                    default=self._data.get(CONF_SSH_KEY, ""),
                ): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.TEXT, multiline=True)
                ),
                vol.Optional(
                    CONF_SSH_KEY_PASSPHRASE,
                    default=self._data.get(CONF_SSH_KEY_PASSPHRASE, ""),
                ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
                vol.Required(
                    CONF_TIMEKPRA_PATH,
                    default=self._data.get(CONF_TIMEKPRA_PATH, DEFAULT_TIMEKPRA_PATH),
                ): str,
                vol.Required(
                    CONF_UNLOCK_GRACE_MINUTES,
                    default=self._data.get(
                        CONF_UNLOCK_GRACE_MINUTES,
                        DEFAULT_UNLOCK_GRACE_MINUTES,
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=24 * 60,
                        mode=NumberSelectorMode.BOX,
                        step=1,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_select_users(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Select which users to manage."""
        errors: dict[str, str] = {}

        if user_input is not None:
            selected_users = list(user_input.get(CONF_USERS, []))
            if not selected_users:
                errors[CONF_USERS] = "no_users_selected"
            else:
                self._data[CONF_USERS] = sorted(set(selected_users))
                title = f"timekpr {self._data[CONF_HOST]}"
                return self.async_create_entry(
                    title=title,
                    data={
                        CONF_HOST: self._data[CONF_HOST],
                        CONF_PORT: self._data[CONF_PORT],
                        CONF_USERNAME: self._data[CONF_USERNAME],
                        CONF_SSH_ENTRY_ID: self._data[CONF_SSH_ENTRY_ID],
                        CONF_SSH_DEVICE_ID: self._data[CONF_SSH_DEVICE_ID],
                        CONF_USERS: self._data[CONF_USERS],
                        CONF_TIMEKPRA_PATH: self._data[CONF_TIMEKPRA_PATH],
                        CONF_UNLOCK_GRACE_MINUTES: int(
                            self._data[CONF_UNLOCK_GRACE_MINUTES]
                        ),
                        CONF_SSH_KEY_PATH: self._data.get(CONF_SSH_KEY_PATH, ""),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERS,
                    default=self._data.get(CONF_USERS, self._available_users),
                ): _managed_users_selector(self._available_users)
            }
        )

        return self.async_show_form(
            step_id="select_users",
            data_schema=schema,
            errors=errors,
        )

    async def _async_ensure_ssh_entry(self, data: Mapping[str, Any]) -> str:
        """Create or reuse a matching SSH config entry."""
        key_path = await self.hass.async_add_executor_job(
            self._write_private_key,
            str(data[CONF_HOST]),
            int(data[CONF_PORT]),
            str(data[CONF_USERNAME]),
            str(data[CONF_SSH_KEY]),
        )
        self._data[CONF_SSH_KEY_PATH] = key_path

        existing = self._find_matching_ssh_entry(
            host=str(data[CONF_HOST]),
            port=int(data[CONF_PORT]),
            username=str(data[CONF_USERNAME]),
            key_path=key_path,
        )
        if existing is not None:
            return existing.entry_id

        ssh_input: dict[str, Any] = {
            CONF_HOST: str(data[CONF_HOST]),
            CONF_PORT: int(data[CONF_PORT]),
            CONF_USERNAME: str(data[CONF_USERNAME]),
            SSH_CONF_DEFAULT_COMMANDS: "none",
            SSH_CONF_KEY_FILENAME: key_path,
            SSH_CONF_HOST_KEYS_FILENAME: self.hass.config.path("known_hosts"),
            SSH_CONF_ADD_HOST_KEYS: True,
            SSH_CONF_LOAD_SYSTEM_HOST_KEYS: True,
            SSH_CONF_INVOKE_SHELL: False,
        }

        passphrase = str(data.get(CONF_SSH_KEY_PASSPHRASE, "")).strip()
        if passphrase:
            ssh_input[CONF_PASSWORD] = passphrase

        try:
            result = await self.hass.config_entries.flow.async_init(
                SSH_DOMAIN,
                context={"source": config_entries.SOURCE_USER},
                data=ssh_input,
            )
        except UnknownHandler as exc:
            raise MissingSSHIntegrationError(
                "Required integration 'ssh' is not installed"
            ) from exc

        return await self._finish_ssh_flow(result, data)

    async def _finish_ssh_flow(
        self,
        result: FlowResult,
        data: Mapping[str, Any],
    ) -> str:
        """Continue SSH flow until entry is created or reused."""
        host = str(data[CONF_HOST])
        port = int(data[CONF_PORT])
        username = str(data[CONF_USERNAME])

        while True:
            if result["type"] == "create_entry":
                created_entry = result["result"]
                return created_entry.entry_id

            if result["type"] == "abort":
                reason = result.get("reason")
                if reason in {"unknown_handler", "invalid_handler", "unknown"}:
                    raise MissingSSHIntegrationError(
                        "Required integration 'ssh' is not installed"
                    )
                existing = self._find_matching_ssh_entry(
                    host=host,
                    port=port,
                    username=username,
                    key_path=self._data[CONF_SSH_KEY_PATH],
                )
                if existing is not None:
                    return existing.entry_id
                raise TimekprError("SSH flow aborted before creating entry")

            if result["type"] != "form":
                raise TimekprError("Unexpected SSH flow result")

            step_id = result.get("step_id")
            flow_id = result["flow_id"]
            if step_id == "mac_address":
                mac = self._build_synthetic_mac(host, port, username)
                result = await self.hass.config_entries.flow.async_configure(
                    flow_id,
                    {CONF_MAC: mac},
                )
                continue

            if step_id == "name":
                result = await self.hass.config_entries.flow.async_configure(
                    flow_id,
                    {CONF_NAME: f"{username}@{host}"},
                )
                continue

            if step_id == "user":
                # Validation failed inside ssh flow despite previous checks.
                raise TimekprError("SSH flow validation failed")

            raise TimekprError(f"Unhandled SSH flow step '{step_id}'")

    def _find_matching_ssh_entry(
        self,
        *,
        host: str,
        port: int,
        username: str,
        key_path: str,
    ) -> ConfigEntry | None:
        """Find an existing SSH config entry matching our connection details."""
        for entry in self.hass.config_entries.async_entries(SSH_DOMAIN):
            if (
                str(entry.data.get(CONF_HOST)) == host
                and int(entry.data.get(CONF_PORT, 0)) == port
                and str(entry.data.get(CONF_USERNAME, "")) == username
                and str(entry.data.get(SSH_CONF_KEY_FILENAME, "")) == key_path
            ):
                return entry
        return None

    def _get_ssh_device_id(self, ssh_entry_id: str) -> str:
        """Resolve SSH config entry to a device ID for service targeting."""
        dev_reg = dr.async_get(self.hass)
        devices = dr.async_entries_for_config_entry(dev_reg, ssh_entry_id)
        if not devices:
            raise TimekprError("No device found for linked SSH entry")
        return devices[0].id

    def _write_private_key(
        self,
        host: str,
        port: int,
        username: str,
        key_contents: str,
    ) -> str:
        """Write private key to HA config storage and return absolute path."""
        if not key_contents.strip():
            raise TimekprError("SSH key cannot be empty")

        base = Path(self.hass.config.path(".storage", DOMAIN, "keys"))
        base.mkdir(parents=True, exist_ok=True)

        digest = sha256(f"{host}:{port}:{username}".encode()).hexdigest()[:16]
        key_path = base / f"{username}_{host.replace('.', '_')}_{digest}.pem"

        text = key_contents if key_contents.endswith("\n") else f"{key_contents}\n"
        key_path.write_text(text, encoding="utf-8")
        key_path.chmod(0o600)

        return str(key_path)

    @staticmethod
    def _build_synthetic_mac(host: str, port: int, username: str) -> str:
        """Build a stable locally-administered MAC for SSH flow fallback."""
        digest = sha256(f"{host}:{port}:{username}".encode()).digest()
        octets = [0x02, digest[0], digest[1], digest[2], digest[3], digest[4]]
        return ":".join(f"{value:02x}" for value in octets)


class MissingSSHIntegrationError(TimekprError):
    """Raised when the ssh integration is not installed or not loadable."""


class TimekprOptionsFlow(config_entries.OptionsFlow):
    """Handle options for timekpr integration."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage users and runtime options."""
        errors: dict[str, str] = {}

        merged = {**self.config_entry.data, **self.config_entry.options}
        ssh_device_id = merged.get(CONF_SSH_DEVICE_ID)
        timekpra_path = str(merged.get(CONF_TIMEKPRA_PATH, DEFAULT_TIMEKPRA_PATH))

        available_users: list[str]
        if ssh_device_id:
            try:
                adapter = TimekprCommandAdapter(
                    self.hass,
                    ssh_device_id=ssh_device_id,
                    timekpra_path=timekpra_path,
                )
                await adapter.async_validate_sudo()
                available_users = await adapter.async_list_users()
            except Exception:
                available_users = list(merged.get(CONF_USERS, []))
                errors["base"] = "cannot_connect"
        else:
            available_users = list(merged.get(CONF_USERS, []))
            errors["base"] = "cannot_connect"

        available_users = sorted(set(available_users))

        if user_input is not None:
            selected_users = list(user_input.get(CONF_USERS, []))
            if not selected_users:
                errors[CONF_USERS] = "no_users_selected"
            else:
                return self.async_create_entry(
                    title="",
                    data={
                        CONF_USERS: sorted(set(selected_users)),
                        CONF_TIMEKPRA_PATH: user_input[CONF_TIMEKPRA_PATH],
                        CONF_UNLOCK_GRACE_MINUTES: int(
                            user_input[CONF_UNLOCK_GRACE_MINUTES]
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_USERS,
                    default=merged.get(CONF_USERS, available_users),
                ): _managed_users_selector(available_users),
                vol.Required(
                    CONF_TIMEKPRA_PATH,
                    default=timekpra_path,
                ): str,
                vol.Required(
                    CONF_UNLOCK_GRACE_MINUTES,
                    default=int(
                        merged.get(
                            CONF_UNLOCK_GRACE_MINUTES,
                            DEFAULT_UNLOCK_GRACE_MINUTES,
                        )
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(
                        min=1,
                        max=24 * 60,
                        mode=NumberSelectorMode.BOX,
                        step=1,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
