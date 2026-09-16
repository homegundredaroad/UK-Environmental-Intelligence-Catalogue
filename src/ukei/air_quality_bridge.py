"""Governed Air Quality export from a validated UK-EIC catalogue release."""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

FILTER_VERSION = "air-quality-bridge-v1"
_AIR_QUALITY_PATTERN = re.compile(
    r"\b(air quality|air pollution|ambient air|nitrogen dioxide|no2|pm2\.?5|pm10|"
    r"particulate matter|aurn)\b",
    re.IGNORECASE,
)


def _load_catalogue(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("catalogue input must be an object containing a records list")
    return payload


def _is_air_quality(record: dict[str, Any]) -> bool:
    text = " ".join(
        [
            str(record.get("title", "")),
            str(record.get("description", "")),
            " ".join(str(value) for value in record.get("themes", []) or []),
        ]
    )
    return bool(_AIR_QUALITY_PATTERN.search(text))


def _licence_status(value: object) -> str:
    text = str(value or "").strip().casefold()
    if not text or text == "unknown" or text.startswith("not supplied"):
        return "REVIEW_REQUIRED"
    return "SUPPLIED_NOT_NORMALIZED"


def build_air_quality_bridge(
    input_path: str | Path,
    output_directory: str | Path,
    *,
    release_id: str = "",
) -> dict[str, Any]:
    """Export Air Quality candidates without promoting them into scientific evidence."""
    source_path = Path(input_path)
    payload = _load_catalogue(source_path)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    selected = [record for record in payload["records"] if isinstance(record, dict) and _is_air_quality(record)]
    selected.sort(key=lambda record: str(record.get("source_id", "")))

    source_fields = [
        "source_id",
        "publisher",
        "title",
        "canonical_url",
        "provenance_url",
        "connector",
        "catalogue_status",
        "licence",
        "licence_status",
        "geographic_scope",
        "update_frequency",
        "formats",
        "themes",
        "last_verified_at",
        "content_hash",
        "approval_status",
    ]
    with (output / "air-quality-sources.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=source_fields)
        writer.writeheader()
        for record in selected:
            writer.writerow(
                {
                    "source_id": record.get("source_id", ""),
                    "publisher": record.get("publisher", ""),
                    "title": record.get("title", ""),
                    "canonical_url": record.get("url", ""),
                    "provenance_url": record.get("provenance_url", ""),
                    "connector": record.get("connector", ""),
                    "catalogue_status": record.get("status", ""),
                    "licence": record.get("licence", ""),
                    "licence_status": _licence_status(record.get("licence")),
                    "geographic_scope": record.get("geographic_scope", ""),
                    "update_frequency": record.get("update_frequency", ""),
                    "formats": "|".join(str(value) for value in record.get("formats", []) or []),
                    "themes": "|".join(str(value) for value in record.get("themes", []) or []),
                    "last_verified_at": record.get("last_verified_at", ""),
                    "content_hash": record.get("content_hash", ""),
                    "approval_status": "REVIEW_REQUIRED",
                }
            )

    resource_fields = [
        "source_id",
        "resource_id",
        "resource_url",
        "name",
        "format",
        "media_type",
        "licence",
        "last_modified",
        "provenance_url",
        "authoritative_flag",
        "approval_status",
    ]
    resource_count = 0
    with (output / "air-quality-resources.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=resource_fields)
        writer.writeheader()
        for record in selected:
            resources = record.get("resources", []) or []
            if not isinstance(resources, list):
                continue
            for resource in resources:
                if not isinstance(resource, dict):
                    continue
                resource_count += 1
                writer.writerow(
                    {
                        "source_id": record.get("source_id", ""),
                        "resource_id": resource.get("resource_id", ""),
                        "resource_url": resource.get("url", ""),
                        "name": resource.get("name", ""),
                        "format": resource.get("format", ""),
                        "media_type": resource.get("media_type", ""),
                        "licence": resource.get("licence", ""),
                        "last_modified": resource.get("last_modified", ""),
                        "provenance_url": resource.get("provenance_url", ""),
                        "authoritative_flag": bool(resource.get("authoritative", False)),
                        "approval_status": "REVIEW_REQUIRED",
                    }
                )

    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    manifest = {
        "bridge_version": 1,
        "filter_version": FILTER_VERSION,
        "release_id": release_id,
        "catalogue_schema_version": payload.get("schema_version"),
        "catalogue_exported_at": payload.get("exported_at"),
        "catalogue_record_count": payload.get("record_count", len(payload["records"])),
        "catalogue_sha256": source_sha256,
        "air_quality_source_count": len(selected),
        "air_quality_resource_count": resource_count,
        "approval_policy": "All exported rows remain REVIEW_REQUIRED until approved by SCC Air Quality.",
        "canonical_evidence_modified": False,
    }
    (output / "air-quality-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) not in {2, 3}:
        print(
            "usage: python -m ukei.air_quality_bridge INPUT_CATALOGUE OUTPUT_DIRECTORY [RELEASE_ID]",
            file=sys.stderr,
        )
        return 2
    manifest = build_air_quality_bridge(args[0], args[1], release_id=args[2] if len(args) == 3 else "")
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
