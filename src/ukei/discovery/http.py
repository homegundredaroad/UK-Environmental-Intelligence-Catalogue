"""Bounded JSON HTTP transport for public discovery catalogues."""

from __future__ import annotations

import ipaddress
import json
import socket
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener, urlopen

from ukei.discovery.base import DiscoveryError
from ukei.url_safety import url_error

MAX_RESPONSE_BYTES = 5_000_000


class _RejectRedirects(HTTPRedirectHandler):
    """Do not follow unvalidated redirect targets during strict discovery."""

    def redirect_request(
        self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        raise DiscoveryError("strict discovery blocked an HTTP redirect")


def _require_public_dns(url: str) -> None:
    """Reject explicitly non-public DNS answers before attempting a request.

    This is a preflight, not DNS pinning. Operate only with reviewed providers.
    """
    parts = urlsplit(url)
    hostname = parts.hostname
    if not hostname:
        raise DiscoveryError("strict discovery URL lacks a hostname")
    try:
        answers = socket.getaddrinfo(hostname, parts.port or 443, type=socket.SOCK_STREAM)
    except (OSError, ValueError) as exc:
        raise DiscoveryError("strict discovery cannot resolve endpoint") from exc
    if not answers:
        raise DiscoveryError("strict discovery DNS returned no addresses")
    for answer in answers:
        try:
            address = ipaddress.ip_address(answer[4][0])
        except (IndexError, TypeError, ValueError) as exc:
            raise DiscoveryError("strict discovery DNS returned an invalid address") from exc
        if not address.is_global:
            raise DiscoveryError("strict discovery rejected a non-public DNS address")



def open_public_request(request: Request, timeout_seconds: float) -> Any:
    """Open a reviewed public HTTPS request without proxies or redirects.

    DNS checks are not connection pinning; restrict use to vetted providers.
    """
    if url_error(request.full_url, require_https=True, public_only=True) is not None:
        raise DiscoveryError("strict discovery requires a public HTTPS endpoint")
    _require_public_dns(request.full_url)
    opener = build_opener(ProxyHandler({}), _RejectRedirects())
    return opener.open(request, timeout=timeout_seconds)


class JsonHttpClient:
    """Small injectable transport with HTTPS and response-size guards.

    strict_public also disallows redirects/proxies and rejects non-public DNS
    answers. It does not guarantee protection against a DNS rebinding race.
    """

    def __init__(self, timeout_seconds: float = 20.0, *, strict_public: bool = False) -> None:
        self.timeout_seconds = timeout_seconds
        self.strict_public = strict_public

    def get_json(self, url: str, parameters: dict[str, str | int]) -> Any:
        if urlsplit(url).scheme != "https":
            raise DiscoveryError("discovery endpoint must use HTTPS")
        if self.strict_public:
            if url_error(url, require_https=True, public_only=True) is not None:
                raise DiscoveryError("strict discovery requires a public HTTPS endpoint")
        request_url = f"{url}?{urlencode(parameters)}"
        request = Request(
            request_url,
            headers={"Accept": "application/json", "User-Agent": "ukei-catalogue/0.3"},
        )
        try:
            if self.strict_public:
                response_context = open_public_request(request, self.timeout_seconds)
            else:
                response_context = urlopen(request, timeout=self.timeout_seconds)
            with response_context as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except (HTTPError, URLError, TimeoutError, OSError) as exc:
            raise DiscoveryError(f"request failed: {exc}") from exc
        if len(body) > MAX_RESPONSE_BYTES:
            raise DiscoveryError("response exceeded 5 MB safety limit")
        try:
            return json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DiscoveryError("response was not valid JSON") from exc
