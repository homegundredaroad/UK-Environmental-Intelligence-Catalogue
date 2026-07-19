"""Consistent review severity for validation observations."""

from __future__ import annotations

from ukei.models import ValidationResult

_TRANSIENT = {
    "access_restricted",
    "authentication_required",
    "blocked_by_policy",
    "network_failure",
    "rate_limited",
    "request_rejected",
    "service_error",
    "semantic_failure",
    "tls_failure",
    "transient_network_failure",
    "transient_server_failure",
}


def result_severity(result: ValidationResult) -> str:
    """Classify evidence without conflating review needs with unavailability."""
    outcome = str(result.details.get("outcome", ""))
    if outcome == "stale_warning":
        return "warning"
    if result.passed:
        return "pass"
    if outcome == "confirmed_missing":
        return "critical"
    if outcome in _TRANSIENT or result.check_name in {
        "metadata.completeness",
        "metadata.licence",
        "resource.licence",
        "resource.presence",
    }:
        return "warning"
    return "error"


def source_severity(results: tuple[ValidationResult, ...]) -> str:
    order = {"pass": 0, "warning": 1, "error": 2, "critical": 3}
    return max((result_severity(result) for result in results), key=order.__getitem__)
