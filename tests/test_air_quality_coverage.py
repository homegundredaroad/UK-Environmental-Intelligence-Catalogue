from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from ukei import air_quality_coverage


EXPECTED_NETWORKS = {
    "aurn",
    "locally-managed-automatic",
    "automatic-hydrocarbon",
    "nonautomatic-hydrocarbon",
    "pah",
    "tomps",
    "black-carbon",
    "heavy-metals",
    "particle-concentrations-numbers",
    "stratospheric-ozone-uv",
    "precip-net",
    "acid-gas-aerosol",
    "rural-no2",
    "national-ammonia",
    "marga",
    "automatic-mercury",
    "urban-no2",
}

EXPECTED_REQUIRED_SYSTEMS = {
    "ukair-sos",
    "ukair-data-archive",
    "defra-get-air-pollution-data",
    "ukair-locally-managed",
    "laqm-central",
    "scottish-air-quality-api",
    "wales-air-sos",
    "wales-air-atom",
    "ni-air-sos",
    "ni-air-spatial-register",
    "londonair-api",
    "air-quality-england",
    "breathe-london-api",
    "actris-data-portal",
    "ceda-moles",
}


def _write_manifest(path: Path) -> None:
    fields = [
        "provider",
        "dataset",
        "canonical_url",
        "member_source_ids",
        "air_context",
        "machine_readable",
        "reachable",
        "sccaq_status",
    ]
    rows = [
        {
            "provider": "Department for Environment, Food and Rural Affairs",
            "dataset": "AURN hourly air quality",
            "canonical_url": "https://uk-air.defra.gov.uk/data/",
            "member_source_ids": "defra-aurn",
            "air_context": "yes",
            "machine_readable": "yes",
            "reachable": "yes",
            "sccaq_status": "CANDIDATE_FOR_TEST",
        },
        {
            "provider": "Greater London Authority",
            "dataset": "London air quality monitoring stations",
            "canonical_url": "https://www.londonair.org.uk/",
            "member_source_ids": "laqn",
            "air_context": "yes",
            "machine_readable": "yes",
            "reachable": "yes",
            "sccaq_status": "DISCOVERED_ONLY",
        },
        {
            "provider": "Unrelated",
            "dataset": "River chemistry",
            "canonical_url": "https://example.test/river.csv",
            "member_source_ids": "river",
            "air_context": "no",
            "machine_readable": "yes",
            "reachable": "yes",
            "sccaq_status": "DISCOVERED_ONLY",
        },
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def test_registry_covers_required_source_systems_and_national_networks() -> None:
    registry = air_quality_coverage.load_coverage_registry()
    systems = {system["id"]: system for system in registry["source_systems"]}
    networks = {network["id"]: network for network in registry["national_networks"]}

    assert set(networks) == EXPECTED_NETWORKS
    assert {
        source_id
        for source_id, system in systems.items()
        if system["required_for_exhaustive"]
    } >= EXPECTED_REQUIRED_SYSTEMS
    assert systems["breathe-london-api"]["quality_tier"] == "LOW_COST_SENSOR"
    assert systems["openair-ukaq"]["quality_tier"] == "DERIVED_TOOL"
    assert networks["national-ammonia"]["enumeration_status"] == "MISSING"
    assert registry["coverage_policy"]["fail_closed_status"].startswith("INCOMPLETE_")


def test_registry_validation_fails_closed() -> None:
    with pytest.raises(ValueError, match="registry_version"):
        air_quality_coverage.validate_coverage_registry({})
    with pytest.raises(ValueError, match="source_systems"):
        air_quality_coverage.validate_coverage_registry(
            {"registry_version": 1, "source_systems": [], "national_networks": []}
        )

    bad_system = {
        "registry_version": 1,
        "source_systems": [
            {
                "id": "x",
                "quality_tier": "BAD",
                "canonical_url": "https://example.test",
                "required_for_exhaustive": True,
                "catalogue_match_patterns": [],
            }
        ],
        "national_networks": [
            {
                "id": "n",
                "source_system": "x",
                "quality_tier": "STATUTORY_REFERENCE",
                "enumeration_status": "MISSING",
            }
        ],
    }
    with pytest.raises(ValueError, match="quality tier"):
        air_quality_coverage.validate_coverage_registry(bad_system)


def test_coverage_report_exposes_connector_and_network_gaps(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest)
    receipt = air_quality_coverage.build_air_quality_coverage_report(manifest, tmp_path / "out")

    assert receipt["manifest_record_count"] == 3
    assert receipt["manifest_air_context_count"] == 2
    assert receipt["manifest_candidate_for_test_count"] == 1
    assert receipt["required_direct_connector_gap_count"] == len(EXPECTED_REQUIRED_SYSTEMS)
    assert set(receipt["required_direct_connector_gaps"]) == EXPECTED_REQUIRED_SYSTEMS
    assert receipt["network_enumeration_gap_count"] == len(EXPECTED_NETWORKS)
    assert set(receipt["network_enumeration_gaps"]) == EXPECTED_NETWORKS
    assert receipt["governance"]["completeness_may_be_claimed"] is False
    assert receipt["governance"]["scientific_admissibility_conferred"] is False

    matrix = list(
        csv.DictReader(
            (tmp_path / "out" / "authoritative-coverage-matrix.csv").open(
                newline="", encoding="utf-8"
            )
        )
    )
    ukair = next(row for row in matrix if row["source_system_id"] == "ukair-sos")
    london = next(row for row in matrix if row["source_system_id"] == "londonair-api")
    breathe = next(row for row in matrix if row["source_system_id"] == "breathe-london-api")
    assert ukair["coverage_status"] == "CATALOGUE_SIGNAL_ONLY"
    assert ukair["catalogue_record_matches"] == "1"
    assert london["coverage_status"] == "CATALOGUE_SIGNAL_ONLY"
    assert breathe["coverage_status"] == "NOT_REPRESENTED"


def test_validation_rejects_duplicate_unknown_and_bad_network_status() -> None:
    base_system = {
        "id": "x",
        "quality_tier": "STATUTORY_REFERENCE",
        "canonical_url": "https://example.test",
        "required_for_exhaustive": True,
        "catalogue_match_patterns": [],
    }
    duplicate = {
        "registry_version": 1,
        "source_systems": [base_system, dict(base_system)],
        "national_networks": [
            {
                "id": "n",
                "source_system": "x",
                "quality_tier": "STATUTORY_REFERENCE",
                "enumeration_status": "MISSING",
            }
        ],
    }
    with pytest.raises(ValueError, match="unique"):
        air_quality_coverage.validate_coverage_registry(duplicate)

    unknown = {
        "registry_version": 1,
        "source_systems": [base_system],
        "national_networks": [
            {
                "id": "n",
                "source_system": "missing",
                "quality_tier": "STATUTORY_REFERENCE",
                "enumeration_status": "MISSING",
            }
        ],
    }
    with pytest.raises(ValueError, match="unknown"):
        air_quality_coverage.validate_coverage_registry(unknown)

    bad_status = {
        "registry_version": 1,
        "source_systems": [base_system],
        "national_networks": [
            {
                "id": "n",
                "source_system": "x",
                "quality_tier": "STATUTORY_REFERENCE",
                "enumeration_status": "MAYBE",
            }
        ],
    }
    with pytest.raises(ValueError, match="enumeration_status"):
        air_quality_coverage.validate_coverage_registry(bad_status)


def test_main_writes_machine_readable_receipt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest)
    assert air_quality_coverage.main([str(manifest), str(tmp_path / "cli")]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["schema"] == "ukei_scc_air_quality_coverage_v1"
    assert (tmp_path / "cli" / "authoritative-coverage-receipt.json").exists()
