"""Contract and safety tests for opt-in OGC API Records discovery."""

from __future__ import annotations

from typing import Any

import pytest

from ukei.cli import build_parser
from ukei.discovery.base import DiscoveryError, run_discovery
from ukei.discovery.ogc_records import OgcRecordsConnector
from ukei.models import SourceStatus


class FakeClient:
    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = iter(payloads)
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(self, url: str, parameters: dict[str, str | int]) -> Any:
        self.calls.append((url, parameters))
        return next(self.payloads)


ENDPOINT = "https://data.example.org/collections/environment/items"


def record(number: int = 1) -> dict[str, Any]:
    return {
        "id": f"record-{number}",
        "type": "Feature",
        "properties": {
            "title": f"Water quality {number}",
            "description": "Fixture only; not live evidence",
            "license": "OGL-3.0",
            "keywords": ["water", "environment"],
            "contacts": [
                {"name": "Example Agency", "roles": ["publisher"]}
            ],
        },
        "links": [
            {"rel": "self", "href": f"{ENDPOINT}/record-{number}"},
            {
                "rel": "data",
                "href": f"https://data.example.org/water-{number}.csv",
                "type": "text/csv",
                "title": "Observations",
            },
        ],
    }


def test_discovers_candidate_with_original_metadata_provenance() -> None:
    client = FakeClient([{"features": [record()], "numberMatched": 1}])
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    report = run_discovery((connector,), "water", 5)
    assert report.to_dict()["candidate_count"] == 1
    item = report.candidates[0]
    assert item.source.status is SourceStatus.CANDIDATE
    assert item.source.publisher == "Example Agency"
    assert item.source.licence == "OGL-3.0"
    assert item.source.resources[0].media_type == "text/csv"
    assert item.source.resources[0].url.endswith("water-1.csv")
    assert len(item.metadata_hash) == 64
    assert "Unknown; verify UK coverage" in item.source.geographic_scope
    assert connector.coverage()["complete"] is True
    assert client.calls[0][1] == {"q": "water", "limit": 5}


def test_next_links_are_used_and_same_origin_enforced() -> None:
    client = FakeClient(
        [
            {
                "features": [record(1)],
                "numberMatched": 2,
                "links": [{"rel": "next", "href": "?q=water&limit=1&offset=1"}],
            },
            {"features": [record(2)], "numberMatched": 2},
        ]
    )
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    values = connector.discover("water", 3)
    assert len(values) == 2
    assert connector.coverage()["pages_fetched"] == 2
    assert connector.coverage()["complete"] is True
    assert client.calls[1][1]["offset"] == "1"


def test_bounded_limit_marks_incomplete_coverage() -> None:
    client = FakeClient(
        [{"features": [record()], "numberMatched": 300, "links": [
            {"rel": "next", "href": "?offset=1"}
        ]}]
    )
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    assert len(connector.discover("water", 1)) == 1
    assert connector.coverage()["complete"] is False
    assert connector.coverage()["truncated_by_limit"] is True


def test_unknown_total_at_limit_does_not_claim_completeness() -> None:
    connector = OgcRecordsConnector(
        ENDPOINT, client=FakeClient([{"features": [record()]}])  # type: ignore[arg-type]
    )
    connector.discover("water", 1)
    assert connector.coverage()["coverage_unknown"] is True
    assert connector.coverage()["complete"] is False


@pytest.mark.parametrize("endpoint", [
    "http://data.example.org/items",
    "https://127.0.0.1/items",
    "https://localhost/items",
    "https://data.example.org/items?token=secret",
])
def test_rejects_unsafe_endpoint(endpoint: str) -> None:
    with pytest.raises(DiscoveryError):
        OgcRecordsConnector(endpoint)


@pytest.mark.parametrize("href", [
    "https://evil.example.org/next",
    "http://data.example.org/next",
    "?token=secret&offset=1",
])
def test_rejects_unsafe_pagination(href: str) -> None:
    client = FakeClient([
        {"features": [record()], "links": [{"rel": "next", "href": href}]}
    ])
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    with pytest.raises(DiscoveryError):
        connector.discover("water", 5)


def test_rejects_pagination_cycle() -> None:
    client = FakeClient([
        {"features": [record()], "links": [{"rel": "next", "href": "?q=water&limit=3"}]},
        {"features": [record()], "links": [{"rel": "next", "href": "?q=water&limit=3"}]},
    ])
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    with pytest.raises(DiscoveryError, match="cycle"):
        connector.discover("water", 5)


@pytest.mark.parametrize("payload", [{}, [], {"features": "not-a-list"}])
def test_bad_response_contract_fails_closed(payload: Any) -> None:
    connector = OgcRecordsConnector(
        ENDPOINT, client=FakeClient([payload])  # type: ignore[arg-type]
    )
    with pytest.raises(DiscoveryError):
        connector.discover("water", 3)


def test_untrusted_invalid_record_and_link_are_skipped() -> None:
    malformed = record()
    malformed["links"] = [
        {"rel": "data", "href": "http://127.0.0.1/private.csv"},
        {"rel": "self", "href": "http://127.0.0.1/secret"},
    ]
    client = FakeClient([{
        "features": [{"id": "invalid"}, malformed],
        "numberMatched": 2,
    }])
    connector = OgcRecordsConnector(ENDPOINT, client=client)  # type: ignore[arg-type]
    values = connector.discover("water", 5)
    assert len(values) == 1
    assert values[0].source.resources == ()
    assert values[0].source.url.startswith(ENDPOINT)
    assert connector.coverage()["complete"] is False


def test_cli_exposes_opt_in_endpoint_not_default() -> None:
    parser = build_parser()
    args = parser.parse_args([
        "discover", "--provider", "ogc-records", "--ogc-records-endpoint", ENDPOINT
    ])
    assert args.provider == "ogc-records"
    assert args.ogc_records_endpoint == ENDPOINT
    assert parser.parse_args(["discover"]).ogc_records_endpoint is None
