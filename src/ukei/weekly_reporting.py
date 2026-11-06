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
        (
            metrics["reachable"],
            sum(r.get("reachable") == "yes" for r in manifest),
            "reachable count",
        ),
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


def _actions(state: dict[str, Any]) -> list[dict[str, str]]:
    metrics = state["metrics"]
    actions = [
        {"priority": "P0", "gate": "Official data connectors",
         "finding": f"{metrics['adapters_missing']} required direct adapters absent",
         "evidence_needed": "Provider-native endpoint, bounded test and exact schema receipt"},
        {"priority": "P0", "gate": "Monitoring network coverage",
         "finding": f"{metrics['networks_missing']} inventories lack reconciled stations",
         "evidence_needed": "Current and closed stations, native IDs and dated registry snapshots"},
        {"priority": "P0", "gate": "Transport security",
         "finding": f"{metrics['policy']} blocked URLs; not confirmed missing",
         "evidence_needed": "Source-verified redirect origins and secure allowlist review"},
        {"priority": "P1", "gate": "Historical integrity",
         "finding": "Historical year-by-network completeness not demonstrated",
         "evidence_needed": "Original files, versions, checksums, stations and date grids"},
        {"priority": "P1", "gate": "Scientific admissibility",
         "finding": "Independent measurement validation and corroboration incomplete",
         "evidence_needed": "Raw observations, units, QA flags, second-method reproduction"},
        {"priority": "P1", "gate": "External peer scrutiny",
         "finding": "Scientific publication approval not present",
         "evidence_needed": "Named reviewer assessment, limitations and recorded sign-off"},
    ]
    if state["stale"]:
        actions.insert(0, {
            "priority": "P0", "gate": "Evidence freshness",
            "finding": "Last harvestability receipt is older than seven days",
            "evidence_needed": "New source acquisition and reconciled checksum receipt",
        })
    return actions


