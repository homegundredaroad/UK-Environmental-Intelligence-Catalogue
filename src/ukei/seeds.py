"""Load and validate curated catalogue seed manifests."""

from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

from ukei.catalogue import CatalogueError
from ukei.models import SourceRecord, SourceStatus

SEED_RESOURCE = "official_sources.v1.json"


def load_official_seed() -> tuple[SourceRecord, ...]:
    """Return the packaged, curated official-source seed after integrity checks."""
    resource = files("ukei.data").joinpath(SEED_RESOURCE)
    try:
        payload: Any = json.loads(resource.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogueError(f"cannot load official seed: {exc}") from exc

    return validate_seed_payload(payload)


def validate_seed_payload(payload: Any) -> tuple[SourceRecord, ...]:
    """Validate a decoded seed payload and return canonical source records."""

    if not isinstance(payload, dict) or payload.get("seed_version") != 1:
        raise CatalogueError("official seed has an unsupported or missing seed_version")
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or not raw_records:
        raise CatalogueError("official seed must contain a non-empty records list")

    records = tuple(SourceRecord.from_dict(item) for item in raw_records)
    identifiers = [record.source_id for record in records]
    urls = [record.url for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise CatalogueError("official seed contains duplicate source identifiers")
    if len(urls) != len(set(urls)):
        raise CatalogueError("official seed contains duplicate canonical URLs")

    for record in records:
        if record.status is not SourceStatus.CANDIDATE:
            raise CatalogueError(f"seed source must remain candidate: {record.source_id}")
        if record.connector != "curated-seed-v1":
            raise CatalogueError(f"unexpected seed connector: {record.source_id}")
        if not record.provenance_url:
            raise CatalogueError(f"seed source lacks provenance: {record.source_id}")
        if record.licence.strip().lower() in {"", "unknown"}:
            raise CatalogueError(
                f"seed source lacks an explicit licence position: {record.source_id}"
            )
        if record.content_hash and record.content_hash != record.calculate_hash():
            raise CatalogueError(f"seed source content hash mismatch: {record.source_id}")
    return records
