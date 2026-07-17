from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any

import pytest

from ukei.models import SourceRecord, make_source_id, parse_datetime


def test_source_hash_is_deterministic(source: SourceRecord) -> None:
    reordered = replace(source, formats=("JSON", "CSV"), themes=("environment", "water"))
    assert source.calculate_hash() == reordered.calculate_hash()
    assert len(source.calculate_hash()) == 64


def test_source_round_trip(source: SourceRecord) -> None:
    hashed = source.with_current_hash()
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
