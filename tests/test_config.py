from __future__ import annotations

from pathlib import Path

import pytest

from ukei.config import ConfigurationError, Settings


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "UKEI_DATABASE_PATH",
        "UKEI_LOG_LEVEL",
        "UKEI_LOG_FORMAT",
        "UKEI_HTTP_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    settings = Settings.from_env()
    assert settings.database_path == Path(".ukei/catalogue.sqlite3")
    assert settings.log_level == "INFO"
    assert settings.http_timeout_seconds == 20


def test_settings_environment_and_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("UKEI_DATABASE_PATH", "ignored.sqlite3")
    monkeypatch.setenv("UKEI_LOG_LEVEL", "debug")
    monkeypatch.setenv("UKEI_LOG_FORMAT", "JSON")
    monkeypatch.setenv("UKEI_HTTP_TIMEOUT_SECONDS", "3.5")
    settings = Settings.from_env(database_path="selected.sqlite3")
    assert settings.database_path == Path("selected.sqlite3")
    assert settings.log_level == "DEBUG"
    assert settings.log_format == "json"
    assert settings.http_timeout_seconds == 3.5


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("UKEI_LOG_LEVEL", "LOUD"),
        ("UKEI_LOG_FORMAT", "xml"),
        ("UKEI_HTTP_TIMEOUT_SECONDS", "never"),
        ("UKEI_HTTP_TIMEOUT_SECONDS", "0"),
    ],
)
def test_invalid_settings(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError):
        Settings.from_env()
