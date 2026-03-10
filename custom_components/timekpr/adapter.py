"""Timekpr command adapter executed through the SSH integration."""

from __future__ import annotations

from dataclasses import dataclass
import ast
import logging
import re
import shlex
from typing import Any

from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    SSH_DOMAIN,
    SSH_SERVICE_EXECUTE_COMMAND,
    TIMEKPR_CMD_SET_ALLOWED_DAYS,
    TIMEKPR_CMD_SET_ALLOWED_HOURS,
    TIMEKPR_CMD_SET_TIME_LEFT,
    TIMEKPR_CMD_SET_TIME_LIMITS,
    TIMEKPR_CMD_USERINFO,
    TIMEKPR_CMD_USERLIST,
)
from .models import TimekprUserState

_USER_RE = re.compile(r"^[a-z_][a-z0-9_.-]*\$?$", re.IGNORECASE)
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_WINDOWS_RE = re.compile(
    r"^((?:[01]\d|2[0-3]):[0-5]\d)-(?:([01]\d|2[0-3]|24):([0-5]\d))$"
)
_LOGGER = logging.getLogger(__name__)


class TimekprError(HomeAssistantError):
    """Base integration error."""


class TimekprSudoRequiredError(TimekprError):
    """Raised when sudo requires password or TTY."""


class TimekprSSHError(TimekprError):
    """Raised when SSH integration call fails."""


class TimekprParseError(TimekprError):
    """Raised when command output cannot be parsed."""


class TimekprCommandExecutionError(TimekprError):
    """Raised when timekpra command fails."""


class TimekprNoUsersError(TimekprError):
    """Raised when timekpra returns no controllable users."""


@dataclass(slots=True)
class CommandOutput:
    """Normalized command output from ssh.execute_command."""

    command: str
    stdout: str
    stderr: str
    code: int


