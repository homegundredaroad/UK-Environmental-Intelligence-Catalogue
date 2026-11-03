"""Fail-closed candidate-only SCC Air Quality governance source receipts."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from ukei.discovery.base import canonical_url_key

QUERIES = (
    "industrial emissions",
    "waste incineration",
    "pollution inventory",
    "air quality monitoring",
    "air pollution monitoring",
    "environmental permitting",
    "continuous emissions monitoring",
    "air quality calibration",
    "compliance assessment",
    "industrial installations",
)
HASH_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")
PRIORITY_P0 = (
    "incinerator annual monitoring",
    "air quality data from uk-air",
    "automatic urban and rural",
    "air quality monitoring stations data",
    "pollution inventory",
)
PRIORITY_P1 = (
    "air quality", "air pollution", "incinerat", "emission",
    "environmental permit", "industrial installation", "air pollutant",
    "monitoring station",
)
PRIORITY_P2 = ("pollution", "waste", "regulat", "environment", "monitor")


def _review_priority(title: str) -> tuple[str, str]:
    """A review-order hint from names, never a verification judgement."""
    lower = title.casefold()
    if any(term in lower for term in PRIORITY_P0):
        return "P0", "specific-title-keyword"
    if any(term in lower for term in PRIORITY_P1):
        return "P1", "air-emissions-title-keyword"
    if any(term in lower for term in PRIORITY_P2):
        return "P2", "broader-environment-title-keyword"
    return "P3", "no-target-title-keyword"


def _csv_cell(value: object) -> str:
    """Prevent spreadsheet formula execution in untrusted catalogue titles."""
    text = str(value) if value is not None else ""
    if text.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + text
    return text



def _write_json(path: Path, payload: object) -> str:
    encoded = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode("utf-8")
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def summarize_discovery(input_dir: Path, output_dir: Path) -> dict[str, Any]:
    """Retain source candidates, coverage and exceptions; never confer verification."""
    output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    provider_errors: list[dict[str, str]] = []
    queries: list[dict[str, Any]] = []
    sources: dict[str, dict[str, Any]] = {}
    hashes: dict[str, str] = {}
    observations = 0

    for index, expected in enumerate(QUERIES):
        filename = f"{index:02d}.json"
        path = input_dir / filename
        if not path.is_file():
            errors.append(f"missing discovery receipt: {filename} ({expected})")
            continue
        raw = path.read_bytes()
        hashes[filename] = hashlib.sha256(raw).hexdigest()
        try:
            report = json.loads(raw)
            if not isinstance(report, dict):
                raise ValueError("receipt is not a JSON object")
            if report.get("report_version") != 3 or report.get("query") != expected:
                raise ValueError("unexpected report version or query")
            candidates = report.get("candidates")
            if not isinstance(candidates, list):
                raise ValueError("candidates missing")
            if report.get("candidate_count") != len(candidates):
                raise ValueError("candidate count differs from observations")
            reported_errors = report.get("errors")
            if not isinstance(reported_errors, list):
                raise ValueError("provider errors not a list")
            counts = report.get("provider_counts")
            coverage = report.get("provider_coverage")
            if not isinstance(counts, dict) or not isinstance(coverage, dict):
                raise ValueError("provider coverage missing")
            queries.append(
                {
                    "query": expected,
                    "receipt": filename,
                    "receipt_sha256": hashes[filename],
                    "candidate_count": len(candidates),
                    "provider_counts": counts,
                    "provider_coverage": coverage,
                    "provider_error_count": len(reported_errors),
                }
            )
            for error in reported_errors:
                provider_errors.append({"query": expected, "error": str(error)[:300]})
            for position, item in enumerate(candidates):
                if not isinstance(item, dict) or not isinstance(item.get("source"), dict):
                    raise ValueError(f"invalid candidate at {position}")
                source = item["source"]
                if source.get("status") != "candidate":
                    raise ValueError(f"non-candidate status at {position}")
                url = source.get("url")
                if not isinstance(url, str) or not url.startswith("https://"):
                    raise ValueError(f"unsafe source URL at {position}")
                metadata_hash = item.get("metadata_hash")
                if not isinstance(metadata_hash, str):
                    raise ValueError(f"missing metadata hash at {position}")
                if not HASH_PATTERN.fullmatch(metadata_hash):
                    raise ValueError(f"invalid metadata hash at {position}")
                provider = item.get("provider")
                remote_id = item.get("remote_id")
                if not isinstance(provider, str) or not provider.strip():
                    raise ValueError(f"missing provider at {position}")
                if not isinstance(remote_id, str):
                    raise ValueError(f"missing remote ID at {position}")

                key = canonical_url_key(url)
                row = sources.setdefault(
                    key,
                    {
                        "source_url": key,
                        "title": str(source.get("title", "")),
                        "publisher": str(source.get("publisher", "")),
                        "declared_licence": str(source.get("licence", "unknown")),
                        "formats": source.get("formats", []),
                        "resource_count": None,
                        "metadata_observations": [],
                        "matched_queries": [],
                        "status": "CANDIDATE_METADATA_ONLY",
                        "permit_and_effective_limits_verified": False,
                        "instrument_qaqc_verified": False,
                        "measurements_comparable": False,
                        "licence_reuse_cleared": False,
                        "compliance_conclusion_allowed": False,
                        "scientific_publication_allowed": False,
                    },
                )
                resource_list = source.get("resources")
                if isinstance(resource_list, list):
                    current_count = row["resource_count"]
                    current = int(current_count) if isinstance(current_count, int) else 0
                    row["resource_count"] = max(current, len(resource_list))
                row["metadata_observations"].append(
                    {
                        "provider": provider,
                        "remote_id": remote_id,
                        "metadata_sha256": metadata_hash,
                        "query": expected,
                        "receipt_sha256": hashes[filename],
                    }
                )
                if expected not in row["matched_queries"]:
                    row["matched_queries"].append(expected)
                observations += 1
        except (ValueError, TypeError) as exc:
            errors.append(f"invalid discovery receipt {filename}: {exc}")

    rows = sorted(sources.values(), key=lambda row: row["source_url"])
    for row in rows:
        row["matched_queries"].sort()
        row["metadata_observations"].sort(
            key=lambda observation: (observation["query"], observation["provider"])
        )
    truncated_queries: list[dict[str, Any]] = []
    for receipt in queries:
        for provider, provider_info in receipt["provider_coverage"].items():
            if not isinstance(provider_info, dict):
                errors.append("invalid provider coverage record")
                continue
            if provider_info.get("truncated_by_limit") or (
                provider_info.get("complete") is False
            ):
                truncated_queries.append({
                    "query": receipt["query"],
                    "provider": provider,
                    "provider_total": provider_info.get("provider_total"),
                    "records_returned": provider_info.get("records_returned"),
                    "reason": "bounded_or_incomplete_provider_search",
                })

    # Deterministic candidate-only review ordering, separate from discovery status.
    review: list[dict[str, str]] = []
    for row in rows:
        rank, basis = _review_priority(row["title"])
        licence = row["declared_licence"].casefold()
        unknown_licence = any(
            text in licence for text in ("unknown", "not supplied", "not specified")
        ) or not licence.strip()
        count = row["resource_count"]
        resource_evidence = (
            "NOT_IN_SOURCE_METADATA" if count is None else
            "NO_LISTED_RESOURCE" if count == 0 else "LISTED_NOT_VERIFIED"
        )
        review.append({
            "review_priority": rank,
            "priority_basis": basis,
            "title": row["title"],
            "publisher": row["publisher"],
            "source_url": row["source_url"],
            "matched_queries": " | ".join(row["matched_queries"]),
            "licence_evidence": (
                "NOT_SUPPLIED" if unknown_licence else "DECLARED_NOT_VERIFIED"
            ),
            "resource_evidence": resource_evidence,
            "scientific_status": "CANDIDATE_METADATA_ONLY",
            "measurements_comparable": "FALSE",
            "regulatory_conclusion_allowed": "FALSE",
        })
    review.sort(key=lambda x: (x["review_priority"], x["title"].casefold(), x["source_url"]))
    queue_path = output_dir / "scc_airquality_review_queue.csv"
    with queue_path.open("w", newline="", encoding="utf-8") as stream:
        fields = list(review[0]) if review else [
            "review_priority", "priority_basis", "title", "publisher", "source_url",
            "matched_queries", "licence_evidence", "resource_evidence",
            "scientific_status", "measurements_comparable",
            "regulatory_conclusion_allowed",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in review:
            writer.writerow({key: _csv_cell(item[key]) for key in fields})
    queue_hash = hashlib.sha256(queue_path.read_bytes()).hexdigest()
    gaps_hash = _write_json(
        output_dir / "scc_airquality_coverage_warnings.json",
        {
            "schema": "scc-airquality-discovery-coverage-warnings/1",
            "truncated_provider_queries": truncated_queries,
            "provider_coverage_complete": not truncated_queries,
            "national_coverage_verified": False,
            "scope": "bounded metadata search, not an exhaustive UK census",
        },
    )

    coverage = {
        "schema": "scc-airquality-governance-coverage/2",
        "query_receipts_expected": len(QUERIES),
        "query_receipts_valid": len(queries),
        "queries": queries,
        "provider_errors": provider_errors,
        "schema_errors": errors,
        "candidate_observations": observations,
        "candidate_sources_after_dedup": len(rows),
        "raw_receipt_sha256": hashes,
        "truncated_provider_queries": truncated_queries,
        "national_coverage_verified": False,
    }
    candidates_output = {
        "schema": "scc-airquality-governance-candidates/2",
        "sources": rows,
    }
    coverage_hash = _write_json(output_dir / "query_coverage_receipts.json", coverage)
    candidate_hash = _write_json(
        output_dir / "scc_airquality_candidate_sources.json", candidates_output
    )
    incomplete = len(queries) != len(QUERIES) or bool(errors) or bool(provider_errors)
    incomplete = incomplete or not rows
    manifest = {
        "schema": "scc-airquality-governance-discovery/2",
        "status": "INCOMPLETE_DISCOVERY" if incomplete else "CANDIDATE_DISCOVERY_ONLY",
        "query_receipts_valid": len(queries),
        "query_receipts_expected": len(QUERIES),
        "unique_candidate_sources": len(rows),
        "provider_error_count": len(provider_errors),
        "schema_error_count": len(errors),
        "query_coverage_sha256": coverage_hash,
        "candidate_register_sha256": candidate_hash,
        "review_queue_sha256": queue_hash,
        "coverage_warnings_sha256": gaps_hash,
        "review_priority_counts": dict(sorted(Counter(
            item["review_priority"] for item in review
        ).items())),
        "truncated_provider_query_count": len(truncated_queries),
        "provider_coverage_complete": not truncated_queries,
        "national_coverage_verified": False,
        "public_release_allowed": False,
        "legal_noncompliance_established": False,
        "licence_redistribution_authorised": False,
        "instrument_qaqc_verified": False,
        "measurement_comparability_verified": False,
    }
    _write_json(output_dir / "scc_airquality_governance_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    args = parser.parse_args()
    manifest = summarize_discovery(args.input_dir, args.output_dir)
    print(json.dumps(manifest, indent=2))
    return 0 if manifest["status"] == "CANDIDATE_DISCOVERY_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
