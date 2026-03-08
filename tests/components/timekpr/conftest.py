"""Pytest fixtures for timekpr tests."""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations_if_available(request: pytest.FixtureRequest):
    """Enable custom integrations fixture when plugin is installed."""
    try:
        request.getfixturevalue("enable_custom_integrations")
    except Exception:
        pass
    yield
