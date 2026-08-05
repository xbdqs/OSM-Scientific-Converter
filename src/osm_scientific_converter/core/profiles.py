from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any, Mapping

from .rules import validate_expression


@dataclass(frozen=True)
class ResolvedProfile:
    data: dict[str, Any]
    sha256: str
    source: str

    @property
    def id(self) -> str:
        return str(self.data["id"])


def _profile_resource(name: str):
    if Path(name).name != name or not name.replace("-", "_").isalnum():
        raise ValueError(f"Invalid built-in profile name: {name}")
    return files("osm_scientific_converter").joinpath(f"resources/profiles/{name}.json")


def _validate_profile(profile: Mapping[str, Any]) -> None:
    if str(profile.get("schema_version", "")) != "1.0":
        raise ValueError("Profile schema_version must be 1.0")
    if not isinstance(profile.get("id"), str) or not profile["id"]:
        raise ValueError("Profile is missing id")
    rules = profile.get("rules")
    if not isinstance(rules, list) or not rules:
        raise ValueError("Profile must contain at least one rule")
    seen: set[str] = set()
    for rule in rules:
        if not isinstance(rule, Mapping):
            raise ValueError("Profile contains a non-object rule")
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not rule_id:
            raise ValueError("Profile rule is missing id")
        if rule_id in seen:
            raise ValueError(f"Duplicate profile rule id: {rule_id}")
        seen.add(rule_id)
        if not isinstance(rule.get("category"), str) or not rule["category"]:
            raise ValueError(f"Profile rule {rule_id} is missing category")
        expression = rule.get("expression")
        if not isinstance(expression, Mapping):
            raise ValueError(f"Profile rule {rule_id} is missing expression")
        validate_expression(expression)
        expected = rule.get("expected_fields", {})
        if not isinstance(expected, Mapping):
            raise ValueError(f"Profile rule {rule_id} expected_fields must be an object")
        unknown_levels = sorted(set(expected) - {"required", "recommended", "optional"})
        if unknown_levels:
            raise ValueError(f"Profile rule {rule_id} has unknown expected_fields levels: {', '.join(unknown_levels)}")
        for level in ("required", "recommended", "optional"):
            values = expected.get(level, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError(f"Profile rule {rule_id} expected_fields.{level} must be a list of tag keys")
    attributes = profile.get("attributes", [])
    if not isinstance(attributes, list) or any(not isinstance(value, str) for value in attributes):
        raise ValueError("Profile attributes must be a list of tag keys")
    category_expected = profile.get("expected_fields_by_category", {})
    if not isinstance(category_expected, Mapping):
        raise ValueError("Profile expected_fields_by_category must be an object")
    for category, expected in category_expected.items():
        if not isinstance(category, str) or not category or not isinstance(expected, Mapping):
            raise ValueError("Profile expected_fields_by_category entries must map category names to objects")
        unknown_levels = sorted(set(expected) - {"required", "recommended", "optional"})
        if unknown_levels:
            raise ValueError(f"Category {category} has unknown expected_fields levels: {', '.join(unknown_levels)}")
        for level in ("required", "recommended", "optional"):
            values = expected.get(level, [])
            if not isinstance(values, list) or any(not isinstance(value, str) or not value for value in values):
                raise ValueError(f"Category {category} expected_fields.{level} must be a list of tag keys")


def _decode_profile(raw: bytes, source: str, fallback_id: str | None = None) -> ResolvedProfile:
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid profile JSON in {source}: {error}") from error
    if not isinstance(data, dict):
        raise ValueError(f"Profile JSON in {source} must be an object")
    if "rules" not in data and "expression" in data:
        rule = dict(data)
        profile_id = fallback_id or str(rule.get("id", "custom"))
        rule.setdefault("category", str(rule.get("id", "custom")))
        data = {
            "schema_version": str(rule.pop("schema_version", "1.0")),
            "id": profile_id,
            "label_en": profile_id,
            "label_zh": profile_id,
            "attributes": [],
            "rules": [rule],
        }
    _validate_profile(data)
    return ResolvedProfile(dict(data), hashlib.sha256(raw).hexdigest(), source)


def load_builtin_profile(name: str) -> ResolvedProfile:
    resource = _profile_resource(name)
    if not resource.is_file():
        raise FileNotFoundError(f"Unknown built-in profile: {name}")
    return _decode_profile(resource.read_bytes(), f"builtin:{name}")


def load_custom_profile(path: str | Path) -> ResolvedProfile:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Custom rule file does not exist: {source}")
    return _decode_profile(source.read_bytes(), str(source), source.stem)


def resolve_profile_text(text: str, source: str = "gui:advanced-json") -> ResolvedProfile:
    """Validate and resolve an editable UTF-8 JSON profile without writing it first."""
    return _decode_profile(text.encode("utf-8"), source, "gui_advanced")


def summarize_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    """Return a compact, deterministic rule summary for GUI review."""
    _validate_profile(profile)
    categories: dict[str, int] = {}
    logical_rules = 0
    for rule in profile["rules"]:
        category = str(rule["category"])
        categories[category] = categories.get(category, 0) + 1
        if any(key in rule["expression"] for key in ("all", "any", "none")):
            logical_rules += 1
    return {
        "id": str(profile["id"]),
        "rules": len(profile["rules"]),
        "categories": dict(sorted(categories.items())),
        "nested_logical_rules": logical_rules,
        "attributes": [str(value) for value in profile.get("attributes", [])],
    }


def resolve_profile(*, profile: str | None = None, rules: str | Path | None = None) -> ResolvedProfile:
    if bool(profile) == bool(rules):
        raise ValueError("Specify exactly one of --profile or --rules")
    return load_builtin_profile(str(profile)) if profile else load_custom_profile(Path(rules))


def list_builtin_profiles() -> list[dict[str, Any]]:
    result = []
    for name in ("aeroway", "pipeline", "power"):
        resolved = load_builtin_profile(name)
        result.append({
            "id": resolved.id,
            "label_en": resolved.data.get("label_en"),
            "label_zh": resolved.data.get("label_zh"),
            "rules": len(resolved.data["rules"]),
            "sha256": resolved.sha256,
        })
    return result


def inspect_builtin_profile(name: str) -> dict[str, Any]:
    resolved = load_builtin_profile(name)
    return {
        **resolved.data,
        "resolved_source": resolved.source,
        "profile_sha256": resolved.sha256,
    }
