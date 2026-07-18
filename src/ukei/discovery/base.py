"""Discovery contracts, provenance records and deterministic orchestration."""

from __future__ import annotations

import hashlib
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ukei.models import SourceRecord, SourceStatus, utc_now


class DiscoveryError(RuntimeError):
    """A discovery provider failed or returned an invalid contract."""


@dataclass(frozen=True, slots=True)
class DiscoveryCandidate:
    """A candidate plus immutable evidence identifying its discovery response."""

    source: SourceRecord
    provider: str
    remote_id: str
    metadata_hash: str

    @classmethod
    def from_metadata(
        cls, source: SourceRecord, provider: str, remote_id: str, raw_metadata: Any
    ) -> DiscoveryCandidate:
        if source.status is not SourceStatus.CANDIDATE:
            raise DiscoveryError("discovery may only produce candidate records")
        encoded = json.dumps(raw_metadata, sort_keys=True, separators=(",", ":")).encode()
        return cls(source, provider, remote_id, hashlib.sha256(encoded).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "remote_id": self.remote_id,
            "metadata_hash": self.metadata_hash,
            "source": self.source.to_dict(),
        }


class DiscoveryConnector(ABC):
    """Discover untrusted candidates from one remote catalogue."""

    name: str

    @abstractmethod
    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        """Return bounded candidate observations or raise DiscoveryError."""

    def coverage(self) -> dict[str, Any]:
        """Return provider pagination evidence from the most recent discovery call."""
        return {}


@dataclass(frozen=True, slots=True)
class DiscoveryReport:
    """Complete, serializable receipt for one discovery run."""

    query: str
    started_at: datetime
    completed_at: datetime
    candidates: tuple[DiscoveryCandidate, ...]
    provider_counts: dict[str, int]
    provider_coverage: dict[str, dict[str, Any]]
    duplicates_removed: int
    errors: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_version": 3,
            "query": self.query,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "completed_at": self.completed_at.astimezone(UTC).isoformat(),
            "candidate_count": len(self.candidates),
            "provider_counts": dict(sorted(self.provider_counts.items())),
            "provider_coverage": dict(sorted(self.provider_coverage.items())),
            "duplicates_removed": self.duplicates_removed,
            "errors": list(self.errors),
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


def canonical_url_key(url: str) -> str:
    """Normalize an HTTP URL only for duplicate comparison."""
    split = urlsplit(url)
    path = split.path.rstrip("/") or "/"
    return urlunsplit((split.scheme.lower(), split.netloc.lower(), path, split.query, ""))


def run_discovery(
    connectors: tuple[DiscoveryConnector, ...], query: str, limit: int
) -> DiscoveryReport:
    """Run providers independently and deterministically remove duplicate URLs."""
    if not query.strip():
        raise DiscoveryError("discovery query must not be empty")
    if limit < 1 or limit > 1_000:
        raise DiscoveryError("discovery limit must be between 1 and 1,000")
    if not connectors:
        raise DiscoveryError("at least one discovery connector is required")

    started = utc_now()
    observations: list[DiscoveryCandidate] = []
    counts: dict[str, int] = {}
    coverage: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for connector in connectors:
        try:
            discovered = connector.discover(query, limit)
        except DiscoveryError as exc:
            errors.append(f"{connector.name}: {exc}")
            counts[connector.name] = 0
            coverage[connector.name] = connector.coverage()
            continue
        counts[connector.name] = len(discovered)
        coverage[connector.name] = connector.coverage()
        observations.extend(discovered)

    unique: list[DiscoveryCandidate] = []
    seen: set[str] = set()
    for candidate in observations:
        key = canonical_url_key(candidate.source.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)

    if not unique and errors:
        raise DiscoveryError("all discovery providers failed: " + "; ".join(errors))
    return DiscoveryReport(
        query=query,
        started_at=started,
        completed_at=utc_now(),
        candidates=tuple(unique),
        provider_counts=counts,
        provider_coverage=coverage,
        duplicates_removed=len(observations) - len(unique),
        errors=tuple(errors),
    )
