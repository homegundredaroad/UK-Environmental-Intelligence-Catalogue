from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from ukei.cross_media import build_cross_media_report, classify_record, load_registry


def test_registry_contains_emerging_cross_media_stressors() -> None:
    registry = load_registry()
    by_id = {entry["id"]: entry for entry in registry["entries"]}
    assert by_id["microplastics"]["air_relevance"] == "EMERGING_CROSS_MEDIA"
    assert "air" in by_id["microplastics"]["compartments"]
    assert "water" in by_id["microplastics"]["compartments"]
    assert by_id["pfas"]["evidence_maturity"] == "DEVELOPING"


def test_classification_is_candidate_only() -> None:
    record = {
        "title": "Atmospheric microplastics deposition survey",
        "description": "Particles measured in air and deposition samples.",
        "publisher": "Example",
        "themes": ["air quality"],
        "formats": ["CSV"],
    }
    matches = classify_record(record)
    ids = {match["stressor_id"] for match in matches}
    assert "microplastics" in ids
    assert "atmospheric-deposition" in ids
    deposition = next(
        match for match in matches if match["stressor_id"] == "atmospheric-deposition"
    )
    assert deposition["matched_terms"] == ["derived:atmospheric-context+deposition"]


def test_generic_deposition_is_not_assumed_atmospheric() -> None:
    record = {
        "title": "Sediment deposition survey",
        "description": "Deposition measured in an estuarine sediment core.",
        "publisher": "Example",
        "themes": ["sediment"],
        "formats": ["CSV"],
    }
    ids = {match["stressor_id"] for match in classify_record(record)}
    assert "atmospheric-deposition" not in ids


def test_cross_media_report_keeps_review_gate(tmp_path: Path) -> None:
    source = tmp_path / "catalogue.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_id": "source-1",
                        "title": "PFAS in air and water",
                        "publisher": "Example",
                        "url": "https://example.org/pfas",
                        "status": "candidate",
                        "themes": ["PFAS", "air"],
                        "formats": ["CSV"],
                        "content_hash": "abc",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    report = build_cross_media_report(source, tmp_path / "out")
    assert report["review_only"] is True
    assert report["canonical_evidence_modified"] is False
    csv_text = (tmp_path / "out" / "cross-media-candidates.csv").read_text(encoding="utf-8")
    assert "REVIEW_REQUIRED" in csv_text
    assert "pfas" in csv_text


def test_cross_media_report_accepts_gzip_catalogue(tmp_path: Path) -> None:
    source = tmp_path / "catalogue.json.gz"
    with gzip.open(source, "wt", encoding="utf-8") as handle:
        json.dump(
            {
                "records": [
                    {
                        "source_id": "source-2",
                        "title": "Black carbon deposition monitoring",
                        "publisher": "Example",
                        "themes": ["air"],
                        "formats": ["CSV"],
                    }
                ]
            },
            handle,
        )
    report = build_cross_media_report(source, tmp_path / "out-gzip")
    assert report["unique_source_count"] == 1
    assert report["candidate_match_count"] >= 1


def test_cross_media_report_rejects_invalid_catalogue_shape(tmp_path: Path) -> None:
    source = tmp_path / "bad.json"
    source.write_text(json.dumps({"records": "not-a-list"}), encoding="utf-8")
    with pytest.raises(ValueError, match="records list"):
        build_cross_media_report(source, tmp_path / "out-bad")
