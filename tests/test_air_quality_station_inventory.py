from __future__ import annotations

import io
import json
from http.client import HTTPMessage
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

import ukei.air_quality_station_inventory as inventory  # isort: skip


CURRENT_HTML = """
<html><body>
<p>Current sites: 2</p>
<p>Total sites: 3</p>
<p>Data availability: 01/01/2000 to 12/10/2026</p>
<select>
<option value="">Select</option>
<option value="/networks/site-info?uka_id=UKA00001">Alpha (UKA00001)</option>
<option value="/networks/site-info?uka_id=UKA00002">Beta (UKA00002)</option>
</select>
</body></html>
"""

CLOSED_HTML = """
<html><body>
<a href="/networks/aurn-site-info?site_id=OLD1">Old Alpha</a>
<a href="/networks/site-info?site_id=OLD2">Old Beta</a>
<a href="/data/">Not a station</a>
</body></html>
"""


def _page(url: str, body: str, *, etag: str = "") -> inventory.FetchedPage:
    encoded = body.encode()
    return inventory.FetchedPage(
        body=encoded,
        receipt=inventory.FetchReceipt(
            url=url,
            retrieved_at_utc="2026-10-13T04:00:00+00:00",
            status_code=200,
            content_type="text/html",
            etag=etag,
            last_modified="Mon, 12 Oct 2026 12:00:00 GMT",
            sha256=inventory._sha256(encoded),
            byte_count=len(encoded),
        ),
    )


def test_station_link_parser_preserves_provider_ids() -> None:
    current = inventory.parse_ukair_station_links(
        CURRENT_HTML,
        source_url=inventory.AURN_CURRENT_URL,
        network_id="aurn",
        status="current",
    )
    closed = inventory.parse_ukair_station_links(
        CLOSED_HTML,
        source_url=inventory.AURN_CLOSED_URL,
        network_id="aurn",
        status="closed",
    )

    assert [station.uka_id for station in current] == ["UKA00001", "UKA00002"]
    assert current[0].identity == "uka:UKA00001"
    assert {station.site_id for station in closed} == {"OLD1", "OLD2"}
    assert {station.identity for station in closed} == {"site:OLD1", "site:OLD2"}
    assert all(station.detail_url.startswith("https://uk-air.defra.gov.uk/") for station in closed)


def test_parser_accepts_uka_in_text_and_deduplicates() -> None:
    html = """
    <a href="/networks/site-info?site_id=A1">Example UKA01234</a>
    <option value="/networks/site-info?uka_id=UKA01234">Example duplicate</option>
    """
    stations = inventory.parse_ukair_station_links(
        html,
        source_url=inventory.AURN_CURRENT_URL,
        network_id="aurn",
        status="current",
    )
    assert len(stations) == 1
    assert stations[0].uka_id == "UKA01234"


def test_network_summary_parses_counts_and_availability() -> None:
    summary = inventory.parse_network_summary(CURRENT_HTML)
    assert summary["current_site_count"] == 2
    assert summary["total_site_count"] == 3
    assert summary["data_availability"].startswith("01/01/2000")


def test_snapshot_comparison_never_turns_absence_into_closure() -> None:
    previous = [
        inventory.StationSeed(
            "aurn", "current", "Alpha", "UKA00001", "", "https://x/1", "https://x"
        ),
        inventory.StationSeed(
            "aurn", "current", "Beta", "UKA00002", "", "https://x/2", "https://x"
        ),
    ]
    current = [previous[0]]
    receipt = inventory.compare_station_snapshots(previous, current)
    assert receipt["missing_from_current_snapshot"] == ["uka:UKA00002"]
    assert receipt["silent_disappearance_gate"] == "REVIEW_REQUIRED"
    assert "not evidence" in receipt["absence_claim_boundary"]

    unchanged = inventory.compare_station_snapshots(previous, previous)
    assert unchanged["silent_disappearance_gate"] == "PASS"


