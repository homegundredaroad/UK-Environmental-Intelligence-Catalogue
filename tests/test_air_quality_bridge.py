from __future__ import annotations

import csv
import json
from pathlib import Path

from ukei.air_quality_bridge import build_air_quality_bridge


def test_air_quality_bridge_filters_and_preserves_review_gate(tmp_path: Path) -> None:
    source = tmp_path / "catalogue.json"
    source.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "exported_at": "2026-09-15T18:00:00+00:00",
                "record_count": 2,
                "records": [
                    {
                        "source_id": "air-1",
                        "title": "Nitrogen dioxide monitoring",
                        "description": "Air quality observations",
                        "publisher": "Example authority",
                        "url": "https://example.org/air",
                        "provenance_url": "https://example.org/air/meta",
                        "connector": "test",
                        "status": "candidate",
                        "licence": "unknown",
                        "geographic_scope": "England",
                        "update_frequency": "daily",
                        "formats": ["CSV"],
                        "themes": ["air quality"],
                        "content_hash": "abc",
                        "last_verified_at": None,
                        "resources": [
                            {
                                "resource_id": "resource-1",
                                "url": "https://example.org/air.csv",
                                "name": "observations",
                                "format": "CSV",
                                "media_type": "text/csv",
                                "licence": "unknown",
                                "last_modified": None,
                                "provenance_url": "https://example.org/air/meta",
                                "authoritative": False,
                            }
                        ],
                    },
                    {
                        "source_id": "water-1",
                        "title": "River levels",
                        "description": "Hydrology data",
                        "publisher": "Example authority",
                        "url": "https://example.org/water",
                        "status": "candidate",
                        "licence": "OGL",
                        "themes": ["water"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "bridge"
    manifest = build_air_quality_bridge(source, output, release_id="ci-43")

    assert manifest["air_quality_source_count"] == 1
    assert manifest["air_quality_resource_count"] == 1
    assert manifest["release_id"] == "ci-43"
    assert manifest["canonical_evidence_modified"] is False

    with (output / "air-quality-sources.csv").open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["source_id"] for row in rows] == ["air-1"]
    assert rows[0]["approval_status"] == "REVIEW_REQUIRED"
    assert rows[0]["licence_status"] == "REVIEW_REQUIRED"

    with (output / "air-quality-resources.csv").open(encoding="utf-8") as handle:
        resources = list(csv.DictReader(handle))
    assert resources[0]["source_id"] == "air-1"
    assert resources[0]["approval_status"] == "REVIEW_REQUIRED"
