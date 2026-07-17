from __future__ import annotations

from dataclasses import replace

from ukei.models import SourceRecord
from ukei.validation import MetadataValidator


def test_metadata_validator_passes_complete_source(source: SourceRecord) -> None:
    results = MetadataValidator().validate(source)
    assert len(results) == 5
    assert all(result.passed for result in results)
    assert {result.check_name for result in results} == {
        "metadata.title",
        "metadata.publisher",
        "metadata.url",
        "metadata.licence",
        "metadata.provenance",
    }


def test_metadata_validator_exposes_incomplete_assertions(source: SourceRecord) -> None:
    candidate = replace(
        source,
        url="http://example.gov.uk/data",
        licence="unknown",
        provenance_url=None,
    )
    failed = [result for result in MetadataValidator().validate(candidate) if not result.passed]
    assert [result.check_name for result in failed] == [
        "metadata.url",
        "metadata.licence",
        "metadata.provenance",
    ]
    assert all(result.message.startswith("FAILED:") for result in failed)
