from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ukei.models import ValidationResult
from ukei.validation.severity import result_severity, source_severity
from ukei.validation.summary import build_validation_summary


def test_build_validation_summary_writes_compact_review_files(tmp_path: Path) -> None:
    report = {
        "source_count": 1,
        "resource_checks": {"attempted": 1},
        "sources": [
            {
                "source_id": "source-1",
                "title": "Fixture",
                "results": [
                    {
                        "check_name": "resource.url",
                        "passed": False,
                        "message": "missing",
                        "details": {
                            "outcome": "confirmed_missing",
                            "resource_url": "https://example.org/missing.csv",
                        },
                    },
                    {
                        "check_name": "metadata.licence",
                        "passed": False,
                        "message": "unknown",
                        "details": {},
                    },
                ],
            }
        ],
    }
    source = tmp_path / "report.json"
    source.write_text(json.dumps(report), encoding="utf-8")
    summary = build_validation_summary(source, tmp_path / "summary")
    assert summary["critical_rows"] == 1
    assert summary["licence_review_rows"] == 1
    with (tmp_path / "summary" / "confirmed-missing.csv").open(encoding="utf-8") as handle:
        assert next(iter(csv.DictReader(handle)))["source_id"] == "source-1"


def test_summary_rejects_report_without_sources(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="sources list"):
        build_validation_summary(source, tmp_path / "output")


def test_validation_severity_distinguishes_review_states() -> None:
    passed = ValidationResult("source-1", "metadata.title", True, "ok")
    warning = ValidationResult(
        "source-1", "resource.url", False, "blocked", details={"outcome": "blocked_by_policy"}
    )
    critical = ValidationResult(
        "source-1", "resource.url", False, "missing", details={"outcome": "confirmed_missing"}
    )
    error = ValidationResult("source-1", "metadata.url", False, "invalid")
    assert [result_severity(item) for item in (passed, warning, critical, error)] == [
        "pass",
        "warning",
        "critical",
        "error",
    ]
    assert source_severity((passed, warning, critical)) == "critical"
