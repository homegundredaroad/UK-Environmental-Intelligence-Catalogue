import csv
import gzip
import json
from pathlib import Path
from typing import Any

import pytest

from ukei.harvestability import (
    _authentication,
    _dataset_key,
    _has_air_context,
    _load_json,
    _load_relevance_csv,
    _machine_readable,
    _policy_block_category,
    _safe_probe_url,
    _validation_index,
    build_harvestability_manifest,
    main,
)


def _catalogue() -> dict[str, Any]:
    return {
        "schema_version": 2,
        "records": [
            {
                "source_id": "one",
                "publisher": "Council A",
                "title": "Air Quality",
                "geographic_scope": "Town A",
                "licence": "Open Government Licence v3.0",
                "update_frequency": "hourly",
                "url": "https://catalogue.example/dataset/1",
                "resources": [
                    {
                        "resource_id": "csv",
                        "url": "https://data.example/air.csv",
                        "format": "CSV",
                        "media_type": "text/csv",
                        "authoritative": True,
                    }
                ],
            },
            {
                "source_id": "two",
                "publisher": "Council A",
                "title": "Air Quality",
                "geographic_scope": "Town A",
                "licence": "Open Government Licence v3.0",
                "url": "https://catalogue.example/dataset/duplicate",
            },
            {
                "source_id": "three",
                "publisher": "Council B",
                "title": "NO2",
                "geographic_scope": "Town B",
                "licence": "Not supplied by discovery response; verify",
                "url": "https://catalogue.example/dataset/3",
                "resources": [
                    {
                        "resource_id": "secret",
                        "url": "https://data.example/feed?api_key=REDACTED",
                        "format": "JSON",
                    }
                ],
            },
            {
                "source_id": "four",
                "publisher": "Agency C",
                "title": "River Water Quality Monitoring - Ammonia",
                "geographic_scope": "Town C",
                "licence": "UK Open Government Licence (OGL)",
                "url": "https://catalogue.example/dataset/4",
                "resources": [
                    {
                        "resource_id": "json",
                        "url": "https://data.example/river.json",
                        "format": "JSON",
                    }
                ],
            },
        ],
    }


def _write_relevance(path: Path) -> None:
    path.write_text(
        "source_id,stressor_id,air_relevance,matched_terms\n"
        "one,nitrogen-dioxide,DIRECT,NO2\n"
        "two,nitrogen-dioxide,DIRECT,NO2\n"
        "four,ammonia-ammonium,DIRECT_CROSS_MEDIA,ammonia\n",
        encoding="utf-8",
    )


def test_helpers_cover_auth_machine_and_validation(tmp_path: Path) -> None:
    assert _authentication("https://x.test/data") == "none_observed"
    assert _authentication("https://x.test/data?token=x") == "credential_parameter_present"
    assert _authentication("https://u:p@x.test/data") == "embedded_credentials_blocked"
    assert _authentication("https://x.test/data?token=REDACTED") == "redacted_or_required"
    assert _safe_probe_url("https://x.test/a.csv")
    assert not _safe_probe_url("http://x.test/a.csv")
    assert not _safe_probe_url("https://127.0.0.1/private.csv")
    assert not _safe_probe_url("https://localhost/private.csv")
    assert _machine_readable({"url": "https://x.test/a.csv", "format": "", "media_type": ""})
    assert _machine_readable(
        {"url": "https://x.test/a", "format": "", "media_type": ""}, "application/json"
    )
    assert not _machine_readable(
        {"url": "https://x.test/page", "format": "", "media_type": "text/html"}
    )
    record = _catalogue()["records"][0]
    assert isinstance(record, dict)
    assert _dataset_key(record) == _dataset_key(dict(record))
    assert _has_air_context(record)
    assert not _has_air_context(
        {"title": "River Water Quality Monitoring - Ammonia", "themes": ["water quality"]}
    )
    assert _validation_index(None) == {}
    assert _load_relevance_csv(None) == {}
    assert _validation_index({"sources": "bad"}) == {}
    payload = {
        "sources": [{"source_id": "one", "results": [{"check_name": "live.url", "details": {}}]}]
    }
    assert ("one", "") in _validation_index(payload)
    plain = tmp_path / "plain.json"
    plain.write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert _load_json(plain)["x"] == 1
    gz = tmp_path / "data.json.gz"
    with gzip.open(gz, "wt", encoding="utf-8") as fh:
        json.dump({"x": 2}, fh)
    assert _load_json(gz)["x"] == 2
    plain.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        _load_json(plain)


