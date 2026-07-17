"""ArcGIS Online item-search discovery adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ukei.discovery.base import DiscoveryCandidate, DiscoveryConnector, DiscoveryError
from ukei.discovery.http import JsonHttpClient
from ukei.models import SourceRecord, make_source_id, utc_now


class ArcGisConnector(DiscoveryConnector):
    """Discover geospatial candidates through the ArcGIS sharing REST API."""

    name = "arcgis:natural-england"

    def __init__(
        self,
        client: JsonHttpClient | None = None,
        endpoint: str = "https://www.arcgis.com/sharing/rest/search",
    ) -> None:
        self.client = client or JsonHttpClient()
        self.endpoint = endpoint

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        scoped_query = f'({query}) AND (owner:naturalengland OR owner:"Natural England")'
        payload = self.client.get_json(
            self.endpoint, {"q": scoped_query, "num": limit, "f": "json", "sortField": "modified"}
        )
        return self.parse_response(payload)

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
            owner = _text(item.get("owner")) or "Natural England ArcGIS publisher"
            licence = _text(item.get("licenseInfo")) or (
                "Not supplied by discovery response; verify the ArcGIS item before reuse"
            )
            raw_tags = item.get("tags")
            tags: list[object] = list(raw_tags) if isinstance(raw_tags, list) else []
            source = SourceRecord(
                source_id=make_source_id(remote_id, self.name),
                title=title,
                url=canonical_url,
                publisher=owner,
                description=_text(item.get("description")) or _text(item.get("snippet")),
                licence=licence,
                geographic_scope="England; verify item extent",
                update_frequency="not supplied by discovery response",
                formats=(_text(item.get("type")) or "ArcGIS item",),
                themes=tuple(_text(tag) for tag in tags if _text(tag)),
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
