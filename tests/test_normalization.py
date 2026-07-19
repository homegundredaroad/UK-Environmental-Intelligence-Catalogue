from ukei.normalization import clean_text, normalize_format


def test_clean_text_removes_markup_css_and_decodes_entities() -> None:
    value = "<style>.x { color: red }</style><p>Water &amp; habitat</p><br> survey"
    assert clean_text(value) == "Water & habitat survey"


def test_normalize_format_maps_common_aliases() -> None:
    assert normalize_format(".csv") == "CSV"
    assert normalize_format("OGC WMS") == "WMS"
    assert normalize_format("Feature Service") == "ArcGIS GeoServices REST API"
    assert (
        normalize_format("https://www.iana.org/assignments/media-types/application/json") == "JSON"
    )
    assert normalize_format("") == ""
