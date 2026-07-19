"""Compact human-review outputs derived from a detailed validation report."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any


def build_validation_summary(input_path: str | Path, output_dir: str | Path) -> dict[str, Any]:
    report = json.loads(Path(input_path).read_text(encoding="utf-8"))
    sources = report.get("sources")
    if not isinstance(sources, list):
        raise ValueError("validation report must contain a sources list")
    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    outcomes: Counter[str] = Counter()
    checks: Counter[str] = Counter()
    critical: list[dict[str, object]] = []
    licence: list[dict[str, object]] = []
    for source in sources:
        if not isinstance(source, dict):
            continue
        for result in source.get("results", []):
            if not isinstance(result, dict):
                continue
            raw_details = result.get("details")
            details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
            outcome = str(details.get("outcome", "unspecified"))
            check_name = str(result.get("check_name", "unknown"))
            if not result.get("passed"):
                checks[check_name] += 1
                outcomes[outcome] += 1
            row = {
                "source_id": source.get("source_id", ""),
                "title": source.get("title", ""),
                "check_name": check_name,
                "outcome": outcome,
                "message": result.get("message", ""),
                "resource_url": details.get("resource_url", ""),
            }
            if outcome == "confirmed_missing":
                critical.append(row)
            if check_name in {"metadata.licence", "resource.licence"} and not result.get("passed"):
                licence.append(row)
    summary = {
        key: value for key, value in report.items() if key not in {"sources", "resource_checks"}
    }
    summary.update(
        {
            "critical_rows": len(critical),
            "failed_check_counts": dict(sorted(checks.items())),
            "failed_outcome_counts": dict(sorted(outcomes.items())),
            "licence_review_rows": len(licence),
            "resource_checks": report.get("resource_checks", {}),
            "summary_version": 1,
        }
    )
    (destination / "validation-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _write_csv(destination / "confirmed-missing.csv", critical)
    _write_csv(destination / "licence-review.csv", licence)
    return summary


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fields = ("source_id", "title", "check_name", "outcome", "message", "resource_url")
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
