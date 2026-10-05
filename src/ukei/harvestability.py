"""Build a governed SCC Air Quality harvestability qualification manifest."""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlparse

SCHEMA = "ukei_scc_air_quality_harvestability_v1"
_MACHINE_FORMATS = {
    "api", "atom", "csv", "geojson", "geopackage", "gpkg", "json", "kml",
    "netcdf", "rdf", "rss", "shp", "tsv", "wfs", "wms", "xls", "xlsx", "xml", "zip",
}
_MACHINE_MIME_MARKERS = (
    "application/json", "application/geo+json", "application/xml", "text/csv", "text/xml",
    "application/vnd.google-earth.kml", "application/zip", "application/x-netcdf",
)
_AUTH_KEYS = {
    "access_token",
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "client_secret",
    "key",
    "passwd",
    "password",
    "pwd",
    "secret",
    "token",
}
ProbeFunction = Callable[[str, str, float], dict[str, Any]]


def _load_json(path: str | Path) -> dict[str, Any]:
    source = Path(path)
    opener = gzip.open if source.suffix == ".gz" else open
    with opener(source, "rt", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"{source} must contain a JSON object")
    return payload


def _normalise(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _dataset_key(record: Mapping[str, Any]) -> str:
    identity = "\0".join(
        (
            _normalise(record.get("publisher")),
            _normalise(record.get("title")),
            _normalise(record.get("geographic_scope")),
        )
    )
    return hashlib.sha256(identity.encode()).hexdigest()[:20]


def _explicit_licence(value: object) -> bool:
    text = str(value or "").strip().casefold()
    return bool(text) and text != "unknown" and not text.startswith("not supplied")


def _format_tokens(endpoint: Mapping[str, Any]) -> set[str]:
    values = [endpoint.get("format", ""), endpoint.get("media_type", ""), endpoint.get("url", "")]
    text = " ".join(str(value).casefold() for value in values)
    return {token for token in _MACHINE_FORMATS if re.search(rf"\b{re.escape(token)}\b", text)}


def _machine_readable(endpoint: Mapping[str, Any], content_type: str = "") -> bool:
    lowered = content_type.casefold()
    return bool(_format_tokens(endpoint)) or any(
        marker in lowered for marker in _MACHINE_MIME_MARKERS
    )


def _authentication(url: str) -> str:
    if "REDACTED" in url:
        return "redacted_or_required"
    parsed = urlparse(url)
    if parsed.username or parsed.password:
        return "embedded_credentials_blocked"
    keys = {key.casefold() for key, _ in parse_qsl(parsed.query, keep_blank_values=True)}
    if keys & _AUTH_KEYS:
        return "credential_parameter_present"
    return "none_observed"


def _safe_probe_url(url: str) -> bool:
    parsed = urlparse(url)
    return (
        parsed.scheme == "https"
        and bool(parsed.hostname)
        and _authentication(url) == "none_observed"
    )


def _endpoint_candidates(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    endpoints: list[dict[str, Any]] = []
    resources = record.get("resources", [])
    if isinstance(resources, list):
        for resource in resources:
            if not isinstance(resource, Mapping) or not resource.get("url"):
                continue
            endpoints.append(
                {
                    "kind": "resource",
                    "source_id": str(record.get("source_id", "")),
                    "resource_id": str(resource.get("resource_id", "")),
                    "url": str(resource.get("url", "")),
                    "format": str(resource.get("format", "")),
                    "media_type": str(resource.get("media_type", "")),
                    "name": str(resource.get("name", "")),
                    "authoritative": bool(resource.get("authoritative", False)),
                }
            )
    if record.get("url"):
        endpoints.append(
            {
                "kind": "landing_page",
                "source_id": str(record.get("source_id", "")),
                "resource_id": "",
                "url": str(record.get("url", "")),
                "format": "",
                "media_type": "",
                "name": str(record.get("title", "")),
                "authoritative": False,
            }
        )
    return endpoints


def _rank_endpoint(endpoint: Mapping[str, Any]) -> tuple[int, str]:
    score = 0
    if endpoint.get("kind") == "resource":
        score += 40
    if _machine_readable(endpoint):
        score += 35
    if endpoint.get("authoritative"):
        score += 10
    if _safe_probe_url(str(endpoint.get("url", ""))):
        score += 10
    if str(endpoint.get("format", "")).strip():
        score += 5
    return score, str(endpoint.get("url", ""))


def _validation_index(payload: Mapping[str, Any] | None) -> dict[tuple[str, str], dict[str, Any]]:
    index: dict[tuple[str, str], dict[str, Any]] = {}
    if not payload:
        return index
    sources = payload.get("sources", [])
    if not isinstance(sources, list):
        return index
    for source in sources:
        if not isinstance(source, Mapping):
            continue
        source_id = str(source.get("source_id", ""))
        results = source.get("results", [])
        if not isinstance(results, list):
            continue
        for result in results:
            if not isinstance(result, Mapping):
                continue
            check = str(result.get("check_name", ""))
            details = result.get("details", {})
            resource_id = ""
            if isinstance(details, Mapping):
                resource_id = str(details.get("resource_id", ""))
            if check == "live.url":
                index[(source_id, "")] = dict(result)
            elif check == "resource.url" and resource_id:
                index[(source_id, resource_id)] = dict(result)
    return index


def _load_relevance_csv(path: str | Path | None) -> dict[str, list[dict[str, str]]]:
    index: dict[str, list[dict[str, str]]] = {}
    if path is None:
        return index
    with Path(path).open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            source_id = str(row.get("source_id", "")).strip()
            if not source_id:
                continue
            index.setdefault(source_id, []).append(
                {
                    "stressor_id": str(row.get("stressor_id", "")),
                    "air_relevance": str(row.get("air_relevance", "")),
                    "matched_terms": str(row.get("matched_terms", "")),
                }
            )
    return index


def _default_probe(source_id: str, url: str, timeout_seconds: float) -> dict[str, Any]:
    from ukei.validation.live import bounded_url_result

    result = bounded_url_result(source_id, url, "harvestability.url", timeout_seconds)
    return result.to_dict()


def _observation(result: Mapping[str, Any] | None) -> tuple[str, str, str, str]:
    if not result:
        return "unknown", "", "", ""
    details = result.get("details", {})
    if not isinstance(details, Mapping):
        details = {}
    outcome = str(details.get("outcome", ""))
    reachable = "yes" if bool(result.get("passed")) else "no"
    return (
        reachable,
        str(details.get("content_type", "")),
        str(result.get("checked_at", "")),
        outcome,
    )


def build_harvestability_manifest(
    catalogue_path: str | Path,
    output_directory: str | Path,
    *,
    validation_path: str | Path | None = None,
    relevance_path: str | Path | None = None,
    probe: bool = False,
    probe_limit: int = 100,
    timeout_seconds: float = 6.0,
    probe_function: ProbeFunction | None = None,
) -> dict[str, Any]:
    """Qualify discovery candidates for SCC Air Quality test review without promotion."""
    if probe_limit < 0 or timeout_seconds <= 0:
        raise ValueError("probe limits must be non-negative and timeout must be positive")
    catalogue = _load_json(catalogue_path)
    records = catalogue.get("records", [])
    if not isinstance(records, list):
        raise ValueError("catalogue must contain a records list")
    validation = _load_json(validation_path) if validation_path else None
    validation_index = _validation_index(validation)
    relevance_index = _load_relevance_csv(relevance_path)
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in records:
        if isinstance(item, dict):
            groups.setdefault(_dataset_key(item), []).append(item)

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    prober = probe_function or _default_probe
    rows: list[dict[str, Any]] = []
    evidence: list[dict[str, Any]] = []
    probes_used = 0

    for dataset_key, members in sorted(groups.items()):
        endpoints = [endpoint for member in members for endpoint in _endpoint_candidates(member)]
        endpoints.sort(key=_rank_endpoint, reverse=True)
        selected = endpoints[0] if endpoints else {"url": "", "source_id": "", "resource_id": ""}
        representative = members[0]
        relevance_matches = [
            match
            for member in members
            for match in relevance_index.get(str(member.get("source_id", "")), [])
        ]
        stressor_ids = sorted(
            {match["stressor_id"] for match in relevance_matches if match["stressor_id"]}
        )
        air_relevance = sorted(
            {match["air_relevance"] for match in relevance_matches if match["air_relevance"]}
        )
        relevance_status = "MATCHED" if relevance_matches else "NO_MATCH"
        machine = _machine_readable(selected)
        evidence_result = validation_index.get(
            (str(selected.get("source_id", "")), str(selected.get("resource_id", "")))
        )
        should_probe = (
            probe
            and relevance_status == "MATCHED"
            and machine
            and probes_used < probe_limit
            and _safe_probe_url(str(selected.get("url", "")))
        )
        if should_probe:
            evidence_result = prober(
                str(selected.get("source_id", "")),
                str(selected.get("url", "")),
                timeout_seconds,
            )
            probes_used += 1
        reachable, content_type, checked_at, outcome = _observation(evidence_result)
        machine = _machine_readable(selected, content_type)
        auth = _authentication(str(selected.get("url", "")))
        licence = str(representative.get("licence", ""))
        licence_ok = _explicit_licence(licence)
        candidate_for_test = (
            relevance_status == "MATCHED"
            and reachable == "yes"
            and machine
            and licence_ok
            and auth == "none_observed"
        )
        member_ids = sorted(str(member.get("source_id", "")) for member in members)
        group_hash = hashlib.sha256(
            json.dumps(members, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        access_type = "machine_service" if machine else (
            "catalogue_landing_page" if selected.get("kind") == "landing_page" else "unknown"
        )
        reasons = []
        if relevance_status != "MATCHED":
            reasons.append("no governed pollutant/stressor relevance match")
        if not machine:
            reasons.append("no machine-readable endpoint established")
        if reachable != "yes":
            reasons.append(f"reachability {reachable}")
        if not licence_ok:
            reasons.append("licence review required")
        if auth != "none_observed":
            reasons.append(f"authentication {auth}")
        if not reasons:
            reasons.append("eligible for independent SCC Air Quality test reacquisition")
        row = {
            "dataset_key": dataset_key,
            "source_id": str(selected.get("source_id", "")),
            "provider": str(representative.get("publisher", "")),
            "dataset": str(representative.get("title", "")),
            "canonical_url": str(selected.get("url", "")),
            "access_type": access_type,
            "geography": str(representative.get("geographic_scope", "")),
            "pollutants_variables": "|".join(
                str(value) for value in representative.get("themes", []) or []
            ),
            "temporal_resolution": str(representative.get("update_frequency", "")),
            "relevance_status": relevance_status,
            "stressor_ids": "|".join(stressor_ids),
            "air_relevance": "|".join(air_relevance),
            "authentication": auth,
            "licence": licence,
            "reachable": reachable,
            "machine_readable": "yes" if machine else "no",
            "schema_verified": "no",
            "provider_verified": "no",
            "last_probe_utc": checked_at,
            "probe_outcome": outcome,
            "content_type": content_type,
            "content_hash": group_hash,
            "duplicate_count": len(members),
            "member_source_ids": "|".join(member_ids),
            "vvip_status": "REVIEW_REQUIRED",
            "sccaq_status": "CANDIDATE_FOR_TEST" if candidate_for_test else "DISCOVERED_ONLY",
            "reason": "; ".join(reasons),
        }
        rows.append(row)
        evidence.append(
            {"dataset_key": dataset_key, "selected_endpoint": selected, "members": members}
        )

    fields = list(rows[0]) if rows else [
        "dataset_key", "source_id", "provider", "dataset", "canonical_url", "access_type",
        "geography", "pollutants_variables", "temporal_resolution", "relevance_status",
        "stressor_ids", "air_relevance", "authentication", "licence",
        "reachable", "machine_readable", "schema_verified", "provider_verified", "last_probe_utc",
        "probe_outcome", "content_type", "content_hash", "duplicate_count", "member_source_ids",
        "vvip_status", "sccaq_status", "reason",
    ]
    with (output / "harvestability-manifest.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    (output / "harvestability-evidence.json").write_text(
        json.dumps({"schema": SCHEMA, "datasets": evidence}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    receipt = {
        "schema": SCHEMA,
        "generated_at_utc": datetime.now(UTC).replace(microsecond=0).isoformat(),
        "input_record_count": len(records),
        "deduplicated_dataset_count": len(rows),
        "duplicate_records_collapsed": len(records) - len(rows),
        "relevant_dataset_count": sum(row["relevance_status"] == "MATCHED" for row in rows),
        "machine_readable_count": sum(row["machine_readable"] == "yes" for row in rows),
        "reachable_count": sum(row["reachable"] == "yes" for row in rows),
        "candidate_for_test_count": sum(
            row["sccaq_status"] == "CANDIDATE_FOR_TEST" for row in rows
        ),
        "blocked_or_redacted_auth_count": sum(
            row["authentication"] != "none_observed" for row in rows
        ),
        "live_probes_performed": probes_used,
        "governance": {
            "review_status": "REVIEW_REQUIRED",
            "scientific_admissibility_conferred": False,
            "production_change_authorised": False,
            "claim_boundary": (
                "Harvestability qualification is discovery evidence only. SCC Air Quality must "
                "independently reacquire and validate original-provider evidence before use."
            ),
        },
    }
    (output / "harvestability-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("catalogue")
    parser.add_argument("output")
    parser.add_argument("--validation")
    parser.add_argument("--relevance-csv")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--probe-limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=6.0)
    args = parser.parse_args(argv)
    receipt = build_harvestability_manifest(
        args.catalogue,
        args.output,
        validation_path=args.validation,
        relevance_path=args.relevance_csv,
        probe=args.probe,
        probe_limit=args.probe_limit,
        timeout_seconds=args.timeout,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
