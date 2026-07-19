from __future__ import annotations

import io
from dataclasses import replace
from typing import Any
from urllib.error import URLError

import pytest

from ukei.discovery.arcgis import ArcGisConnector
from ukei.discovery.base import (
    DiscoveryCandidate,
    DiscoveryConnector,
    DiscoveryError,
    canonical_url_key,
    run_discovery,
)
from ukei.discovery.ckan import CkanConnector
from ukei.discovery.http import MAX_RESPONSE_BYTES, JsonHttpClient
from ukei.models import SourceRecord, SourceStatus


class FakeClient:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(self, url: str, parameters: dict[str, str | int]) -> Any:
        self.calls.append((url, parameters))
        return self.payload


class SequenceClient:
    def __init__(self, payloads: list[Any]) -> None:
        self.payloads = iter(payloads)
        self.calls: list[tuple[str, dict[str, str | int]]] = []

    def get_json(self, url: str, parameters: dict[str, str | int]) -> Any:
        self.calls.append((url, parameters))
        return next(self.payloads)


def ckan_payload() -> dict[str, object]:
    return {
        "success": True,
        "result": {
            "results": [
                {
                    "id": "dataset-1",
                    "name": "air-quality-example",
                    "title": "Air quality example",
                    "notes": "Fixture metadata",
                    "license_title": "Open Government Licence",
                    "organization": {"title": "Defra"},
                    "metadata_modified": "2026-07-01T12:00:00+00:00",
                    "resources": [
                        {
                            "id": "csv-1",
                            "url": "https://example.gov.uk/air.csv",
                            "name": "Readings",
                            "format": "CSV",
                            "mimetype": "text/csv",
                        },
                        {"format": "JSON"},
                    ],
                    "tags": [{"name": "air-quality"}],
                }
            ]
        },
    }


def arcgis_payload() -> dict[str, object]:
    return {
        "total": 1,
        "results": [
            {
                "id": "abc123",
                "title": "Protected habitat fixture",
                "owner": "Opendata_NE",
                "type": "Feature Service",
                "url": "https://services.arcgis.com/example/FeatureServer",
                "modified": 1782907200000,
                "contentStatus": "public_authoritative",
                "snippet": "Fixture metadata",
                "licenseInfo": "Open Government Licence",
                "tags": ["habitat", "protected sites"],
            }
        ],
    }


def test_ckan_connector_parses_candidates() -> None:
    client = FakeClient(ckan_payload())
    connector = CkanConnector(client=client)  # type: ignore[arg-type]
    candidates = connector.discover("air", 5)
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.provider == "ckan:data.gov.uk"
    assert candidate.source.status is SourceStatus.CANDIDATE
    assert candidate.source.formats == ("CSV", "JSON")
    assert len(candidate.source.resources) == 1
    assert candidate.source.resources[0].media_type == "text/csv"
    assert candidate.source.resources[0].last_modified is not None
    assert len(candidate.metadata_hash) == 64
    assert client.calls[0][1] == {"q": "air", "rows": 5, "start": 0}


@pytest.mark.parametrize(
    "payload",
    [{}, {"success": False}, {"success": True, "result": {}}],
)
def test_ckan_connector_rejects_invalid_contract(payload: object) -> None:
    with pytest.raises(DiscoveryError):
        CkanConnector().parse_response(payload)


def test_ckan_skips_malformed_items() -> None:
    payload = {"success": True, "result": {"results": [None, {"id": "missing"}]}}
    assert CkanConnector().parse_response(payload) == ()


def test_ckan_rejects_html_contaminated_resource_url() -> None:
    payload = ckan_payload()
    result = payload["result"]
    assert isinstance(result, dict)
    records = result["results"]
    assert isinstance(records, list)
    record = records[0]
    assert isinstance(record, dict)
    record["resources"] = [
        {
            "id": "bad-1",
            "url": "http://<div>https://example.gov.uk/data.csv</div>",
            "format": "CSV",
        }
    ]
    candidate = CkanConnector().parse_response(payload)[0]
    assert candidate.source.resources == ()


def test_arcgis_connector_parses_candidates() -> None:
    client = FakeClient(arcgis_payload())
    connector = ArcGisConnector(client=client)  # type: ignore[arg-type]
    candidates = connector.discover("habitat", 10)
    assert len(candidates) == 1
    assert candidates[0].source.publisher == "Natural England"
    assert candidates[0].source.formats == ("ArcGIS GeoServices REST API",)
    assert candidates[0].source.resources[0].authoritative
    assert candidates[0].source.resources[0].url.endswith("/FeatureServer")
    assert client.calls[0][1]["q"] == "(habitat) AND owner:Opendata_NE"
    assert client.calls[0][1]["start"] == 1


def test_discovery_report_contains_provider_coverage(source: SourceRecord) -> None:
    report = run_discovery((StaticConnector("fixture", (_candidate(source),)),), "air", 5)
    assert report.to_dict()["report_version"] == 3
    assert report.to_dict()["provider_coverage"] == {"fixture": {}}


