"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def own_settings(tmp_path, monkeypatch):
    """Give every test a settings file of its own, which does not exist yet.

    Without this a test would read the developer's real ~/.pyhood/settings.json,
    and one that changes the confirmation setting would write to it.
    """
    path = tmp_path / "settings.json"
    monkeypatch.setenv("PYHOOD_SETTINGS", str(path))
    return path
