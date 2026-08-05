from __future__ import annotations

import csv
import json
import shutil
import sqlite3
import zipfile
from contextlib import closing
from pathlib import Path

import pytest

from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.environment import inspect_environment
from osm_scientific_converter.core.exporter import export_selection
from osm_scientific_converter.core.profiles import load_builtin_profile, load_custom_profile
from osm_scientific_converter.core.scanner import ScanOptions, scan
from osm_scientific_converter.gui.quality import run_quality_checks


ROOT = Path(__file__).resolve().parents[2]
try:
    INFO = inspect_environment(require_gdal=False)
    GDAL_READY = not INFO["problems"] and INFO["gdal"]["python_bindings"]
except Exception:
    GDAL_READY = False


@pytest.fixture()
def retained_project(tmp_path):
    if not GDAL_READY:
        pytest.skip("GDAL OSM/GPKG and Python bindings are required")
    project = tmp_path / "phase2_project"
    scan(ROOT / "tests/fixtures/synthetic.osm", project, ScanOptions(keep_raw_master=True))
    return project


def test_power_classification_is_traceable_and_repeatable(retained_project):
    profile = load_builtin_profile("power")
    first = classify_project(retained_project, profile)
    summary1 = json.loads(first.summary.read_text(encoding="utf-8"))
    second = classify_project(retained_project, profile)
    summary2 = json.loads(second.summary.read_text(encoding="utf-8"))
    assert summary1["software"]["version"] == "0.4.1"
    assert summary1["phase1_project"] == "."
    assert summary1["determinism"] == summary2["determinism"]
    assert summary1["counts"]["matched_objects"] == 2
    with closing(sqlite3.connect(second.database)) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        row = connection.execute(
            """
            SELECT o.osm_id, o.osm_type, o.source_layer, o.geometry_group, o.tags_json,
                   o.lifecycle, m.profile_id, m.rule_id, m.match_summary, m.classified_at_utc,
                   m.profile_sha256
            FROM objects o JOIN matches m USING(object_pk)
            WHERE o.osm_id = 'way/100'
            """
        ).fetchone()
    assert row[:4] == ("way/100", "way", "lines", "line")
    assert '"voltage":"220000;500000"' in row[4]
    assert row[6:8] == ("power", "power_line")
    assert len(row[10]) == 64


def test_custom_multi_category_point_line_area_relation(retained_project, tmp_path):
    custom = tmp_path / "custom.json"
    custom.write_text(json.dumps({
        "schema_version": "1.0",
        "id": "multi_geometry",
        "label_en": "Multi geometry",
        "label_zh": "多几何",
        "attributes": ["name", "voltage"],
        "rules": [
            {"id": "point", "category": "point", "geometry": ["point"], "expression": {"key": "amenity", "op": "exists"}},
            {"id": "line", "category": "line", "geometry": ["line"], "expression": {"key": "power", "op": "equals", "value": "line"}},
            {"id": "high_voltage", "category": "high_voltage", "geometry": ["line"], "expression": {"key": "voltage", "op": "numeric_any_gte", "value": 220000}},
            {"id": "area", "category": "area", "geometry": ["polygon"], "expression": {"key": "landuse", "op": "exists"}},
            {"id": "relation", "category": "relation", "source_layer": ["other_relations"], "expression": {"key": "type", "op": "equals", "value": "site"}}
        ]
    }, ensure_ascii=False), encoding="utf-8")
    result = classify_project(retained_project, load_custom_profile(custom))
    custom_summary = json.loads(result.summary.read_text(encoding="utf-8"))
    resolved_profile = json.loads(
        (retained_project / "profiles" / "resolved_profile.json").read_text(encoding="utf-8")
    )
    assert custom_summary["profile"]["source"] == "custom:custom.json"
    assert resolved_profile["resolved_source"] == "custom:custom.json"
    with closing(sqlite3.connect(result.database)) as connection:
        categories = dict(connection.execute("SELECT category, COUNT(*) FROM matches GROUP BY category"))
        multi = connection.execute(
            """
            SELECT COUNT(*) FROM objects o
            WHERE (SELECT COUNT(*) FROM matches m WHERE m.object_pk=o.object_pk) > 1
            """
        ).fetchone()[0]
    assert set(categories) == {"point", "line", "high_voltage", "area", "relation"}
    assert multi >= 1


