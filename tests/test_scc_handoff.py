import gzip
import json
from pathlib import Path

from ukei.scc_handoff import build_handoff


def test_handoff_redacts_sensitive_urls(tmp_path: Path):
    catalogue = {
        "records": [{
            "source_id": "x",
            "url": "https://example.test/data?api_key=secret&x=1",
            "resources": [{"url": "https://u:p@example.test/file.csv?token=abc"}],
        }]
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
    assert receipt["governance"]["scientific_admissibility_conferred"] is False
