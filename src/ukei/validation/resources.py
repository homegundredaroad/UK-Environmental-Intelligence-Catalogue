"""Resource-level reachability, licence and recency observations."""

from __future__ import annotations

from datetime import UTC, datetime

from ukei.models import SourceRecord, ValidationResult, utc_now
from ukei.validation.base import is_explicit_metadata
from ukei.validation.live import bounded_url_result


class ResourceValidator:
    """Validate a bounded number of underlying files or machine services per source."""

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_resources_per_source: int = 2,
        stale_after_days: int = 730,
    ) -> None:
        if timeout_seconds <= 0 or max_resources_per_source <= 0 or stale_after_days <= 0:
            raise ValueError("resource validation limits must be greater than zero")
        self.timeout_seconds = timeout_seconds
        self.max_resources_per_source = max_resources_per_source
        self.stale_after_days = stale_after_days

    def validate(self, source: SourceRecord) -> tuple[ValidationResult, ...]:
        if not source.resources:
            return (
                ValidationResult(
                    source_id=source.source_id,
                    check_name="resource.presence",
                    passed=False,
                    message="FAILED: No underlying resource URL was discovered",
                    details={"resource_count": 0},
                ),
            )
        results: list[ValidationResult] = []
        for resource in source.resources[: self.max_resources_per_source]:
            context: dict[str, object] = {
                "authoritative": resource.authoritative,
                "format": resource.format,
                "media_type_declared": resource.media_type,
                "resource_id": resource.resource_id,
                "resource_name": resource.name,
                "resource_url": resource.url,
            }
            results.append(
                bounded_url_result(
                    source.source_id,
                    resource.url,
                    "resource.url",
                    self.timeout_seconds,
                    context,
                )
            )
            explicit_licence = is_explicit_metadata(resource.licence)
            results.append(
                ValidationResult(
                    source_id=source.source_id,
                    check_name="resource.licence",
                    passed=explicit_licence,
                    message=(
                        "Resource licence evidence is explicit"
                        if explicit_licence
                        else "FAILED: Resource licence evidence is missing or ambiguous"
                    ),
                    details={
                        "licence": resource.licence,
                        "provenance_url": resource.provenance_url,
                        "resource_id": resource.resource_id,
                    },
                )
            )
            results.append(self._recency(source, resource.resource_id, resource.last_modified))
        return tuple(results)

    def _recency(
        self, source: SourceRecord, resource_id: str, modified: datetime | None
    ) -> ValidationResult:
        age_days = (utc_now() - modified.astimezone(UTC)).days if modified else None
        current = age_days is not None and 0 <= age_days <= self.stale_after_days
        if age_days is None:
            message = "FAILED: Resource modification date was not supplied"
        elif age_days < 0:
            message = "FAILED: Resource modification date is in the future"
        elif current:
            message = f"Resource was modified {age_days} days ago"
        else:
            message = f"FAILED: Resource was last modified {age_days} days ago"
        return ValidationResult(
            source_id=source.source_id,
            check_name="resource.recency",
            passed=current,
            message=message,
            details={
                "age_days": age_days,
                "last_modified": modified.astimezone(UTC).isoformat() if modified else None,
                "resource_id": resource_id,
                "stale_after_days": self.stale_after_days,
            },
        )
