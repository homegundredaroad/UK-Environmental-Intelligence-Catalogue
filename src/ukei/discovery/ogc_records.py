"""Opt-in, candidate-only discovery from OGC API - Records collection items.

No publisher is implicitly trusted. No source is promoted by discovery.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urljoin, urlsplit

from ukei.discovery.base import DiscoveryCandidate, DiscoveryConnector, DiscoveryError
from ukei.discovery.http import JsonHttpClient
from ukei.models import ResourceReference, SourceRecord, make_source_id, utc_now
from ukei.normalization import clean_text, normalize_format
from ukei.url_safety import url_error

_DATA_RELS = {"data", "download", "enclosure", "service"}
_AUTH_KEYS = {"key", "api_key", "apikey", "token", "access_token", "password", "secret"}


def _text(value: object) -> str:
    return clean_text(value)


def _links(item: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    raw = item.get("links")
    return [value for value in raw if isinstance(value, Mapping)] if isinstance(raw, list) else []


def _safe_public_url(value: object) -> str:
    url = _text(value)
    if url_error(url, require_https=True, public_only=True) is not None:
        return ""
    query_keys = {key.casefold() for key, _ in parse_qsl(urlsplit(url).query)}
    return "" if query_keys & _AUTH_KEYS else url


def _next_request(current_url: str, href: str, origin: str) -> tuple[str, dict[str, str | int]]:
    target = urljoin(current_url, href)
    parts, root = urlsplit(target), urlsplit(origin)
    if url_error(target, require_https=True, public_only=True) is not None or (
        parts.scheme,
        parts.netloc.lower(),
    ) != (root.scheme, root.netloc.lower()):
        raise DiscoveryError("OGC Records pagination escaped the configured HTTPS origin")
    params: dict[str, str | int] = dict(parse_qsl(parts.query, keep_blank_values=True))
    if any(key.lower() in _AUTH_KEYS for key in params):
        raise DiscoveryError("OGC Records next link contained credential parameters")
    return target.split("?")[0].split("#")[0], params


class OgcRecordsConnector(DiscoveryConnector):
    """Read an explicitly selected OGC API Records /collections/{id}/items endpoint."""

    name = "ogc-records:opt-in"

    def __init__(self, endpoint: str, client: JsonHttpClient | None = None) -> None:
        if url_error(endpoint, require_https=True, public_only=True) is not None:
            raise DiscoveryError("OGC Records endpoint must be a public HTTPS URL")
        if urlsplit(endpoint).query or urlsplit(endpoint).fragment:
            raise DiscoveryError("OGC Records endpoint must not contain query or fragment")
        self.endpoint = endpoint.rstrip("/")
        self.client = client or JsonHttpClient(strict_public=True)
        self._coverage: dict[str, Any] = {}

    def coverage(self) -> dict[str, Any]:
        return dict(self._coverage)

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        if not query.strip() or not 1 <= limit <= 1_000:
            raise DiscoveryError("OGC Records requires a query and limit of 1-1000")
        candidates: list[DiscoveryCandidate] = []
        current = self.endpoint
        params: dict[str, str | int] = {"q": query, "limit": min(100, limit)}
        seen: set[str] = set()
        matched: int | None = None
        pages = 0
        received = 0
        has_next = False
        while len(candidates) < limit:
            key = f"{current}?{urlencode(sorted(params.items()))}"
            if key in seen:
                raise DiscoveryError("OGC Records pagination cycle detected")
            seen.add(key)
            payload = self.client.get_json(current, params)
            if not isinstance(payload, Mapping):
                raise DiscoveryError("OGC Records response must be an object")
            raw = payload.get("features")
            if not isinstance(raw, list):
                raise DiscoveryError("OGC Records response lacks features list")
            pages += 1
            received += len(raw)
            value = payload.get("numberMatched")
            if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
                matched = value
            for item in raw:
                if isinstance(item, Mapping):
                    candidate = self._parse_record(item)
                    if candidate:
                        candidates.append(candidate)
            raw_links = payload.get("links")
            next_links = (
                [
                    link
                    for link in raw_links
                    if isinstance(link, Mapping) and _text(link.get("rel")) == "next"
                ]
                if isinstance(raw_links, list)
                else []
            )
            has_next = bool(next_links)
            if not has_next or len(candidates) >= limit:
                break
            if not raw:
                raise DiscoveryError("OGC Records returned an empty page with a next link")
            href = _text(next_links[0].get("href"))
            if not href:
                raise DiscoveryError("OGC Records next link has no href")
            current, params = _next_request(current, href, self.endpoint)

        returned = len(candidates[:limit])
        unknown = matched is None
        truncated = has_next or (matched is not None and returned < matched)
        self._coverage = {
            "complete": not truncated and not unknown,
            "coverage_unknown": unknown,
            "truncated_by_limit": truncated,
            "limit": limit,
            "provider_total": matched,
            "pages_fetched": pages,
            "records_received": received,
            "records_returned": returned,
            "claim": "candidate-only; source coverage, licences and schemas not verified",
        }
        return tuple(candidates[:limit])

    def _parse_record(self, item: Mapping[str, Any]) -> DiscoveryCandidate | None:
        raw_id = _text(item.get("id"))
        props = item.get("properties")
        properties = props if isinstance(props, Mapping) else {}
        title = _text(properties.get("title")) or _text(item.get("title"))
        if not raw_id or not title:
            return None
        links = _links(item)
        canonical = (
            next(
                (
                    safe
                    for link in links
                    if _text(link.get("rel")) == "self"
                    if (safe := _safe_public_url(link.get("href")))
                ),
                "",
            )
            or f"{self.endpoint}/{quote(raw_id, safe='')}"
        )
        publisher = "Publisher not supplied by OGC Records"
        contacts = properties.get("contacts")
        if isinstance(contacts, list):
            for contact in contacts:
                if isinstance(contact, Mapping):
                    roles = contact.get("roles")
                    if isinstance(roles, list) and "publisher" in roles:
                        publisher = (
                            _text(contact.get("organization"))
                            or _text(contact.get("name"))
                            or publisher
                        )
                        break
        licence = _text(properties.get("license")) or (
            "Not supplied by discovery response; independently verify rights"
        )
        resources = []
        formats: set[str] = set()
        for index, link in enumerate(links):
            if _text(link.get("rel")) not in _DATA_RELS:
                continue
            url = _safe_public_url(link.get("href"))
            if not url:
                continue
            media = _text(link.get("type"))
            fmt = normalize_format(media) or _text(link.get("title")) or "machine service"
            formats.add(fmt)
            resources.append(
                ResourceReference(
                    resource_id=make_source_id(url, f"ogc-link-{index}"),
                    url=url,
                    name=_text(link.get("title")),
                    format=fmt,
                    media_type=media,
                    licence=licence,
                    provenance_url=canonical,
                )
            )
        keywords = properties.get("keywords")
        themes = (
            tuple(_text(item) for item in keywords if _text(item))
            if isinstance(keywords, list)
            else ()
        )
        now = utc_now()
        source = SourceRecord(
            source_id=make_source_id(raw_id, self.name + ":" + self.endpoint),
            title=title,
            url=canonical,
            publisher=publisher,
            description=_text(properties.get("description")),
            licence=licence,
            geographic_scope="Unknown; verify UK coverage and spatial extent",
            update_frequency="Not supplied by discovery response",
            formats=tuple(formats),
            themes=themes,
            resources=tuple(resources),
            discovered_at=now,
            provenance_url=canonical,
            connector=self.name,
            created_at=now,
            updated_at=now,
        )
        return DiscoveryCandidate.from_metadata(source, self.name, raw_id, item)
