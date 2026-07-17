"""Contracts for environmental catalogue connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from ukei.models import SourceRecord


class ConnectorError(RuntimeError):
    """A connector could not complete without compromising its contract."""


@dataclass(frozen=True, slots=True)
class ConnectorContext:
    """Non-secret runtime inputs shared with a connector."""

    timeout_seconds: float = 20.0
    user_agent: str = "ukei-catalogue/0.1"


class Connector(ABC):
    """Discover and harvest source metadata without asserting verification."""

    name: str

    def __init__(self, context: ConnectorContext | None = None) -> None:
        self.context = context or ConnectorContext()

    @abstractmethod
    def discover(self) -> Iterable[SourceRecord]:
        """Yield candidate source records."""

    @abstractmethod
    def raw_metadata(self, source: SourceRecord) -> Mapping[str, object]:
        """Return unmodified source metadata suitable for provenance storage."""
