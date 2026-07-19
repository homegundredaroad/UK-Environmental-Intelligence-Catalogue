from __future__ import annotations

import json
from pathlib import Path

import pytest

from ukei import intelligence


def test_enrichment_isolates_provider_failures_and_checkpoints(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "catalogue.json"
    source.write_text(
        json.dumps(
            {
                "records": [
                    {
                        "source_id": "source-1",
                        "title": "Water data",
                        "licence": "unknown",
                        "update_frequency": "not supplied",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test")
    monkeypatch.setenv("OPENAI_MODEL", "test-model")
    monkeypatch.setenv("GEMINI_API_KEY", "test")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    monkeypatch.setattr(
        intelligence,
        "_openai",
        lambda _prompt, model: (
            {
                "themes": ["water"],
                "source_type": "dataset",
                "review_priority": 50,
                "review_reasons": ["licence"],
                "uncertainties": [],
            },
            model,
        ),
    )

    def fail(_prompt: str, _model: str) -> tuple[dict[str, object], str]:
        raise RuntimeError("quota")

    monkeypatch.setattr(intelligence, "_gemini", fail)
    destination = tmp_path / "advisory.json"
    report = intelligence.enrich_catalogue(source, destination, provider="both")
    assert report["successful_classifications"] == 1
    assert report["error_count"] == 1
    assert report["errors"][0]["provider"] == "gemini"
    assert json.loads(destination.read_text(encoding="utf-8")) == report


def test_ai_payload_rejects_unexpected_schema() -> None:
    with pytest.raises(ValueError, match="unexpected schema"):
        intelligence._validate_ai_payload({"themes": []})