def test_manifest_deduplicates_selects_resource_and_blocks_redacted_probe(tmp_path: Path) -> None:
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps(_catalogue()), encoding="utf-8")
    calls: list[str] = []

    def probe(source_id: str, url: str, timeout: float) -> dict[str, object]:
        calls.append(url)
        assert source_id == "one"
        assert timeout == 4.0
        return {
            "passed": True,
            "checked_at": "2026-10-05T17:00:00+00:00",
            "details": {"outcome": "reachable_secure", "content_type": "text/csv"},
        }

    relevance = tmp_path / "relevance.csv"
    _write_relevance(relevance)
    receipt = build_harvestability_manifest(
        source,
        tmp_path / "out",
        relevance_path=relevance,
        probe=True,
        probe_limit=10,
        timeout_seconds=4.0,
        probe_function=probe,
    )
    assert receipt["input_record_count"] == 4
    assert receipt["deduplicated_dataset_count"] == 3
    assert receipt["duplicate_records_collapsed"] == 1
    assert receipt["live_probes_performed"] == 1
    assert calls == ["https://data.example/air.csv"]
    assert receipt["blocked_or_redacted_auth_count"] == 1
    assert receipt["relevant_dataset_count"] == 2
    assert receipt["air_context_dataset_count"] == 1
    assert receipt["candidate_for_test_count"] == 1
    assert receipt["governance"]["scientific_admissibility_conferred"] is False

    rows = list(csv.DictReader((tmp_path / "out" / "harvestability-manifest.csv").open()))
    one = next(row for row in rows if row["provider"] == "Council A")
    assert one["canonical_url"] == "https://data.example/air.csv"
    assert one["machine_readable"] == "yes"
    assert one["reachable"] == "yes"
    assert one["sccaq_status"] == "CANDIDATE_FOR_TEST"
    assert one["duplicate_count"] == "2"
    three = next(row for row in rows if row["provider"] == "Council B")
    assert three["authentication"] == "redacted_or_required"
    assert three["sccaq_status"] == "DISCOVERED_ONLY"
    four = next(row for row in rows if row["provider"] == "Agency C")
    assert four["relevance_status"] == "MATCHED"
    assert four["air_context"] == "no"
    assert four["sccaq_status"] == "DISCOVERED_ONLY"
    assert "no explicit air-context evidence" in four["reason"]
    assert (tmp_path / "out" / "harvestability-evidence.json").exists()
    assert (tmp_path / "out" / "harvestability-receipt.json").exists()


def test_manifest_escapes_untrusted_spreadsheet_formulas(tmp_path: Path) -> None:
    payload = _catalogue()
    payload["records"] = [payload["records"][0]]
    payload["records"][0]["publisher"] = '=HYPERLINK("https://malicious.example","click")'
    source = tmp_path / "input.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    build_harvestability_manifest(source, tmp_path / "out")
    rows = list(csv.DictReader((tmp_path / "out" / "harvestability-manifest.csv").open()))
    assert rows[0]["provider"].startswith("'=HYPERLINK")
    evidence = json.loads((tmp_path / "out" / "harvestability-evidence.json").read_text())
    assert evidence["datasets"][0]["members"][0]["publisher"].startswith("=HYPERLINK")


@pytest.mark.parametrize(
    ("failure_reason", "expected"),
    [
        ("strict discovery blocked an HTTP redirect", "redirect_disallowed"),
        ("strict discovery rejected a non-public DNS address", "non_public_dns"),
        ("strict discovery cannot resolve endpoint", "dns_resolution_failure"),
        ("strict discovery requires a public HTTPS endpoint", "non_public_endpoint"),
        ("unclassified transport denial", "other_policy_block"),
    ],
)
def test_policy_block_categories_do_not_expose_untrusted_details(
    failure_reason: str, expected: str
) -> None:
    result = {
        "details": {"outcome": "blocked_by_policy", "failure_reason": failure_reason}
    }
    assert _policy_block_category(result) == expected
    assert _policy_block_category({"details": {"outcome": "reachable_secure"}}) == ""


