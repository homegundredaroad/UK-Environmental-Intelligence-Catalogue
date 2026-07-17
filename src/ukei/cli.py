"""Dependency-free command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from ukei import __version__
from ukei.catalogue import Catalogue, CatalogueError
from ukei.config import ConfigurationError, Settings
from ukei.logging_config import configure_logging
from ukei.models import SourceRecord, SourceStatus, make_source_id
from ukei.validation import MetadataValidator


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

    listing = subparsers.add_parser("list", help="list source records")
    listing.add_argument("--format", choices=("table", "json"), default="table")
    listing.add_argument("--status", choices=tuple(status.value for status in SourceStatus))

    show = subparsers.add_parser("show", help="show one complete source record")
    show.add_argument("source_id")

    validate = subparsers.add_parser("validate", help="run deterministic metadata checks")
    validate.add_argument("source_id", nargs="?")

    export = subparsers.add_parser("export", help="export canonical JSON")
    export.add_argument("output", type=Path)

    import_json = subparsers.add_parser("import-json", help="import canonical JSON")
    import_json.add_argument("input", type=Path)
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
            results = tuple(
                result for record in records for result in MetadataValidator().validate(record)
            )
            catalogue.record_validations(results)
            for result in results:
                marker = "PASS" if result.passed else "FAIL"
                print(f"{marker} {result.source_id} {result.check_name}: {result.message}")
            return 0 if all(result.passed for result in results) else 1
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
        return 0
    except (CatalogueError, ConfigurationError, ValueError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run())
