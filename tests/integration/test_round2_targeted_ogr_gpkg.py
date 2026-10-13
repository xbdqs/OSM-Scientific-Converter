"""Reproduce the GeoPackage spatial-function trigger regression on real GDAL.

Required for Windows acceptance: unlike mocked SQLite unit tests, this test
runs actual ogr2ogr and updates an indexed GPKG through OGR's driver.
"""
from __future__ import annotations

import json
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from osm_scientific_converter.core.profiles import load_custom_profile
from osm_scientific_converter.core.targeted import targeted_highway_extract

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("deferred", [False, True], ids=["default-index", "deferred-index"])
@pytest.mark.skipif(shutil.which("ogr2ogr") is None, reason="ogr2ogr not installed")
def test_targeted_ogr_update_real_indexed_geopackage(tmp_path, deferred):
    pytest.importorskip("osgeo.ogr")
    source = ROOT / "examples/round2_roads_small.osm"
    config = ROOT / "src/osm_scientific_converter/resources/osmconf.ini"
    profile = load_custom_profile(ROOT / "examples/round2_road_extraction_rules.json")
    output = tmp_path / "roads.gpkg"

    audit = targeted_highway_extract(source, output, profile, base_config=config,
                                     experimental_deferred_index=deferred)
    assert audit["status"] == "success"
    assert audit["feature_count"] == 4
    assert audit["experimental_deferred_index"] == deferred
    assert audit["spatial_index"]["mode"] == (
        "deferred_then_created" if deferred else "default_gdal_creation"
    )
    assert output.exists()
    sidecar = Path(str(output) + ".audit.json")
    assert sidecar.is_file()
    assert json.loads(sidecar.read_text(encoding="utf-8"))["feature_count"] == 4

    with closing(sqlite3.connect(f"file:{output.as_posix()}?mode=ro", uri=True)) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        rows = conn.execute(
            "SELECT canonical_osm_id, osm_type, source_layer, category, rule_ids, "
            "profile_id, profile_sha256, tags_json FROM highway_lines ORDER BY osm_id"
        ).fetchall()
        assert len(rows) == 4
        assert {r[0] for r in rows} == {"way/1001", "way/1002", "way/1003", "way/1004"}
        assert all(r[1] == "way" and r[2] == "lines" for r in rows)
        assert all(r[3] and r[4] and r[5] == profile.id and r[6] == profile.sha256 for r in rows)
        assert all(json.loads(r[7]).get("highway") for r in rows)
        trigger_names = {
            row[0] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'rtree_%'"
            )
        }
        # With spatial index triggers present, raw sqlite UPDATE would raise
        # 'no such function ST_IsEmpty' on Windows, but OGR UPDATE must succeed.
        assert trigger_names, "Test output must contain native GeoPackage spatial index triggers"
        rtree_count = conn.execute("SELECT COUNT(*) FROM rtree_highway_lines_geom").fetchone()[0]
        assert rtree_count == 4, "RTree must cover all four geometries"

    assert not list(tmp_path.glob(".osm-sci-targeted-*"))