class TimekprCommandAdapter:
    """Execute and parse timekpra commands via ssh.execute_command."""

    def __init__(
        self,
        hass: HomeAssistant,
        ssh_device_id: str,
        timekpra_path: str,
    ) -> None:
        self._hass = hass
        self._ssh_device_id = ssh_device_id
        self._timekpra_path = timekpra_path

    async def async_validate_sudo(self) -> None:
        """Validate passwordless sudo for timekpra."""
        await self._async_run_raw(f"LC_ALL=C sudo -n {shlex.quote(self._timekpra_path)} --help")

    async def async_list_users(self) -> list[str]:
        """Return list of controllable users from timekpra."""
        output = await self._async_run_timekpra(TIMEKPR_CMD_USERLIST)
        raw_text = self._pick_structured_output(output)

        users = self._extract_usernames(raw_text)

        if not users:
            lower = raw_text.lower()
            if re.search(r"\b0\s+users?\b", lower) or "no users" in lower:
                preview = raw_text.strip().replace("\n", "\\n")
                _LOGGER.error(
                    "timekpra --userlist returned zero users for device=%s (output=%r)",
                    self._ssh_device_id,
                    preview[:400],
                )
                raise TimekprNoUsersError(preview[:300] or "empty output")
            _LOGGER.warning(
                "timekpra --userlist returned no parsable users for device=%s (stdout=%r, stderr=%r)",
                self._ssh_device_id,
                output.stdout[:400],
                output.stderr[:400],
            )
            preview = raw_text.strip().replace("\n", "\\n")
            raise TimekprParseError(
                f"No usernames parsed from --userlist output: {preview[:300]}"
            )
        return sorted(set(users))

    async def async_fetch_user_state(self, user: str) -> TimekprUserState:
        """Fetch user info and normalize it for entities."""
        output = await self._async_run_timekpra(TIMEKPR_CMD_USERINFO, user)
        info = self._parse_userinfo(self._pick_structured_output(output))

        state = TimekprUserState(username=user, raw=info)

        state.allowed_weekdays = self._parse_int_set(info.get("ALLOWED_WEEKDAYS", ""))
        if not state.allowed_weekdays:
            state.allowed_weekdays = {1, 2, 3, 4, 5, 6, 7}

        limits = self._parse_int_list(info.get("LIMITS_PER_WEEKDAYS", ""), expected=7)
        if limits:
            state.limits_per_weekday_seconds = {
                index: value for index, value in enumerate(limits, start=1)
            }
        else:
            state.limits_per_weekday_seconds = {index: 0 for index in range(1, 8)}

        for day in range(1, 8):
            key = f"ALLOWED_HOURS_{day}"
            spec = info.get(key, "")
            state.raw_allowed_hours_per_weekday[day] = spec
            windows = self.hour_spec_to_windows(spec)
            state.windows_per_weekday[day] = windows if day in state.allowed_weekdays else ""

        for key in ("ACTUAL_TIME_LEFT_DAY", "TIME_LEFT_DAY"):
            if key in info:
                try:
                    state.actual_time_left_day_seconds = int(info[key])
                except ValueError:
                    state.actual_time_left_day_seconds = None
                break

        state.lockout_type = info.get("LOCKOUT_TYPE")
        return state

    async def async_set_daily_limit(self, user: str, weekday_number: int, minutes: int) -> None:
        """Set per-weekday daily allowance in minutes."""
        if weekday_number < 1 or weekday_number > 7:
            raise TimekprParseError("Invalid weekday number")

        state = await self.async_fetch_user_state(user)
        limits = [state.limits_per_weekday_seconds.get(day, 0) for day in range(1, 8)]
        limits[weekday_number - 1] = minutes * 60

        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_TIME_LIMITS,
            user,
            ";".join(str(value) for value in limits),
        )

    async def async_set_allowed_windows(
        self,
        user: str,
        weekday_number: int,
        windows: str,
    ) -> None:
        """Set allowed usage windows for a weekday."""
        if weekday_number < 1 or weekday_number > 7:
            raise TimekprParseError("Invalid weekday number")

        hour_spec = self.windows_to_hour_spec(windows)

        state = await self.async_fetch_user_state(user)
        allowed_days = set(state.allowed_weekdays)
        allowed_days.add(weekday_number)

        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_ALLOWED_DAYS,
            user,
            ";".join(str(day) for day in sorted(allowed_days)),
        )
        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_ALLOWED_HOURS,
            user,
            str(weekday_number),
            hour_spec,
        )

    async def async_add_time(self, user: str, minutes: int) -> None:
        """Add time for today in minutes."""
        if minutes <= 0:
            raise TimekprParseError("Minutes to add must be greater than zero")
        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_TIME_LEFT,
            user,
            "+",
            str(minutes * 60),
        )

    async def async_lock_user(self, user: str) -> None:
        """Force lock by exhausting all remaining time for the day."""
        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_TIME_LEFT,
            user,
            "-",
            str(24 * 60 * 60),
        )

    async def async_unlock_user(self, user: str, restore_seconds: int) -> None:
        """Unlock by setting a positive remaining time balance for today."""
        seconds = max(1, int(restore_seconds))
        await self._async_run_timekpra(
            TIMEKPR_CMD_SET_TIME_LEFT,
            user,
            "=",
            str(seconds),
        )

    async def _async_run_timekpra(self, *args: str) -> CommandOutput:
        quoted = " ".join(shlex.quote(arg) for arg in args)
        command = f"LC_ALL=C sudo -n {shlex.quote(self._timekpra_path)} {quoted}".strip()
        return await self._async_run_raw(command)

    async def _async_run_raw(self, command: str) -> CommandOutput:
        """Run a raw command through ssh.execute_command."""
        service_data: dict[str, Any] = {
            ATTR_DEVICE_ID: [self._ssh_device_id],
            "command": command,
        }

        _LOGGER.debug(
            "Executing ssh command for timekpr (device=%s): %s",
            self._ssh_device_id,
            command,
        )
        try:
            response = await self._hass.services.async_call(
                SSH_DOMAIN,
                SSH_SERVICE_EXECUTE_COMMAND,
                service_data,
                blocking=True,
                return_response=True,
            )
        except Exception as exc:
            _LOGGER.exception(
                "ssh.execute_command call failed for device=%s command=%s",
                self._ssh_device_id,
                command,
            )
            raise TimekprSSHError(str(exc)) from exc

        if not isinstance(response, dict) or "results" not in response:
            _LOGGER.error(
                "Unexpected ssh.execute_command response for device=%s command=%s: %r",
                self._ssh_device_id,
                command,
                response,
            )
            raise TimekprSSHError("Unexpected response from ssh.execute_command")

        results = response.get("results")
        if not isinstance(results, list) or not results:
            raise TimekprSSHError("Empty response from ssh.execute_command")

        result = results[0]
        if not isinstance(result, dict):
            raise TimekprSSHError("Malformed response from ssh.execute_command")

        if not result.get("success", False):
            error = str(result.get("error", "SSH command failed"))
            _LOGGER.warning(
                "ssh.execute_command reported failure for device=%s command=%s error=%s",
                self._ssh_device_id,
                command,
                error,
            )
            lowered = error.lower()
            if "sudo" in lowered or "password" in lowered or "tty" in lowered:
                raise TimekprSudoRequiredError(error)
            raise TimekprSSHError(error)

        output = CommandOutput(
            command=str(result.get("command", command)),
            stdout=str(result.get("stdout", "")),
            stderr=str(result.get("stderr", "")),
            code=int(result.get("code", 0)),
        )

        if output.code != 0:
            lowered = f"{output.stderr}\n{output.stdout}".lower()
            _LOGGER.warning(
                "timekpra command failed for device=%s code=%s stderr=%s stdout=%s",
                self._ssh_device_id,
                output.code,
                output.stderr,
                output.stdout,
            )
            if "sudo" in lowered or "password" in lowered or "tty" in lowered:
                raise TimekprSudoRequiredError(
                    output.stderr or output.stdout or "sudo requires password"
                )
            raise TimekprCommandExecutionError(
                output.stderr or output.stdout or f"timekpra exited with code {output.code}"
            )

        return output

    @staticmethod
    def _parse_userinfo(text: str) -> dict[str, str]:
        info: dict[str, str] = {}
        for line in text.splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if key:
                info[key] = value
        if not info:
            raise TimekprParseError("Unable to parse user info output")
        return info

    @staticmethod
    def _pick_structured_output(output: CommandOutput) -> str:
        """Pick output channel that contains command result text.

        Some SSH/server combinations emit command output to stderr even when exit
        code is 0; prefer stdout when present, otherwise use stderr.
        """
        if output.stdout.strip():
            return output.stdout
        return output.stderr

    @staticmethod
    def _extract_usernames(raw_text: str) -> list[str]:
        """Extract usernames from raw `--userlist` output."""
        users: set[str] = set()
        cleaned_text = _ANSI_ESCAPE_RE.sub("", raw_text.replace("\r", "\n"))
        for line in cleaned_text.splitlines():
            candidate = line.strip()
            if not candidate:
                continue

            if (
                len(candidate) >= 3
                and candidate[0:2] in {"b'", 'b"'}
                and candidate[-1] == candidate[1]
            ):
                try:
                    parsed = ast.literal_eval(candidate)
                except (SyntaxError, ValueError):
                    parsed = None
                if isinstance(parsed, (bytes, bytearray)):
                    candidate = parsed.decode(errors="ignore").strip()
                elif isinstance(parsed, str):
                    candidate = parsed.strip()

            if candidate.startswith(("- ", "* ")):
                candidate = candidate[2:].strip()

            if _USER_RE.fullmatch(candidate):
                users.add(candidate)
                continue

            if "," in candidate:
                comma_parts = [part.strip() for part in candidate.split(",") if part.strip()]
                if comma_parts and all(_USER_RE.fullmatch(part) for part in comma_parts):
                    users.update(comma_parts)

        return sorted(users)

    @staticmethod
    def _parse_int_list(raw: str, expected: int | None = None) -> list[int]:
        if not raw:
            return []
        parts = [part.strip() for part in raw.split(";") if part.strip() != ""]
        values: list[int] = []
        for part in parts:
            try:
                values.append(int(part))
            except ValueError:
                return []
        if expected is not None and len(values) != expected:
            return []
        return values

    @staticmethod
    def _parse_int_set(raw: str) -> set[int]:
        if not raw:
            return set()
        result: set[int] = set()
        for part in raw.split(";"):
            part = part.strip()
            if not part:
                continue
            try:
                day = int(part)
            except ValueError:
                continue
            if 1 <= day <= 7:
                result.add(day)
        return result

    @staticmethod
    def windows_to_hour_spec(windows: str) -> str:
        """Convert `HH:MM-HH:MM[,HH:MM-HH:MM]` to timekpra hour spec."""
        windows = windows.strip()
        if not windows:
            raise TimekprParseError("Windows value cannot be empty")

        hour_ranges: dict[int, tuple[int, int]] = {}

        for interval in [part.strip() for part in windows.split(",") if part.strip()]:
            match = _WINDOWS_RE.fullmatch(interval)
            if match is None:
                raise TimekprParseError(
                    "Windows must use HH:MM-HH:MM format, comma-separated"
                )

            start_text, end_hour_text, end_minute_text = interval.split("-")[0], match.group(2), match.group(3)
            start_hour, start_minute = map(int, start_text.split(":"))
            end_hour = int(end_hour_text)
            end_minute = int(end_minute_text)

            if end_hour == 24 and end_minute != 0:
                raise TimekprParseError("24:00 is the only valid 24-hour end time")

            start_total = start_hour * 60 + start_minute
            end_total = end_hour * 60 + end_minute
            if end_total <= start_total:
                raise TimekprParseError("Window end time must be after start time")

            cursor = start_total
            while cursor < end_total:
                hour = cursor // 60
                next_hour = min((hour + 1) * 60, end_total)
                start = cursor % 60
                end = next_hour % 60
                end = 60 if end == 0 and next_hour > cursor else end

                existing = hour_ranges.get(hour)
                current = (start, end)

                if existing is None:
                    hour_ranges[hour] = current
                else:
                    # timekpra supports one range per hour key; merge only if contiguous/overlapping.
                    merged_start = min(existing[0], current[0])
                    merged_end = max(existing[1], current[1])
                    if not (
                        current[0] <= existing[1] and current[1] >= existing[0]
                    ) and not (
                        current[0] == existing[1] or existing[0] == current[1]
                    ):
                        raise TimekprParseError(
                            "Disjoint windows inside the same hour are not supported"
                        )
                    hour_ranges[hour] = (merged_start, merged_end)

                cursor = next_hour

        if not hour_ranges:
            raise TimekprParseError("No valid windows provided")

        tokens: list[str] = []
        for hour in sorted(hour_ranges):
            start, end = hour_ranges[hour]
            if start == 0 and end == 60:
                tokens.append(str(hour))
            else:
                tokens.append(f"{hour}[{start:02d}-{end:02d}]")

        return ";".join(tokens)

    @staticmethod
    def hour_spec_to_windows(spec: str) -> str:
        """Convert timekpra `ALLOWED_HOURS_*` to `HH:MM-HH:MM[,..]`."""
        spec = spec.strip()
        if not spec:
            return ""

        ranges: list[tuple[int, int]] = []
        for token in [part.strip() for part in spec.split(";") if part.strip()]:
            if token.startswith("!"):
                # unaccounted hour markers are ignored in allowed windows display
                continue

            if "[" in token:
                match = re.fullmatch(r"(\d{1,2})\[(\d{1,2})-(\d{1,2})\]", token)
                if match is None:
                    continue
                hour = int(match.group(1))
                start_minute = int(match.group(2))
                end_minute = int(match.group(3))
            else:
                if not token.isdigit():
                    continue
                hour = int(token)
                start_minute = 0
                end_minute = 60

            if hour < 0 or hour > 23:
                continue
            if start_minute < 0 or start_minute > 59:
                continue
            if end_minute < 1 or end_minute > 60:
                continue
            if end_minute <= start_minute:
                continue

            start_total = hour * 60 + start_minute
            end_total = hour * 60 + end_minute
            ranges.append((start_total, end_total))

        if not ranges:
            return ""

        ranges.sort()
        merged: list[tuple[int, int]] = []
        for start, end in ranges:
            if not merged or start > merged[-1][1]:
                merged.append((start, end))
            else:
                merged[-1] = (merged[-1][0], max(merged[-1][1], end))

        return ",".join(
            f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"
            for start, end in merged
        )
