"""Conservative licence normalisation for catalogue evidence."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass

_TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True, slots=True)
class LicenceClassification:
    category: str
    identifier: str | None
    commercial_use: bool | None
    attribution_required: bool | None
    normalized_text: str

    def to_dict(self) -> dict[str, object]:
        return {
            "attribution_required": self.attribution_required,
            "category": self.category,
            "commercial_use": self.commercial_use,
            "identifier": self.identifier,
            "normalized_text": self.normalized_text,
        }


def classify_licence(value: str) -> LicenceClassification:
    """Classify common UK public-data terms without overstating reuse rights."""
    text = " ".join(html.unescape(_TAG_RE.sub(" ", value)).split())
    lowered = text.casefold()
    if not text or lowered.startswith(("unknown", "not supplied", "verify")):
        return LicenceClassification("unknown", None, None, None, text)
    if "non-commercial government licence" in lowered or "non commercial" in lowered:
        return LicenceClassification("restricted", "NCGL-2.0", False, True, text)
    if "open government licence" in lowered or re.search(r"\bogl(?:[- ]?v?3(?:\.0)?)?\b", lowered):
        identifier = "OGL-3.0" if "3" in lowered else "OGL"
        return LicenceClassification("open", identifier, True, True, text)
    if "creative commons" in lowered and "noncommercial" in lowered:
        return LicenceClassification("restricted", "CC-BY-NC", False, True, text)
    if "creative commons" in lowered or "cc-by" in lowered:
        return LicenceClassification("open", "CC-BY", True, True, text)
    if "terms of use" in lowered or "terms and conditions" in lowered:
        return LicenceClassification("custom", None, None, None, text)
    return LicenceClassification("explicit-unclassified", None, None, None, text)
