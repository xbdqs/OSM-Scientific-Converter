from __future__ import annotations

import json
from pathlib import Path

from osm_scientific_converter.core.profiles import resolve_profile
from osm_scientific_converter.core.targeted import reviewed_highway_mapping


def test_packaged_quick_rule_is_exact_reviewed_profile():
    root = Path(__file__).resolve().parents[2]
    bundled = root / 'src/osm_scientific_converter/resources/profiles/reviewer_roads_lines_v1.json'
    original = root / 'examples/round2_road_extraction_rules.json'
    assert bundled.read_bytes() == original.read_bytes()
    resolved = resolve_profile(rules=bundled)
    values, mapping = reviewed_highway_mapping(resolved)
    assert len(values) == 13
    assert len(mapping) == 13
    assert set(category for category, rule_id in mapping.values()) == {
        'motorways_and_trunks', 'pedestrian', 'primary_secondary_tertiary', 'residential_and_service'
    }
