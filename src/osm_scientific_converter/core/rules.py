from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence


STRING_OPERATORS = {
    "equals",
    "not_equals",
    "in",
    "not_in",
    "contains",
    "contains_any",
    "starts_with",
    "ends_with",
    "regex",
    "exists",
    "not_exists",
}
NUMERIC_OPERATORS = {
    "numeric_eq",
    "numeric_gt",
    "numeric_gte",
    "numeric_lt",
    "numeric_lte",
    "numeric_between",
    "numeric_any_gte",
    "numeric_any_between",
}
SUPPORTED_OPERATORS = STRING_OPERATORS | NUMERIC_OPERATORS
LOGICAL_KEYS = {"all", "any", "none"}
SPECIAL_KEYS = {
    "__lifecycle__": "lifecycle",
    "__geometry__": "geometry_group",
    "__source_layer__": "source_layer",
    "__osm_type__": "osm_type",
}

_NUMBER = re.compile(r"^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+))\s*([A-Za-z]+)?\s*$")


@dataclass(frozen=True)
class NumericParseFailure:
    key: str
    raw_value: str
    token: str
    reason: str


@dataclass
class EvaluationResult:
    matched: bool
    numeric_failures: list[NumericParseFailure] = field(default_factory=list)


def parse_numeric_values(raw_value: Any) -> tuple[list[float], list[tuple[str, str]]]:
    """Parse OSM numeric values without guessing unsupported units.

    Bare numbers and V/kV are accepted. Semicolons represent OSM multi-values.
    Every rejected token is returned with a reason for the audit table.
    """
    text = "" if raw_value is None else str(raw_value)
    values: list[float] = []
    failures: list[tuple[str, str]] = []
    for token in text.split(";"):
        stripped = token.strip()
        if not stripped:
            failures.append((token, "empty_numeric_token"))
            continue
        match = _NUMBER.fullmatch(stripped)
        if match is None:
            failures.append((stripped, "invalid_numeric_syntax"))
            continue
        value = float(match.group(1))
        unit = (match.group(2) or "").lower()
        if unit == "kv":
            value *= 1000.0
        elif unit not in {"", "v"}:
            failures.append((stripped, f"unsupported_numeric_unit:{unit}"))
            continue
        if not math.isfinite(value):
            failures.append((stripped, "non_finite_numeric_value"))
            continue
        values.append(value)
    return values, failures


def _as_sequence(value: Any) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value]
    return [str(value)]


def _actual_values(
    key: str,
    tags: Mapping[str, str],
    context: Mapping[str, Any],
) -> tuple[bool, list[str]]:
    special = SPECIAL_KEYS.get(key)
    if special is not None:
        raw = context.get(special)
        if raw is None:
            return False, []
        if isinstance(raw, (list, tuple, set)):
            values = [str(item) for item in raw]
        else:
            values = [str(raw)]
        return bool(values), values
    if key not in tags:
        return False, []
    return True, [str(tags[key])]


def _numeric_result(
    key: str,
    actual: Sequence[str],
    op: str,
    expected: Any,
) -> EvaluationResult:
    parsed: list[float] = []
    audit: list[NumericParseFailure] = []
    for raw in actual:
        values, failures = parse_numeric_values(raw)
        parsed.extend(values)
        audit.extend(NumericParseFailure(key, raw, token, reason) for token, reason in failures)
    if not parsed:
        return EvaluationResult(False, audit)

    if op in {"numeric_between", "numeric_any_between"}:
        if not isinstance(expected, (list, tuple)) or len(expected) != 2:
            raise ValueError(f"{op} requires a two-value range")
        low, high = float(expected[0]), float(expected[1])
        if low > high:
            raise ValueError(f"{op} range minimum exceeds maximum")
        matched = any(low <= value <= high for value in parsed)
    else:
        target = float(expected)
        predicates = {
            "numeric_eq": lambda value: value == target,
            "numeric_gt": lambda value: value > target,
            "numeric_gte": lambda value: value >= target,
            "numeric_lt": lambda value: value < target,
            "numeric_lte": lambda value: value <= target,
            "numeric_any_gte": lambda value: value >= target,
        }
        matched = any(predicates[op](value) for value in parsed)
    return EvaluationResult(matched, audit)


