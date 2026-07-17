from __future__ import annotations

from copy import deepcopy

import pytest

from ukei.catalogue import CatalogueError
from ukei.models import SourceStatus
from ukei.seeds import load_official_seed, validate_seed_payload
from ukei.validation import MetadataValidator


def test_official_seed_is_unique_and_policy_compliant() -> None:
    records = load_official_seed()
    assert len(records) == 8
    assert len({record.source_id for record in records}) == len(records)
    assert len({record.url for record in records}) == len(records)
    assert all(record.status is SourceStatus.CANDIDATE for record in records)
    assert all(record.connector == "curated-seed-v1" for record in records)
    assert all(record.provenance_url for record in records)


def test_official_seed_passes_deterministic_metadata_validation() -> None:
    results = [
        result for record in load_official_seed() for result in MetadataValidator().validate(record)
    ]
    assert len(results) == 48
    assert all(result.passed for result in results)


def test_official_seed_hashes_are_deterministic() -> None:
    first = load_official_seed()
    second = load_official_seed()
    assert [record.calculate_hash() for record in first] == [
        record.calculate_hash() for record in second
    ]


def _valid_payload() -> dict[str, object]:
    return {
        "seed_version": 1,
        "records": [record.to_dict() for record in load_official_seed()],
    }


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({}, "seed_version"),
        ({"seed_version": 1, "records": []}, "non-empty"),
    ],
)
def test_seed_rejects_invalid_manifest(payload: object, message: str) -> None:
    with pytest.raises(CatalogueError, match=message):
        validate_seed_payload(payload)


def test_seed_rejects_duplicate_identifiers_and_urls() -> None:
    payload = _valid_payload()
    records = payload["records"]
    assert isinstance(records, list)
    records.append(deepcopy(records[0]))
    with pytest.raises(CatalogueError, match="duplicate source identifiers"):
        validate_seed_payload(payload)

    duplicate_url_payload = _valid_payload()
    duplicate_url_records = duplicate_url_payload["records"]
    assert isinstance(duplicate_url_records, list)
    duplicate_url_records[1]["url"] = duplicate_url_records[0]["url"]
    with pytest.raises(CatalogueError, match="duplicate canonical URLs"):
        validate_seed_payload(duplicate_url_payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("status", "verified", "must remain candidate"),
        ("connector", "unexpected", "unexpected seed connector"),
        ("provenance_url", None, "lacks provenance"),
        ("licence", "unknown", "lacks an explicit licence"),
        ("content_hash", "0" * 64, "content hash mismatch"),
    ],
)
def test_seed_rejects_policy_violations(field: str, value: object, message: str) -> None:
    payload = _valid_payload()
    records = payload["records"]
    assert isinstance(records, list)
    records[0][field] = value
    with pytest.raises(CatalogueError, match=message):
        validate_seed_payload(payload)
