"""Shared test isolation.

The unit suite must behave identically on a developer machine that exports
``SAT_BROWSER_CHANNEL`` (or keeps a local ``.env``) and on a clean CI runner, so
every inherited ``SAT_*`` setting is removed before each test runs.
"""

from __future__ import annotations

import os

import pytest

from sat_tariff import config as config_module


@pytest.fixture(autouse=True)
def isolated_sat_environment(monkeypatch):
    for name in [key for key in os.environ if key.startswith("SAT_")]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(config_module, "_load_optional_dotenv", lambda env_file: {})
    yield
