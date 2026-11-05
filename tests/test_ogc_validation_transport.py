"""Regression checks for trusted-transport boundaries after OGC discovery."""

from __future__ import annotations

import io
from dataclasses import replace
from email.message import Message
from urllib.request import Request

import pytest

from ukei.discovery.base import DiscoveryError
from ukei.models import ResourceReference, SourceRecord
from ukei.validation import ResourceValidator, UrlValidator


class FakeResponse(io.BytesIO):
    status = 200

    def __init__(self, body: bytes = b"{}") -> None:
        super().__init__(body)
        self.headers = Message()
        self.headers["Content-Type"] = "application/json"

    def geturl(self) -> str:
        return "https://example.gov.uk/data"


def block_legacy(*_args: object, **_kwargs: object) -> None:
    raise AssertionError("legacy redirect-following transport was called")


def test_ogc_landing_page_uses_strict_transport(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def strict_open(request: Request, timeout_seconds: float) -> FakeResponse:
        assert request.full_url == source.url
        assert timeout_seconds == 2.0
        return FakeResponse()

    monkeypatch.setattr("ukei.validation.live.urlopen", block_legacy)
    monkeypatch.setattr("ukei.validation.live.open_public_request", strict_open)
    result = UrlValidator(2).validate(replace(source, connector="ogc-records:opt-in"))[0]
    assert result.passed


def test_ogc_resource_private_dns_is_not_queried(
    source: SourceRecord, monkeypatch: pytest.MonkeyPatch
) -> None:
    def block_strict(_request: Request, _timeout_seconds: float) -> None:
        raise DiscoveryError("strict discovery rejected a non-public DNS address")

    monkeypatch.setattr("ukei.validation.live.urlopen", block_legacy)
    monkeypatch.setattr("ukei.validation.live.open_public_request", block_strict)
    resource = ResourceReference(
        resource_id="ogc-csv",
        url="https://data.example.gov.uk/file.csv",
        format="CSV",
        licence="OGL-3.0",
    )
    results = ResourceValidator().validate(
        replace(source, connector="ogc-records:opt-in", resources=(resource,))
    )
    url_result = next(item for item in results if item.check_name == "resource.url")
    assert url_result.passed is False
    assert url_result.details["outcome"] == "blocked_by_policy"


@pytest.mark.parametrize(
    ("url", "format_name", "body"),
    [
        (
            "https://services.arcgis.com/example/FeatureServer",
            "ArcGIS GeoServices REST API",
            b'{"currentVersion":11.3,"layers":[{"id":0}],"tables":[]}',
        ),
        (
            "https://example.gov.uk/wms",
            "WMS",
            b"<WMS_Capabilities><Layer><Name>water</Name></Layer></WMS_Capabilities>",
        ),
    ],
)
def test_ogc_service_metadata_uses_strict_transport(
    source: SourceRecord,
    monkeypatch: pytest.MonkeyPatch,
    url: str,
    format_name: str,
    body: bytes,
) -> None:
    monkeypatch.setattr("ukei.validation.live.urlopen", block_legacy)
    monkeypatch.setattr("ukei.validation.resources.urlopen", block_legacy)
    monkeypatch.setattr(
        "ukei.validation.live.open_public_request",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        "ukei.validation.resources.open_public_request",
        lambda *_args, **_kwargs: FakeResponse(body),
    )
    resource = ResourceReference(
        resource_id="ogc-service",
        url=url,
        format=format_name,
        licence="OGL-3.0",
    )
    results = ResourceValidator().validate(
        replace(source, connector="ogc-records:opt-in", resources=(resource,))
    )
    service = next(item for item in results if item.check_name == "resource.service")
    assert service.passed is True
    assert service.details["outcome"] == "semantically_valid"
