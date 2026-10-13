"""Bounded, source-native UK-AIR station inventory discovery for SCC/VVIP."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urljoin, urlparse
from urllib.request import Request, urlopen

AURN_NETWORK_INFO_URL = "https://uk-air.defra.gov.uk/networks/network-info?view=aurn"
AURN_CURRENT_URL = (
    "https://uk-air.defra.gov.uk/networks/find-sites?"
    "action=results&country_id=9999&group_id=4&location_type=9999&pollutant="
    "&region_id=9999&site_name=&view=advanced"
)
AURN_REPORTING_URL = "https://uk-air.defra.gov.uk/latest/currentlevels"
AURN_CLOSED_URL = "https://uk-air.defra.gov.uk/networks/aurn-sites"
INVENTORY_SCHEMA = "ukei_ukair_station_inventory_v2"
_USER_AGENT = "SCC-AirQuality-Coverage-Audit/1.0 (+https://sccairquality.com)"
_MAX_RESPONSE_BYTES = 4_000_000
_UKA_RE = re.compile(r"\bUKA\d{5}\b", re.IGNORECASE)
_COUNT_RE = re.compile(r"\b(Current|Total)\s+sites?\s*:\s*(\d+)\b", re.IGNORECASE)
_AVAILABILITY_RE = re.compile(
    r"Data\s+availability\s*:\s*([^\n<]+?)(?=(?:What is|How is|Monitoring|$))",
    re.IGNORECASE,
)


class InventoryError(RuntimeError):
    """A bounded inventory request or parser failed."""


@dataclass(frozen=True, slots=True)
class StationSeed:
    """One provider-native station identity observed on a UK-AIR inventory page."""

    network_id: str
    status: str
    name: str
    uka_id: str
    site_id: str
    detail_url: str
    source_url: str
    latitude: str = ""
    longitude: str = ""

    @property
    def identity(self) -> str:
        if self.uka_id:
            return f"uka:{self.uka_id}"
        if self.site_id:
            return f"site:{self.site_id}"
        return f"url:{self.detail_url}"


@dataclass(frozen=True, slots=True)
class FetchReceipt:
    """Immutable retrieval evidence for one inventory page."""

    url: str
    retrieved_at_utc: str
    status_code: int
    content_type: str
    etag: str
    last_modified: str
    sha256: str
    byte_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FetchedPage:
    body: bytes
    receipt: FetchReceipt


FetchFunction = Callable[[str, float, int], FetchedPage]


class _StationLinkParser(HTMLParser):
    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self._active_url = ""
        self._active_parts: list[str] = []
        self.observations: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.casefold(): value or "" for key, value in attrs}
        candidate = ""
        if tag.casefold() == "a":
            candidate = values.get("href", "")
        elif tag.casefold() == "option":
            candidate = values.get("value", "")
        if candidate:
            self._active_url = urljoin(self.source_url, candidate)
            self._active_parts = []

    def handle_data(self, data: str) -> None:
        if self._active_url:
            self._active_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._active_url and tag.casefold() in {"a", "option"}:
            text = " ".join(" ".join(self._active_parts).split())
            self.observations.append((self._active_url, text))
            self._active_url = ""
            self._active_parts = []



class _StationSearchParser(HTMLParser):
    """Parse the server-rendered UK-AIR Network Site Search result table."""

    def __init__(self, source_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_url = source_url
        self._in_row = False
        self._row_parts: list[str] = []
        self._row_urls: list[str] = []
        self.rows: list[tuple[str, tuple[str, ...]]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lowered = tag.casefold()
        if lowered == "tr":
            self._in_row = True
            self._row_parts = []
            self._row_urls = []
            return
        if not self._in_row or lowered != "a":
            return
        values = {key.casefold(): value or "" for key, value in attrs}
        href = values.get("href", "")
        if href:
            self._row_urls.append(urljoin(self.source_url, href))

    def handle_data(self, data: str) -> None:
        if self._in_row:
            self._row_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "tr" or not self._in_row:
            return
        text = " ".join(" ".join(self._row_parts).split())
        self.rows.append((text, tuple(self._row_urls)))
        self._in_row = False
        self._row_parts = []
        self._row_urls = []


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _query_id(url: str, key: str) -> str:
    values = parse_qs(urlparse(url).query).get(key, [])
    return str(values[0]).strip() if values else ""


def _station_identity(url: str, text: str) -> tuple[str, str]:
    uka_id = _query_id(url, "uka_id").upper()
    if not uka_id:
        match = _UKA_RE.search(text)
        if match:
            uka_id = match.group(0).upper()
    site_id = _query_id(url, "site_id").upper()
    return uka_id, site_id


def _looks_like_station_url(url: str, text: str) -> bool:
    path = urlparse(url).path.casefold()
    return (
        "site-info" in path
        or "aurn-site-info" in path
        or bool(_UKA_RE.search(text))
        or bool(_query_id(url, "site_id"))
        or bool(_query_id(url, "uka_id"))
    )


def parse_ukair_station_links(
    html: str,
    *,
    source_url: str,
    network_id: str,
    status: str,
) -> list[StationSeed]:
    """Extract provider-native site links without inventing station identifiers."""
    parser = _StationLinkParser(source_url)
    parser.feed(html)
    stations: dict[str, StationSeed] = {}
    for url, text in parser.observations:
        if not _looks_like_station_url(url, text):
            continue
        uka_id, site_id = _station_identity(url, text)
        if not uka_id and not site_id:
            continue
        name = _UKA_RE.sub("", text).strip(" ()-") or uka_id or site_id
        seed = StationSeed(
            network_id=network_id,
            status=status,
            name=name,
            uka_id=uka_id,
            site_id=site_id,
            detail_url=url,
            source_url=source_url,
        )
        stations.setdefault(seed.identity, seed)
    return sorted(stations.values(), key=lambda item: (item.name.casefold(), item.identity))



def parse_network_search_rows(
    html: str,
    *,
    source_url: str,
    network_id: str,
) -> list[StationSeed]:
    """Extract the active network roster with UK-AIR IDs and coordinates."""
    parser = _StationSearchParser(source_url)
    parser.feed(html)
    stations: dict[str, StationSeed] = {}
    row_pattern = re.compile(
        r"^\s*\d+\s+(?P<name>.+?)\s+UK-AIR ID:\s*(?P<uka>UKA\d{5})"
        r"\s+Location:\s*(?P<lat>-?\d+(?:\.\d+)?),\s*(?P<lon>-?\d+(?:\.\d+)?)",
        re.IGNORECASE,
    )
    for text, urls in parser.rows:
        match = row_pattern.search(text)
        if not match:
            continue
        uka_id = match.group("uka").upper()
        detail_url = next(
            (
                url
                for url in urls
                if "site-info" in urlparse(url).path.casefold()
                and _query_id(url, "uka_id").upper() == uka_id
            ),
            "",
        )
        if not detail_url:
            detail_url = (
                "https://uk-air.defra.gov.uk/networks/site-info?provider=&uka_id=" + uka_id
            )
        seed = StationSeed(
            network_id=network_id,
            status="current_roster",
            name=match.group("name").strip(),
            uka_id=uka_id,
            site_id="",
            detail_url=detail_url,
            source_url=source_url,
            latitude=match.group("lat"),
            longitude=match.group("lon"),
        )
        stations.setdefault(seed.identity, seed)
    return sorted(stations.values(), key=lambda item: (item.name.casefold(), item.identity))


def parse_network_summary(html: str) -> dict[str, Any]:
    """Parse headline provider counts as audit evidence, never as station identity."""
    text = " ".join(re.sub(r"<[^>]+>", " ", html).split())
    counts = {label.casefold(): int(value) for label, value in _COUNT_RE.findall(text)}
    availability = _AVAILABILITY_RE.search(text)
    return {
        "current_site_count": counts.get("current"),
        "total_site_count": counts.get("total"),
        "data_availability": availability.group(1).strip() if availability else "",
    }


def _header(headers: Any, name: str) -> str:
    value = headers.get(name) if headers is not None else None
    return str(value or "")


def fetch_page(url: str, timeout_seconds: float = 8.0, retries: int = 2) -> FetchedPage:
    """Fetch one small HTTPS page with bounded retries and immutable retrieval evidence."""
    if urlparse(url).scheme.casefold() != "https":
        raise InventoryError("station inventory only permits HTTPS source URLs")
    if timeout_seconds <= 0 or retries < 0 or retries > 4:
        raise ValueError("invalid inventory request budget")

    request = Request(
        url,
        headers={
            "User-Agent": _USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.2",
        },
    )
    last_error = ""
    for attempt in range(retries + 1):
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                body = response.read(_MAX_RESPONSE_BYTES + 1)
                if len(body) > _MAX_RESPONSE_BYTES:
                    raise InventoryError("inventory response exceeded the byte budget")
                status = int(getattr(response, "status", 200))
                receipt = FetchReceipt(
                    url=url,
                    retrieved_at_utc=datetime.now(UTC).replace(microsecond=0).isoformat(),
                    status_code=status,
                    content_type=_header(response.headers, "Content-Type"),
                    etag=_header(response.headers, "ETag"),
                    last_modified=_header(response.headers, "Last-Modified"),
                    sha256=_sha256(body),
                    byte_count=len(body),
                )
                return FetchedPage(body=body, receipt=receipt)
        except HTTPError as exc:
            last_error = f"HTTP {exc.code}"
            if exc.code == 429:
                message = "provider rate limited inventory request; no same-run retry"
                raise InventoryError(message) from exc
            if exc.code < 500 or attempt >= retries:
                raise InventoryError(f"inventory request failed: {last_error}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            last_error = type(exc).__name__
            if attempt >= retries:
                raise InventoryError(f"inventory request failed: {last_error}") from exc
        time.sleep(min(4.0, 0.5 * (2**attempt)))
    raise InventoryError(f"inventory request failed: {last_error}")


def compare_station_snapshots(
    previous: list[StationSeed],
    current: list[StationSeed],
) -> dict[str, Any]:
    """Detect unexplained source-registry disappearance without declaring real-world closure."""
    previous_ids = {station.identity for station in previous}
    current_ids = {station.identity for station in current}
    missing = sorted(previous_ids - current_ids)
    added = sorted(current_ids - previous_ids)
    return {
        "previous_station_count": len(previous_ids),
        "current_station_count": len(current_ids),
        "missing_from_current_snapshot": missing,
        "added_in_current_snapshot": added,
        "silent_disappearance_gate": "REVIEW_REQUIRED" if missing else "PASS",
        "absence_claim_boundary": (
            "Absence from one collection run is not evidence that a real-world station was removed."
        ),
    }


def _seed_from_payload(raw: dict[str, Any]) -> StationSeed:
    return StationSeed(
        network_id=str(raw.get("network_id", "")),
        status=str(raw.get("status", "")),
        name=str(raw.get("name", "")),
        uka_id=str(raw.get("uka_id", "")),
        site_id=str(raw.get("site_id", "")),
        detail_url=str(raw.get("detail_url", "")),
        source_url=str(raw.get("source_url", "")),
        latitude=str(raw.get("latitude", "")),
        longitude=str(raw.get("longitude", "")),
    )


def _load_previous_current_roster(path: str | Path | None) -> list[StationSeed]:
    if path is None or not Path(path).exists():
        return []
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    raw_current = payload.get("current_roster")
    if isinstance(raw_current, list):
        return [_seed_from_payload(raw) for raw in raw_current if isinstance(raw, dict)]
    legacy = payload.get("stations", [])
    if not isinstance(legacy, list):
        return []
    return [
        _seed_from_payload(raw)
        for raw in legacy
        if isinstance(raw, dict) and str(raw.get("status", "")) == "current"
    ]


def build_aurn_inventory(
    output_directory: str | Path,
    *,
    fetch_function: FetchFunction = fetch_page,
    timeout_seconds: float = 8.0,
    retries: int = 2,
    previous_inventory_path: str | Path | None = None,
) -> dict[str, Any]:
    """Build separate AURN roster, latest-reporting and closed-reference inventories."""
    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)

    network_info_page = fetch_function(AURN_NETWORK_INFO_URL, timeout_seconds, retries)
    current_page = fetch_function(AURN_CURRENT_URL, timeout_seconds, retries)
    reporting_page = fetch_function(AURN_REPORTING_URL, timeout_seconds, retries)
    closed_page = fetch_function(AURN_CLOSED_URL, timeout_seconds, retries)

    network_info_html = network_info_page.body.decode("utf-8", errors="replace")
    current_html = current_page.body.decode("utf-8", errors="replace")
    reporting_html = reporting_page.body.decode("utf-8", errors="replace")
    closed_html = closed_page.body.decode("utf-8", errors="replace")

    current_roster = parse_network_search_rows(
        current_html,
        source_url=AURN_CURRENT_URL,
        network_id="aurn",
    )
    latest_reporting = parse_ukair_station_links(
        reporting_html,
        source_url=AURN_REPORTING_URL,
        network_id="aurn",
        status="latest_reporting",
    )
    closed_reference = parse_ukair_station_links(
        closed_html,
        source_url=AURN_CLOSED_URL,
        network_id="aurn",
        status="closed_reference",
    )
    summary = parse_network_summary(network_info_html)

    previous = _load_previous_current_roster(previous_inventory_path)
    continuity = compare_station_snapshots(previous, current_roster) if previous else None
    observed_current = summary.get("current_site_count")
    current_count_gate = (
        "PASS"
        if isinstance(observed_current, int) and observed_current == len(current_roster)
        else "REVIEW_REQUIRED"
    )
    reporting_gap = (
        observed_current - len(latest_reporting)
        if isinstance(observed_current, int) and observed_current >= len(latest_reporting)
        else None
    )
    reporting_closed_site_ids = sorted(
        {seed.site_id for seed in latest_reporting if seed.site_id}
        & {seed.site_id for seed in closed_reference if seed.site_id}
    )

    receipt = {
        "schema": INVENTORY_SCHEMA,
        "network_id": "aurn",
        "provider": "Department for Environment, Food and Rural Affairs",
        "current_station_seed_count": len(current_roster),
        "latest_reporting_station_seed_count": len(latest_reporting),
        "closed_reference_seed_count": len(closed_reference),
        "latest_reporting_gap_count": reporting_gap,
        "reporting_closed_site_id_overlap_count": len(reporting_closed_site_ids),
        "reporting_closed_site_id_overlaps": reporting_closed_site_ids,
        "provider_network_summary": summary,
        "current_count_reconciliation": current_count_gate,
        "identity_crosswalk_status": "REVIEW_REQUIRED",
        "retrievals": [
            network_info_page.receipt.to_dict(),
            current_page.receipt.to_dict(),
            reporting_page.receipt.to_dict(),
            closed_page.receipt.to_dict(),
        ],
        "continuity": continuity,
        "governance": {
            "review_status": "REVIEW_REQUIRED",
            "scientific_admissibility_conferred": False,
            "production_change_authorised": False,
            "station_inventory_complete": False,
            "claim_boundary": (
                "Current network membership, latest reporting status and closed-site history are "
                "separate provider concepts. UK-AIR/site IDs, network membership, pollutant/method "
                "periods and historical identities require crosswalk reconciliation before AURN "
                "enumeration can be marked complete."
            ),
        },
    }
    snapshot = {
        "schema": INVENTORY_SCHEMA,
        "network_id": "aurn",
        "current_roster": [
            asdict(row) | {"identity": row.identity} for row in current_roster
        ],
        "latest_reporting": [
            asdict(row) | {"identity": row.identity} for row in latest_reporting
        ],
        "closed_reference": [
            asdict(row) | {"identity": row.identity} for row in closed_reference
        ],
        "receipt": receipt,
    }
    snapshot["snapshot_sha256"] = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    (output / "aurn-station-inventory.json").write_text(
        json.dumps(snapshot, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (output / "aurn-station-inventory-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output")
    parser.add_argument("--previous-inventory")
    parser.add_argument("--timeout", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=2)
    args = parser.parse_args(argv)
    receipt = build_aurn_inventory(
        args.output,
        previous_inventory_path=args.previous_inventory,
        timeout_seconds=args.timeout,
        retries=args.retries,
    )
    print(json.dumps(receipt, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
