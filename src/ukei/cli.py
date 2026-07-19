"""Dependency-free command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from ukei import __version__
from ukei.catalogue import Catalogue, CatalogueError
from ukei.config import ConfigurationError, Settings
from ukei.discovery import ArcGisConnector, CkanConnector, DiscoveryError, run_discovery
from ukei.discovery.http import JsonHttpClient
from ukei.intelligence import build_ml_report, enrich_catalogue
from ukei.logging_config import configure_logging
from ukei.models import SourceRecord, SourceStatus, make_source_id
from ukei.seeds import load_official_seed
from ukei.validation import ResourceValidator, UrlValidator, run_validation
from ukei.validation.merge import merge_report_shards


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ukei", description="UK Environmental Intelligence Catalogue"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--database", help="override the SQLite catalogue path")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="initialise or migrate the catalogue")
    subparsers.add_parser("status", help="show catalogue status and integrity")

    add = subparsers.add_parser("add", help="add or update one source record")
    add.add_argument(
        "--id", dest="source_id", help="stable source identifier; generated if omitted"
    )
    add.add_argument("--title", required=True)
    add.add_argument("--url", required=True)
    add.add_argument("--publisher", required=True)
    add.add_argument("--description", default="")
    add.add_argument("--licence", default="unknown")
    add.add_argument("--scope", default="United Kingdom")
    add.add_argument("--frequency", default="unknown")
    add.add_argument("--format", action="append", dest="formats", default=[])
    add.add_argument("--theme", action="append", dest="themes", default=[])
    add.add_argument("--provenance-url")
    add.add_argument("--connector", default="manual")

    subparsers.add_parser("demo", help="add a clearly labelled demonstration record")

    seed = subparsers.add_parser("seed", help="load the reviewed official-source candidate set")
    seed.add_argument(
        "--dry-run", action="store_true", help="validate and list seed records without writing"
    )

    listing = subparsers.add_parser("list", help="list source records")
    listing.add_argument("--format", choices=("table", "json"), default="table")
    listing.add_argument("--status", choices=tuple(status.value for status in SourceStatus))

    show = subparsers.add_parser("show", help="show one complete source record")
    show.add_argument("source_id")

    validate = subparsers.add_parser("validate", help="run metadata and optional live checks")
    validate.add_argument("source_id", nargs="?")
    validate.add_argument("--live", action="store_true", help="perform bounded live URL checks")
    validate.add_argument(
        "--resources",
        action="store_true",
        help="validate underlying resource URLs, licence evidence and recency",
    )
    validate.add_argument(
        "--resource-limit",
        type=int,
        default=2,
        help="maximum resources checked per source (default: 2)",
    )
    validate.add_argument("--limit", type=int, help="maximum number of sources to validate")
    validate.add_argument("--offset", type=int, default=0, help="sources to skip before validation")
    validate.add_argument("--output", type=Path, help="write a machine-readable JSON report")
    validate.add_argument(
        "--report-only",
        action="store_true",
        help="return success after producing a report even when checks find failures",
    )

    export = subparsers.add_parser("export", help="export canonical JSON")
    export.add_argument("output", type=Path)

    import_json = subparsers.add_parser("import-json", help="import canonical JSON")
    import_json.add_argument("input", type=Path)

    discover = subparsers.add_parser("discover", help="discover untrusted source candidates")
    discover.add_argument("--provider", choices=("all", "ckan", "arcgis"), default="all")
    discover.add_argument("--query", default="environment")
    discover.add_argument("--limit", type=int, default=25)
    discover.add_argument("--output", type=Path, default=Path("discovery-report.json"))
    discover.add_argument(
        "--import-candidates",
        action="store_true",
        help="write discovered candidates to the local catalogue",
    )

    shard_plan = subparsers.add_parser("shard-plan", help="emit a GitHub Actions shard matrix")
    shard_plan.add_argument("--size", type=int, default=500, help="sources per shard")

    merge_shards = subparsers.add_parser("merge-shards", help="merge validation shard databases")
    merge_shards.add_argument("directory", type=Path)

    merge_reports = subparsers.add_parser("merge-reports", help="merge validation JSON reports")
    merge_reports.add_argument("directory", type=Path)
    merge_reports.add_argument("output", type=Path)

    ml = subparsers.add_parser("ml", help="run optional local clustering and anomaly detection")
    ml.add_argument("input", type=Path)
    ml.add_argument("output", type=Path)

    enrich = subparsers.add_parser("enrich", help="produce optional advisory AI classifications")
    enrich.add_argument("input", type=Path)
    enrich.add_argument("output", type=Path)
    enrich.add_argument("--provider", choices=("openai", "gemini", "both"), default="both")
    enrich.add_argument("--max-records", type=int, default=50)
    return parser


def _render_table(records: Sequence[SourceRecord]) -> str:
    headings = ("ID", "STATUS", "PUBLISHER", "TITLE")
    rows = [(r.source_id, r.status.value, r.publisher, r.title) for r in records]
    widths = [len(value) for value in headings]
    for row in rows:
        widths = [max(width, len(value)) for width, value in zip(widths, row, strict=True)]
    rendered = [
        "  ".join(value.ljust(width) for value, width in zip(headings, widths, strict=True))
    ]
    rendered.append("  ".join("-" * width for width in widths))
    rendered.extend(
        "  ".join(value.ljust(width) for value, width in zip(row, widths, strict=True))
        for row in rows
    )
    return "\n".join(rendered)


def _load_import(path: Path) -> list[dict[str, object]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogueError(f"cannot read import: {exc}") from exc
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
        raise CatalogueError("import must be a record list or an object containing a records list")
    return records


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = Settings.from_env(database_path=args.database)
        configure_logging(settings.log_level, settings.log_format)
        catalogue = Catalogue(settings.database_path)

        if args.command == "init":
            version = catalogue.initialize()
            print(f"Initialised {settings.database_path} (schema {version})")
        elif args.command == "status":
            version = catalogue.initialize()
            counts = catalogue.counts()
            errors = catalogue.integrity_errors()
            print(f"Database: {settings.database_path}")
            print(f"Schema: {version}")
            print(f"Sources: {counts['total']}")
            print(f"Validation events: {counts['validation_events']}")
            print(f"Integrity: {'PASS' if not errors else 'FAIL'}")
            if errors:
                for error in errors:
                    print(f"- {error}")
                return 1
        elif args.command == "add":
            source_id = args.source_id or make_source_id(args.title, args.publisher)
            record = SourceRecord(
                source_id=source_id,
                title=args.title,
                url=args.url,
                publisher=args.publisher,
                description=args.description,
                licence=args.licence,
                geographic_scope=args.scope,
                update_frequency=args.frequency,
                formats=tuple(args.formats),
                themes=tuple(args.themes),
                provenance_url=args.provenance_url,
                connector=args.connector,
            )
            stored = catalogue.upsert_source(record)
            print(stored.source_id)
        elif args.command == "demo":
            record = SourceRecord(
                source_id="demo-environmental-source",
                title="Demonstration environmental source (not verified)",
                url="https://example.org/environmental-data",
                publisher="Example publisher",
                description="Synthetic metadata used only to exercise the Sprint 0 catalogue.",
                licence="Demonstration only",
                formats=("JSON",),
                themes=("demonstration",),
                provenance_url="https://example.org/environmental-data/metadata",
                connector="demo",
            )
            catalogue.upsert_source(record)
            print(record.source_id)
        elif args.command == "seed":
            seed_records = load_official_seed()
            if args.dry_run:
                print(_render_table(seed_records))
                print(f"Validated {len(seed_records)} candidate seed records; no changes written")
            else:
                imported = catalogue.import_records(
                    [record.with_current_hash().to_dict() for record in seed_records]
                )
                print(f"Imported {imported} curated candidate records")
        elif args.command == "list":
            status = SourceStatus(args.status) if args.status else None
            records = catalogue.list_sources(status=status)
            if args.format == "json":
                print(
                    json.dumps([record.to_dict() for record in records], indent=2, sort_keys=True)
                )
            else:
                print(_render_table(records))
        elif args.command == "show":
            shown_record = catalogue.get_source(args.source_id)
            if shown_record is None:
                print(f"Source not found: {args.source_id}", file=sys.stderr)
                return 2
            print(json.dumps(shown_record.to_dict(), indent=2, sort_keys=True))
        elif args.command == "validate":
            if args.source_id:
                selected_record = catalogue.get_source(args.source_id)
                records = [selected_record] if selected_record is not None else []
            else:
                records = catalogue.list_sources()
            if not records:
                print("No matching sources to validate", file=sys.stderr)
                return 2
            if args.limit is not None and args.limit <= 0:
                raise ValueError("--limit must be greater than zero")
            if args.offset < 0:
                raise ValueError("--offset must not be negative")
            if args.resource_limit <= 0:
                raise ValueError("--resource-limit must be greater than zero")
            records = records[args.offset :]
            if args.limit is not None:
                records = records[: args.limit]
            if not records:
                print("No sources in requested validation range", file=sys.stderr)
                return 2
            validation_report = run_validation(
                tuple(records),
                UrlValidator(settings.http_timeout_seconds) if args.live else None,
                (
                    ResourceValidator(
                        settings.http_timeout_seconds,
                        max_resources_per_source=args.resource_limit,
                    )
                    if args.resources
                    else None
                ),
            )
            results = tuple(
                result for source in validation_report.sources for result in source.results
            )
            catalogue.record_validations(results)
            records_by_id = {record.source_id: record for record in records}
            for assessment in validation_report.sources:
                if assessment.status_after is not assessment.status_before:
                    catalogue.upsert_source(
                        replace(records_by_id[assessment.source_id], status=assessment.status_after)
                    )
            for result in results:
                marker = "PASS" if result.passed else "FAIL"
                print(f"{marker} {result.source_id} {result.check_name}: {result.message}")
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(
                    json.dumps(validation_report.to_dict(), indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
                print(f"Report: {args.output}")
            print(
                f"Validated {len(validation_report.sources)} sources; "
                f"{validation_report.to_dict()['failed_count']} require review"
            )
            return 0 if args.report_only or validation_report.all_passed else 1
        elif args.command == "export":
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(catalogue.export_records(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            print(f"Exported {catalogue.counts()['total']} records to {args.output}")
        elif args.command == "import-json":
            count = catalogue.import_records(_load_import(args.input))
            print(f"Imported {count} records")
        elif args.command == "discover":
            client = JsonHttpClient(settings.http_timeout_seconds)
            available = {
                "ckan": CkanConnector(client),
                "arcgis": ArcGisConnector(client),
            }
            selected = (
                tuple(available.values()) if args.provider == "all" else (available[args.provider],)
            )
            discovery_report = run_discovery(selected, args.query, args.limit)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(discovery_report.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            if args.import_candidates:
                imported = catalogue.import_records(
                    [candidate.source.to_dict() for candidate in discovery_report.candidates]
                )
                print(f"Imported {imported} discovered candidates")
            print(f"Discovered {len(discovery_report.candidates)} unique candidates")
            print(f"Removed {discovery_report.duplicates_removed} duplicate candidates")
            print(f"Report: {args.output}")
            for error in discovery_report.errors:
                print(f"WARNING: {error}", file=sys.stderr)
        elif args.command == "shard-plan":
            if args.size <= 0:
                raise ValueError("--size must be greater than zero")
            total = catalogue.counts()["total"]
            include = [
                {"index": index, "offset": offset, "limit": min(args.size, total - offset)}
                for index, offset in enumerate(range(0, total, args.size))
            ]
            print(json.dumps({"include": include}, separators=(",", ":")))
        elif args.command == "merge-shards":
            print(json.dumps(catalogue.merge_validation_shards(args.directory), sort_keys=True))
        elif args.command == "merge-reports":
            report = merge_report_shards(args.directory)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(f"Merged {report['source_count']} source assessments to {args.output}")
        elif args.command == "ml":
            report = build_ml_report(args.input, args.output)
            print(f"Analysed {report['record_count']} records to {args.output}")
        elif args.command == "enrich":
            report = enrich_catalogue(
                args.input, args.output, provider=args.provider, max_records=args.max_records
            )
            print(f"Generated {len(report['rows'])} advisory classifications to {args.output}")
        return 0
    except (
        CatalogueError,
        ConfigurationError,
        DiscoveryError,
        RuntimeError,
        ValueError,
        OSError,
    ) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())
