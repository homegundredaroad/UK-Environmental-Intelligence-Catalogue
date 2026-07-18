"""CKAN package-search discovery adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ukei.discovery.base import DiscoveryCandidate, DiscoveryConnector, DiscoveryError
from ukei.discovery.http import JsonHttpClient
from ukei.models import ResourceReference, SourceRecord, make_source_id, utc_now
from ukei.url_safety import url_error


class CkanConnector(DiscoveryConnector):
    """Discover dataset candidates from a CKAN action API."""

    name = "ckan:data.gov.uk"

    def __init__(
        self,
        client: JsonHttpClient | None = None,
        endpoint: str = "https://data.gov.uk/api/action/package_search",
    ) -> None:
        self.client = client or JsonHttpClient()
        self.endpoint = endpoint
        self._coverage: dict[str, Any] = {}

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        candidates: list[DiscoveryCandidate] = []
        start = 0
        pages = 0
        provider_total: int | None = None
        exhausted = False
        records_received = 0
        while len(candidates) < limit:
            rows = min(100, limit - len(candidates))
            payload = self.client.get_json(
                self.endpoint, {"q": query, "rows": rows, "start": start}
            )
            pages += 1
            result = payload.get("result") if isinstance(payload, Mapping) else None
            if isinstance(result, Mapping):
                try:
                    provider_total = int(str(result.get("count")))
                except (TypeError, ValueError):
                    provider_total = None
            raw_results = result.get("results") if isinstance(result, Mapping) else None
            received = len(raw_results) if isinstance(raw_results, list) else 0
            records_received += received
            page = self.parse_response(payload)
            candidates.extend(page)
            start += rows
            exhausted = received < rows
            if exhausted or (provider_total is not None and start >= provider_total):
                break
        self._coverage = {
            "complete": exhausted or (provider_total is not None and start >= provider_total),
            "limit": limit,
            "pages_fetched": pages,
            "provider_total": provider_total,
            "records_returned": len(candidates[:limit]),
            "records_received": records_received,
            "truncated_by_limit": not exhausted
            and (provider_total is None or len(candidates) < provider_total),
        }
        return tuple(candidates[:limit])

    def coverage(self) -> dict[str, Any]:
        return dict(self._coverage)

    def parse_response(self, payload: Any) -> tuple[DiscoveryCandidate, ...]:
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            raise DiscoveryError("CKAN response did not report success")
        result = payload.get("result")
        if not isinstance(result, Mapping) or not isinstance(result.get("results"), list):
            raise DiscoveryError("CKAN response lacks result.results")

        retrieved_at = utc_now()
        candidates: list[DiscoveryCandidate] = []
        for item in result["results"]:
            if not isinstance(item, Mapping):
                continue
            remote_id = _text(item.get("id")) or _text(item.get("name"))
            title = _text(item.get("title"))
            name = _text(item.get("name"))
            if not remote_id or not title or not name:
                continue
            canonical_url = f"https://www.data.gov.uk/dataset/{name}"
            organization = item.get("organization")
            publisher = (
                _text(organization.get("title"))
                if isinstance(organization, Mapping)
                else "Publisher not supplied by CKAN"
            )
            licence = _text(item.get("license_title")) or (
                "Not supplied by discovery response; verify the dataset record before reuse"
            )
            resources = _resources(item, canonical_url, licence)
            formats = sorted(
                {
                    value
                    for resource in item.get("resources", [])
                    if isinstance(resource, Mapping)
                    if (value := _text(resource.get("format")))
                }
            )
            themes = sorted(
                {
                    value
                    for tag in item.get("tags", [])
                    if isinstance(tag, Mapping)
                    if (value := _text(tag.get("display_name")) or _text(tag.get("name")))
                }
            )
            source = SourceRecord(
                source_id=make_source_id(remote_id, self.name),
                title=title,
                url=canonical_url,
                publisher=publisher or "Publisher not supplied by CKAN",
                description=_text(item.get("notes")),
                licence=licence,
                geographic_scope="United Kingdom; verify dataset record",
                update_frequency="not supplied by discovery response",
                formats=tuple(formats),
                themes=tuple(themes),
                resources=resources,
                discovered_at=retrieved_at,
                provenance_url=canonical_url,
                connector=self.name,
                created_at=retrieved_at,
                updated_at=retrieved_at,
            )
            candidates.append(DiscoveryCandidate.from_metadata(source, self.name, remote_id, item))
        return tuple(candidates)


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _resources(
    item: Mapping[object, object], provenance_url: str, licence: str
) -> tuple[ResourceReference, ...]:
    raw_resources = item.get("resources")
    if not isinstance(raw_resources, list):
        return ()
    package_modified = _optional_datetime(item.get("metadata_modified"))
    resources: list[ResourceReference] = []
    for raw in raw_resources:
        if not isinstance(raw, Mapping):
            continue
        url = _text(raw.get("url"))
        if url_error(url) is not None:
            continue
        resource_id = _text(raw.get("id")) or make_source_id(url, "ckan-resource")
        resources.append(
            ResourceReference(
                resource_id=resource_id,
                url=url,
                name=_text(raw.get("name")) or _text(raw.get("description")),
                format=_text(raw.get("format")),
                media_type=_text(raw.get("mimetype")),
                licence=licence,
                last_modified=_optional_datetime(raw.get("last_modified")) or package_modified,
                provenance_url=provenance_url,
            )
        )
    return tuple(resources)


def _optional_datetime(value: object) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
