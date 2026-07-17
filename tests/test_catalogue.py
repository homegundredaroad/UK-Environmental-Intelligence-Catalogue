from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from pathlib import Path

import pytest

from ukei.catalogue import SCHEMA_VERSION, Catalogue, CatalogueError
from ukei.models import SourceRecord, SourceStatus
from ukei.validation import MetadataValidator


@pytest.fixture
def catalogue(tmp_path: Path) -> Catalogue:
    return Catalogue(tmp_path / "nested" / "catalogue.sqlite3")


def test_initialize_is_idempotent(catalogue: Catalogue) -> None:
    assert catalogue.schema_version() == 0
    assert catalogue.initialize() == SCHEMA_VERSION
    assert catalogue.initialize() == SCHEMA_VERSION
    assert catalogue.schema_version() == SCHEMA_VERSION


def test_upsert_and_get(catalogue: Catalogue, source: SourceRecord) -> None:
    stored = catalogue.upsert_source(source)
    restored = catalogue.get_source(source.source_id)
    assert restored == stored
    assert restored is not None
    assert restored.content_hash == restored.calculate_hash()


def test_upsert_preserves_created_at(catalogue: Catalogue, source: SourceRecord) -> None:
    first = catalogue.upsert_source(source)
    second = catalogue.upsert_source(replace(source, title="Updated title"))
    assert second.created_at == first.created_at
    assert second.title == "Updated title"
    assert second.updated_at >= first.updated_at


def test_unique_url_guard(catalogue: Catalogue, source: SourceRecord) -> None:
    catalogue.upsert_source(source)
    with pytest.raises(CatalogueError, match="another record"):
        catalogue.upsert_source(replace(source, source_id="different-source-id"))


def test_list_and_counts(catalogue: Catalogue, source: SourceRecord) -> None:
    catalogue.upsert_source(source)
    catalogue.upsert_source(
        replace(
            source,
            source_id="retired-example-source",
            url="https://example.gov.uk/retired",
            status=SourceStatus.RETIRED,
        )
    )
    assert len(catalogue.list_sources()) == 2
    assert len(catalogue.list_sources(status=SourceStatus.RETIRED)) == 1
    assert catalogue.counts()["candidate"] == 1
    assert catalogue.counts()["retired"] == 1
    assert catalogue.counts()["total"] == 2


def test_validation_history_is_append_only(catalogue: Catalogue, source: SourceRecord) -> None:
    catalogue.upsert_source(source)
    results = MetadataValidator().validate(source)
    catalogue.record_validations(results)
    history = catalogue.validation_history(source.source_id)
    assert len(history) == 5
    assert catalogue.counts()["validation_events"] == 5
    assert {result.validation_id for result in history} == {
        result.validation_id for result in results
    }


def test_empty_validation_batch_is_noop(catalogue: Catalogue) -> None:
    catalogue.record_validations(())
    assert not catalogue.path.exists()


def test_export_import_round_trip(
    catalogue: Catalogue, source: SourceRecord, tmp_path: Path
) -> None:
    stored = catalogue.upsert_source(source)
    export = catalogue.export_records()
    encoded = json.loads(json.dumps(export))
    destination = Catalogue(tmp_path / "imported.sqlite3")
    assert destination.import_records(encoded["records"]) == 1
    assert destination.get_source(source.source_id) == stored


def test_import_rejects_hash_tampering(catalogue: Catalogue, source: SourceRecord) -> None:
    payload = source.with_current_hash().to_dict()
    payload["title"] = "Changed after hashing"
    with pytest.raises(CatalogueError, match="hash mismatch"):
        catalogue.import_records([payload])


def test_integrity_errors_detect_hash_mutation(catalogue: Catalogue, source: SourceRecord) -> None:
    catalogue.upsert_source(source)
    assert catalogue.integrity_errors() == []
    with sqlite3.connect(catalogue.path) as connection:
        connection.execute(
            "UPDATE sources SET title = 'Tampered' WHERE source_id = ?", (source.source_id,)
        )
    assert catalogue.integrity_errors() == [f"hash mismatch: {source.source_id}"]


def test_missing_source_returns_none(catalogue: Catalogue) -> None:
    assert catalogue.get_source("missing-source") is None
