"""Source-backed SCC Nexus weekly environmental reporting (no network access)."""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = "scc-environmental-intelligence-weekly-v1"
ROOT = Path("handoff/sccairquality")
FILES = {
    "catalogue": ROOT / "run-receipt.json",
    "handoff": ROOT / "handoff-receipt.json",
    "harvest": ROOT / "harvestability/harvestability-receipt.json",
    "manifest": ROOT / "harvestability/harvestability-manifest.csv",
    "coverage": ROOT / "harvestability/authoritative-coverage-receipt.json",
    "matrix": ROOT / "harvestability/authoritative-coverage-matrix.csv",
    "policy": ROOT / "harvestability/policy-block-review.csv",
}
METRICS = {
    "records": "Discovery records",
    "datasets": "Distinct candidate datasets",
    "relevant": "Pollutant-relevant datasets",
    "air_context": "Explicit air-context datasets",
    "machine": "Machine-readable candidates",
    "probed": "Endpoint probes",
    "reachable": "Reachable endpoints",
    "policy": "Safety-policy blocks",
    "eligible": "Candidates for independent tests",
    "adapters_missing": "Missing direct provider adapters",
    "networks_missing": "Unreconciled monitoring networks",
    "source_systems": "Registered source systems",
    "cross_media_sources": "Cross-media source signals",
}


