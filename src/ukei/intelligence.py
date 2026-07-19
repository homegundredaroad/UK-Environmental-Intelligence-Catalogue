"""Optional advisory ML and LLM enrichment; canonical evidence is never mutated."""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

PROMPT_VERSION = "ukei-advisory-v1"


def _records(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    records = payload.get("records") if isinstance(payload, dict) else payload
    if not isinstance(records, list):
        raise ValueError("catalogue input must contain a records list")
    return [record for record in records if isinstance(record, dict)]


def build_ml_report(input_path: str | Path, output_path: str | Path) -> dict[str, Any]:
    """Cluster sources and identify metadata outliers using deterministic local ML."""
    try:
        from sklearn.cluster import MiniBatchKMeans  # type: ignore[import-untyped]
        from sklearn.ensemble import IsolationForest  # type: ignore[import-untyped]
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore[import-untyped]
    except ImportError as exc:  # pragma: no cover - exercised by installation smoke tests
        raise RuntimeError("install the 'intelligence' extra to run ML analysis") from exc
    records = _records(input_path)
    if len(records) < 8:
        raise ValueError("at least eight records are required for ML analysis")
    corpus = [
        " ".join(
            [
                str(record.get("title", "")),
                str(record.get("description", "")),
                str(record.get("publisher", "")),
                " ".join(str(value) for value in record.get("themes", [])),
                " ".join(str(value) for value in record.get("formats", [])),
            ]
        )
        for record in records
    ]
    vectorizer = TfidfVectorizer(
        stop_words="english", max_features=5_000, ngram_range=(1, 2), min_df=2
    )
    matrix = vectorizer.fit_transform(corpus)
    cluster_count = min(48, max(8, int(math.sqrt(len(records) / 2))))
    clusters = MiniBatchKMeans(
        n_clusters=cluster_count, random_state=26, n_init="auto", batch_size=512
    ).fit_predict(matrix)
    forest = IsolationForest(contamination=0.02, random_state=26, n_jobs=-1)
    outlier_labels = forest.fit_predict(matrix)
    anomaly_scores = -forest.score_samples(matrix)
    terms = vectorizer.get_feature_names_out()
    model = MiniBatchKMeans(
        n_clusters=cluster_count, random_state=26, n_init="auto", batch_size=512
    ).fit(matrix)
    cluster_terms = {
        str(index): [str(terms[position]) for position in center.argsort()[-8:][::-1]]
        for index, center in enumerate(model.cluster_centers_)
    }
    rows = [
        {
            "anomaly_score": round(float(anomaly_scores[index]), 6),
            "cluster": int(clusters[index]),
            "is_outlier": bool(outlier_labels[index] == -1),
            "source_id": str(record["source_id"]),
        }
        for index, record in enumerate(records)
    ]
    report = {
        "advisory_only": True,
        "cluster_count": cluster_count,
        "cluster_terms": cluster_terms,
        "method": "TF-IDF + MiniBatchKMeans + IsolationForest",
        "record_count": len(records),
        "report_version": 1,
        "rows": rows,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def _prompt(record: dict[str, Any]) -> str:
    evidence = {
        key: record.get(key)
        for key in (
            "source_id",
            "title",
            "publisher",
            "description",
            "licence",
            "geographic_scope",
            "update_frequency",
            "formats",
            "themes",
            "connector",
        )
    }
    return (
        "Classify this UK environmental catalogue metadata. Use only supplied evidence. "
        "Return JSON with keys themes (list of short strings), source_type (short string), "
        "review_priority (integer 0-100), review_reasons (list), and uncertainties (list). "
        "Do not infer a licence, availability, scientific validity, or legal permission. "
        f"Evidence: {json.dumps(evidence, sort_keys=True)}"
    )


def _validate_ai_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("AI response must be a JSON object")
    expected = {"themes", "source_type", "review_priority", "review_reasons", "uncertainties"}
    if set(payload) != expected:
        raise ValueError("AI response has an unexpected schema")
    if not isinstance(payload["themes"], list) or not isinstance(payload["review_reasons"], list):
        raise ValueError("AI response list fields are invalid")
    if not isinstance(payload["uncertainties"], list) or not isinstance(
        payload["review_priority"], int
    ):
        raise ValueError("AI response confidence fields are invalid")
    if not 0 <= payload["review_priority"] <= 100:
        raise ValueError("AI review_priority must be between 0 and 100")
    return payload


def _openai(prompt: str, model: str) -> tuple[dict[str, Any], str]:
    from openai import OpenAI  # type: ignore[import-not-found]

    response = OpenAI().responses.create(
        model=model,
        reasoning={"effort": "low"},
        input=[
            {
                "role": "developer",
                "content": "You are a conservative metadata classifier. Output JSON only.",
            },
            {"role": "user", "content": prompt},
        ],
    )
    return _validate_ai_payload(json.loads(response.output_text)), str(response.model)


def _gemini(prompt: str, model: str) -> tuple[dict[str, Any], str]:
    from google import genai  # type: ignore[import-not-found]

    response = genai.Client(api_key=os.environ["GEMINI_API_KEY"]).models.generate_content(
        model=model,
        contents=prompt + "\nOutput JSON only.",
        config={"response_mime_type": "application/json"},
    )
    return _validate_ai_payload(json.loads(response.text or "")), model


def enrich_catalogue(
    input_path: str | Path,
    output_path: str | Path,
    *,
    provider: str = "both",
    max_records: int = 50,
) -> dict[str, Any]:
    """Produce capped, cache-keyed advisory classifications using configured API providers."""
    if provider not in {"openai", "gemini", "both"}:
        raise ValueError("provider must be openai, gemini or both")
    if max_records < 1 or max_records > 500:
        raise ValueError("max_records must be between 1 and 500")
    openai_model = os.getenv("OPENAI_MODEL", "").strip()
    gemini_model = os.getenv("GEMINI_MODEL", "").strip()
    if provider in {"openai", "both"} and not (os.getenv("OPENAI_API_KEY") and openai_model):
        raise ValueError("OPENAI_API_KEY and OPENAI_MODEL are required")
    if provider in {"gemini", "both"} and not (os.getenv("GEMINI_API_KEY") and gemini_model):
        raise ValueError("GEMINI_API_KEY and GEMINI_MODEL are required")
    records = sorted(
        _records(input_path),
        key=lambda record: (
            str(record.get("licence", "")).casefold() not in {"", "unknown"},
            not str(record.get("update_frequency", "")).casefold().startswith("not supplied"),
            str(record.get("source_id", "")),
        ),
    )[:max_records]
    providers = [provider] if provider != "both" else ["openai", "gemini"]
    rows: list[dict[str, Any]] = []
    for record in records:
        prompt = _prompt(record)
        for selected in providers:
            model = openai_model if selected == "openai" else gemini_model
            cache_key = hashlib.sha256(
                f"{PROMPT_VERSION}\0{selected}\0{model}\0{prompt}".encode()
            ).hexdigest()
            payload, returned_model = (
                _openai(prompt, model) if selected == "openai" else _gemini(prompt, model)
            )
            rows.append(
                {
                    "advisory_only": True,
                    "cache_key": cache_key,
                    "classification": payload,
                    "model": returned_model,
                    "prompt_version": PROMPT_VERSION,
                    "provider": selected,
                    "source_id": record["source_id"],
                }
            )
    report = {
        "advisory_only": True,
        "canonical_evidence_modified": False,
        "provider_mode": provider,
        "record_count": len(records),
        "report_version": 1,
        "rows": rows,
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report
