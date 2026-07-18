"""ArcGIS Online item-search discovery adapter."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ukei.discovery.base import DiscoveryCandidate, DiscoveryConnector, DiscoveryError
from ukei.discovery.http import JsonHttpClient
from ukei.models import ResourceReference, SourceRecord, make_source_id, utc_now
from ukei.url_safety import url_error


class ArcGisConnector(DiscoveryConnector):
    """Discover geospatial candidates through the ArcGIS sharing REST API."""

    name = "arcgis:natural-england"
    owner = "Opendata_NE"

    def __init__(
        self,
        client: JsonHttpClient | None = None,
        endpoint: str = "https://www.arcgis.com/sharing/rest/search",
    ) -> None:
        self.client = client or JsonHttpClient()
        self.endpoint = endpoint
        self._coverage: dict[str, Any] = {}

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        scoped_query = f"({query}) AND owner:{self.owner}"
        candidates: list[DiscoveryCandidate] = []
        start = 1
        pages = 0
        provider_total: int | None = None
        next_start = start
        records_received = 0
        while len(candidates) < limit and next_start != -1:
            page_size = min(100, limit - len(candidates))
            payload = self.client.get_json(
                self.endpoint,
                {
                    "q": scoped_query,
                    "num": page_size,
                    "start": next_start,
                    "f": "json",
                    "sortField": "modified",
                },
            )
            pages += 1
            if isinstance(payload, Mapping):
                try:
                    provider_total = int(str(payload.get("total")))
                except (TypeError, ValueError):
                    provider_total = None
                try:
                    next_start = int(str(payload.get("nextStart", -1)))
                except (TypeError, ValueError):
                    next_start = -1
            else:
                next_start = -1
            raw_results = payload.get("results") if isinstance(payload, Mapping) else None
            received = len(raw_results) if isinstance(raw_results, list) else 0
            records_received += received
            page = self.parse_response(payload)
            candidates.extend(page)
            if received == 0:
                break
        returned = len(candidates[:limit])
        self._coverage = {
            "complete": next_start == -1 and (provider_total is None or returned >= provider_total),
            "limit": limit,
            "next_start": next_start,
            "pages_fetched": pages,
            "provider_total": provider_total,
            "records_returned": returned,
            "records_received": records_received,
            "truncated_by_limit": next_start != -1
            or (provider_total is not None and returned < provider_total),
        }
        return tuple(candidates[:limit])

    def coverage(self) -> dict[str, Any]:
        return dict(self._coverage)

    def parse_response(self, payload: Any) -> tuple[DiscoveryCandidate, ...]:
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise DiscoveryError("ArcGIS response lacks results")
        if payload.get("error"):
            raise DiscoveryError("ArcGIS response contains an error")

        retrieved_at = utc_now()
        candidates: list[DiscoveryCandidate] = []
        for item in payload["results"]:
            if not isinstance(item, Mapping):
                continue
            remote_id = _text(item.get("id"))
            title = _text(item.get("title"))
            if not remote_id or not title:
                continue
            canonical_url = f"https://www.arcgis.com/home/item.html?id={remote_id}"
            owner = _text(item.get("owner"))
            licence = _text(item.get("licenseInfo")) or (
                "Not supplied by discovery response; verify the ArcGIS item before reuse"
            )
            raw_tags = item.get("tags")
            tags: list[object] = list(raw_tags) if isinstance(raw_tags, list) else []
            resource_url = _text(item.get("url"))
            resources = (
                (
                    ResourceReference(
                        resource_id=remote_id,
                        url=resource_url,
                        name=title,
                        format=_text(item.get("type")) or "ArcGIS item",
                        licence=licence,
                        last_modified=_arcgis_datetime(item.get("modified")),
                        provenance_url=canonical_url,
                        authoritative="authoritative" in _text(item.get("contentStatus")).lower(),
                    ),
                )
                if url_error(resource_url) is None
                else ()
            )
            source = SourceRecord(
                source_id=make_source_id(remote_id, self.name),
                title=title,
                url=canonical_url,
                publisher="Natural England" if owner == self.owner else owner or "Natural England",
                description=_text(item.get("description")) or _text(item.get("snippet")),
                licence=licence,
                geographic_scope="England; verify item extent",
                update_frequency="not supplied by discovery response",
                formats=(_text(item.get("type")) or "ArcGIS item",),
                themes=tuple(_text(tag) for tag in tags if _text(tag)),
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


def _arcgis_datetime(value: object) -> datetime | None:
    try:
        milliseconds = int(str(value))
    except (TypeError, ValueError):
        return None
    return datetime.fromtimestamp(milliseconds / 1000, UTC)
