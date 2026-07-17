"""Validation contracts and deterministic metadata checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from ukei.models import SourceRecord, ValidationResult


class Validator(ABC):
    """Validate one aspect of a source and return observations, never assertions by exception."""

    name: str

    @abstractmethod
    def validate(self, source: SourceRecord) -> tuple[ValidationResult, ...]:
        """Return one or more immutable validation observations."""


class MetadataValidator(Validator):
    """Check deterministic record completeness without making network requests."""

    name = "metadata"

    def validate(self, source: SourceRecord) -> tuple[ValidationResult, ...]:
        parsed = urlparse(source.url)
        checks = (
            ("metadata.title", bool(source.title.strip()), "Title is present"),
            ("metadata.publisher", bool(source.publisher.strip()), "Publisher is present"),
            (
                "metadata.url",
                parsed.scheme == "https" and bool(parsed.netloc),
                "Canonical URL is absolute HTTPS",
            ),
            (
                "metadata.licence",
                source.licence.strip().lower() not in {"", "unknown"},
                "Licence metadata is explicit",
            ),
            (
                "metadata.provenance",
                bool(source.provenance_url),
                "Provenance URL is present",
            ),
        )
        return tuple(
            ValidationResult(
                source_id=source.source_id,
                check_name=name,
                passed=passed,
                message=message if passed else f"FAILED: {message}",
            )
            for name, passed, message in checks
        )
