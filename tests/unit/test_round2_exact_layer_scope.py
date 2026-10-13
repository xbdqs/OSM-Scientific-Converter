"""Round-2 regression: exact GDAL source-layer restrictions and measured progress.

These tests use a deterministic synthetic GeoPackage-like SQLite source and do
not require GDAL binaries, external downloads or PySide6.
"""
import json
import sqlite3
from pathlib import Path

import pytest

from osm_scientific_converter.cli.main import build_parser
from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.profiles import load_builtin_profile


def fake_project(tmp_path: Path) -> Path:
    project = tmp_path / "p"
    (project / "data").mkdir(parents=True)
    (project / "project_manifest.json").write_text(json.dumps({
        "status": "success", "input": {"sha256": "f"*64},
    }), encoding="utf-8")
    c = sqlite3.connect(project / "data" / "raw_master.gpkg")
    try:
        for layer in ("points", "lines", "multilinestrings", "multipolygons", "other_relations"):
            c.execute(f'CREATE TABLE "{layer}" (fid INTEGER PRIMARY KEY, osm_id TEXT, all_tags TEXT)')
        # Identical thematic tags in different GDAL source layers: group=line
        # must NOT silently include multilinestrings when exact lines requested.
        tags = json.dumps({"power": "line", "voltage": "220000"})
        c.execute('INSERT INTO lines VALUES (1, ?, ?)', ('100', tags))
        c.execute('INSERT INTO multilinestrings VALUES (1, ?, ?)', ('200', tags))
        c.execute('INSERT INTO points VALUES (1, ?, ?)', ('300', json.dumps({"power": "tower"})))
        c.execute('INSERT INTO multipolygons VALUES (1, ?, ?)', ('400', json.dumps({"power": "substation"})))
        c.execute('INSERT INTO other_relations VALUES (1, ?, ?)', ('500', tags))
        c.commit()
    finally:
        c.close()
    return project


def test_lines_are_strictly_exclusive_and_audited(tmp_path):
    project = fake_project(tmp_path)
    events = []
    result = classify_project(project, load_builtin_profile("power"), source_layers=["lines"], progress=events.append)
    with sqlite3.connect(result.database) as c:
        layers = [r[0] for r in c.execute("SELECT DISTINCT source_layer FROM objects")]
        meta = dict(c.execute("SELECT key, value FROM metadata"))
    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    assert layers == ["lines"]
    assert summary["classification_scope"]["source_layers"] == ["lines"]
    assert summary["classification_scope"]["eligible_source_objects"] == 1
    assert json.loads(meta["classification_source_layers"]) == ["lines"]
    assert summary["classification_scope"]["sha256"] == meta["classification_scope_sha256"]
    progress = [json.loads(e.split("@@PROGRESS ", 1)[1]) for e in events if e.startswith("@@PROGRESS ")]
    assert progress[0]["processed"] == 0
    assert progress[-1] == {"operation": "classify", "processed": 1, "total": 1}
    assert not any(l in layers for l in ("points", "multilinestrings", "multipolygons", "other_relations"))


def test_unrestricted_layers_remain_available(tmp_path):
    project = fake_project(tmp_path)
    result = classify_project(project, load_builtin_profile("power"))
    with sqlite3.connect(result.database) as c:
        layers = {r[0] for r in c.execute("SELECT DISTINCT source_layer FROM objects")}
    assert "lines" in layers
    assert "multilinestrings" in layers
    assert "points" in layers


def test_invalid_or_empty_scope_rejected_before_touching_project(tmp_path):
    for layers in ([], ["not_a_layer"], "lines"):
        with pytest.raises(ValueError):
            classify_project(tmp_path / "nonexistent", load_builtin_profile("power"), source_layers=layers)


def test_cli_exact_source_layer_selection_is_explicit():
    cli = build_parser()
    args = cli.parse_args(["classify", "p", "--profile", "power", "--source-layer", "lines"])
    assert args.source_layer == ["lines"]
    with pytest.raises(SystemExit):
        cli.parse_args(["classify", "p", "--profile", "power", "--source-layer", "line"])


def test_road_profile_covers_exact_reviewer_value_set_and_restricts_context():
    from osm_scientific_converter.core.profiles import load_custom_profile
    from osm_scientific_converter.core.rules import evaluate_expression, rule_context_matches
    profile_path = Path(__file__).resolve().parents[2] / 'examples' / 'round2_road_extraction_rules.json'
    profile = load_custom_profile(profile_path)
    expected = {
        'motorway', 'motorway_link', 'trunk', 'trunk_link',
        'primary', 'primary_link', 'secondary', 'secondary_link',
        'tertiary', 'tertiary_link', 'residential', 'service', 'pedestrian',
    }
    contexts = {
        layer: {'source_layer': layer, 'geometry_group': group, 'osm_type': 'way', 'lifecycle': []}
        for layer, group in [('lines', 'line'), ('multilinestrings', 'line'), ('points', 'point'),
                             ('multipolygons', 'polygon'), ('other_relations', 'other')]
    }
    for road_class in expected:
        matching = [rule for rule in profile.data['rules']
                    if rule_context_matches(rule, contexts['lines'])
                    and evaluate_expression(rule['expression'], {'highway': road_class}, contexts['lines']).matched]
        assert len(matching) == 1, f'{road_class}: {[rule["id"] for rule in matching]}'
        for excluded_layer in ('multilinestrings', 'points', 'multipolygons', 'other_relations'):
            assert not any(rule_context_matches(rule, contexts[excluded_layer]) for rule in profile.data['rules'])
    for excluded in ('building', 'track', 'footway', 'cycleway', 'busway'):
        assert not any(evaluate_expression(rule['expression'], {'highway': excluded}, contexts['lines']).matched
                       for rule in profile.data['rules'])


def test_source_layer_scope_affects_provenance_hash(tmp_path):
    project = fake_project(tmp_path)
    profile = load_builtin_profile('power')
    line = classify_project(project, profile, source_layers=['lines'])
    line_hash = json.loads(line.summary.read_text(encoding='utf-8'))['classification_scope']['sha256']
    multi = classify_project(project, profile, source_layers=['multilinestrings'])
    multi_hash = json.loads(multi.summary.read_text(encoding='utf-8'))['classification_scope']['sha256']
    assert line_hash != multi_hash