def _markdown(
    state: dict[str, Any],
    week: str,
    previous: dict[str, Any] | None,
    changes: dict[str, int] | None,
    *,
    reviewer: bool,
) -> str:
    metrics = state["metrics"]
    actions = _actions(state)
    lines = [
        "# SCC Nexus Limited — UK Environmental Intelligence",
        f"**Weekly review:** {week} | **Evidence as of:** {state['evidence_as_of']}",
        "",
        "## Executive summary",
        f"- **{metrics['datasets']:,}** distinct catalogue candidates, of which only "
        f"**{metrics['eligible']:,}** currently qualify for independent testing.",
        f"- **{metrics['policy']:,}** source endpoints were blocked by network policy; "
        "they have not been established as missing or permanently inaccessible.",
        f"- **{metrics['adapters_missing']}** official direct adapters and "
        f"**{metrics['networks_missing']}** monitoring-network enumerations remain missing.",
        "- **Scientific decision: HOLD.** No claim of national completeness, "
        "scientific admissibility, exposure effects or historical data accuracy.",
        f"- Evidence age: **{state['age_days']:.1f} days** — "
        f"{'STALE' if state['stale'] else 'within 7-day reporting threshold'}.",
        "",
        "## Harvestability and coverage",
        "| Measure | Latest count | Change from prior distinct week |",
        "|---|---:|---:|",
    ]
    for key, label in METRICS.items():
        delta = "Not available" if changes is None else f"{changes[key]:+d}"
        lines.append(f"| {label} | {metrics[key]:,} | {delta} |")
    lines.extend(["", "## Priority recommendations"])
    for action in actions[:5]:
        lines.append(
            f"- **{action['priority']} — {action['gate']}:** {action['finding']}. "
            f"Evidence needed: {action['evidence_needed']}."
        )
    lines.extend([
        "",
        "## SCC and VVIP claim boundary",
        "SCC = Search, Corroborate, Communicate. VVIP = Validation, Verification, "
        "Integrity, Provenance. Discovery and software checks do not grant scientific "
        "publication permission. SCC Air Quality reacquires and validates evidence "
        "independently in its separate project.",
    ])
    if not reviewer:
        return "\n".join(lines) + "\n"
    coverage = state["coverage"]
    catalogue = state["catalogue"]
    lines.extend([
        "",
        "---",
        "## Independent technical and scientific reviewer appendix",
        "",
        "### 1. Acquisition provenance and evidence vintage",
        f"The underlying focused discovery retained "
        f"{catalogue.get('successful_query_count', 'unknown')} successful searches "
        f"from {catalogue.get('targeted_query_count', 'unknown')} queries. "
        "These are from the original recorded discovery run, not fresh weekly observations.",
        "A weekly report run reads previously committed files only. It does not prove "
        "any original-provider API or environmental station has been updated this week.",
        f"Previous comparable week: "
        f"{previous['week'] if previous and changes is not None else 'none available'}.",
        "",
        "### 2. Authoritative source connector gaps",
        "| Direct source adapter ID | Status |",
        "|---|---|",
    ])
    lines.extend(
        f"| {md_cell(item)} | MISSING |"
        for item in coverage["required_direct_connector_gaps"]
    )
    lines.extend([
        "",
        "### 3. Unreconciled monitoring network inventories",
        "| Network ID | Status |",
        "|---|---|",
    ])
    lines.extend(
        f"| {md_cell(item)} | NOT ENUMERATED |"
        for item in coverage["network_enumeration_gaps"]
    )
    lines.extend([
        "",
        "### 4. Network metadata signals",
        "| Source system | Jurisdiction | Direct adapter | Catalogue signals | Reachable signals |",
        "|---|---|---|---:|---:|",
    ])
    for row in state["matrix"]:
        lines.append(
            f"| {md_cell(row.get('source_system_id', ''))} "
            f"| {md_cell(row.get('jurisdiction', ''))} "
            f"| {md_cell(row.get('direct_connector_status', ''))} "
            f"| {md_cell(row.get('catalogue_record_matches', ''))} "
            f"| {md_cell(row.get('reachable_matches', ''))} |"
        )
    lines.extend([
        "",
        "### 5. Policy-blocked sources by publisher and category",
        "Safety denials remain UNKNOWN reachability. They must never be automatically "
        "unblocked, counted as dataset losses or promoted to research-ready.",
        "| Publisher | Blocked |",
        "|---|---:|",
    ])
    providers = Counter(row.get("provider", "Unknown") for row in state["policy"])
    lines.extend(f"| {md_cell(k)} | {v} |" for k, v in sorted(providers.items()))
    lines.extend(["", "| Safety category | Count |", "|---|---:|"])
    categories = Counter(row.get("policy_block_category", "Unknown") for row in state["policy"])
    lines.extend(f"| {md_cell(k)} | {v} |" for k, v in sorted(categories.items()))
    lines.extend([
        "",
        "### 6. Historical and scientific interpretation safeguards",
        "- Reconcile UK-AIR, devolved and local records against native station and network IDs.",
        "- Audit yearly completeness, start/end dates, missing intervals, revisions, "
        "retrospective corrections, UTC/BST transitions, units and measurement methods.",
        "- Check ratified versus provisional data, source licences and reuse restrictions.",
        "- Validate row-level observation files using independent tools and researchers.",
        "- Do not treat a year-index URL, successful HTTP request, metadata title or "
        "automated QA gate as a complete historical time series.",
        f"- Registry references {coverage.get('historical_revision_rule_count', 'unknown')} "
        "historical revision rules; these are not evidence of fully exercised checks.",
        "",
        "### 7. Verified-input SHA-256 fingerprints",
        "| Source type | SHA-256 |",
        "|---|---|",
    ])
    lines.extend(
        f"| {key} | {digest} |" for key, digest in sorted(state["digests"].items())
    )
    lines.extend([
        "",
        "### 8. Reviewer evidence requests",
        "| Priority | Review gate | Current limitation | Required new evidence |",
        "|---|---|---|---|",
    ])
    lines.extend(
        f"| {md_cell(item['priority'])} | {md_cell(item['gate'])} "
        f"| {md_cell(item['finding'])} | {md_cell(item['evidence_needed'])} |"
        for item in actions
    )
    lines.extend([
        "",
        "### 9. Publication and independent scrutiny",
        "A named scientific reviewer must examine original observations, reproduce "
        "findings, approve licensing and limitations, and record an explicit decision. "
        "This report does not constitute that approval.",
        "The accompanying machine-readable receipt, snapshot, summary metrics, "
        "gap register and bundle manifest support independent inspection.",
        "",
    ])
    return "\n".join(lines)


