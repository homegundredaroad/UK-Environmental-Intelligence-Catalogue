from __future__ import annotations

import json
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from ukei.catalogue import Catalogue, CatalogueError
from ukei.cli import run
from ukei.models import SourceRecord, SourceStatus, ValidationResult
from ukei.validation.merge import merge_report_shards


def test_shard_plan_cli(
    tmp_path: Path, source: SourceRecord, capsys: pytest.CaptureFixture[str]
) -> None:
    database = tmp_path / "catalogue.sqlite3"
    catalogue = Catalogue(database)
    for index in range(3):
        catalogue.upsert_source(
            replace(source, source_id=f"source-{index}", url=f"https://example.org/{index}")
        )
    assert run(["--database", str(database), "shard-plan", "--size", "2"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "include": [
            {"index": 0, "limit": 2, "offset": 0},
            {"index": 1, "limit": 1, "offset": 2},
        ]
    }


def test_merge_validation_shard(tmp_path: Path, source: SourceRecord) -> None:
    canonical_path = tmp_path / "canonical.sqlite3"
    canonical = Catalogue(canonical_path)
    canonical.upsert_source(source)
    shard_path = tmp_path / "shards" / "shard-0.sqlite3"
    shard_path.parent.mkdir()
    shutil.copy2(canonical_path, shard_path)
    shard = Catalogue(shard_path)
    shard.record_validations(
        [
            ValidationResult(
                source_id=source.source_id,
                check_name="url",
                passed=False,
                message="missing",
            )
        ]
    )
    shard.upsert_source(replace(source, status=SourceStatus.DEGRADED))
    result = canonical.merge_validation_shards(shard_path.parent)
    assert result["shards_merged"] == 1
    assert canonical.counts()["validation_events"] == 1
    assert canonical.get_source(source.source_id).status is SourceStatus.DEGRADED  # type: ignore[union-attr]


def test_merge_validation_shards_requires_input(tmp_path: Path) -> None:
    with pytest.raises(CatalogueError, match="no validation shard"):
        Catalogue(tmp_path / "canonical.sqlite3").merge_validation_shards(tmp_path / "empty")


def test_merge_report_shards(tmp_path: Path) -> None:
    for index, passed in enumerate((True, False)):
        payload = {
            "completed_at": f"2026-07-19T12:0{index}:00+00:00",
            "live": True,
            "resources": True,
            "started_at": f"2026-07-19T11:0{index}:00+00:00",
            "sources": [
                {
                    "passed": passed,
                    "resource_count": 1,
                    "results": [],
                    "source_id": f"s-{index}",
                    "status_after": "candidate",
                }
            ],
        }
        (tmp_path / f"validation-report-{index}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    report = merge_report_shards(tmp_path)
    assert report["shard_count"] == 2
    assert report["failed_count"] == 1
    assert report["source_count"] == 2


def test_merge_report_shards_rejects_missing_and_duplicate(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no validation report"):
        merge_report_shards(tmp_path)
    payload = {
        "completed_at": "x",
        "started_at": "x",
        "sources": [{"source_id": "same"}],
    }
    for index in range(2):
        (tmp_path / f"validation-report-{index}.json").write_text(
            json.dumps(payload), encoding="utf-8"
        )
    with pytest.raises(ValueError, match="duplicate source"):
        merge_report_shards(tmp_path)
