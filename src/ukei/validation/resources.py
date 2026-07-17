"""Resource-level reachability, licence and recency observations."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from urllib.request import Request, urlopen

from ukei.licensing import classify_licence
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
            classification = classify_licence(resource.licence)
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
                        "classification": classification.to_dict(),
                    },
                )
            )
            results.append(self._recency(source, resource.resource_id, resource.last_modified))
            if _is_arcgis_service(resource.url, resource.format):
                results.append(self._arcgis_service(source, resource.resource_id, resource.url))
        return tuple(results)

    def _recency(
        self, source: SourceRecord, resource_id: str, modified: datetime | None
    ) -> ValidationResult:
        age_days = (utc_now() - modified.astimezone(UTC)).days if modified else None
        current = age_days is not None and 0 <= age_days <= self.stale_after_days
        if age_days is None:
            outcome = "unknown"
            message = "Resource modification date was not supplied; manual review required"
        elif age_days < 0:
            outcome = "invalid_future_date"
            message = "FAILED: Resource modification date is in the future"
        elif current:
            outcome = "current"
            message = f"Resource was modified {age_days} days ago"
        else:
            outcome = "stale_warning"
            message = (
                f"Resource was last modified {age_days} days ago; this is a warning because "
                "update cadence is not yet confirmed"
            )
        return ValidationResult(
            source_id=source.source_id,
            check_name="resource.recency",
            passed=age_days is None or age_days >= 0,
            message=message,
            details={
                "age_days": age_days,
                "last_modified": modified.astimezone(UTC).isoformat() if modified else None,
                "resource_id": resource_id,
                "stale_after_days": self.stale_after_days,
                "outcome": outcome,
                "policy": "warning_until_update_cadence_is_confirmed",
            },
        )

    def _arcgis_service(self, source: SourceRecord, resource_id: str, url: str) -> ValidationResult:
        query = dict(parse_qsl(urlparse(url).query, keep_blank_values=True))
        query["f"] = "json"
        parsed = urlparse(url)
        endpoint = urlunparse(parsed._replace(query=urlencode(query)))
        details: dict[str, object] = {"endpoint": endpoint, "resource_id": resource_id}
        try:
            request = Request(
                endpoint,
                headers={"Accept": "application/json", "User-Agent": "ukei-catalogue/0.6"},
            )
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(1_048_577)
            if len(body) > 1_048_576:
                raise ValueError("service metadata exceeded 1 MiB")
            payload = json.loads(body)
            if not isinstance(payload, dict) or payload.get("error"):
                raise ValueError("ArcGIS returned an error or invalid service document")
            layers = payload.get("layers", [])
            tables = payload.get("tables", [])
            valid = isinstance(layers, list) and isinstance(tables, list) and bool(layers or tables)
            details.update(
                {
                    "capabilities": payload.get("capabilities", ""),
                    "current_version": payload.get("currentVersion"),
                    "layer_count": len(layers) if isinstance(layers, list) else None,
                    "table_count": len(tables) if isinstance(tables, list) else None,
                }
            )
            message = (
                "ArcGIS service metadata is valid"
                if valid
                else "FAILED: ArcGIS service contains no layers or tables"
            )
            return ValidationResult(
                source_id=source.source_id,
                check_name="resource.service",
                passed=valid,
                message=message,
                details=details,
            )
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            details["failure_reason"] = str(exc)
            return ValidationResult(
                source_id=source.source_id,
                check_name="resource.service",
                passed=False,
                message=f"FAILED: ArcGIS service metadata check failed: {exc}",
                details=details,
            )


def _is_arcgis_service(url: str, format_name: str) -> bool:
    lowered = f"{url} {format_name}".casefold()
    return "featureserver" in lowered or "mapserver" in lowered or "feature service" in lowered
