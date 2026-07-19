"""Conservative normalization helpers that preserve original catalogue evidence."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser

_SPACE = re.compile(r"\s+")
_FORMAT_ALIASES = {
    ".csv": "CSV",
    ".json": "JSON",
    ".pdf": "PDF",
    ".xlsx": "XLSX",
    "esri rest": "ArcGIS GeoServices REST API",
    "feature service": "ArcGIS GeoServices REST API",
    "ogc wfs": "WFS",
    "ogc wms": "WMS",
}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.casefold() in {"script", "style"}:
            self.ignored_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in {"script", "style"} and self.ignored_depth:
            self.ignored_depth -= 1

    def handle_data(self, data: str) -> None:
        if not self.ignored_depth:
            self.parts.append(data)


def clean_text(value: object) -> str:
    """Remove markup and collapse whitespace without inventing metadata."""
    raw = html.unescape(str(value or ""))
    parser = _TextExtractor()
    try:
        parser.feed(raw)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:  # pragma: no cover - HTMLParser is intentionally defensive
        text = re.sub(r"<[^>]+>", " ", raw)
    return _SPACE.sub(" ", text).strip()


def normalize_format(value: object) -> str:
    """Return a display-level canonical format while retaining unknown labels."""
    cleaned = clean_text(value)
    if not cleaned:
        return ""
    lowered = cleaned.casefold()
    if lowered in _FORMAT_ALIASES:
        return _FORMAT_ALIASES[lowered]
    if lowered.startswith("https://www.iana.org/assignments/media-types/"):
        return cleaned.rsplit("/", 1)[-1].upper()
    return cleaned.upper() if len(cleaned) <= 8 and " " not in cleaned else cleaned
