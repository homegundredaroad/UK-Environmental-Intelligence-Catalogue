from ukei.licensing import classify_licence


def test_licence_classification_distinguishes_open_and_restricted() -> None:
    open_licence = classify_licence("<p>Open Government Licence v3.0</p>")
    restricted = classify_licence("Non-Commercial Government Licence v2.0")
    assert open_licence.category == "open"
    assert open_licence.identifier == "OGL-3.0"
    assert open_licence.normalized_text == "Open Government Licence v3.0"
    assert restricted.category == "restricted"
    assert restricted.commercial_use is False
