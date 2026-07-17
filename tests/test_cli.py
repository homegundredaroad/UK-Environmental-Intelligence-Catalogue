from __future__ import annotations

import json
from pathlib import Path

import pytest

from ukei.cli import run


@pytest.fixture
def database(tmp_path: Path) -> Path:
    return tmp_path / "catalogue.sqlite3"


def test_init_and_status(database: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run(["--database", str(database), "init"]) == 0
    assert run(["--database", str(database), "status"]) == 0
    output = capsys.readouterr().out
    assert "schema 1" in output
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
