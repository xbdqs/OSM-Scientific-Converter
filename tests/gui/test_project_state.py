from __future__ import annotations

import json

from osm_scientific_converter.gui.project_state import GuiProject


def test_project_roundtrip_chinese_path(tmp_path):
    project = tmp_path / "中文工程"
    state = GuiProject(
        input_path=str(tmp_path / "数据.osm.pbf"),
        input_sha256="a" * 64,
        project_dir=str(project),
        profile_id="pipeline",
        profile_sha256="b" * 64,
        classification_rules=[{"id": "rule", "category": "pipeline", "expression": {"key": "man_made", "op": "equals", "value": "pipeline"}}],
        selected_categories=["pipeline", "valve"],
        selected_tag_values={"power": ["line", "substation"], "aeroway": ["runway"]},
        selected_fields=["osm_id", "tags_json", "voltage"],
        export_format="GPKG",
        crs="EPSG:4326",
        run_results={"scan": {"status": "success"}},
    )
    path = state.save()
    loaded = GuiProject.load(path)
    assert path.name == "project.osmproject.json"
    assert loaded.input_sha256 == "a" * 64
    assert loaded.profile_sha256 == "b" * 64
    assert loaded.selected_categories == ["pipeline", "valve"]
    assert loaded.selected_tag_values == {"power": ["line", "substation"], "aeroway": ["runway"]}
    assert loaded.selected_fields == ["osm_id", "tags_json", "voltage"]
    assert loaded.quality_settings["auto_repair"] is False
    payload = json.loads(path.read_text(encoding="utf-8"))
    for key in ("input_sha256", "software_version", "profile_sha256", "classification_rules", "selected_categories", "export_format", "crs", "quality_settings", "run_results"):
        assert key in payload


def test_project_save_is_atomic(tmp_path):
    state = GuiProject(project_dir=str(tmp_path / "project"))
    destination = state.save()
    assert destination.is_file()
    assert not list(destination.parent.glob(".project.osmproject.json.partial-*"))
