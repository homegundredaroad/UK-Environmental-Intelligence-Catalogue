"""Bounded live reachability validation for catalogue URLs."""

from __future__ import annotations

import ipaddress
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ukei.models import SourceRecord, ValidationResult


class UrlValidator:
    """Record one bounded HTTPS reachability observation without downloading a dataset."""

    name = "live.url"

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        self.timeout_seconds = timeout_seconds

    def validate(self, source: SourceRecord) -> tuple[ValidationResult, ...]:
        guard_error = _public_https_error(source.url)
        if guard_error:
            return (
                ValidationResult(
                    source_id=source.source_id,
                    check_name=self.name,
                    passed=False,
                    message=f"FAILED: URL check blocked: {guard_error}",
                    details={"failure_reason": guard_error, "status_code": None},
                ),
            )
        request = Request(
            source.url,
            headers={
                "Accept": "*/*",
                "Range": "bytes=0-0",
                "User-Agent": "ukei-catalogue/0.4 (+catalogue reachability check)",
            },
            method="GET",
        )
        started = monotonic()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response.read(1)
                status = int(getattr(response, "status", 200))
                final_url = response.geturl()
                content_type = response.headers.get("Content-Type", "")
            elapsed_ms = round((monotonic() - started) * 1000)
            redirect_error = _public_https_error(final_url)
            passed = 200 <= status < 400 and redirect_error is None
            message = (
                f"URL returned HTTP {status} in {elapsed_ms} ms"
                if redirect_error is None
                else f"URL redirect blocked: {redirect_error}"
            )
            return (
                ValidationResult(
                    source_id=source.source_id,
                    check_name=self.name,
                    passed=passed,
                    message=message if passed else f"FAILED: {message}",
                    details={
                        "content_type": content_type,
                        "elapsed_ms": elapsed_ms,
                        "final_url": final_url,
                        "status_code": status,
                    },
                ),
            )
        except HTTPError as exc:
            return (self._failure(source, started, f"HTTP {exc.code}", exc.code),)
        except (URLError, OSError) as exc:
            reason = getattr(exc, "reason", exc)
            return (self._failure(source, started, str(reason), None),)

    @staticmethod
    def _failure(
        source: SourceRecord, started: float, reason: str, status_code: int | None
    ) -> ValidationResult:
        elapsed_ms = round((monotonic() - started) * 1000)
        return ValidationResult(
            source_id=source.source_id,
            check_name="live.url",
            passed=False,
            message=f"FAILED: URL check failed: {reason}",
            details={
                "elapsed_ms": elapsed_ms,
                "status_code": status_code,
                "failure_reason": reason,
            },
        )


def _public_https_error(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return "only absolute HTTPS URLs are allowed"
    hostname = parsed.hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        return "local hostnames are not allowed"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return None
    return None if address.is_global else "non-public IP addresses are not allowed"
