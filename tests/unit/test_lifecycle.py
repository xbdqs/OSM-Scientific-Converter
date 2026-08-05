from osm_scientific_converter.core.lifecycle import detect_lifecycle


def test_prefix_and_replacement_lifecycle_forms():
    found = detect_lifecycle({"construction:power": "line", "power": "construction", "construction": "line"})
    assert ("construction", "construction:power=line") in found
    assert ("construction", "power=construction") in found


def test_all_supported_states():
    states = {"proposed", "planned", "construction", "disused", "abandoned", "demolished", "removed", "razed"}
    tags = {f"{state}:railway": "rail" for state in states}
    assert {state for state, _ in detect_lifecycle(tags)} == states
