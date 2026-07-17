from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from email.message import Message
from pathlib import Path
from urllib.error import URLError

import pytest

from ukei.catalogue import Catalogue
from ukei.cli import run
from ukei.models import ResourceReference, SourceRecord


class LiveResponse(io.BytesIO):
    status = 200

    def __init__(self) -> None:
        super().__init__(b"x")
        self.headers = Message()

    def __enter__(self) -> LiveResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def geturl(self) -> str:
        return "https://example.org/data"


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "catalogue.sqlite3"


def test_init_and_status(database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--database", str(database), "init"]) == 0
    assert run(["--database", str(database), "status"]) == 0
    output = capsys.readouterr().out
    assert "schema 2" in output
    assert "Integrity: PASS" in output


def test_add_list_show_and_validate(database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--database", str(database)]
    assert (
        run(
            [
                *base,
                "add",
                "--title",
                "Test data",
                "--url",
                "https://example.org/data",
                "--publisher",
                "Test publisher",
                "--licence",
                "OGL-3.0",
                "--provenance-url",
                "https://example.org/metadata",
                "--format",
                "CSV",
            ]
        )
        == 0
    )
    source_id = capsys.readouterr().out.strip()
    assert run([*base, "list"]) == 0
    assert source_id in capsys.readouterr().out
    assert run([*base, "show", source_id]) == 0
    shown = json.loads(capsys.readouterr().out)
    assert shown["formats"] == ["CSV"]
    assert run([*base, "validate", source_id]) == 0
    assert "PASS" in capsys.readouterr().out


def test_demo_is_explicit_and_reproducible(
    database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--database", str(database)]
    assert run([*base, "demo"]) == 0
    assert run([*base, "demo"]) == 0
    capsys.readouterr()
    assert run([*base, "list", "--format", "json"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert len(records) == 1
    assert "not verified" in records[0]["title"].lower()


def test_seed_dry_run_does_not_write(database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--database", str(database)]
    assert run([*base, "seed", "--dry-run"]) == 0
    output = capsys.readouterr().out
    assert "Validated 8 candidate seed records" in output
    assert not database.exists()


def test_seed_is_idempotent_and_remains_candidate(
    database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--database", str(database)]
    assert run([*base, "seed"]) == 0
    assert run([*base, "seed"]) == 0
    capsys.readouterr()
    assert run([*base, "list", "--format", "json", "--status", "candidate"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert len(records) == 8
    assert all(record["status"] == "candidate" for record in records)


def test_export_import(database: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--database", str(database)]
    export_path = tmp_path / "exports" / "catalogue.json"
    assert run([*base, "demo"]) == 0
    assert run([*base, "export", str(export_path)]) == 0
    payload = json.loads(export_path.read_text(encoding="utf-8"))
    assert payload["record_count"] == 1
    imported_database = tmp_path / "imported.sqlite3"
    assert run(["--database", str(imported_database), "import-json", str(export_path)]) == 0
    capsys.readouterr()
    assert run(["--database", str(imported_database), "status"]) == 0
    assert "Sources: 1" in capsys.readouterr().out


def test_missing_and_invalid_inputs(database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = ["--database", str(database)]
    assert run([*base, "show", "missing-source"]) == 2
    assert run([*base, "validate", "missing-source"]) == 2
    assert (
        run(
            [
                *base,
                "add",
                "--title",
                "Bad",
                "--url",
                "not-a-url",
                "--publisher",
                "Test",
            ]
        )
        == 2
    )
    assert "ERROR" in capsys.readouterr().err


def test_invalid_import(database: Path, tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text('{"not_records": true}', encoding="utf-8")
    assert run(["--database", str(database), "import-json", str(invalid)]) == 2


def test_incomplete_demo_validation_fails_when_metadata_is_unknown(
    database: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    base = ["--database", str(database)]
    assert (
        run(
            [
                *base,
                "add",
                "--id",
                "incomplete-source",
                "--title",
                "Incomplete",
                "--url",
                "http://example.org/data",
                "--publisher",
                "Example",
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert run([*base, "validate", "incomplete-source"]) == 1
    assert "FAIL" in capsys.readouterr().out


def test_live_validation_writes_report_without_promoting(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = ["--database", str(database)]
    assert run([*base, "seed"]) == 0
    capsys.readouterr()
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: LiveResponse())
    report_path = tmp_path / "reports" / "validation.json"
    assert (
        run(
            [
                *base,
                "validate",
                "--live",
                "--limit",
                "2",
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["live"] is True
    assert report["checked_count"] == 2
    assert all(source["status_after"] == "candidate" for source in report["sources"])


def test_live_failure_degrades_and_report_only_returns_success(
    database: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = ["--database", str(database)]
    assert run([*base, "demo"]) == 0
    source_id = capsys.readouterr().out.strip()

    def offline(*_args: object, **_kwargs: object) -> None:
        raise URLError("offline")

    monkeypatch.setattr("ukei.validation.live.urlopen", offline)
    report_path = tmp_path / "validation.json"
    assert (
        run(
            [
                *base,
                "validate",
                source_id,
                "--live",
                "--report-only",
                "--output",
                str(report_path),
            ]
        )
        == 0
    )
    capsys.readouterr()
    assert run([*base, "list", "--format", "json", "--status", "degraded"]) == 0
    records = json.loads(capsys.readouterr().out)
    assert [record["source_id"] for record in records] == [source_id]


def test_validate_rejects_nonpositive_limit(database: Path) -> None:
    assert run(["--database", str(database), "demo"]) == 0
    assert run(["--database", str(database), "validate", "--limit", "0"]) == 2
    assert run(["--database", str(database), "validate", "--resource-limit", "0"]) == 2


def test_resource_validation_cli_writes_schema_two_report(
    database: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = datetime(2026, 7, 1, tzinfo=UTC)
    resource = ResourceReference(
        resource_id="csv-1",
        url="https://example.org/data.csv",
        name="Data",
        format="CSV",
        licence="OGL-3.0",
        last_modified=timestamp,
        provenance_url="https://example.org/metadata",
    )
    Catalogue(database).upsert_source(
        SourceRecord(
            source_id="resource-cli-source",
            title="Resource CLI source",
            url="https://example.org/catalogue",
            publisher="Example",
            description="CLI fixture",
            licence="OGL-3.0",
            update_frequency="monthly",
            formats=("CSV",),
            themes=("environment",),
            resources=(resource,),
            provenance_url="https://example.org/metadata",
        )
    )
    monkeypatch.setattr("ukei.validation.live.urlopen", lambda *_args, **_kwargs: LiveResponse())
    output = tmp_path / "resource-report.json"
    assert (
        run(
            [
                "--database",
                str(database),
                "validate",
                "--resources",
                "--report-only",
                "--output",
                str(output),
            ]
        )
        == 0
    )
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["report_version"] == 2
    assert report["resource_count"] == 1
    assert report["resources"] is True