def test_build_aurn_inventory_writes_hashed_snapshot_and_continuity(tmp_path: Path) -> None:
    calls: list[str] = []

    def fake_fetch(url: str, timeout: float, retries: int) -> inventory.FetchedPage:
        calls.append(url)
        assert timeout == 5.0
        assert retries == 1
        if url == inventory.AURN_CURRENT_URL:
            return _page(url, CURRENT_HTML, etag='"current"')
        return _page(url, CLOSED_HTML)

    first_dir = tmp_path / "first"
    first = inventory.build_aurn_inventory(
        first_dir,
        fetch_function=fake_fetch,
        timeout_seconds=5.0,
        retries=1,
    )
    assert first["current_station_seed_count"] == 2
    assert first["closed_station_seed_count"] == 2
    assert first["current_count_reconciliation"] == "PASS"
    assert first["continuity"] is None
    assert first["governance"]["station_inventory_complete"] is False
    assert calls == [inventory.AURN_CURRENT_URL, inventory.AURN_CLOSED_URL]

    snapshot_path = first_dir / "aurn-station-inventory.json"
    snapshot = json.loads(snapshot_path.read_text())
    assert len(snapshot["snapshot_sha256"]) == 64
    assert snapshot["receipt"]["retrievals"][0]["etag"] == '"current"'

    changed_html = CURRENT_HTML.replace(
        '<option value="/networks/site-info?uka_id=UKA00002">Beta (UKA00002)</option>',
        "",
    )

    def changed_fetch(url: str, timeout: float, retries: int) -> inventory.FetchedPage:
        body = changed_html if url == inventory.AURN_CURRENT_URL else CLOSED_HTML
        return _page(url, body)

    second = inventory.build_aurn_inventory(
        tmp_path / "second",
        fetch_function=changed_fetch,
        previous_inventory_path=snapshot_path,
    )
    assert second["current_count_reconciliation"] == "REVIEW_REQUIRED"
    assert second["continuity"]["silent_disappearance_gate"] == "REVIEW_REQUIRED"
    assert "uka:UKA00002" in second["continuity"]["missing_from_current_snapshot"]


def test_fetch_page_rejects_bad_budget_and_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(inventory.InventoryError, match="HTTPS"):
        inventory.fetch_page("http://example.test")
    with pytest.raises(ValueError, match="budget"):
        inventory.fetch_page("https://example.test", timeout_seconds=0)
    with pytest.raises(ValueError, match="budget"):
        inventory.fetch_page("https://example.test", retries=5)

    error = HTTPError(
        "https://example.test",
        429,
        "rate limited",
        hdrs=HTTPMessage(),
        fp=io.BytesIO(b""),
    )

    def rate_limited(*args: object, **kwargs: object) -> object:
        del args, kwargs
        raise error

    monkeypatch.setattr(inventory, "urlopen", rate_limited)
    with pytest.raises(inventory.InventoryError, match="rate limited"):
        inventory.fetch_page("https://example.test")


def test_fetch_page_records_headers_and_handles_transient_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Headers(dict[str, str]):
        pass

    class Response:
        status = 200
        headers = Headers(
            {
                "Content-Type": "text/html",
                "ETag": '"abc"',
                "Last-Modified": "Mon, 12 Oct 2026 12:00:00 GMT",
            }
        )

        def __enter__(self) -> Response:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def read(self, size: int) -> bytes:
            assert size == inventory._MAX_RESPONSE_BYTES + 1
            return b"<html>ok</html>"

    attempts = 0

    def flaky(*args: object, **kwargs: object) -> Response:
        nonlocal attempts
        del args, kwargs
        attempts += 1
        if attempts == 1:
            raise URLError("temporary")
        return Response()

    monkeypatch.setattr(inventory, "urlopen", flaky)
    monkeypatch.setattr("ukei.air_quality_station_inventory.time.sleep", lambda _: None)
    page = inventory.fetch_page("https://example.test", timeout_seconds=1, retries=1)
    assert attempts == 2
    assert page.receipt.status_code == 200
    assert page.receipt.content_type == "text/html"
    assert page.receipt.etag == '"abc"'
    assert len(page.receipt.sha256) == 64


def test_fetch_page_fails_on_large_body_and_non_retryable_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class LargeResponse:
        status = 200

        def __init__(self) -> None:
            self.headers: dict[str, str] = {}

        def __enter__(self) -> LargeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            del args

        def read(self, size: int) -> bytes:
            del size
            return b"x" * (inventory._MAX_RESPONSE_BYTES + 1)

    monkeypatch.setattr(inventory, "urlopen", lambda *args, **kwargs: LargeResponse())
    with pytest.raises(inventory.InventoryError, match="byte budget"):
        inventory.fetch_page("https://example.test")

    not_found = HTTPError(
        "https://example.test",
        404,
        "not found",
        hdrs=HTTPMessage(),
        fp=io.BytesIO(b""),
    )
    monkeypatch.setattr(
        inventory,
        "urlopen",
        lambda *args, **kwargs: (_ for _ in ()).throw(not_found),
    )
    with pytest.raises(inventory.InventoryError, match="HTTP 404"):
        inventory.fetch_page("https://example.test")


def test_main_uses_builder(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    expected: dict[str, object] = {"schema": inventory.INVENTORY_SCHEMA}

    def fake_build(*args: object, **kwargs: object) -> dict[str, object]:
        del args, kwargs
        return expected

    monkeypatch.setattr(inventory, "build_aurn_inventory", fake_build)
    assert inventory.main([str(tmp_path), "--timeout", "2", "--retries", "0"]) == 0
    assert json.loads(capsys.readouterr().out) == expected
