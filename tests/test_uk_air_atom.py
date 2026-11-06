"""Synthetic and fully offline SCC/VVIP UK-AIR historical Atom index tests."""

from __future__ import annotations

import hashlib
import io
import json
from email.message import Message
from pathlib import Path

import pytest

from ukei.discovery.base import DiscoveryError
from ukei.uk_air_atom import (
    INDEX_URL,
    MAX_INDEX_BYTES,
    _fetch_index,
    build_inventory,
    main,
    parse_atom_index,
)


def index_html(*, full: bool = False) -> bytes:
    years = range(1973, 2027) if full else (1973, 2026)
    links = [
        f'<a href="{kind}/{year}/atom.en.xml">{year}</a>'
        for kind in ("auto", "non-auto", "aggregated")
        for year in years
    ]
    links.append('<a href="metadata/atom.en.xml">Methods metadata</a>')
    return ("<html><body>" + "\n".join(links) + "</body></html>").encode()


def test_exact_historical_index_inventory_is_links_not_data() -> None:
    result = parse_atom_index(index_html(full=True), reference_year=2026)
    assert result["feed_links_found"] == 163
    assert result["category_counts"] == {
        "auto": 54, "non-auto": 54, "aggregated": 54, "metadata": 1
    }
    assert result["index_has_all_year_links"] is True
    assert result["metadata_link_present"] is True
    assert result["missing_index_years"] == {
        "auto": [], "non-auto": [], "aggregated": []
    }
    assert all(item["status"] == "CANDIDATE_METADATA_ONLY" for item in result["rows"])
    assert all(item["vvip_review"] == "REVIEW_REQUIRED" for item in result["rows"])


def test_missing_years_not_silently_certified() -> None:
    result = parse_atom_index(index_html(), reference_year=2026)
    assert result["feed_links_found"] == 7
    assert result["index_has_all_year_links"] is False
    assert len(result["missing_index_years"]["auto"]) == 52
    assert result["missing_index_years"]["auto"][0] == 1974


def test_deduplicates_without_hiding_rejected_redirect_links() -> None:
    raw = (
        '<a href="auto/2026/atom.en.xml">good</a>'
        '<a href="auto/2026/atom.en.xml">duplicate</a>'
        '<a href="https://evil.example.org/data/atom-dls/auto/2025/atom.en.xml">evil</a>'
        '<a href="https://uk-air.defra.gov.uk/data/atom-dls/auto/2024/atom.en.xml?token=x">'
        'credential URL</a>'
        '<a href="http://uk-air.defra.gov.uk/data/atom-dls/auto/2023/atom.en.xml">'
        'downgrade</a>'
        '<a href="metadata/atom.en.xml">metadata</a>'
        '<a href="https://uk-air.defra.gov.uk/other">unrelated</a>'
    ).encode()
    receipt = parse_atom_index(raw, reference_year=2026)
    assert receipt["feed_links_found"] == 2
    assert receipt["duplicate_links_seen"] == 1
    assert receipt["rejected_feed_links"] == 3
    assert receipt["rows"][0]["feed_url"].startswith(INDEX_URL)


@pytest.mark.parametrize(
    ("html", "year"),
    [
        (b"", 2026),
        (b"x" * (MAX_INDEX_BYTES + 1), 2026),
        (b"some html", 1972),
        (b"some html", 2101),
        (b"\xff", 2026),
    ],
)
def test_invalid_source_or_reference_year_fails_closed(html: bytes, year: int) -> None:
    with pytest.raises((ValueError, UnicodeError)):
        parse_atom_index(html, reference_year=year)


def test_inventory_retains_bytes_and_explicit_admissibility_hold(tmp_path: Path) -> None:
    raw = index_html(full=True)
    receipt = build_inventory(tmp_path, raw_html=raw, reference_year=2026, live=False)
    assert (tmp_path / "atom-index-original.html").read_bytes() == raw
    assert receipt["source_index_sha256"] == hashlib.sha256(raw).hexdigest()
    assert receipt["manifest_sha256"] == hashlib.sha256(
        (tmp_path / "atom-index-manifest.csv").read_bytes()
    ).hexdigest()
    assert receipt["observation_files_downloaded"] == 0
    assert receipt["release_state"] == "REVIEW_REQUIRED"
    assert receipt["scientific_admissibility_conferred"] is False
    assert receipt["national_completeness_claimed"] is False
    assert receipt["publication_allowed"] is False
    assert receipt["acquisition_mode"] == "OFFLINE_INPUT"
    assert json.loads(
        (tmp_path / "atom-index-receipt.json").read_text()
    )["feed_links_found"] == 163


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, body: bytes, content_type: str = "text/html") -> None:
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["ETag"] = '"revision-1"'

    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_bounded_live_index_fetch_delegates_to_strict_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def strict_open(request: object, seconds: float) -> FakeResponse:
        assert getattr(request, "full_url") == INDEX_URL
        assert seconds == 5
        return FakeResponse(index_html())

    monkeypatch.setattr("ukei.uk_air_atom.open_public_request", strict_open)
    raw, info = _fetch_index(5)
    assert raw == index_html()
    assert info["http_status"] == 200
    assert info["etag"] == '"revision-1"'


@pytest.mark.parametrize(
    ("body", "mime", "expected"),
    [
        (b"a" * (MAX_INDEX_BYTES + 1), "text/html", "byte budget"),
        (b"{}", "application/json", "not an HTTP 200 HTML"),
    ],
)
def test_live_index_invalid_responses_are_rejected(
    monkeypatch: pytest.MonkeyPatch,
    body: bytes,
    mime: str,
    expected: str,
) -> None:
    monkeypatch.setattr(
        "ukei.uk_air_atom.open_public_request",
        lambda *_args, **_kwargs: FakeResponse(body, mime),
    )
    with pytest.raises(DiscoveryError, match=expected):
        _fetch_index(5)


def test_live_failure_uses_no_untrusted_details(monkeypatch: pytest.MonkeyPatch) -> None:
    def offline(*_args: object, **_kwargs: object) -> None:
        raise DiscoveryError("possible sensitive original request detail")

    monkeypatch.setattr("ukei.uk_air_atom.open_public_request", offline)
    with pytest.raises(DiscoveryError, match="retrieval failed or was blocked") as err:
        _fetch_index(5)
    assert "sensitive original" not in str(err.value)


def test_invalid_live_timeout_fails() -> None:
    with pytest.raises(ValueError):
        _fetch_index(0)


def test_cli_offline_workflow_writes_three_reviewable_outputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "source.html"
    source.write_bytes(index_html(full=True))
    dest = tmp_path / "results"
    assert main(["--input-html", str(source), "--output", str(dest), "--year", "2026"]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response["feed_links_found"] == 163
    assert response["observation_files_downloaded"] == 0
    assert sorted(file.name for file in dest.iterdir()) == [
        "atom-index-manifest.csv", "atom-index-original.html", "atom-index-receipt.json"
    ]


def test_cli_live_source_is_explicit_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "ukei.uk_air_atom._fetch_index",
        lambda _seconds: (index_html(), {"http_status": 200}),
    )
    assert main(["--live", "--output", str(tmp_path), "--year", "2026"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["acquisition_mode"] == "LIVE"
    assert report["retrieval"]["http_status"] == 200