def _dashboard(state: dict[str, Any], week: str, changes: dict[str, int] | None) -> str:
    m = state["metrics"]
    def esc(value: object) -> str:
        return html.escape(str(value), quote=True)
    tiles = [
        ("Catalogued datasets", m["datasets"], "Discovery only"),
        ("Reachable endpoints", m["reachable"], "Not schema-verified"),
        ("Policy blocks", m["policy"], "Unknown, under review"),
        ("Independent-test candidates", m["eligible"], "Not research-ready"),
        ("Missing adapters", m["adapters_missing"], "Official provider access"),
        ("Network gaps", m["networks_missing"], "Station-level enumeration"),
    ]
    cards = "\n".join(
        "<article class='tile'><span>" + esc(label) + "</span><strong>"
        + f"{value:,}" + "</strong><small>" + esc(note) + "</small></article>"
        for label, value, note in tiles
    )
    table = "\n".join(
        "<tr><th scope='row'>" + esc(label) + "</th><td>"
        + f"{m[key]:,}" + "</td><td>"
        + ("No baseline" if changes is None else f"{changes[key]:+d}")
        + "</td></tr>" for key, label in METRICS.items()
    )
    actions = "\n".join(
        "<li><strong>" + esc(item["gate"]) + "</strong>: " + esc(item["finding"])
        + "<small>" + esc(item["evidence_needed"]) + "</small></li>"
        for item in _actions(state)
    )
    return f"""<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SCC Nexus | Environmental Weekly {esc(week)}</title>
<style>
:root{{--navy:#172846;--gold:#b69a5c;--line:#dce3e9;--muted:#5c6878}}
*{{box-sizing:border-box}}
body{{margin:0;background:#fff;color:#1e2f42;font:16px/1.5 system-ui,sans-serif}}
header{{background:var(--navy);color:white;padding:2rem max(1.25rem,calc((100vw - 1060px)/2))}}
.brand{{letter-spacing:.12em;color:#ecd5a4;font-weight:800;font-size:.85rem}}
h1{{font-size:clamp(1.8rem,4vw,2.7rem);max-width:23ch;line-height:1.2}}
header p{{color:#dfe7f0;max-width:70ch}}
main{{max-width:1060px;margin:auto;padding:1rem 1.2rem 4rem}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:1rem}}
 .tile{{background:#f5f6f8;border:1px solid var(--line);border-radius:12px;
 padding:1rem;display:flex;flex-direction:column}}
 .tile strong{{font-size:2.3rem;color:var(--navy)}}
small{{color:var(--muted)}}.tile small{{display:block}}
h2{{margin-top:2.2rem;border-bottom:2px solid var(--gold);padding-bottom:.3rem}}
.hold{{background:#fbf6ea;border-left:5px solid var(--gold);padding:1rem}}
.table-scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}}
th,td{{text-align:left;border-bottom:1px solid var(--line);padding:.5rem}}
th:not(:first-child),td:not(:first-child){{text-align:right}}
li{{margin:.7rem 0}}li small{{display:block}}
footer{{border-top:1px solid var(--line);color:var(--muted);margin-top:2rem;padding-top:1rem}}
@media print{{.tile{{break-inside:avoid}}header{{print-color-adjust:exact}}}}
</style></head><body>
<header><div class="brand">SCC NEXUS LIMITED · SEARCH / CORROBORATE / COMMUNICATE</div>
<h1>UK Environmental Intelligence — Weekly Evidence Review</h1>
<p>Week {esc(week)} · Source evidence as of {esc(state['evidence_as_of'])} ·
{esc('STALE' if state['stale'] else 'within 7-day freshness threshold')}</p></header>
<main><section><h2>Executive position</h2>
<p class="hold"><strong>Scientific release: HOLD.</strong> Source discovery,
URL reachability and software checks do not establish scientific quality,
national coverage, exposure or health outcomes.</p>
<div class="tiles">{cards}</div></section>
<section><h2>All tracked metrics</h2>
<p>Differences require an earlier distinct reporting week;
a missing baseline is not zero change.</p>
<div class="table-scroll"><table><thead><tr><th>Metric</th><th>Latest</th><th>Weekly difference</th>
</tr></thead><tbody>{table}</tbody></table></div></section>
<section><h2>Priority reviewer actions</h2><ol>{actions}</ol></section>
<footer><strong>SCC/VVIP</strong> · Validation · Verification · Integrity · Provenance.
Original-provider reacquisition and independent human approval required. The complete
scientific reviewer appendix, input hashes and machine-readable receipt are in this report pack.
The separate SCC Air Quality repository is not modified.</footer></main></body></html>"""


