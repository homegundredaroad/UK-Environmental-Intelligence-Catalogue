"""Audit SCC Air Quality coverage against the governed authoritative-source registry."""

from __future__ import annotations

import argparse
import csv
import json
from importlib.resources import files
from pathlib import Path
from typing import Any

REGISTRY_RESOURCE = "air_quality_authoritative_sources.v1.json"
COVERAGE_SCHEMA = "ukei_scc_air_quality_coverage_v1"
_ALLOWED_TIERS = {
    "STATUTORY_REFERENCE",
    "OFFICIAL_LOCAL",
    "LOW_COST_SENSOR",
    "RESEARCH_SPECIALIST",
    "DERIVED_TOOL",
}


def load_coverage_registry() -> dict[str, Any]:
    """Load and validate the packaged authoritative Air Quality coverage registry."""
    resource = files("ukei.data").joinpath(REGISTRY_RESOURCE)
    payload = json.loads(resource.read_text(encoding="utf-8"))
    validate_coverage_registry(payload)
    return payload


def validate_coverage_registry(payload: object) -> None:
    """Fail closed when the registry cannot support a reproducible coverage audit."""
    if not isinstance(payload, dict) or payload.get("registry_version") != 1:
        raise ValueError("coverage registry has an unsupported or missing registry_version")
    systems = payload.get("source_systems")
    networks = payload.get("national_networks")
    if not isinstance(systems, list) or not systems:
        raise ValueError("coverage registry requires source_systems")
    if not isinstance(networks, list) or not networks:
        raise ValueError("coverage registry requires national_networks")

    system_ids: set[str] = set()
    for system in systems:
        if not isinstance(system, dict):
            raise ValueError("source_system entry must be an object")
        source_id = str(system.get("id", "")).strip()
        if not source_id or source_id in system_ids:
            raise ValueError("source_system ids must be non-empty and unique")
        system_ids.add(source_id)
        if system.get("quality_tier") not in _ALLOWED_TIERS:
            raise ValueError(f"invalid quality tier for {source_id}")
        if not str(system.get("canonical_url", "")).startswith("https://"):
            raise ValueError(f"source_system canonical URL must use HTTPS: {source_id}")
        if not isinstance(system.get("required_for_exhaustive"), bool):
            raise ValueError(f"required_for_exhaustive must be boolean: {source_id}")
        patterns = system.get("catalogue_match_patterns")
        if not isinstance(patterns, list):
            raise ValueError(f"catalogue_match_patterns must be a list: {source_id}")

    network_ids: set[str] = set()
    for network in networks:
        if not isinstance(network, dict):
            raise ValueError("national_network entry must be an object")
        network_id = str(network.get("id", "")).strip()
        if not network_id or network_id in network_ids:
            raise ValueError("national_network ids must be non-empty and unique")
        network_ids.add(network_id)
        if network.get("source_system") not in system_ids:
            raise ValueError(f"network source system is unknown: {network_id}")
        if network.get("quality_tier") not in _ALLOWED_TIERS:
            raise ValueError(f"invalid network quality tier: {network_id}")
        if network.get("enumeration_status") not in {
            "MISSING",
            "IMPLEMENTED",
            "EXCEPTION_REVIEWED",
        }:
            raise ValueError(f"invalid enumeration_status: {network_id}")


def _read_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _system_matches(row: dict[str, str], patterns: list[object]) -> bool:
    haystack = " ".join(
        [
            row.get("provider", ""),
            row.get("dataset", ""),
            row.get("canonical_url", ""),
            row.get("member_source_ids", ""),
        ]
    ).casefold()
    return any(
        str(pattern).strip().casefold() in haystack
        for pattern in patterns
        if str(pattern).strip()
    )


def _row_count(rows: list[dict[str, str]], key: str, value: str) -> int:
    return sum(row.get(key) == value for row in rows)


