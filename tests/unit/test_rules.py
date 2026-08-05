import pytest

from osm_scientific_converter.core.rules import (
    evaluate_expression,
    parse_numeric_values,
    rule_context_matches,
)


CONTEXT = {
    "geometry_group": "line",
    "source_layer": "lines",
    "osm_type": "way",
    "lifecycle": ["abandoned"],
}


@pytest.mark.parametrize(
    ("op", "value", "expected"),
    [
        ("equals", "alpha", True),
        ("not_equals", "beta", True),
        ("in", ["alpha", "beta"], True),
        ("not_in", ["beta", "gamma"], True),
        ("contains", "ph", True),
        ("contains_any", ["zz", "ph"], True),
        ("starts_with", "al", True),
        ("ends_with", "ha", True),
        ("regex", "^a.*a$", True),
    ],
)
def test_string_operators(op, value, expected):
    result = evaluate_expression({"key": "name", "op": op, "value": value}, {"name": "alpha"}, CONTEXT)
    assert result.matched is expected


def test_exists_and_missing_comparisons():
    assert evaluate_expression({"key": "name", "op": "exists"}, {"name": ""}, CONTEXT).matched
    assert evaluate_expression({"key": "missing", "op": "not_exists"}, {}, CONTEXT).matched
    assert not evaluate_expression({"key": "missing", "op": "not_equals", "value": "x"}, {}, CONTEXT).matched


def test_nested_all_any_none_and_special_lifecycle():
    expression = {
        "all": [
            {"key": "power", "op": "in", "value": ["line", "cable"]},
            {"any": [
                {"key": "voltage", "op": "numeric_any_gte", "value": 220000},
                {"key": "circuits", "op": "numeric_gte", "value": 4},
            ]},
        ],
        "none": [
            {"key": "__lifecycle__", "op": "in", "value": ["demolished", "removed", "razed"]}
        ],
    }
    result = evaluate_expression(
        expression,
        {"power": "line", "voltage": "110000;220 kV"},
        {**CONTEXT, "lifecycle": ["construction"]},
    )
    assert result.matched
    assert result.numeric_failures == []


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("220000", [220000.0]),
        ("220000;110000", [220000.0, 110000.0]),
        ("220 kV", [220000.0]),
        ("220000 V", [220000.0]),
    ],
)
def test_osm_numeric_parsing(raw, expected):
    values, failures = parse_numeric_values(raw)
    assert values == expected
    assert failures == []


def test_numeric_parse_failure_is_auditable_and_not_guessed():
    result = evaluate_expression(
        {"key": "voltage", "op": "numeric_any_gte", "value": 220000},
        {"voltage": "220 MW"},
        CONTEXT,
    )
    assert not result.matched
    assert result.numeric_failures[0].reason == "unsupported_numeric_unit:mw"
    assert result.numeric_failures[0].raw_value == "220 MW"


def test_numeric_comparison_family():
    tags = {"value": "10;20"}
    assert evaluate_expression({"key": "value", "op": "numeric_eq", "value": 10}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_gt", "value": 19}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_gte", "value": 20}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_lt", "value": 11}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_lte", "value": 10}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_between", "value": [15, 25]}, tags, CONTEXT).matched
    assert evaluate_expression({"key": "value", "op": "numeric_any_between", "value": [9, 11]}, tags, CONTEXT).matched


def test_rule_context_constraints():
    rule = {
        "geometry": ["line"],
        "source_layer": ["lines"],
        "osm_type": ["way"],
        "lifecycle": ["abandoned", "disused"],
    }
    assert rule_context_matches(rule, CONTEXT)
    assert not rule_context_matches({**rule, "geometry": ["point"]}, CONTEXT)