def test_ckan_paginates_and_records_complete_coverage() -> None:
    def item(index: int) -> dict[str, object]:
        return {
            "id": f"dataset-{index}",
            "name": f"dataset-{index}",
            "title": f"Dataset {index}",
            "resources": [],
        }

    client = SequenceClient(
        [
            {"success": True, "result": {"count": 101, "results": [item(i) for i in range(100)]}},
            {"success": True, "result": {"count": 101, "results": [item(100)]}},
        ]
    )
    connector = CkanConnector(client=client)  # type: ignore[arg-type]
    assert len(connector.discover("water", 101)) == 101
    assert connector.coverage()["complete"] is True
    assert connector.coverage()["pages_fetched"] == 2
    assert client.calls[1][1]["start"] == 100


def test_arcgis_paginates_and_records_truncation() -> None:
    first = arcgis_payload()
    second = arcgis_payload()
    first["total"] = 300
    first["nextStart"] = 101
    second["total"] = 300
    second["nextStart"] = 201
    first_result = first["results"]
    second_result = second["results"]
    assert isinstance(first_result, list) and isinstance(second_result, list)
    first_result[0] = {**first_result[0], "id": "first"}
    second_result[0] = {**second_result[0], "id": "second"}
    client = SequenceClient([first, second])
    connector = ArcGisConnector(client=client)  # type: ignore[arg-type]
    assert len(connector.discover("habitat", 2)) == 2
    assert connector.coverage()["truncated_by_limit"] is True
    assert connector.coverage()["next_start"] == 201


@pytest.mark.parametrize("payload", [{}, {"results": [], "error": {"code": 400}}])
def test_arcgis_connector_rejects_invalid_contract(payload: object) -> None:
    with pytest.raises(DiscoveryError):
        ArcGisConnector().parse_response(payload)


def test_arcgis_skips_malformed_items() -> None:
    assert ArcGisConnector().parse_response({"results": [None, {"id": "missing"}]}) == ()


class StaticConnector(DiscoveryConnector):
    def __init__(
        self,
        name: str,
        candidates: tuple[DiscoveryCandidate, ...] = (),
        error: str | None = None,
    ) -> None:
        self.name = name
        self.candidates = candidates
        self.error = error

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        if self.error:
            raise DiscoveryError(self.error)
        return self.candidates[:limit]


def _candidate(source: SourceRecord, provider: str = "fixture") -> DiscoveryCandidate:
    return DiscoveryCandidate.from_metadata(
        source, provider, source.source_id, {"id": source.source_id}
    )


def test_discovery_deduplicates_and_preserves_partial_errors(source: SourceRecord) -> None:
    duplicate = replace(source, url=source.url + "/")
    report = run_discovery(
        (
            StaticConnector("first", (_candidate(source, "first"),)),
            StaticConnector("second", (_candidate(duplicate, "second"),)),
            StaticConnector("broken", error="unavailable"),
        ),
        "water",
        10,
    )
    assert len(report.candidates) == 1
    assert report.duplicates_removed == 1
    assert report.provider_counts == {"first": 1, "second": 1, "broken": 0}
    assert report.errors == ("broken: unavailable",)
    assert report.to_dict()["candidate_count"] == 1


@pytest.mark.parametrize(
    ("connectors", "query", "limit"),
    [((StaticConnector("ok"),), "", 1), ((StaticConnector("ok"),), "x", 0), ((), "x", 1)],
)
def test_discovery_rejects_invalid_inputs(
    connectors: tuple[DiscoveryConnector, ...], query: str, limit: int
) -> None:
    with pytest.raises(DiscoveryError):
        run_discovery(connectors, query, limit)


def test_discovery_raises_when_all_providers_fail() -> None:
    with pytest.raises(DiscoveryError, match="all discovery providers failed"):
        run_discovery((StaticConnector("broken", error="offline"),), "air", 5)


def test_candidate_rejects_promoted_source(source: SourceRecord) -> None:
    with pytest.raises(DiscoveryError, match="only produce candidate"):
        DiscoveryCandidate.from_metadata(
            replace(source, status=SourceStatus.VERIFIED), "fixture", "1", {}
        )


def test_canonical_url_key_normalizes_host_path_and_fragment() -> None:
    assert canonical_url_key("HTTPS://EXAMPLE.ORG/data/#part") == "https://example.org/data"


class FakeResponse(io.BytesIO):
    def __enter__(self) -> FakeResponse:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def test_http_client_parses_bounded_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ukei.discovery.http.urlopen", lambda *_args, **_kwargs: FakeResponse(b'{"ok": true}')
    )
    assert JsonHttpClient().get_json("https://example.org/api", {"q": "air"}) == {"ok": True}


def test_http_client_guards_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(DiscoveryError, match="HTTPS"):
        JsonHttpClient().get_json("http://example.org/api", {})

    monkeypatch.setattr(
        "ukei.discovery.http.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(URLError("offline")),
    )
    with pytest.raises(DiscoveryError, match="request failed"):
        JsonHttpClient().get_json("https://example.org/api", {})


def test_http_client_rejects_oversize_and_invalid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "ukei.discovery.http.urlopen",
        lambda *_args, **_kwargs: FakeResponse(b"x" * (MAX_RESPONSE_BYTES + 1)),
    )
    with pytest.raises(DiscoveryError, match="5 MB"):
        JsonHttpClient().get_json("https://example.org/api", {})

    monkeypatch.setattr(
        "ukei.discovery.http.urlopen", lambda *_args, **_kwargs: FakeResponse(b"not-json")
    )
    with pytest.raises(DiscoveryError, match="valid JSON"):
        JsonHttpClient().get_json("https://example.org/api", {})
