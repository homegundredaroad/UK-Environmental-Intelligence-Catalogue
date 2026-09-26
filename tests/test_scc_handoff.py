import gzip
import json
from pathlib import Path

from pytest import CaptureFixture

from ukei.scc_handoff import _redact_url, _sanitise, build_handoff, main


def test_redact_url_leaves_non_url_and_plain_url_unchanged() -> None:
    assert _redact_url("plain text") == ("plain text", 0)
    assert _redact_url("https://example.test/data?x=1") == (
        "https://example.test/data?x=1",
        0,
    )


def test_redact_url_still_redacts_token_on_malformed_port() -> None:
    value = "https://example.test:notaport/data?token=secret"
    cleaned, count = _redact_url(value)
    assert cleaned == "https://example.test:notaport/data?token=REDACTED"
    assert count == 1


def test_sanitise_nested_values() -> None:
    value = {
        "items": [
            "https://example.test/a?token=abc",
            {"url": "https://example.test/b?x=1"},
            42,
        ]
    }
    cleaned, count = _sanitise(value)
    assert count == 1
    assert cleaned["items"][0] == "https://example.test/a?token=REDACTED"
    assert cleaned["items"][1]["url"] == "https://example.test/b?x=1"
    assert cleaned["items"][2] == 42


def test_handoff_redacts_sensitive_urls(tmp_path: Path) -> None:
    catalogue = {
        "records": [
            {
                "source_id": "x",
                "url": "https://example.test/data?api_key=secret&x=1",
                "resources": [{"url": "https://u:p@example.test/file.csv?token=abc"}],
            }
        ]
    }
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps(catalogue), encoding="utf-8")
    receipt = build_handoff(source, tmp_path / "out", upstream_run_id="123")
    assert receipt["security"]["sensitive_url_values_redacted"] == 3
    raw = gzip.decompress((tmp_path / "out" / "focused-catalogue.json.gz").read_bytes()).decode()
    assert "secret" not in raw
    assert "token=abc" not in raw
    assert "u:p@" not in raw
    assert "REDACTED" in raw
    assert receipt["catalogue"]["record_count"] == 1
    assert receipt["governance"]["scientific_admissibility_conferred"] is False


def test_handoff_copies_validation_and_run_receipt(tmp_path: Path) -> None:
    catalogue = {"schema_version": "1", "records": []}
    validation = {"sources": [{"url": "https://example.test/check?password=secret"}]}
    run_receipt = {"receipt_version": 2, "review_status": "REVIEW_REQUIRED"}
    source = tmp_path / "catalogue.json"
    validation_path = tmp_path / "validation.json"
    run_receipt_path = tmp_path / "run-receipt.json"
    source.write_text(json.dumps(catalogue), encoding="utf-8")
    validation_path.write_text(json.dumps(validation), encoding="utf-8")
    run_receipt_path.write_text(json.dumps(run_receipt), encoding="utf-8")

    receipt = build_handoff(
        source,
        tmp_path / "out",
        validation_path=validation_path,
        run_receipt_path=run_receipt_path,
        upstream_run_id="11",
        upstream_artifact_id="22",
        upstream_artifact_digest="sha256:abc",
    )

    assert receipt["validation"] is not None
    assert receipt["security"]["validation_redactions"] == 1
    assert receipt["upstream_run_id"] == "11"
    assert receipt["upstream_artifact_id"] == "22"
    assert receipt["upstream_artifact_digest"] == "sha256:abc"
    copied = json.loads((tmp_path / "out" / "run-receipt.json").read_text())
    assert copied == run_receipt
    validation_raw = gzip.decompress(
        (tmp_path / "out" / "focused-validation-report.json.gz").read_bytes()
    ).decode()
    assert "secret" not in validation_raw
    assert "REDACTED" in validation_raw


def test_main_builds_receipt(tmp_path: Path, capsys: CaptureFixture[str]) -> None:
    source = tmp_path / "catalogue.json"
    source.write_text(json.dumps({"records": []}), encoding="utf-8")
    output = tmp_path / "out"

    rc = main(
        [
            "--catalogue",
            str(source),
            "--output",
            str(output),
            "--upstream-run-id",
            "99",
        ]
    )

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["upstream_run_id"] == "99"
    assert (output / "handoff-receipt.json").exists()
