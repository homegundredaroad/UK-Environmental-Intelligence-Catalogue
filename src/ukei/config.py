"""Runtime configuration sourced from explicit values and environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_LOG_FORMATS = {"text", "json"}


class ConfigurationError(ValueError):
    """Raised when runtime configuration is invalid."""


@dataclass(frozen=True, slots=True)
class Settings:
    """Validated application settings."""

    database_path: Path = Path(".ukei/catalogue.sqlite3")
    log_level: str = "INFO"
    log_format: str = "text"
    http_timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, *, database_path: str | Path | None = None) -> Settings:
        """Build settings from the environment, with an optional CLI database override."""
        path_value = (
            database_path
            if database_path is not None
            else os.getenv("UKEI_DATABASE_PATH", ".ukei/catalogue.sqlite3")
        )
        level = os.getenv("UKEI_LOG_LEVEL", "INFO").upper()
        log_format = os.getenv("UKEI_LOG_FORMAT", "text").lower()
        timeout_text = os.getenv("UKEI_HTTP_TIMEOUT_SECONDS", "20")

        if level not in _LOG_LEVELS:
            raise ConfigurationError(f"UKEI_LOG_LEVEL must be one of {sorted(_LOG_LEVELS)}")
        if log_format not in _LOG_FORMATS:
            raise ConfigurationError("UKEI_LOG_FORMAT must be 'text' or 'json'")
        try:
            timeout = float(timeout_text)
        except ValueError as exc:
            raise ConfigurationError("UKEI_HTTP_TIMEOUT_SECONDS must be numeric") from exc
        if timeout <= 0:
            raise ConfigurationError("UKEI_HTTP_TIMEOUT_SECONDS must be greater than zero")

        return cls(Path(path_value).expanduser(), level, log_format, timeout)
