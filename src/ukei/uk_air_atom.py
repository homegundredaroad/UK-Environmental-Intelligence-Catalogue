"""Bounded UK-AIR Atom historical feed index, discovery evidence only.

The provider homepage advertises feeds for automatic, non-automatic and
aggregated series by year. This module inventories *links*, not observations,
station coverage, QA status, or historical completeness of the feed contents.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit
from urllib.request import Request

from ukei.discovery.base import DiscoveryError
from ukei.discovery.http import open_public_request

INDEX_URL = "https://uk-air.defra.gov.uk/data/atom-dls/"
SCHEMA = "scc_ukair_atom_index_discovery_v1"
MAX_INDEX_BYTES = 2_000_000
FIRST_PUBLISHED_YEAR = 1973
_SERIES = ("auto", "non-auto", "aggregated")
_FEED_PATTERN = re.compile(
    r"/data/atom-dls/(auto|non-auto|aggregated)/(\d{4})/atom\.en\.xml"
)
_METADATA_PATH = "/data/atom-dls/metadata/atom.en.xml"
_ORIGIN = ("https", "uk-air.defra.gov.uk")


class _Anchors(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            for key, value in attrs:
                if key.lower() == "href" and value:
                    self.hrefs.append(value)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_atom_index(
    raw_html: bytes,
    *,
    reference_year: int,
) -> dict[str, Any]:
    """Extract provider-native year links without inventing observations."""
    if not raw_html or len(raw_html) > MAX_INDEX_BYTES:
        raise ValueError("UK-AIR index body missing or larger than safety budget")
    if not FIRST_PUBLISHED_YEAR <= reference_year <= 2100:
        raise ValueError("invalid reporting reference year")
    parser = _Anchors()
    parser.feed(raw_html.decode("utf-8-sig"))
    found: dict[tuple[str, int | None], str] = {}
    duplicates = 0
    rejected = 0
    for href in parser.hrefs:
        url = urljoin(INDEX_URL, href)
        parts = urlsplit(url)
        match = _FEED_PATTERN.fullmatch(parts.path)
        metadata = parts.path == _METADATA_PATH
        if match is None and not metadata:
            continue
        if (
            (parts.scheme, parts.hostname) != _ORIGIN
            or parts.port is not None
            or parts.username is not None
            or parts.password is not None
            or parts.query
            or parts.fragment
        ):
            rejected += 1
            continue
        kind = match.group(1) if match else "metadata"
        year = int(match.group(2)) if match else None
        if year is not None and not FIRST_PUBLISHED_YEAR <= year <= reference_year:
            rejected += 1
            continue
        key = (kind, year)
        if key in found:
            duplicates += 1
        else:
            found[key] = url

    rows: list[dict[str, str]] = []
    for (kind, year), url in sorted(found.items(), key=lambda pair: pair[0]):
        rows.append(
            {
                "category": kind,
                "year": str(year) if year is not None else "",
                "feed_url": url,
                "source_url": INDEX_URL,
                "status": "CANDIDATE_METADATA_ONLY",
                "vvip_review": "REVIEW_REQUIRED",
            }
        )
    counts = Counter(row["category"] for row in rows)
    missing = {
        kind: [
            year
            for year in range(FIRST_PUBLISHED_YEAR, reference_year + 1)
            if (kind, year) not in found
        ]
        for kind in _SERIES
    }
    return {
        "schema": SCHEMA,
        "reference_year": reference_year,
        "first_published_year": FIRST_PUBLISHED_YEAR,
        "index_links_seen": len(parser.hrefs),
        "feed_links_found": len(rows),
        "category_counts": {kind: counts[kind] for kind in (*_SERIES, "metadata")},
        "missing_index_years": missing,
        "duplicate_links_seen": duplicates,
        "rejected_feed_links": rejected,
        "index_has_all_year_links": all(not years for years in missing.values()),
        "metadata_link_present": ("metadata", None) in found,
        "rows": rows,
    }


def _fetch_index(timeout_seconds: float) -> tuple[bytes, dict[str, str | int]]:
    if not 1 <= timeout_seconds <= 30:
        raise ValueError("timeout must be between 1 and 30 seconds")
    request = Request(
        INDEX_URL,
        headers={
            "Accept": "text/html",
            "User-Agent": "SCC-Nexus-Environmental-Index/1.0",
        },
    )
    try:
        with open_public_request(request, timeout_seconds) as response:
            body = response.read(MAX_INDEX_BYTES + 1)
            headers = response.headers
            receipt: dict[str, str | int] = {
                "http_status": int(response.status),
                "content_type": str(headers.get("Content-Type", "")),
                "etag": str(headers.get("ETag", "")),
                "last_modified": str(headers.get("Last-Modified", "")),
            }
    except (DiscoveryError, OSError) as exc:
        raise DiscoveryError("UK-AIR source index retrieval failed or was blocked") from exc
    if len(body) > MAX_INDEX_BYTES:
        raise DiscoveryError("UK-AIR source index exceeded byte budget")
    if receipt["http_status"] != 200 or "html" not in receipt["content_type"]:
        raise DiscoveryError("UK-AIR source index response was not an HTTP 200 HTML page")
    return body, receipt


def build_inventory(
    output_dir: Path,
    *,
    raw_html: bytes,
    reference_year: int,
    live: bool,
    retrieval: dict[str, str | int] | None = None,
) -> dict[str, Any]:
    """Preserve the original index and emit a review-only, versioned manifest."""
    parsed = parse_atom_index(raw_html, reference_year=reference_year)
    output_dir.mkdir(parents=True, exist_ok=True)
    original = output_dir / "atom-index-original.html"
    original.write_bytes(raw_html)
    manifest = output_dir / "atom-index-manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        fields = ("category", "year", "feed_url", "source_url", "status", "vvip_review")
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(parsed["rows"])
    result = {key: value for key, value in parsed.items() if key != "rows"}
    result.update(
        {
            "indexed_at_utc": datetime.now(UTC).isoformat(),
            "index_url": INDEX_URL,
            "acquisition_mode": "LIVE" if live else "OFFLINE_INPUT",
            "source_index_sha256": _sha(raw_html),
            "source_index_bytes": len(raw_html),
            "manifest_sha256": _sha(manifest.read_bytes()),
            "retrieval": retrieval or {},
            "observation_files_downloaded": 0,
            "scientific_admissibility_conferred": False,
            "national_completeness_claimed": False,
            "publication_allowed": False,
            "release_state": "REVIEW_REQUIRED",
            "claim_boundary": (
                "Links identified in a provider index; feed content, station inventory, "
                "data quality, revisions and national completeness are unverified"
            ),
        }
    )
    (output_dir / "atom-index-receipt.json").write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SCC/VVIP UK-AIR Atom historical feed inventory")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--live", action="store_true", help="fetch official source index only")
    source.add_argument("--input-html", type=Path, help="analyse a preserved HTML index offline")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--year", type=int, default=datetime.now(UTC).year)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    if args.live:
        raw_html, retrieval = _fetch_index(args.timeout)
    else:
        raw_html = args.input_html.read_bytes()
        retrieval = {}
    receipt = build_inventory(
        args.output,
        raw_html=raw_html,
        reference_year=args.year,
        live=args.live,
        retrieval=retrieval,
    )
    print(json.dumps(receipt, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