def build_air_quality_coverage_report(
    manifest_path: str | Path,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Compare current harvestability evidence with the authoritative coverage registry."""
    registry = load_coverage_registry()
    manifest = _read_manifest(manifest_path)
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    matrix: list[dict[str, object]] = []
    required_direct_connector_gaps: list[str] = []
    for system in registry["source_systems"]:
        patterns = system.get("catalogue_match_patterns", [])
        assert isinstance(patterns, list)
        matched = [row for row in manifest if _system_matches(row, patterns)]
        machine_count = _row_count(matched, "machine_readable", "yes")
        reachable_count = _row_count(matched, "reachable", "yes")
        candidate_count = _row_count(matched, "sccaq_status", "CANDIDATE_FOR_TEST")
        connector_status = str(system.get("direct_connector_status", "MISSING"))
        required = bool(system.get("required_for_exhaustive"))
        if required and connector_status not in {"IMPLEMENTED", "EXCEPTION_REVIEWED"}:
            required_direct_connector_gaps.append(str(system["id"]))

        if connector_status == "IMPLEMENTED":
            coverage_status = "DIRECT_CONNECTOR_READY"
        elif matched:
            coverage_status = "CATALOGUE_SIGNAL_ONLY"
        else:
            coverage_status = "NOT_REPRESENTED"

        matrix.append(
            {
                "source_system_id": str(system["id"]),
                "source_system": str(system["name"]),
                "jurisdiction": str(system.get("jurisdiction", "")),
                "quality_tier": str(system.get("quality_tier", "")),
                "scope": str(system.get("scope", "")),
                "endpoint_kind": str(system.get("endpoint_kind", "")),
                "access": str(system.get("access", "")),
                "machine_readable_declared": bool(system.get("machine_readable", False)),
                "required_for_exhaustive": required,
                "required_for_statutory": bool(system.get("required_for_statutory", False)),
                "direct_connector_status": connector_status,
                "coverage_status": coverage_status,
                "catalogue_record_matches": len(matched),
                "machine_readable_matches": machine_count,
                "reachable_matches": reachable_count,
                "candidate_for_test_matches": candidate_count,
                "canonical_url": str(system.get("canonical_url", "")),
                "endpoint": str(system.get("endpoint", "")),
                "endpoint_status": str(system.get("endpoint_status", "")),
                "station_inventory_strategy": str(system.get("station_inventory_strategy", "")),
                "historical_revision_expected": bool(
                    system.get("historical_revision_expected", False)
                ),
                "completeness_note": str(system.get("completeness_note", "")),
            }
        )

    network_enumeration_gaps = [
        str(network["id"])
        for network in registry["national_networks"]
        if network.get("enumeration_status") not in {"IMPLEMENTED", "EXCEPTION_REVIEWED"}
    ]
    network_count_conflicts = [
        str(network["id"])
        for network in registry["national_networks"]
        if network.get("count_status") in {"conflict", "provider_count_conflict"}
        or bool(network.get("count_conflict", False))
    ]
    required_systems = [
        system for system in registry["source_systems"] if system.get("required_for_exhaustive")
    ]
    represented_required = sum(
        row["coverage_status"] != "NOT_REPRESENTED"
        for row in matrix
        if row["required_for_exhaustive"]
    )

    fields = list(matrix[0]) if matrix else []
    with (output / "authoritative-coverage-matrix.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(matrix)

    receipt = {
        "schema": COVERAGE_SCHEMA,
        "registry_version": registry["registry_version"],
        "registry_reviewed_on": registry["reviewed_on"],
        "manifest_record_count": len(manifest),
        "manifest_air_context_count": _row_count(manifest, "air_context", "yes"),
        "manifest_candidate_for_test_count": _row_count(
            manifest, "sccaq_status", "CANDIDATE_FOR_TEST"
        ),
        "source_system_count": len(registry["source_systems"]),
        "required_source_system_count": len(required_systems),
        "required_source_systems_with_catalogue_signal": represented_required,
        "required_direct_connector_gap_count": len(required_direct_connector_gaps),
        "required_direct_connector_gaps": sorted(required_direct_connector_gaps),
        "national_network_count": len(registry["national_networks"]),
        "network_enumeration_gap_count": len(network_enumeration_gaps),
        "network_enumeration_gaps": sorted(network_enumeration_gaps),
        "network_count_conflicts": sorted(network_count_conflicts),
        "historical_revision_rule_count": len(registry.get("historical_revision_rules", [])),
        "coverage_claim": registry["coverage_policy"]["fail_closed_status"],
        "governance": {
            "review_status": "REVIEW_REQUIRED",
            "scientific_admissibility_conferred": False,
            "production_change_authorised": False,
            "canonical_provider_evidence_required": True,
            "completeness_may_be_claimed": (
                not required_direct_connector_gaps and not network_enumeration_gaps
            ),
        },
    }
    (output / "authoritative-coverage-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest")
    parser.add_argument("output")
    args = parser.parse_args(argv)
    receipt = build_air_quality_coverage_report(args.manifest, args.output)
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
