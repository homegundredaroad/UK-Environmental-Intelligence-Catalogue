"""Conservative cross-media pollutant/stressor discovery support.

This module identifies catalogue records that may be relevant to AirQuality or to
linked environmental compartments. Matches are discovery metadata only: they do
not establish causation, comparability, exposure, or scientific admissibility.
"""

from __future__ import annotations

import csv
import gzip
import json
import re
from importlib.resources import files
from pathlib import Path
from typing import Any

REGISTRY_RESOURCE = "pollutant_stressor_registry.v1.json"


def load_registry() -> dict[str, Any]:
    resource = files("ukei.data").joinpath(REGISTRY_RESOURCE)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("entries"), list):
        raise ValueError("pollutant/stressor registry has an invalid schema")
    return payload


def _load_catalogue(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
        raise ValueError("catalogue input must be an object containing a records list")
    return payload


def _record_text(record: dict[str, Any]) -> str:
    return " ".join(
        [
            str(record.get("title", "")),
            str(record.get("description", "")),
            str(record.get("publisher", "")),
            " ".join(str(value) for value in record.get("themes", []) or []),
            " ".join(str(value) for value in record.get("formats", []) or []),
        ]
    )


def _term_pattern(term: str) -> re.Pattern[str]:
    escaped = re.escape(term.strip())
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.IGNORECASE)


def classify_record(
    record: dict[str, Any], registry: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Return registry matches for one record without altering canonical evidence."""
    registry = registry or load_registry()
    text = _record_text(record)
    matches: list[dict[str, Any]] = []
    for entry in registry["entries"]:
        if not isinstance(entry, dict):
            continue
        terms = [entry.get("canonical_name", ""), *(entry.get("synonyms", []) or [])]
        matched_terms = sorted(
            {
                str(term)
                for term in terms
                if str(term).strip() and _term_pattern(str(term)).search(text)
            },
            key=str.casefold,
        )
        if not matched_terms:
            continue
        matches.append(
            {
                "stressor_id": str(entry.get("id", "")),
                "canonical_name": str(entry.get("canonical_name", "")),
                "air_relevance": str(entry.get("air_relevance", "")),
                "compartments": list(entry.get("compartments", []) or []),
                "monitoring_status": str(entry.get("monitoring_status", "")),
                "evidence_maturity": str(entry.get("evidence_maturity", "")),
                "matched_terms": matched_terms,
            }
        )
    return matches


def build_cross_media_report(
    input_path: str | Path, output_directory: str | Path
) -> dict[str, Any]:
    """Create a review-only cross-media candidate report from a catalogue export."""
    payload = _load_catalogue(input_path)
    registry = load_registry()
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, Any]] = []
    for record in payload["records"]:
        if not isinstance(record, dict):
            continue
        for match in classify_record(record, registry):
            rows.append(
                {
                    "source_id": str(record.get("source_id", "")),
                    "publisher": str(record.get("publisher", "")),
                    "title": str(record.get("title", "")),
                    "canonical_url": str(record.get("url", "")),
                    "catalogue_status": str(record.get("status", "")),
                    "last_verified_at": str(record.get("last_verified_at", "")),
                    "content_hash": str(record.get("content_hash", "")),
                    "stressor_id": match["stressor_id"],
                    "canonical_name": match["canonical_name"],
                    "air_relevance": match["air_relevance"],
                    "compartments": "|".join(match["compartments"]),
                    "monitoring_status": match["monitoring_status"],
                    "evidence_maturity": match["evidence_maturity"],
                    "matched_terms": "|".join(match["matched_terms"]),
                    "review_status": "REVIEW_REQUIRED",
                }
            )

    rows.sort(key=lambda row: (row["stressor_id"], row["source_id"]))
    fields = [
        "source_id",
        "publisher",
        "title",
        "canonical_url",
        "catalogue_status",
        "last_verified_at",
        "content_hash",
        "stressor_id",
        "canonical_name",
        "air_relevance",
        "compartments",
        "monitoring_status",
        "evidence_maturity",
        "matched_terms",
        "review_status",
    ]
    with (output / "cross-media-candidates.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["stressor_id"]] = counts.get(row["stressor_id"], 0) + 1
    report = {
        "report_version": 1,
        "registry_version": registry.get("registry_version"),
        "canonical_evidence_modified": False,
        "review_only": True,
        "candidate_match_count": len(rows),
        "unique_source_count": len({row["source_id"] for row in rows}),
        "counts_by_stressor": dict(sorted(counts.items())),
        "limitations": [
            "Text matching identifies candidates only and does not establish causation.",
            (
                "Measurements across air, water, soil, sediment, deposition and biota "
                "are not assumed comparable."
            ),
            (
                "AirQuality must independently reacquire and validate original-provider "
                "evidence before scientific use."
            ),
        ],
    }
    (output / "cross-media-summary.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report
