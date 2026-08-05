import json

import pytest

from osm_scientific_converter.core.profiles import (
    inspect_builtin_profile,
    list_builtin_profiles,
    load_builtin_profile,
    load_custom_profile,
)
from osm_scientific_converter.core.rules import evaluate_expression, rule_context_matches


PIPELINE_CONTEXT = {
    "geometry_group": "point",
    "source_layer": "points",
    "osm_type": "node",
    "lifecycle": [],
}


def pipeline_matches(tags):
    profile = load_builtin_profile("pipeline")
    return {
        rule["id"]
        for rule in profile.data["rules"]
        if rule_context_matches(rule, PIPELINE_CONTEXT)
        and evaluate_expression(rule["expression"], tags, PIPELINE_CONTEXT).matched
    }


def test_three_builtin_profiles_are_versioned_and_hashed():
    profiles = list_builtin_profiles()
    assert [profile["id"] for profile in profiles] == ["aeroway", "pipeline", "power"]
    assert all(profile["rules"] >= 13 for profile in profiles)
    assert all(len(profile["sha256"]) == 64 for profile in profiles)
    assert inspect_builtin_profile("power")["schema_version"] == "1.0"


def test_single_custom_rule_is_normalized_to_profile(tmp_path):
    path = tmp_path / "高压规则.json"
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "id": "high_voltage",
        "category": "high_voltage",
        "geometry": ["line"],
        "expression": {"key": "voltage", "op": "numeric_any_gte", "value": 220000},
    }, ensure_ascii=False), encoding="utf-8")
    resolved = load_custom_profile(path)
    assert resolved.id == "高压规则"
    assert resolved.data["rules"][0]["id"] == "high_voltage"
    assert len(resolved.sha256) == 64


def test_invalid_operator_rejected(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text(json.dumps({
        "schema_version": "1.0",
        "id": "invalid",
        "rules": [{
            "id": "bad",
            "category": "bad",
            "expression": {"key": "x", "op": "guess", "value": "y"},
        }],
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported rule operator"):
        load_custom_profile(path)


def test_pipeline_substance_rules_require_pipeline_context():
    profile = load_builtin_profile("pipeline")
    oil_rule = next(rule for rule in profile.data["rules"] if rule["id"] == "pipeline_oil")
    context = {
        "geometry_group": "point",
        "source_layer": "points",
        "osm_type": "node",
        "lifecycle": [],
    }
    assert not evaluate_expression(
        oil_rule["expression"],
        {"man_made": "petroleum_well", "substance": "oil"},
        context,
    ).matched
    assert evaluate_expression(
        oil_rule["expression"],
        {"man_made": "pipeline", "substance": "oil"},
        context,
    ).matched


@pytest.mark.parametrize(("tags", "expected_rule"), [
    ({"man_made": "pipeline"}, "pipeline_main"),
    ({"route": "pipeline", "substance": "gas"}, "pipeline_gas"),
    ({"pipeline": "valve"}, "pipeline_valve"),
    ({"man_made": "pumping_station", "substance": "water"}, "pipeline_pumping"),
    ({"pipeline": "pump"}, "pipeline_pumping"),
    ({"man_made": "compressor_station", "product": "natural_gas"}, "pipeline_compressor"),
    ({"pipeline": "compressor"}, "pipeline_compressor"),
    ({"man_made": "storage_tank", "substance": "gas"}, "pipeline_storage"),
    ({"man_made": "gasometer", "utility": "gas"}, "pipeline_storage"),
    ({"pipeline": "storage"}, "pipeline_storage"),
])
def test_pipeline_ten_positive_context_cases(tags, expected_rule):
    assert expected_rule in pipeline_matches(tags)


@pytest.mark.parametrize(("tags", "forbidden_rule", "candidate_rule"), [
    ({"man_made": "petroleum_well", "substance": "oil"}, "pipeline_oil", None),
    ({"man_made": "storage_tank"}, "pipeline_storage", "pipeline_storage_candidate"),
    ({"man_made": "pumping_station"}, "pipeline_pumping", "pipeline_pumping_candidate"),
    ({"man_made": "compressor_station"}, "pipeline_compressor", "pipeline_compressor_candidate"),
    ({"man_made": "storage_tank", "amenity": "fuel"}, "pipeline_storage", "pipeline_storage_candidate"),
    ({"man_made": "water_works", "substance": "water"}, "pipeline_water", None),
    ({"man_made": "outfall", "substance": "wastewater"}, "pipeline_sewage", None),
    ({"natural": "water", "substance": "water"}, "pipeline_water", None),
    ({"highway": "service", "usage": "transmission"}, "pipeline_transmission", None),
    ({"shop": "gas", "product": "gas"}, "pipeline_gas", None),
])
def test_pipeline_ten_negative_context_cases(tags, forbidden_rule, candidate_rule):
    matches = pipeline_matches(tags)
    assert forbidden_rule not in matches
    if candidate_rule:
        assert candidate_rule in matches


def test_pipeline_candidates_are_excluded_from_default_export():
    profile = load_builtin_profile("pipeline")
    candidates = [rule for rule in profile.data["rules"] if rule["category"].endswith("_candidate")]
    assert {rule["category"] for rule in candidates} == {
        "storage_candidate", "pumping_candidate", "compressor_candidate"
    }
    assert all(rule["default_export"] is False for rule in candidates)