class EvidenceError(ValueError):
    """Fail-closed SCC/VVIP source validation error."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise EvidenceError(f"missing evidence: {path.name}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise EvidenceError(f"unreadable JSON: {path.name}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"invalid JSON object: {path.name}")
    return data


def read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise EvidenceError(f"missing evidence: {path.name}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames:
            raise EvidenceError(f"CSV headers missing: {path.name}")
        rows = list(reader)
    if any(None in row for row in rows):
        raise EvidenceError(f"malformed CSV row: {path.name}")
    return [{str(key): str(value or "") for key, value in row.items()} for row in rows]


def count(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EvidenceError(f"invalid count: {name}")
    return value


def checked_at(value: Any) -> datetime:
    if not isinstance(value, str):
        raise EvidenceError("missing date on harvestability receipt")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("missing UTC offset")
        return parsed.astimezone(UTC)
    except ValueError as exc:
        raise EvidenceError("invalid source receipt timestamp") from exc


def check_governance(data: dict[str, Any], source: str) -> None:
    g = data.get("governance")
    if not isinstance(g, dict):
        raise EvidenceError(f"missing governance: {source}")
    if (g.get("review_status") != "REVIEW_REQUIRED"
        or g.get("scientific_admissibility_conferred") is not False
        or g.get("production_change_authorised") is not False):
        raise EvidenceError(f"scientific release boundary failed: {source}")


def gather(root: Path, now: datetime) -> dict[str, Any]:
    paths = {key: root / relative for key, relative in FILES.items()}
    digests = {key: sha(path.read_bytes()) for key, path in paths.items() if path.is_file()}
    if len(digests) != len(paths):
        raise EvidenceError("mandatory evidence file is missing")
    catalogue = read_json(paths["catalogue"])
    handoff = read_json(paths["handoff"])
    harvest = read_json(paths["harvest"])
    coverage = read_json(paths["coverage"])
    manifest = read_rows(paths["manifest"])
    matrix = read_rows(paths["matrix"])
    policy = read_rows(paths["policy"])
    for name, item in (("handoff", handoff), ("harvest", harvest), ("coverage", coverage)):
        check_governance(item, name)
    if (catalogue.get("review_status") != "REVIEW_REQUIRED"
        or catalogue.get("scientific_admissibility_conferred") is not False):
        raise EvidenceError("focused catalogue scientific gate failed")
    if coverage.get("manifest_sha256") != digests["manifest"]:
        raise EvidenceError("coverage receipt references a different manifest checksum")
    if coverage.get("coverage_claim") != (
        "INCOMPLETE_UNTIL_REQUIRED_CONNECTORS_AND_STATION_RECONCILIATION_PASS"
    ):
        raise EvidenceError("unrecognised national coverage claim")
    metrics = {
        "records": count(harvest.get("input_record_count"), "records"),
        "datasets": count(harvest.get("deduplicated_dataset_count"), "datasets"),
        "relevant": count(harvest.get("relevant_dataset_count"), "relevant"),
        "air_context": count(harvest.get("air_context_dataset_count"), "air_context"),
        "machine": count(harvest.get("machine_readable_count"), "machine"),
        "probed": count(harvest.get("live_probes_performed"), "probed"),
        "reachable": count(harvest.get("reachable_count"), "reachable"),
        "policy": count(harvest.get("policy_blocked_count"), "policy"),
        "eligible": count(harvest.get("candidate_for_test_count"), "eligible"),
        "adapters_missing": count(coverage.get("required_direct_connector_gap_count"), "adapters"),
        "networks_missing": count(coverage.get("network_enumeration_gap_count"), "networks"),
        "source_systems": count(coverage.get("source_system_count"), "source_systems"),
        "cross_media_sources": count(
            catalogue.get("cross_media_unique_source_count"), "cross_media_sources"
        ),
    }
    if metrics["records"] != count(catalogue.get("catalogue_record_count"), "catalogue"):
        raise EvidenceError("upstream discovery and current record counts differ")
    if metrics["records"] != count(
        handoff.get("catalogue", {}).get("record_count"), "handoff records"
    ):
        raise EvidenceError("handoff and current records disagree")
    comparisons = (
        (metrics["datasets"], len(manifest), "dataset count"),
        (metrics["reachable"], sum(r.get("reachable") == "yes" for r in manifest), "reachable count"),
        (metrics["eligible"], sum(r.get("sccaq_status") == "CANDIDATE_FOR_TEST"
                                 for r in manifest), "eligible count"),
        (metrics["policy"], sum(r.get("probe_outcome") == "blocked_by_policy"
                               for r in manifest), "manifest policy count"),
        (metrics["policy"], len(policy), "policy queue count"),
        (metrics["source_systems"], len(matrix), "source-system count"),
        (metrics["adapters_missing"], len(coverage.get("required_direct_connector_gaps", [])),
         "direct adapter ledger"),
        (metrics["networks_missing"], len(coverage.get("network_enumeration_gaps", [])),
         "station gap ledger"),
    )
    for expected, actual, label in comparisons:
        if expected != actual:
            raise EvidenceError(f"unreconciled {label}: {expected} vs {actual}")
    ids = {r.get("dataset_key") for r in manifest}
    if len({r.get("dataset_key") for r in policy}) != len(policy):
        raise EvidenceError("duplicate policy queue dataset IDs")
    for row in policy:
        if (row.get("dataset_key") not in ids
            or row.get("vvip_status") != "REVIEW_REQUIRED"):
            raise EvidenceError("policy queue provenance or VVIP status invalid")
    for row in manifest:
        if (row.get("probe_outcome") == "blocked_by_policy"
            and (row.get("reachable") != "unknown"
                 or row.get("sccaq_status") != "DISCOVERED_ONLY")):
            raise EvidenceError("a blocked source was misclassified or promoted")
    stamp = checked_at(harvest.get("generated_at_utc"))
    if stamp > now:
        raise EvidenceError("future-dated evidence")
    return {
        "metrics": metrics, "digests": digests, "catalogue": catalogue, "handoff": handoff,
        "harvest": harvest, "coverage": coverage, "matrix": matrix, "policy": policy,
        "age_days": round((now - stamp).total_seconds() / 86400, 2),
        "evidence_as_of": stamp.isoformat(), "stale": (now - stamp).days >= 7,
    }


def previous_week(archive: Path | None, current: str) -> dict[str, Any] | None:
    if archive is None or not archive.exists():
        return None
    for path in sorted(archive.glob("????-W??/snapshot.json"), reverse=True):
        if path.parent.name >= current:
            continue
        data = read_json(path)
        if data.get("schema") == SCHEMA and data.get("week") == path.parent.name:
            return data
    return None


def csv_safe(value: object) -> str:
    data = str(value)
    return "'" + data if data.lstrip(" \t\r\n\ufeff").startswith(("=", "+", "-", "@")) else data


def write_csv(path: Path, columns: tuple[str, ...], rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_safe(row.get(key, "")) for key in columns})


def md_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", " ")