def test_all_export_formats_and_shapefile_loss_audit(retained_project, tmp_path):
    classify_project(retained_project, load_builtin_profile("power"))
    selection = tmp_path / "selection.json"
    selection.write_text(json.dumps({
        "schema_version": "1.0",
        "profile": "power",
        "categories": [],
    }), encoding="utf-8")

    gpkg = export_selection(retained_project, selection, tmp_path / "power.gpkg")
    assert gpkg.output.is_file()
    assert gpkg.features_written == 2
    gpkg_audit = json.loads((retained_project / "exports" / "export_audit.json").read_text(encoding="utf-8"))
    assert gpkg_audit["output"] == "<external-output>/power.gpkg"
    assert "lossless_claim" not in gpkg_audit["loss_audit"]
    assert gpkg_audit["loss_audit"]["attribute_truncation_detected"] is False
    assert gpkg_audit["loss_audit"]["field_name_truncation_detected"] is False
    assert gpkg_audit["loss_audit"]["full_tags_json_preserved"] is True
    assert gpkg_audit["loss_audit"]["geometry_conversion"] == "copied through GDAL/OGR into target format"
    assert gpkg_audit["counts"]["feature_count_semantics"].startswith("unique classified objects")

    geojson_selection = tmp_path / "geojson.json"
    geojson_selection.write_text(json.dumps({
        "schema_version": "1.0", "profile": "power", "categories": [], "format": "GeoJSON"
    }), encoding="utf-8")
    geojson = export_selection(retained_project, geojson_selection, tmp_path / "geojson")
    assert list(geojson.output.glob("*.geojson"))
    geojson_audit = json.loads((retained_project / "exports" / "export_audit.json").read_text(encoding="utf-8"))
    assert geojson_audit["counts"]["feature_count_semantics"].startswith("object-category records")

    shp_selection = tmp_path / "shp.json"
    shp_selection.write_text(json.dumps({
        "schema_version": "1.0", "profile": "power", "categories": [], "format": "Shapefile"
    }), encoding="utf-8")
    shapefile = export_selection(retained_project, shp_selection, tmp_path / "shapefiles")
    assert list(shapefile.output.glob("*.shp"))
    exports = retained_project / "exports"
    assert (exports / "shapefile_field_mapping.csv").is_file()
    loss = json.loads((exports / "shapefile_loss_report.json").read_text(encoding="utf-8"))
    assert loss["lossless"] is False
    assert loss["field_name_limit"] == 10
    with zipfile.ZipFile(shapefile.feedback_bundle) as archive:
        names = archive.namelist()
        assert not any(name.endswith((".sqlite", ".gpkg", ".shp", "tags_json")) for name in names)
        for name in names:
            if name.endswith((".json", ".csv", ".log", ".txt")):
                text = archive.read(name).decode("utf-8-sig")
                assert str(tmp_path) not in text
                assert ":\\" not in text


