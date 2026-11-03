"""SCC Air Quality governance discovery: conservative failure-mode tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from ukei.air_quality_governance import QUERIES, summarize_discovery


def _write_receipts(path: Path, error_index: int | None = None) -> None:
    path.mkdir()
    for index, query in enumerate(QUERIES):
        source = {
            "status": "candidate",
            "title": "Example dataset",
            "url": "https://example.gov.uk/environment/data",
            "publisher": "Example Agency",
            "licence": "unknown",
            "formats": ["CSV"],
        }
        item = {
            "provider": "ckan:data.gov.uk",
            "remote_id": f"remote-{index}",
            "metadata_hash": hashlib.sha256(query.encode()).hexdigest(),
            "source": source,
        }
        report = {
            "report_version": 3,
            "query": query,
            "candidate_count": 1,
            "candidates": [item],
            "provider_counts": {"ckan:data.gov.uk": 1},
            "provider_coverage": {"ckan:data.gov.uk": {"complete": True}},
            "errors": ["arcgis: provider unavailable"] if index == error_index else [],
            "started_at": "2026-11-03T12:00:00+00:00",
            "completed_at": "2026-11-03T12:00:01+00:00",
        }
        (path / f"{index:02d}.json").write_text(json.dumps(report))


def test_complete_receipts_are_still_only_candidates(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "CANDIDATE_DISCOVERY_ONLY"
    assert manifest["unique_candidate_sources"] == 1
    result = json.loads((out / "scc_airquality_candidate_sources.json").read_text())
    row = result["sources"][0]
    assert len(row["metadata_observations"]) == 10
    assert len(row["matched_queries"]) == 10
    assert not row["licence_reuse_cleared"]
    assert not row["compliance_conclusion_allowed"]
    assert not manifest["public_release_allowed"]
    result_hash = hashlib.sha256(
        (out / "scc_airquality_candidate_sources.json").read_bytes()
    ).hexdigest()
    assert result_hash == manifest["candidate_register_sha256"]


def test_partial_provider_failure_is_not_success(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp, error_index=2)
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "INCOMPLETE_DISCOVERY"
    assert manifest["provider_error_count"] == 1
    assert (out / "query_coverage_receipts.json").exists()


def test_missing_query_is_fail_closed(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    (inp / "05.json").unlink()
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "INCOMPLETE_DISCOVERY"
    assert manifest["query_receipts_valid"] == 9


def test_non_candidate_source_is_rejected(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    file = inp / "00.json"
    report = json.loads(file.read_text())
    report["candidates"][0]["source"]["status"] = "verified"
    file.write_text(json.dumps(report))
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "INCOMPLETE_DISCOVERY"
    assert manifest["schema_error_count"] == 1


def test_insecure_source_url_is_rejected(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    file = inp / "00.json"
    report = json.loads(file.read_text())
    report["candidates"][0]["source"]["url"] = "http://example.gov.uk/data"
    file.write_text(json.dumps(report))
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "INCOMPLETE_DISCOVERY"


def test_invalid_provenance_hash_is_rejected(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    file = inp / "04.json"
    report = json.loads(file.read_text())
    report["candidates"][0]["metadata_hash"] = "unknown"
    file.write_text(json.dumps(report))
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "INCOMPLETE_DISCOVERY"


def test_review_queue_rejects_scientific_promotion(tmp_path: Path) -> None:
    import csv

    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    manifest = summarize_discovery(inp, out)
    assert manifest["review_priority_counts"]["P3"] == 1
    assert manifest["truncated_provider_query_count"] == 0
    assert manifest["provider_coverage_complete"]
    assert not manifest["national_coverage_verified"]
    with (out / "scc_airquality_review_queue.csv").open() as source:
        row = next(csv.DictReader(source))
    assert row["scientific_status"] == "CANDIDATE_METADATA_ONLY"
    assert row["regulatory_conclusion_allowed"] == "FALSE"
    assert manifest["review_queue_sha256"] == hashlib.sha256(
        (out / "scc_airquality_review_queue.csv").read_bytes()
    ).hexdigest()


def test_truncated_provider_is_visible_not_comprehensive(tmp_path: Path) -> None:
    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    file = inp / "03.json"
    report = json.loads(file.read_text())
    report["provider_coverage"]["ckan:data.gov.uk"] = {
        "complete": False,
        "truncated_by_limit": True,
        "provider_total": 1385,
        "records_returned": 40,
    }
    file.write_text(json.dumps(report))
    manifest = summarize_discovery(inp, out)
    assert manifest["status"] == "CANDIDATE_DISCOVERY_ONLY"
    assert manifest["truncated_provider_query_count"] == 1
    assert not manifest["provider_coverage_complete"]
    warning = json.loads((out / "scc_airquality_coverage_warnings.json").read_text())
    assert warning["truncated_provider_queries"][0]["provider_total"] == 1385
    assert not warning["national_coverage_verified"]


def test_review_queue_escapes_formula_titles(tmp_path: Path) -> None:
    import csv

    inp, out = tmp_path / "in", tmp_path / "out"
    _write_receipts(inp)
    file = inp / "04.json"
    report = json.loads(file.read_text())
    report["candidates"][0]["source"]["title"] = '=HYPERLINK("https://example.org")'
    file.write_text(json.dumps(report))
    summarize_discovery(inp, out)
    with (out / "scc_airquality_review_queue.csv").open() as source:
        rows = list(csv.DictReader(source))
    assert any(row["title"].startswith("'=") for row in rows)
