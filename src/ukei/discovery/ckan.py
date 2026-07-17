"""CKAN package-search discovery adapter."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ukei.discovery.base import DiscoveryCandidate, DiscoveryConnector, DiscoveryError
from ukei.discovery.http import JsonHttpClient
from ukei.models import SourceRecord, make_source_id, utc_now


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

    def discover(self, query: str, limit: int) -> tuple[DiscoveryCandidate, ...]:
        payload = self.client.get_json(self.endpoint, {"q": query, "rows": limit})
        return self.parse_response(payload)

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