def build_weekly(
    root: Path,
    output: Path,
    *,
    archive: Path | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    timestamp = (now or datetime.now(UTC)).astimezone(UTC)
    iso = timestamp.isocalendar()
    week = f"{iso.year}-W{iso.week:02d}"
    state = gather(root, timestamp)
    prior = previous_week(archive, week)
    prior_metrics = prior.get("metrics") if prior else None
    changes = (
        {key: value - prior_metrics[key] for key, value in state["metrics"].items()}
        if isinstance(prior_metrics, dict)
        and all(type(prior_metrics.get(key)) is int for key in state["metrics"])
        else None
    )
    output.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schema": SCHEMA, "week": week, "metrics": state["metrics"],
        "evidence_as_of": state["evidence_as_of"], "source_digests": state["digests"],
        "scientific_release": "HOLD", "national_completeness": "NOT_VERIFIED",
    }
    snap_bytes = (json.dumps(snapshot, sort_keys=True, indent=2) + "\n").encode()
    (output / "snapshot.json").write_bytes(snap_bytes)
    (output / "public-summary.md").write_text(
        _markdown(state, week, prior, changes, reviewer=False), encoding="utf-8"
    )
    (output / "reviewer-report.md").write_text(
        _markdown(state, week, prior, changes, reviewer=True), encoding="utf-8"
    )
    (output / "dashboard.html").write_text(
        _dashboard(state, week, changes), encoding="utf-8"
    )
    write_csv(
        output / "metrics.csv",
        ("metric_id", "measure", "value", "previous_week_change", "evidence_as_of"),
        [{"metric_id": key, "measure": label, "value": state["metrics"][key],
          "previous_week_change": "" if changes is None else changes[key],
          "evidence_as_of": state["evidence_as_of"]} for key, label in METRICS.items()],
    )
    coverage = state["coverage"]
    gaps = (
        [{"priority": "P0", "kind": "direct_adapter", "identifier": item, "status": "MISSING"}
         for item in coverage["required_direct_connector_gaps"]]
        + [{"priority": "P0", "kind": "station_inventory", "identifier": item,
            "status": "NOT_ENUMERATED"} for item in coverage["network_enumeration_gaps"]]
    )
    write_csv(output / "gap-register.csv", ("priority", "kind", "identifier", "status"), gaps)
    write_csv(
        output / "action-register.csv",
        ("priority", "gate", "finding", "evidence_needed"), _actions(state)
    )
    receipt = {
        "schema": SCHEMA, "report_week": week, "generated_at_utc": timestamp.isoformat(),
        "evidence_as_of": state["evidence_as_of"],
        "evidence_age_days": state["age_days"],
        "freshness_status": "STALE" if state["stale"] else "WITHIN_SEVEN_DAYS",
        "comparison_week": prior["week"] if changes is not None and prior else None,
        "comparisons_supported": changes is not None, "changes": changes,
        "metrics": state["metrics"], "source_sha256": state["digests"],
        "snapshot_sha256": sha(snap_bytes),
        "technical_reporting_gate": "PASS", "scientific_release": "HOLD",
        "national_completeness": "NOT_VERIFIED",
        "scientific_publication_approved": False,
        "external_review_completed": False,
        "sibling_repositories_modified": False,
        "vvip": {"validation": "INDEPENDENT_TEST_REQUIRED",
                 "verification": "INDEPENDENT_REACQUISITION_REQUIRED",
                 "integrity": "CHECKSUM_RECONCILED",
                 "provenance": "INPUT_DIGESTS_ATTACHED"},
    }
    (output / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    hashes = {
        p.name: sha(p.read_bytes())
        for p in sorted(output.iterdir())
        if p.is_file() and p.name != "bundle-manifest.json"
    }
    (output / "bundle-manifest.json").write_text(
        json.dumps({"schema": "scc-weekly-artifact-manifest/1", "week": week,
                    "file_sha256": hashes, "human_approval_present": False},
                   indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="SCC Nexus weekly UK Environmental Intelligence reporting"
    )
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    args = parser.parse_args(argv)
    print(json.dumps(build_weekly(args.root, args.output, archive=args.archive), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
