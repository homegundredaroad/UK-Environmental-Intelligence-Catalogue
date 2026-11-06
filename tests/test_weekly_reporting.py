"""SCC/VVIP weekly report integrity and reproducibility contract tests."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ukei.weekly_reporting import (
    SCHEMA,
    EvidenceError,
    build_weekly,
    csv_safe,
    sha,
)


def write_json(path: Path, data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fixture_repo(root: Path) -> None:
    base = root / "handoff/sccairquality"
    directory = base / "harvestability"
    review = {"review_status": "REVIEW_REQUIRED",
              "scientific_admissibility_conferred": False,
              "production_change_authorised": False}
    manifest = [
        {"dataset_key": "alpha", "reachable": "yes",
         "probe_outcome": "reachable_secure", "sccaq_status": "CANDIDATE_FOR_TEST"},
        {"dataset_key": "beta", "reachable": "unknown",
         "probe_outcome": "blocked_by_policy", "sccaq_status": "DISCOVERED_ONLY"},
    ]
    policy = [{"dataset_key": "beta", "provider": "Official Example Council",
               "policy_block_category": "redirect_disallowed",
               "vvip_status": "REVIEW_REQUIRED"}]
    matrix = [{"source_system_id": "official-provider-a", "jurisdiction": "England",
               "direct_connector_status": "MISSING",
               "catalogue_record_matches": "2", "reachable_matches": "1"}]
    write_rows(directory / "harvestability-manifest.csv", manifest)
    write_rows(directory / "policy-block-review.csv", policy)
    write_rows(directory / "authoritative-coverage-matrix.csv", matrix)
    write_json(base / "run-receipt.json", {
        "catalogue_record_count": 3, "cross_media_unique_source_count": 2,
        "successful_query_count": 4, "targeted_query_count": 5,
        "scientific_admissibility_conferred": False, "review_status": "REVIEW_REQUIRED",
    })
    write_json(base / "handoff-receipt.json", {
        "catalogue": {"record_count": 3}, "governance": review
    })
    write_json(directory / "harvestability-receipt.json", {
        "input_record_count": 3, "deduplicated_dataset_count": 2,
        "relevant_dataset_count": 2, "air_context_dataset_count": 2,
        "machine_readable_count": 2, "live_probes_performed": 2,
        "reachable_count": 1, "policy_blocked_count": 1,
        "candidate_for_test_count": 1,
        "generated_at_utc": "2026-11-05T16:00:00+00:00", "governance": review,
    })
    write_json(directory / "authoritative-coverage-receipt.json", {
        "manifest_sha256": sha((directory / "harvestability-manifest.csv").read_bytes()),
        "coverage_claim": "INCOMPLETE_UNTIL_REQUIRED_CONNECTORS_AND_STATION_RECONCILIATION_PASS",
        "required_direct_connector_gap_count": 1,
        "required_direct_connector_gaps": ["official-provider-a"],
        "network_enumeration_gap_count": 1,
        "network_enumeration_gaps": ["aurn"],
        "source_system_count": 1,
        "historical_revision_rule_count": 2,
        "governance": review,
    })


NOW = datetime(2026, 11, 6, 14, tzinfo=UTC)


def test_weekly_suite_has_all_inspectable_outputs_and_holds_release(tmp_path: Path) -> None:
    fixture_repo(tmp_path)
    out = tmp_path / "output"
    receipt = build_weekly(tmp_path, out, now=NOW)
    assert receipt["technical_reporting_gate"] == "PASS"
    assert receipt["scientific_release"] == "HOLD"
    assert receipt["national_completeness"] == "NOT_VERIFIED"
    assert receipt["scientific_publication_approved"] is False
    assert receipt["comparison_week"] is None
    assert receipt["comparisons_supported"] is False
    assert receipt["metrics"]["datasets"] == 2
    assert receipt["metrics"]["eligible"] == 1
    assert receipt["metrics"]["policy"] == 1
    expected = {
        "public-summary.md", "reviewer-report.md", "dashboard.html", "snapshot.json",
        "receipt.json", "bundle-manifest.json", "metrics.csv", "gap-register.csv",
        "action-register.csv",
    }
    assert {item.name for item in out.iterdir()} == expected
    summary = (out / "public-summary.md").read_text()
    reviewer = (out / "reviewer-report.md").read_text()
    html = (out / "dashboard.html").read_text()
    assert "Scientific decision: HOLD" in summary
    assert "No earlier" not in summary or "Not available" in summary
    assert "Historical and scientific" in reviewer
    assert "official-provider-a" in reviewer
    assert "Scientific release: HOLD" in html
    digest = json.loads((out / "bundle-manifest.json").read_text())
    assert digest["file_sha256"]["receipt.json"] == sha((out / "receipt.json").read_bytes())
    assert len(digest["file_sha256"]) == 8


def test_comparison_is_only_prior_distinct_week(tmp_path: Path) -> None:
    fixture_repo(tmp_path)
    archive = tmp_path / "archive"
    prior = archive / "2026-W44"
    write_json(prior / "snapshot.json", {
        "schema": SCHEMA, "week": "2026-W44",
        "metrics": {
            "records": 3, "datasets": 1, "relevant": 2, "air_context": 2,
            "machine": 2, "probed": 2, "reachable": 0, "policy": 2, "eligible": 0,
            "adapters_missing": 1, "networks_missing": 1, "source_systems": 1,
            "cross_media_sources": 2,
        },
    })
    result = build_weekly(tmp_path, tmp_path / "run", archive=archive, now=NOW)
    assert result["comparison_week"] == "2026-W44"
    assert result["changes"]["datasets"] == 1
    assert result["changes"]["reachable"] == 1
    assert result["changes"]["policy"] == -1
    assert result["changes"]["eligible"] == 1
    write_json(archive / "2026-W45/snapshot.json", {
        "schema": SCHEMA, "week": "2026-W45",
        "metrics": result["metrics"],
    })
    again = build_weekly(tmp_path, tmp_path / "rerun", archive=archive, now=NOW)
    assert again["comparison_week"] == "2026-W44"


def test_manifest_digest_mismatch_fails_closed(tmp_path: Path) -> None:
    fixture_repo(tmp_path)
    file = tmp_path / "handoff/sccairquality/harvestability/harvestability-manifest.csv"
    file.write_text(file.read_text() + "\n")
    with pytest.raises(EvidenceError, match="checksum"):
        build_weekly(tmp_path, tmp_path / "output", now=NOW)


def test_blocked_source_cannot_be_promoted(tmp_path: Path) -> None:
    fixture_repo(tmp_path)
    directory = tmp_path / "handoff/sccairquality/harvestability"
    manifest_path = directory / "harvestability-manifest.csv"
    with manifest_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    rows[1]["sccaq_status"] = "CANDIDATE_FOR_TEST"
    write_rows(manifest_path, rows)
    coverage = json.loads((directory / "authoritative-coverage-receipt.json").read_text())
    coverage["manifest_sha256"] = sha(manifest_path.read_bytes())
    write_json(directory / "authoritative-coverage-receipt.json", coverage)
    with pytest.raises(EvidenceError, match=r"eligible count|misclassified"):
        build_weekly(tmp_path, tmp_path / "output", now=NOW)


def test_stale_evidence_remains_stale_when_weekly_renderer_runs(tmp_path: Path) -> None:
    fixture_repo(tmp_path)
    later = datetime(2026, 11, 25, 12, tzinfo=UTC)
    result = build_weekly(tmp_path, tmp_path / "out", now=later)
    assert result["freshness_status"] == "STALE"
    assert result["scientific_release"] == "HOLD"
    assert "STALE" in (tmp_path / "out/dashboard.html").read_text()


def test_formula_injection_cells_are_neutralised() -> None:
    assert csv_safe('=HYPERLINK("http://example.invalid","a")').startswith("'=")
    assert csv_safe("+1+2") == "'+1+2"
    assert csv_safe("safe") == "safe"


def test_missing_receipts_are_not_silently_replaced(tmp_path: Path) -> None:
    with pytest.raises(EvidenceError, match="mandatory evidence file"):
        build_weekly(tmp_path, tmp_path / "output", now=NOW)
