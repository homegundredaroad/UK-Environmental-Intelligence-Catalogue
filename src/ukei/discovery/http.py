"""Bounded JSON HTTP transport for public discovery catalogues."""

from __future__ import annotations

import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

from ukei.discovery.base import DiscoveryError

MAX_RESPONSE_BYTES = 5_000_000


class JsonHttpClient:
    """Small injectable transport with HTTPS and response-size guards."""

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def get_json(self, url: str, parameters: dict[str, str | int]) -> Any:
        if urlsplit(url).scheme != "https":
            raise DiscoveryError("discovery endpoint must use HTTPS")
        request_url = f"{url}?{urlencode(parameters)}"
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "ukei-catalogue/0.3"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DiscoveryError(f"request failed: {exc}") from exc
        if len(body) > MAX_RESPONSE_BYTES:
            raise DiscoveryError("response exceeded 5 MB safety limit")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiscoveryError("response was not valid JSON") from exc
