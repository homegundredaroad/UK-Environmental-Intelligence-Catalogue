"""Deterministic merging of parallel validation report shards."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def merge_report_shards(directory: str | Path) -> dict[str, Any]:
    paths = sorted(Path(directory).rglob("validation-report-*.json"))
    if not paths:
        raise ValueError("no validation report shards were found")
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    sources: list[dict[str, Any]] = []
    seen: set[str] = set()
    for report in reports:
        for source in report.get("sources", []):
            source_id = str(source["source_id"])
            if source_id in seen:
                raise ValueError(f"duplicate source across validation shards: {source_id}")
            seen.add(source_id)
            sources.append(source)
    results = [result for source in sources for result in source.get("results", [])]
    resource_results = [
        result for result in results if str(result.get("check_name", "")).startswith("resource.")
    ]
    severities = [str(result.get("severity", "pass")) for result in results]
    return {
        "all_passed": all(bool(source.get("passed")) for source in sources),
        "checked_count": len(sources),
        "completed_at": max(str(report["completed_at"]) for report in reports),
        "degraded_count": sum(source.get("status_after") == "degraded" for source in sources),
        "failed_count": sum(not bool(source.get("passed")) for source in sources),
        "live": any(bool(report.get("live")) for report in reports),
        "passed_count": sum(bool(source.get("passed")) for source in sources),
        "report_version": 3,
        "resource_count": sum(int(source.get("resource_count", 0)) for source in sources),
        "resource_checks": {
            "attempted": sum(result.get("check_name") == "resource.url" for result in results),
            "blocked_by_policy": sum(
                result.get("check_name") == "resource.url"
                and result.get("details", {}).get("outcome") == "blocked_by_policy"
                for result in results
            ),
            "failed": sum(not bool(result.get("passed")) for result in resource_results),
            "passed": sum(bool(result.get("passed")) for result in resource_results),
            "semantically_validated_services": sum(
                result.get("check_name") == "resource.service" and bool(result.get("passed"))
                for result in results
            ),
        },
        "resources": any(bool(report.get("resources")) for report in reports),
        "shard_count": len(reports),
        "severity_counts": {
            severity: severities.count(severity)
            for severity in ("pass", "warning", "error", "critical")
        },
        "source_count": len(sources),
        "source_severity_counts": {
            severity: sum(source.get("severity") == severity for source in sources)
            for severity in ("pass", "warning", "error", "critical")
        },
        "sources": sorted(sources, key=lambda source: str(source["source_id"])),
        "started_at": min(str(report["started_at"]) for report in reports),
    }
