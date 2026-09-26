"""Publish a sanitised, governed SCC Air Quality handoff snapshot."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA = "ukei_scc_air_quality_handoff_v1"
SENSITIVE_QUERY_KEYS = {
    "password", "passwd", "pwd", "token", "access_token", "apikey", "api_key",
    "key", "secret", "client_secret", "authorization", "auth",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _redact_url(value: str) -> tuple[str, int]:
    if not value.startswith(("http://", "https://")):
        return value, 0
    try:
        parts = urllib.parse.urlsplit(value)
        count = 0
        pairs = []
        for key, item in urllib.parse.parse_qsl(parts.query, keep_blank_values=True):
            if key.casefold() in SENSITIVE_QUERY_KEYS and item:
                item = "REDACTED"
                count += 1
            pairs.append((key, item))
        if parts.username or parts.password:
            host = parts.hostname or ""
            if parts.port:
                host = f"{host}:{parts.port}"
            parts = parts._replace(netloc=host)
            count += 1
        return urllib.parse.urlunsplit((parts.scheme, parts.netloc, parts.path, urllib.parse.urlencode(pairs), parts.fragment)), count
    except Exception:
        return value, 0


def _sanitise(value: Any) -> tuple[Any, int]:
    if isinstance(value, dict):
        output = {}
        count = 0
        for key, item in value.items():
            cleaned, n = _sanitise(item)
            output[key] = cleaned
            count += n
        return output, count
    if isinstance(value, list):
        output = []
        count = 0
        for item in value:
            cleaned, n = _sanitise(item)
            output.append(cleaned)
            count += n
        return output, count
    if isinstance(value, str):
        return _redact_url(value)
    return value, 0


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_gzip_json(path: Path, payload: Any) -> tuple[str, int]:
    raw = (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8")
    blob = gzip.compress(raw, compresslevel=9, mtime=0)
    path.write_bytes(blob)
    return _sha256_bytes(blob), len(blob)


def build_handoff(
    catalogue_path: str | Path,
    output_dir: str | Path,
    *,
    validation_path: str | Path | None = None,
    run_receipt_path: str | Path | None = None,
    upstream_run_id: str = "",
    upstream_artifact_id: str = "",
    upstream_artifact_digest: str = "",
) -> dict[str, Any]:
    catalogue_path = Path(catalogue_path)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    catalogue = _load(catalogue_path)
    safe_catalogue, catalogue_redactions = _sanitise(catalogue)
    cat_out = output / "focused-catalogue.json.gz"
    cat_sha, cat_size = _write_gzip_json(cat_out, safe_catalogue)

    validation_meta = None
    validation_redactions = 0
    if validation_path and Path(validation_path).exists():
        validation_path = Path(validation_path)
        validation = _load(validation_path)
        safe_validation, validation_redactions = _sanitise(validation)
        val_out = output / "focused-validation-report.json.gz"
        val_sha, val_size = _write_gzip_json(val_out, safe_validation)
        validation_meta = {
            "source_sha256": _sha256_bytes(validation_path.read_bytes()),
            "handoff_sha256": val_sha,
            "compressed_bytes": val_size,
        }

    run_receipt = _load(Path(run_receipt_path)) if run_receipt_path and Path(run_receipt_path).exists() else None
    if run_receipt is not None:
        (output / "run-receipt.json").write_text(
            json.dumps(run_receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    receipt = {
        "schema": SCHEMA,
        "generated_at_utc": _utc_now(),
        "purpose": "Sanitised discovery handoff to SCC Air Quality test; not scientific evidence.",
        "upstream_run_id": upstream_run_id or None,
        "upstream_artifact_id": upstream_artifact_id or None,
        "upstream_artifact_digest": upstream_artifact_digest or None,
        "catalogue": {
            "record_count": len(catalogue.get("records", [])) if isinstance(catalogue, dict) else None,
            "source_sha256": _sha256_bytes(catalogue_path.read_bytes()),
            "handoff_sha256": cat_sha,
            "compressed_bytes": cat_size,
        },
        "validation": validation_meta,
        "security": {
            "sensitive_url_values_redacted": catalogue_redactions + validation_redactions,
            "catalogue_redactions": catalogue_redactions,
            "validation_redactions": validation_redactions,
            "raw_payload_published": False,
        },
        "governance": {
            "scientific_admissibility_conferred": False,
            "review_status": "REVIEW_REQUIRED",
            "production_change_authorised": False,
            "claim_boundary": "This handoff preserves discovery intelligence and run identity only. SCC Air Quality must independently reacquire and validate original-provider evidence before scientific use.",
        },
    }
    (output / "handoff-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalogue", required=True)
    p.add_argument("--validation")
    p.add_argument("--run-receipt")
    p.add_argument("--output", required=True)
    p.add_argument("--upstream-run-id", default="")
    p.add_argument("--upstream-artifact-id", default="")
    p.add_argument("--upstream-artifact-digest", default="")
    args = p.parse_args(argv)
    receipt = build_handoff(
        args.catalogue,
        args.output,
        validation_path=args.validation,
        run_receipt_path=args.run_receipt,
        upstream_run_id=args.upstream_run_id,
        upstream_artifact_id=args.upstream_artifact_id,
        upstream_artifact_digest=args.upstream_artifact_digest,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
