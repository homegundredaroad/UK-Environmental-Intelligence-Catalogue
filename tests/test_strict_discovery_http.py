"""Network safety regression tests for opt-in environmental catalogue discovery."""

from __future__ import annotations

import io
from urllib.request import ProxyHandler, Request

import pytest

from ukei.discovery.base import DiscoveryError
from ukei.discovery.http import JsonHttpClient, _RejectRedirects
from ukei.discovery.ogc_records import OgcRecordsConnector


class FakeOpener:
    def __init__(self) -> None:
        self.calls = 0

    def open(self, request: Request, timeout: float) -> io.BytesIO:
        self.calls += 1
        assert request.full_url == "https://catalogue.example.org/items?q=water"
        assert timeout == 3.0
        return io.BytesIO(b'{"features":[],"numberMatched":0}')


def test_strict_transport_rejects_private_dns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "ukei.discovery.http.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("127.0.0.1", 443))],
    )
    with pytest.raises(DiscoveryError, match="non-public DNS"):
        JsonHttpClient(strict_public=True).get_json(
            "https://catalogue.example.org/items", {"q": "water"}
        )


def test_strict_transport_rejects_private_url_without_dns() -> None:
    with pytest.raises(DiscoveryError, match="public HTTPS"):
        JsonHttpClient(strict_public=True).get_json("https://127.0.0.1/items", {})


def test_strict_transport_uses_no_proxy_and_no_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opener = FakeOpener()

    def fake_build_opener(*handlers: object) -> FakeOpener:
        assert any(isinstance(value, _RejectRedirects) for value in handlers)
        assert any(isinstance(value, ProxyHandler) and not value.proxies for value in handlers)
        return opener

    monkeypatch.setattr(
        "ukei.discovery.http.socket.getaddrinfo",
        lambda *_args, **_kwargs: [(None, None, None, None, ("8.8.8.8", 443))],
    )
    monkeypatch.setattr("ukei.discovery.http.build_opener", fake_build_opener)
    payload = JsonHttpClient(3.0, strict_public=True).get_json(
        "https://catalogue.example.org/items", {"q": "water"}
    )
    assert payload["numberMatched"] == 0
    assert opener.calls == 1


def test_strict_transport_rejects_redirect() -> None:
    handler = _RejectRedirects()
    with pytest.raises(DiscoveryError, match="redirect"):
        handler.redirect_request(
            Request("https://catalogue.example.org/items"),
            None,
            302,
            "Found",
            {"Location": "https://127.0.0.1/internal"},
            "https://127.0.0.1/internal",
        )


def test_ogc_connector_defaults_to_strict_transport() -> None:
    connector = OgcRecordsConnector("https://catalogue.example.org/collections/a/items")
    assert isinstance(connector.client, JsonHttpClient)
    assert connector.client.strict_public is True