def _condition_result(
    condition: Mapping[str, Any],
    tags: Mapping[str, str],
    context: Mapping[str, Any],
) -> EvaluationResult:
    key = str(condition.get("key", ""))
    op = str(condition.get("op", ""))
    if not key:
        raise ValueError("Rule condition is missing key")
    if op not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported rule operator: {op}")
    exists, actual = _actual_values(key, tags, context)
    if op == "exists":
        return EvaluationResult(exists)
    if op == "not_exists":
        return EvaluationResult(not exists)
    if not exists:
        return EvaluationResult(False)

    expected = condition.get("value")
    if op in NUMERIC_OPERATORS:
        return _numeric_result(key, actual, op, expected)

    expected_values = _as_sequence(expected)
    if op == "equals":
        matched = any(value == expected_values[0] for value in actual)
    elif op == "not_equals":
        matched = all(value != expected_values[0] for value in actual)
    elif op == "in":
        matched = any(value in expected_values for value in actual)
    elif op == "not_in":
        matched = all(value not in expected_values for value in actual)
    elif op == "contains":
        matched = any(expected_values[0] in value for value in actual)
    elif op == "contains_any":
        matched = any(fragment in value for value in actual for fragment in expected_values)
    elif op == "starts_with":
        matched = any(value.startswith(expected_values[0]) for value in actual)
    elif op == "ends_with":
        matched = any(value.endswith(expected_values[0]) for value in actual)
    elif op == "regex":
        try:
            pattern = re.compile(expected_values[0])
        except re.error as error:
            raise ValueError(f"Invalid regular expression for {key}: {error}") from error
        matched = any(pattern.search(value) is not None for value in actual)
    else:  # pragma: no cover - guarded by SUPPORTED_OPERATORS
        raise AssertionError(op)
    return EvaluationResult(matched)


def evaluate_expression(
    expression: Mapping[str, Any],
    tags: Mapping[str, str],
    context: Mapping[str, Any],
) -> EvaluationResult:
    """Evaluate a nested all/any/none expression and retain parse failures."""
    logical = [key for key in LOGICAL_KEYS if key in expression]
    if not logical:
        return _condition_result(expression, tags, context)

    group_matches: list[bool] = []
    failures: list[NumericParseFailure] = []
    for key in sorted(logical, key=("all", "any", "none").index):
        children = expression[key]
        if not isinstance(children, list):
            raise ValueError(f"Logical group {key} must be a list")
        child_results = [evaluate_expression(child, tags, context) for child in children]
        for result in child_results:
            failures.extend(result.numeric_failures)
        states = [result.matched for result in child_results]
        if key == "all":
            group_matches.append(all(states))
        elif key == "any":
            group_matches.append(any(states))
        else:
            group_matches.append(not any(states))
    return EvaluationResult(all(group_matches), failures)


def rule_context_matches(rule: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    mapping = {
        "geometry": "geometry_group",
        "source_layer": "source_layer",
        "osm_type": "osm_type",
    }
    for rule_key, context_key in mapping.items():
        allowed = rule.get(rule_key)
        if allowed is not None and str(context.get(context_key)) not in _as_sequence(allowed):
            return False
    lifecycle = rule.get("lifecycle")
    if lifecycle is not None:
        actual = {str(value) for value in context.get("lifecycle", [])}
        if not actual.intersection(_as_sequence(lifecycle)):
            return False
    return True


def validate_expression(expression: Mapping[str, Any]) -> None:
    logical = [key for key in LOGICAL_KEYS if key in expression]
    if logical:
        for key in logical:
            children = expression[key]
            if not isinstance(children, list):
                raise ValueError(f"Logical group {key} must be a list")
            for child in children:
                if not isinstance(child, Mapping):
                    raise ValueError(f"Logical group {key} contains a non-object condition")
                validate_expression(child)
        return
    key = expression.get("key")
    op = expression.get("op")
    if not isinstance(key, str) or not key:
        raise ValueError("Rule condition is missing key")
    if op not in SUPPORTED_OPERATORS:
        raise ValueError(f"Unsupported rule operator: {op}")
    if op not in {"exists", "not_exists"} and "value" not in expression:
        raise ValueError(f"Rule condition {key}/{op} is missing value")
    if op == "regex":
        try:
            re.compile(str(expression["value"]))
        except re.error as error:
            raise ValueError(f"Invalid regular expression for {key}: {error}") from error
    if op in {"numeric_between", "numeric_any_between"}:
        value = expression.get("value")
        if not isinstance(value, list) or len(value) != 2:
            raise ValueError(f"{op} requires a two-value list")


def condition_summary(rule: Mapping[str, Any]) -> str:
    return json.dumps(rule.get("expression", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