def test_blocked_probes_remain_unknown_with_dedicated_review_queue(
    tmp_path: Path,
) -> None:
    payload = _catalogue()
    payload["records"] = [payload["records"][0]]
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    relevance = tmp_path / "relevance.csv"
    _write_relevance(relevance)

    def blocked(_source_id: str, _url: str, _timeout: float) -> dict[str, Any]:
        return {
            "passed": False,
            "checked_at": "2026-11-05T13:00:00+00:00",
            "details": {
                "outcome": "blocked_by_policy",
                "failure_reason": "strict discovery blocked an HTTP redirect",
            },
        }

    receipt = build_harvestability_manifest(
        source, tmp_path / "out", relevance_path=relevance, probe=True,
        probe_function=blocked
    )
    assert receipt["live_probes_performed"] == 1
    assert receipt["reachable_count"] == 0
    assert receipt["policy_blocked_count"] == 1
    assert receipt["candidate_for_test_count"] == 0
    assert receipt["governance"]["scientific_admissibility_conferred"] is False
    rows = list(csv.DictReader((tmp_path / "out" / "harvestability-manifest.csv").open()))
    assert rows[0]["reachable"] == "unknown"
    assert rows[0]["probe_outcome"] == "blocked_by_policy"
    assert rows[0]["policy_block_category"] == "redirect_disallowed"
    assert "transport policy review" in rows[0]["reason"]
    assert rows[0]["sccaq_status"] == "DISCOVERED_ONLY"
    with (tmp_path / "out" / "policy-block-review.csv").open(newline="") as handle:
        review = list(csv.DictReader(handle))
    assert len(review) == 1
    assert review[0]["dataset_key"] == rows[0]["dataset_key"]
    assert review[0]["vvip_status"] == "REVIEW_REQUIRED"
    assert "canonical_url" not in review[0]
    assert "failure_reason" not in review[0]


def test_existing_validation_is_used_without_live_probe(tmp_path: Path) -> None:
    payload = _catalogue()
    payload["records"] = [payload["records"][0]]
    source = tmp_path / "catalogue.json"
    validation = tmp_path / "validation.json"
    source.write_text(json.dumps(payload), encoding="utf-8")
    validation.write_text(
        json.dumps(
            {
                "sources": [
                    {
                        "source_id": "one",
                        "results": [
                            {
                                "check_name": "resource.url",
                                "passed": True,
                                "checked_at": "2026-10-05T16:00:00+00:00",
                                "details": {
                                    "resource_id": "csv",
                                    "outcome": "reachable_secure",
                                    "content_type": "text/csv",
                                },
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    relevance = tmp_path / "relevance.csv"
    _write_relevance(relevance)
    receipt = build_harvestability_manifest(
        source, tmp_path / "out", validation_path=validation, relevance_path=relevance
    )
    assert receipt["reachable_count"] == 1
    assert receipt["live_probes_performed"] == 0
    rows = list(csv.DictReader((tmp_path / "out" / "harvestability-manifest.csv").open()))
    assert rows[0]["last_probe_utc"] == "2026-10-05T16:00:00+00:00"


def test_empty_and_invalid_inputs_and_main(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "empty.json"
    source.write_text(json.dumps({"records": []}), encoding="utf-8")
    receipt = build_harvestability_manifest(source, tmp_path / "out")
    assert receipt["deduplicated_dataset_count"] == 0
    assert main([str(source), str(tmp_path / "cli")]) == 0
    assert json.loads(capsys.readouterr().out)["schema"].endswith("_v1")
    source.write_text(json.dumps({"records": "bad"}), encoding="utf-8")
    with pytest.raises(ValueError):
        build_harvestability_manifest(source, tmp_path / "bad")
    source.write_text(json.dumps({"records": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        build_harvestability_manifest(source, tmp_path / "bad2", probe_limit=-1)
