import json
import shutil
import zipfile
from pathlib import Path

import pytest

from osm_scientific_converter.core.environment import inspect_environment
from osm_scientific_converter.core.scanner import ScanExecutionError, ScanOptions, scan


ROOT = Path(__file__).parents[2]


@pytest.mark.skipif(shutil.which("ogr2ogr") is None, reason="ogr2ogr not installed")
def test_synthetic_scan_end_to_end(tmp_path):
    environment = inspect_environment(require_gdal=False)
    if environment["problems"]:
        pytest.skip("; ".join(environment["problems"]))
    result = scan(ROOT / "tests/fixtures/synthetic.osm", tmp_path / "中文项目", ScanOptions(keep_raw_master=True))
    project = result.project_dir
    expected = json.loads((ROOT / "tests/expected/synthetic_expected.json").read_text(encoding="utf-8"))
    inventory = json.loads((project / "raw_inventory.json").read_text(encoding="utf-8"))
    assert [layer["name"] for layer in inventory["layers"]] == expected["required_layers"]
    assert all(layer["present"] for layer in inventory["layers"])
    assert {layer["name"]: layer["feature_count"] for layer in inventory["layers"]} == expected["layer_feature_counts"]
    assert inventory["osm_object_types"] == expected["osm_object_types"]
    for key in ("total_features", "total_tag_assignments", "unique_keys", "unique_key_values"):
        assert inventory[key] == expected[key]
    tags = json.loads((project / "tag_inventory.json").read_text(encoding="utf-8"))
    keys = {row["key"] for row in tags}
    assert set(expected["required_keys"]) <= keys
    assert any(row["key"] == "name" and row["value"] == "科学站 α" for row in tags)
    lifecycle_text = (project / "lifecycle_inventory.csv").read_text(encoding="utf-8-sig")
    assert all(state in lifecycle_text for state in expected["required_lifecycle_states"])
    assert (project / "data/raw_master.gpkg").exists()
    assert (project / "data/inventory.sqlite").exists()
    with zipfile.ZipFile(result.feedback_bundle) as archive:
        names = archive.namelist()
        assert "project_manifest.json" in names
        assert not any(name.endswith((".gpkg", ".osm", ".pbf", ".sqlite")) for name in names)
        assert "tag_inventory.csv" not in names
        assert "tag_inventory.json" not in names


@pytest.mark.skipif(shutil.which("ogr2ogr") is None, reason="ogr2ogr not installed")
def test_inventory_is_repeatable(tmp_path):
    environment = inspect_environment(require_gdal=False)
    if environment["problems"]:
        pytest.skip("; ".join(environment["problems"]))
    source = ROOT / "tests/fixtures/synthetic.osm"
    first = scan(source, tmp_path / "first")
    second = scan(source, tmp_path / "second")
    for filename in ("tag_inventory.json", "tag_inventory.csv", "lifecycle_inventory.csv"):
        assert (first.project_dir / filename).read_bytes() == (second.project_dir / filename).read_bytes()
    first_raw = json.loads((first.project_dir / "raw_inventory.json").read_text(encoding="utf-8"))
    second_raw = json.loads((second.project_dir / "raw_inventory.json").read_text(encoding="utf-8"))
    assert first_raw["inventory_database"]["path"] == "data/inventory.sqlite"
    assert second_raw["inventory_database"]["path"] == "data/inventory.sqlite"
    first_raw.pop("raw_master")
    second_raw.pop("raw_master")
    assert first_raw == second_raw


def test_failed_overwrite_preserves_existing_project(tmp_path):
    project = tmp_path / "existing"
    project.mkdir()
    marker = project / "keep.txt"
    marker.write_text("previous success", encoding="utf-8")
    invalid = tmp_path / "invalid.osm"
    invalid.write_text("not osm", encoding="utf-8")
    with pytest.raises(ScanExecutionError) as caught:
        scan(invalid, project, ScanOptions(overwrite=True))
    assert marker.read_text(encoding="utf-8") == "previous success"
    assert caught.value.feedback_bundle is not None
    assert caught.value.feedback_bundle.exists()
