"""Validation contracts and deterministic metadata checks."""

from __future__ import annotations

from abc import ABC, abstractmethod
from urllib.parse import urlparse

from ukei.models import SourceRecord, ValidationResult

_UNKNOWN_PREFIXES = ("not supplied", "unknown", "verify")


def is_explicit_metadata(value: str) -> bool:
    normalized = value.strip().lower()
    return bool(normalized) and not normalized.startswith(_UNKNOWN_PREFIXES)


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
        weighted_fields = {
            "title": (bool(source.title.strip()), 10),
            "publisher": (bool(source.publisher.strip()), 10),
            "description": (bool(source.description.strip()), 10),
            "url": (parsed.scheme == "https" and bool(parsed.netloc), 15),
            "licence": (is_explicit_metadata(source.licence), 15),
            "provenance": (bool(source.provenance_url), 15),
            "geographic_scope": (is_explicit_metadata(source.geographic_scope), 10),
            "update_frequency": (is_explicit_metadata(source.update_frequency), 5),
            "formats": (bool(source.formats), 5),
            "themes": (bool(source.themes), 5),
        }
        score = sum(weight for present, weight in weighted_fields.values() if present)
        missing = sorted(name for name, (present, _) in weighted_fields.items() if not present)
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
                is_explicit_metadata(source.licence),
                "Licence metadata is explicit",
            ),
            (
                "metadata.provenance",
                bool(source.provenance_url),
                "Provenance URL is present",
            ),
        )
        results = tuple(
            ValidationResult(
                source_id=source.source_id,
                check_name=name,
                passed=passed,
                message=message if passed else f"FAILED: {message}",
            )
            for name, passed, message in checks
        )
        score_result = ValidationResult(
            source_id=source.source_id,
            check_name="metadata.completeness",
            passed=score >= 70,
            message=(
                f"Metadata completeness score is {score}/100"
                if score >= 70
                else f"FAILED: Metadata completeness score is {score}/100"
            ),
            details={"score": score, "threshold": 70, "missing_fields": missing},
        )
        return (*results, score_result)
