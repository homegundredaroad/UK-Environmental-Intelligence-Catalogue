"""Strict URL parsing shared by discovery and validation."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse

_HOST_RE = re.compile(
    r"^(?=.{1,253}\.?$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.?$",
    re.IGNORECASE,
)


def url_error(url: str, *, require_https: bool = False, public_only: bool = False) -> str | None:
    """Return a reason when *url* is unsafe or malformed, otherwise ``None``."""
    if not url or any(character.isspace() or ord(character) < 32 for character in url):
        return "URL contains whitespace or control characters"
    if any(character in url for character in '<>"{}|\\^'):
        return "URL contains markup or unsafe characters"
    parsed = urlparse(url)
    allowed = {"https"} if require_https else {"http", "https"}
    if parsed.scheme.lower() not in allowed or not parsed.hostname:
        scheme = "HTTPS" if require_https else "HTTP(S)"
        return f"only absolute {scheme} URLs are allowed"
    if parsed.username is not None or parsed.password is not None:
        return "embedded credentials are not allowed"
    try:
        port = parsed.port
    except ValueError:
        return "URL port is invalid"
    if port is not None and not 1 <= port <= 65535:
        return "URL port is invalid"
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        if not _HOST_RE.fullmatch(hostname):
            return "URL hostname is invalid"
        if public_only and (
            hostname == "localhost"
            or hostname.endswith(".localhost")
            or hostname.endswith(".local")
        ):
            return "local hostnames are not allowed"
    else:
        if public_only and not address.is_global:
            return "non-public IP addresses are not allowed"
    return None