def test_selected_profile_fields_control_real_output_and_traceability_is_forced(retained_project, tmp_path):
    classify_project(retained_project, load_builtin_profile("power"))
    selection = tmp_path / "selected_fields.json"
    selection.write_text(json.dumps({
        "schema_version": "1.0",
        "profile": "power",
        "categories": [],
        "format": "GPKG",
        "fields": ["voltage"],
    }), encoding="utf-8")
    result = export_selection(retained_project, selection, tmp_path / "selected_fields.gpkg")
    assert result.features_written == 2
    with (retained_project / "exports" / "field_mapping.csv").open(encoding="utf-8") as handle:
        mapping = list(csv.DictReader(handle))
    source_fields = {row["source_field"] for row in mapping}
    assert "voltage" in source_fields
    assert "circuits" not in source_fields
    assert {"osm_id", "osm_type", "source_layer", "geometry_group", "category", "rule_ids", "lifecycle", "profile_id", "profile_sha256", "tags_json"}.issubset(source_fields)
    audit = json.loads(result.audit.read_text(encoding="utf-8"))
    assert audit["selection"]["selected_profile_attributes"] == ["voltage"]
    assert audit["selection"]["field_selection_applied"] is True
    assert audit["selection"]["resolved_categories"]

    explicit_category = audit["selection"]["resolved_categories"][0]
    explicit_selection = tmp_path / "explicit_categories.json"
    explicit_selection.write_text(json.dumps({
        "schema_version": "1.0",
        "profile": "power",
        "categories": [explicit_category],
        "format": "GPKG",
        "fields": ["voltage"],
    }), encoding="utf-8")
    explicit_result = export_selection(retained_project, explicit_selection, tmp_path / "explicit_categories.gpkg")
    explicit_audit = json.loads(explicit_result.audit.read_text(encoding="utf-8"))
    assert explicit_audit["selection"]["resolved_categories"] == [explicit_category]

    invalid = tmp_path / "invalid_fields.json"
    invalid.write_text(json.dumps({
        "schema_version": "1.0", "profile": "power", "fields": ["invented_field"]
    }), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown fields"):
        export_selection(retained_project, invalid, tmp_path / "invalid.gpkg")


def test_quality_uses_deterministic_strata_and_category_applicable_fields(retained_project):
    classify_project(retained_project, load_builtin_profile("power"))
    first = run_quality_checks(retained_project, {"sample_size": 1, "auto_repair": False})
    second = run_quality_checks(retained_project, {"sample_size": 1, "auto_repair": False})
    assert first["sample_audit"] == second["sample_audit"]
    assert first["scope"]["sample_size"] >= len(first["scope"]["strata"])
    assert all(item["sampled"] >= 1 for item in first["scope"]["strata"])
    assert "category × geometry_group" in first["scope"]["sampling"]
    tower = first["missing_thematic_fields"]["by_category"]["tower"]
    assert "generator:source" not in tower["recommended"]
    assert tower["optional_not_scored"]
    assert first["missing_thematic_fields"]["summary"]["optional_missing_is_error"] is False


def test_high_cardinality_classification_is_streamed_and_bounded(tmp_path):
    project = tmp_path / "high_cardinality_project"
    raw_dir = project / "data"
    raw_dir.mkdir(parents=True)
    (project / "project_manifest.json").write_text(json.dumps({
        "status": "success",
        "software": {"version": "0.4.1"},
        "input": {"sha256": "synthetic-high-cardinality"},
    }), encoding="utf-8")
    raw_master = raw_dir / "raw_master.gpkg"
    with closing(sqlite3.connect(raw_master)) as connection:
        connection.execute(
            "CREATE TABLE points (fid INTEGER PRIMARY KEY, osm_id TEXT, all_tags TEXT)"
        )
        connection.executemany(
            "INSERT INTO points(fid, osm_id, all_tags) VALUES (?, ?, ?)",
            (
                (index, str(index), json.dumps({f"unique_key_{index}": f"unique_value_{index}"}))
                for index in range(1, 50_001)
            ),
        )
        connection.commit()

    profile_path = tmp_path / "bounded.json"
    profile_path.write_text(json.dumps({
        "schema_version": "1.0",
        "id": "bounded",
        "label_en": "Bounded memory fixture",
        "rules": [{
            "id": "never_matches",
            "category": "none",
            "expression": {"key": "target", "op": "equals", "value": "yes"},
        }],
    }), encoding="utf-8")

    result = classify_project(project, load_custom_profile(profile_path))
    summary = json.loads(result.summary.read_text(encoding="utf-8"))
    assert summary["counts"]["scanned_objects"] == 50_000
    assert summary["counts"]["matched_objects"] == 0
    assert summary["performance"]["overall_peak_rss_bytes"] < 512 * 1024 * 1024
    with closing(sqlite3.connect(result.database)) as connection:
        assert connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0] == 0
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_chinese_and_korean_unicode_round_trip_in_all_export_formats(tmp_path):
    if not GDAL_READY:
        pytest.skip("GDAL OSM/GPKG and Python bindings are required")
    project = tmp_path / "unicode_project"
    scan(ROOT / "tests/fixtures/unicode_power.osm", project, ScanOptions(keep_raw_master=True))
    classify_project(project, load_builtin_profile("power"))

    expected = {"中文变压器", "한국어 송전선"}
    for format_name, output in (
        ("GPKG", tmp_path / "unicode.gpkg"),
        ("GeoJSON", tmp_path / "unicode_geojson"),
        ("Shapefile", tmp_path / "unicode_shapefile"),
    ):
        selection = tmp_path / f"unicode_{format_name}.json"
        selection.write_text(json.dumps({
            "schema_version": "1.0",
            "profile": "power",
            "categories": [],
            "format": format_name,
        }), encoding="utf-8")
        result = export_selection(project, selection, output)
        paths = [result.output] if result.output.is_file() else sorted(result.output.glob("*"))
        readable = set()
        from osgeo import ogr
        for path in paths:
            if path.suffix.lower() not in {".gpkg", ".geojson", ".shp"}:
                continue
            dataset = ogr.Open(str(path), 0)
            assert dataset is not None
            for index in range(dataset.GetLayerCount()):
                layer = dataset.GetLayerByIndex(index)
                for feature in layer:
                    tags = json.loads(feature.GetField("tags_json"))
                    if "name" in tags:
                        readable.add(tags["name"])
            dataset = None
        assert expected.issubset(readable), format_name
