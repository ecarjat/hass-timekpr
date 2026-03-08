"""Data models for the timekpr integration."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class TimekprUserState:
    """State collected for one managed user."""

    username: str
    limits_per_weekday_seconds: dict[int, int] = field(default_factory=dict)
    windows_per_weekday: dict[int, str] = field(default_factory=dict)
    raw_allowed_hours_per_weekday: dict[int, str] = field(default_factory=dict)
    allowed_weekdays: set[int] = field(default_factory=set)
    actual_time_left_day_seconds: int | None = None
    lockout_type: str | None = None
    raw: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TimekprRuntimeData:
    """Runtime data attached to each config entry."""

    coordinator: "TimekprCoordinator"


# Forward declaration for typing
class TimekprCoordinator:  # pragma: no cover - only for typing
    pass
