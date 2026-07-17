from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ukei.models import SourceRecord


@pytest.fixture
def source() -> SourceRecord:
    timestamp = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)
    return SourceRecord(
        source_id="environment-agency-example",
        title="Example environmental dataset",
        url="https://example.gov.uk/data",
        publisher="Environment Agency",
        description="A fixture, not a real catalogue assertion.",
        licence="Open Government Licence 3.0",
        geographic_scope="England",
        update_frequency="daily",
        formats=("CSV", "JSON"),
        themes=("water", "environment"),
        provenance_url="https://example.gov.uk/data/metadata",
        discovered_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
