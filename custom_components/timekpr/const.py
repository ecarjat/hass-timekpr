"""Constants for the timekpr integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "timekpr"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.TEXT,
    Platform.BUTTON,
]

CONF_SSH_ENTRY_ID = "ssh_entry_id"
CONF_SSH_DEVICE_ID = "ssh_device_id"
CONF_SSH_KEY = "ssh_key"
CONF_SSH_KEY_PASSPHRASE = "ssh_key_passphrase"
CONF_SSH_KEY_PATH = "ssh_key_path"
CONF_USERS = "users"
CONF_TIMEKPRA_PATH = "timekpra_path"
CONF_UNLOCK_GRACE_MINUTES = "unlock_grace_minutes"

DEFAULT_TIMEKPRA_PATH = "/usr/bin/timekpra"
DEFAULT_SCAN_INTERVAL_SECONDS = 60
DEFAULT_UNLOCK_GRACE_MINUTES = 15

SERVICE_SET_DAILY_LIMIT = "set_daily_limit"
SERVICE_SET_ALLOWED_WINDOWS = "set_allowed_windows"
SERVICE_ADD_TIME = "add_time"
SERVICE_LOCK_USER = "lock_user"
SERVICE_UNLOCK_USER = "unlock_user"
SERVICE_REFRESH_USERS = "refresh_users"

WEEKDAYS: tuple[str, ...] = (
    "mon",
    "tue",
    "wed",
    "thu",
    "fri",
    "sat",
    "sun",
)
WEEKDAY_TO_NUMBER = {day: idx + 1 for idx, day in enumerate(WEEKDAYS)}
NUMBER_TO_WEEKDAY = {idx + 1: day for idx, day in enumerate(WEEKDAYS)}

SSH_DOMAIN = "ssh"
SSH_SERVICE_EXECUTE_COMMAND = "execute_command"

SSH_CONF_KEY_FILENAME = "key_filename"
SSH_CONF_DEFAULT_COMMANDS = "default_commands"
SSH_CONF_ADD_HOST_KEYS = "add_host_keys"
SSH_CONF_LOAD_SYSTEM_HOST_KEYS = "load_system_host_keys"
SSH_CONF_INVOKE_SHELL = "invoke_shell"
SSH_CONF_HOST_KEYS_FILENAME = "host_keys_filename"

TIMEKPR_CMD_USERLIST = "--userlist"
TIMEKPR_CMD_USERINFO = "--userinfo"
TIMEKPR_CMD_SET_ALLOWED_DAYS = "--setalloweddays"
TIMEKPR_CMD_SET_ALLOWED_HOURS = "--setallowedhours"
TIMEKPR_CMD_SET_TIME_LIMITS = "--settimelimits"
TIMEKPR_CMD_SET_TIME_LEFT = "--settimeleft"
