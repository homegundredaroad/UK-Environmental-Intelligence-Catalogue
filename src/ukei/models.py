"""Domain models and canonical serialization."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""
    return datetime.now(UTC)


def parse_datetime(value: str | datetime | None) -> datetime | None:
    """Parse an ISO timestamp and normalize it to UTC."""
    if value is None:
        return None
    parsed = (
        value
        if isinstance(value, datetime)
        else datetime.fromisoformat(value.replace("Z", "+00:00"))
    )
    if parsed.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return parsed.astimezone(UTC)


class SourceStatus(StrEnum):
    CANDIDATE = "candidate"
    VERIFIED = "verified"
    DEGRADED = "degraded"
    RETIRED = "retired"


@dataclass(frozen=True, slots=True)
class ResourceReference:
    """One downloadable file or machine service exposed by a source."""

    resource_id: str
    url: str
    name: str = ""
    format: str = ""
    media_type: str = ""
    licence: str = ""
    last_modified: datetime | None = None
    provenance_url: str | None = None
    authoritative: bool = False

    def __post_init__(self) -> None:
        if not self.resource_id.strip():
            raise ValueError("resource_id must not be empty")
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("resource URL must be an absolute HTTP(S) URL")
        if self.provenance_url:
            provenance = urlparse(self.provenance_url)
            if provenance.scheme not in {"http", "https"} or not provenance.netloc:
                raise ValueError("resource provenance_url must be an absolute HTTP(S) URL")
        if self.last_modified is not None and self.last_modified.tzinfo is None:
            raise ValueError("resource timestamps must be timezone-aware")

    def to_dict(self) -> dict[str, Any]:
        return {
            "authoritative": self.authoritative,
            "format": self.format,
            "last_modified": (
                self.last_modified.astimezone(UTC).isoformat() if self.last_modified else None
            ),
            "licence": self.licence,
            "media_type": self.media_type,
            "name": self.name,
            "provenance_url": self.provenance_url,
            "resource_id": self.resource_id,
            "url": self.url,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ResourceReference:
        return cls(
            resource_id=str(data["resource_id"]),
            url=str(data["url"]),
            name=str(data.get("name", "")),
            format=str(data.get("format", "")),
            media_type=str(data.get("media_type", "")),
            licence=str(data.get("licence", "")),
            last_modified=parse_datetime(data.get("last_modified")),
            provenance_url=(str(data["provenance_url"]) if data.get("provenance_url") else None),
            authoritative=bool(data.get("authoritative", False)),
        )


def make_source_id(title: str, publisher: str) -> str:
    """Create a readable stable identifier with a collision-resistant suffix."""
    stem = re.sub(r"[^a-z0-9]+", "-", f"{publisher}-{title}".lower()).strip("-")[:80]
    digest = hashlib.sha256(f"{publisher}\0{title}".encode()).hexdigest()[:10]
    return f"{stem or 'source'}-{digest}"


@dataclass(frozen=True, slots=True)
class SourceRecord:
    """Canonical metadata for one environmental data source."""

    source_id: str
    title: str
    url: str
    publisher: str
    description: str = ""
    licence: str = "unknown"
    geographic_scope: str = "United Kingdom"
    update_frequency: str = "unknown"
    formats: tuple[str, ...] = ()
    themes: tuple[str, ...] = ()
    resources: tuple[ResourceReference, ...] = ()
    status: SourceStatus = SourceStatus.CANDIDATE
    discovered_at: datetime = field(default_factory=utc_now)
    last_verified_at: datetime | None = None
    provenance_url: str | None = None
    connector: str = "manual"
    content_hash: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        object.__setattr__(self, "formats", tuple(sorted(set(self.formats))))
        object.__setattr__(self, "themes", tuple(sorted(set(self.themes))))
        object.__setattr__(
            self, "resources", tuple(sorted(self.resources, key=lambda r: r.resource_id))
        )
        if not _ID_PATTERN.fullmatch(self.source_id):
            raise ValueError("source_id must be 3-128 lowercase URL-safe characters")
        for name, value in (("title", self.title), ("publisher", self.publisher)):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute HTTP(S) URL")
        if self.provenance_url:
            provenance = urlparse(self.provenance_url)
            if provenance.scheme not in {"http", "https"} or not provenance.netloc:
                raise ValueError("provenance_url must be an absolute HTTP(S) URL")
        timestamps = (self.discovered_at, self.last_verified_at, self.created_at, self.updated_at)
        for timestamp in timestamps:
            if timestamp is not None and timestamp.tzinfo is None:
                raise ValueError("timestamps must be timezone-aware")

    def canonical_payload(self) -> dict[str, Any]:
        """Return evidence-bearing fields in a deterministic JSON-compatible form."""
        payload: dict[str, Any] = {
            "connector": self.connector,
            "description": self.description,
            "discovered_at": self.discovered_at.astimezone(UTC).isoformat(),
            "formats": sorted(set(self.formats)),
            "geographic_scope": self.geographic_scope,
            "last_verified_at": (
                self.last_verified_at.astimezone(UTC).isoformat() if self.last_verified_at else None
            ),
            "licence": self.licence,
            "provenance_url": self.provenance_url,
            "publisher": self.publisher,
            "source_id": self.source_id,
            "status": self.status.value,
            "themes": sorted(set(self.themes)),
            "title": self.title,
            "update_frequency": self.update_frequency,
            "url": self.url,
        }
        if self.resources:
            payload["resources"] = [resource.to_dict() for resource in self.resources]
        return payload

    def calculate_hash(self) -> str:
        encoded = json.dumps(
            self.canonical_payload(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def with_current_hash(self) -> SourceRecord:
        """Return a copy carrying the hash of its canonical evidence fields."""
        return replace(self, content_hash=self.calculate_hash())

    def to_dict(self) -> dict[str, Any]:
        payload = self.canonical_payload()
        payload.update(
            {
                "content_hash": self.content_hash or self.calculate_hash(),
                "created_at": self.created_at.astimezone(UTC).isoformat(),
                "updated_at": self.updated_at.astimezone(UTC).isoformat(),
            }
        )
        return payload

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SourceRecord:
        """Construct a validated record from serialized metadata."""
        return cls(
            source_id=str(data["source_id"]),
            title=str(data["title"]),
            url=str(data["url"]),
            publisher=str(data["publisher"]),
            description=str(data.get("description", "")),
            licence=str(data.get("licence", "unknown")),
            geographic_scope=str(data.get("geographic_scope", "United Kingdom")),
            update_frequency=str(data.get("update_frequency", "unknown")),
            formats=tuple(str(value) for value in data.get("formats", ())),
            themes=tuple(str(value) for value in data.get("themes", ())),
            resources=tuple(
                ResourceReference.from_dict(value)
                for value in data.get("resources", ())
                if isinstance(value, Mapping)
            ),
            status=SourceStatus(str(data.get("status", SourceStatus.CANDIDATE.value))),
            discovered_at=parse_datetime(data.get("discovered_at")) or utc_now(),
            last_verified_at=parse_datetime(data.get("last_verified_at")),
            provenance_url=(str(data["provenance_url"]) if data.get("provenance_url") else None),
            connector=str(data.get("connector", "manual")),
            content_hash=str(data.get("content_hash", "")),
            created_at=parse_datetime(data.get("created_at")) or utc_now(),
            updated_at=parse_datetime(data.get("updated_at")) or utc_now(),
        )


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """One immutable validation observation."""

    source_id: str
    check_name: str
    passed: bool
    message: str
    checked_at: datetime = field(default_factory=utc_now)
    details: Mapping[str, Any] = field(default_factory=dict)
    validation_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["checked_at"] = self.checked_at.astimezone(UTC).isoformat()
        return data
