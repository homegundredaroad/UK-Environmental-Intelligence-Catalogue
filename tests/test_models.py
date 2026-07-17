from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import pytest

from ukei.models import ResourceReference, SourceRecord, make_source_id, parse_datetime


def test_source_hash_is_deterministic(source: SourceRecord) -> None:
    reordered = replace(source, formats=("JSON", "CSV"), themes=("environment", "water"))
    assert source.calculate_hash() == reordered.calculate_hash()
    assert len(source.calculate_hash()) == 64


def test_source_round_trip(source: SourceRecord) -> None:
    resource = ResourceReference(
        resource_id="resource-1",
        url="https://example.gov.uk/data.csv",
        name="Data",
        format="CSV",
        media_type="text/csv",
        licence="OGL-3.0",
        last_modified=datetime(2026, 7, 1, tzinfo=UTC),
        provenance_url=source.provenance_url,
        authoritative=True,
    )
    hashed = replace(source, resources=(resource,)).with_current_hash()
    restored = SourceRecord.from_dict(hashed.to_dict())
    assert restored == hashed
    assert restored.content_hash == restored.calculate_hash()


@pytest.mark.parametrize(
    "changes",
    [
        {"source_id": "NO SPACES"},
        {"title": ""},
        {"publisher": "  "},
        {"url": "ftp://example.org/file"},
        {"provenance_url": "relative/path"},
        {"discovered_at": datetime(2026, 1, 1)},
    ],
)
def test_source_rejects_invalid_values(source: SourceRecord, changes: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        replace(source, **changes)


def test_make_source_id_is_stable_and_distinct() -> None:
    first = make_source_id("Air quality", "Defra")
    assert first == make_source_id("Air quality", "Defra")
    assert first != make_source_id("Water quality", "Defra")
    assert first.startswith("defra-air-quality-")


def test_parse_datetime_normalizes_zulu() -> None:
    parsed = parse_datetime("2026-07-17T12:30:00Z")
    assert parsed is not None
    offset = parsed.utcoffset()
    assert offset is not None
    assert offset.total_seconds() == 0


def test_parse_datetime_rejects_naive() -> None:
    with pytest.raises(ValueError, match="timezone"):
        parse_datetime("2026-07-17T12:30:00")


@pytest.mark.parametrize(
    "changes",
    [
        {"resource_id": ""},
        {"url": "file:///tmp/data.csv"},
        {"provenance_url": "relative"},
        {"last_modified": datetime(2026, 1, 1)},
    ],
)
def test_resource_rejects_invalid_values(changes: dict[str, Any]) -> None:
    resource = ResourceReference("resource-1", "https://example.gov.uk/data.csv")
    with pytest.raises(ValueError):
        replace(resource, **changes)
