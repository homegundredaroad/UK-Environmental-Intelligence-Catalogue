"""Validation orchestration, lifecycle policy and report serialization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ukei.models import SourceRecord, SourceStatus, ValidationResult, utc_now
from ukei.validation.base import MetadataValidator
from ukei.validation.live import UrlValidator
from ukei.validation.resources import ResourceValidator


@dataclass(frozen=True, slots=True)
class SourceValidation:
    """All observations and the conservative lifecycle decision for one source."""

    source_id: str
    title: str
    status_before: SourceStatus
    status_after: SourceStatus
    metadata_score: int
    resource_count: int
    results: tuple[ValidationResult, ...]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def to_dict(self) -> dict[str, Any]:
        return {
            "metadata_score": self.metadata_score,
            "passed": self.passed,
            "resource_count": self.resource_count,
            "results": [result.to_dict() for result in self.results],
            "source_id": self.source_id,
            "status_after": self.status_after.value,
            "status_before": self.status_before.value,
            "title": self.title,
        }


@dataclass(frozen=True, slots=True)
class ValidationReport:
    """Machine-readable summary of one bounded validation run."""

    sources: tuple[SourceValidation, ...]
    live: bool
    resources: bool
    started_at: datetime
    completed_at: datetime
    report_version: int = 2

    @property
    def all_passed(self) -> bool:
        return all(source.passed for source in self.sources)

    def to_dict(self) -> dict[str, Any]:
        results = [result for source in self.sources for result in source.results]
        resource_results = [
            result for result in results if result.check_name.startswith("resource.")
        ]
        return {
            "all_passed": self.all_passed,
            "checked_count": len(self.sources),
            "completed_at": self.completed_at.astimezone(UTC).isoformat(),
            "degraded_count": sum(
                source.status_after is SourceStatus.DEGRADED for source in self.sources
            ),
            "failed_count": sum(not source.passed for source in self.sources),
            "live": self.live,
            "passed_count": sum(source.passed for source in self.sources),
            "report_version": self.report_version,
            "resource_count": sum(source.resource_count for source in self.sources),
            "resource_checks": {
                "attempted": sum(result.check_name == "resource.url" for result in results),
                "blocked_by_policy": sum(
                    result.check_name == "resource.url"
                    and result.details.get("outcome") == "blocked_by_policy"
                    for result in results
                ),
                "failed": sum(not result.passed for result in resource_results),
                "passed": sum(result.passed for result in resource_results),
                "semantically_validated_services": sum(
                    result.check_name == "resource.service" and result.passed for result in results
                ),
            },
            "resources": self.resources,
            "sources": [source.to_dict() for source in self.sources],
            "started_at": self.started_at.astimezone(UTC).isoformat(),
        }


def run_validation(
    sources: tuple[SourceRecord, ...],
    live_validator: UrlValidator | None = None,
    resource_validator: ResourceValidator | None = None,
) -> ValidationReport:
    """Validate sources and recommend degradation only for failed live checks."""
    if not sources:
        raise ValueError("at least one source is required")
    started_at = utc_now()
    assessments: list[SourceValidation] = []
    metadata_validator = MetadataValidator()
    for source in sources:
        metadata_results = metadata_validator.validate(source)
        live_results = live_validator.validate(source) if live_validator else ()
        resource_results = resource_validator.validate(source) if resource_validator else ()
        results = (*metadata_results, *live_results, *resource_results)
        score_result = next(
            result for result in metadata_results if result.check_name == "metadata.completeness"
        )
        score = int(score_result.details["score"])
        material_failed = any(
            result.check_name in {"live.url", "resource.url", "resource.service"}
            and not result.passed
            and result.details.get("outcome") != "blocked_by_policy"
            for result in (*live_results, *resource_results)
        )
        status_after = source.status
        if material_failed and source.status is not SourceStatus.RETIRED:
            status_after = SourceStatus.DEGRADED
        assessments.append(
            SourceValidation(
                source_id=source.source_id,
                title=source.title,
                status_before=source.status,
                status_after=status_after,
                metadata_score=score,
                resource_count=len(source.resources),
                results=results,
            )
        )
    return ValidationReport(
        sources=tuple(assessments),
        live=live_validator is not None,
        resources=resource_validator is not None,
        started_at=started_at,
        completed_at=utc_now(),
    )
