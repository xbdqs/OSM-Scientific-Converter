"""Independent stdlib-only frozen-v0.4.2 quick-road smoke GeoPackage verifier.

Usage: python tools/verify_frozen_quick_gpkg_v042.py path/to/SMOKE_QUICK_ROADS.gpkg

This is a deterministic smoke test of FOUR small bundled objects, NOT a
completeness/geometry-topology audit of a general OpenStreetMap extraction.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from contextlib import closing
from pathlib import Path

EXPECTED = {
    "way/1001": ("motorway", "motorways_and_trunks"),
    "way/1002": ("primary", "primary_secondary_tertiary"),
    "way/1003": ("residential", "residential_and_service"),
    "way/1004": ("pedestrian", "pedestrian"),
}


def verify(path: Path) -> dict:
    path = path.resolve(strict=True)
    if not path.is_file() or path.stat().st_size < 100:
        raise ValueError("GeoPackage missing or empty")
    # Explicit read-only URI: a misspelled path cannot create an empty database.
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)) as conn:
        quick_check = conn.execute("PRAGMA quick_check(1)").fetchone()[0]
        if quick_check != "ok":
            raise AssertionError(f"SQLite quick_check failed: {quick_check}")
        layer_info = conn.execute(
            "SELECT column_name, geometry_type_name, srs_id FROM gpkg_geometry_columns "
            "WHERE table_name = ?", ("highway_lines",)
        ).fetchone()
        if not layer_info or layer_info[1].upper() != "LINESTRING" or int(layer_info[2]) != 4326:
            raise AssertionError(f"Unexpected layer geometry or CRS: {layer_info}")
        geom_col = layer_info[0]
        # Table and field names are fixed for this bundled smoke profile.
        required_columns = {
            "canonical_osm_id", "osm_type", "source_layer", "highway", "category",
            "profile_id", "profile_sha256", "rule_ids", "tags_json", geom_col,
        }
        columns = {r[1] for r in conn.execute('PRAGMA table_info("highway_lines")')}
        if not required_columns.issubset(columns):
            raise AssertionError(f"Missing fields: {sorted(required_columns - columns)}")
        rows = conn.execute(
            'SELECT canonical_osm_id, osm_type, source_layer, highway, category, '
            'profile_id, profile_sha256, rule_ids, tags_json, geom '
            'FROM "highway_lines" ORDER BY canonical_osm_id'
        ).fetchall()
        if len(rows) != 4:
            raise AssertionError(f"Expected exactly four roads, got {len(rows)}")
        ids: set[str] = set()
        for canonical_id, osm_type, source_layer, highway, category, profile_id, profile_sha, rule_ids, tags_json, geom in rows:
            if canonical_id in ids or canonical_id not in EXPECTED:
                raise AssertionError(f"Unexpected or duplicate OSM way ID: {canonical_id}")
            ids.add(canonical_id)
            if (highway, category) != EXPECTED[canonical_id]:
                raise AssertionError(f"Road category or highway mismatch: {canonical_id}")
            if (osm_type, source_layer, profile_id) != ("way", "lines", "reviewer_roads_lines_v1"):
                raise AssertionError(f"Provenance mismatch: {canonical_id}")
            if not profile_sha or len(profile_sha) != 64 or not rule_ids or not geom:
                raise AssertionError(f"Missing hash/rule/geometry: {canonical_id}")
            tags = json.loads(tags_json)
            if not isinstance(tags, dict) or tags.get("highway") != highway:
                raise AssertionError(f"OSM tag mismatch: {canonical_id}")
        if ids != set(EXPECTED):
            raise AssertionError("Object identity mismatch")
        rtree_name = f"rtree_highway_lines_{geom_col}"
        if conn.execute(f'SELECT COUNT(*) FROM "{rtree_name}"').fetchone()[0] != 4:
            raise AssertionError("RTree spatial index missing/incomplete")
        trigger_count = conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' AND name LIKE ?",
            (rtree_name + "_%",)
        ).fetchone()[0]
        if trigger_count < 7:
            raise AssertionError(f"RTree maintenance triggers missing: {trigger_count}")
        return {
            "status": "PASS",
            "file": path.name,
            "feature_count": len(rows),
            "source_layer": "lines",
            "CRS": "EPSG:4326",
            "geometry_type": "LINESTRING",
            "canonical_ids_match": True,
            "categories": dict(sorted(Counter(row[4] for row in rows).items())),
            "rtree_rows": 4,
            "rtree_triggers": trigger_count,
            "sqlite_quick_check": quick_check,
            "scope": "Bundled four-road frozen-executable smoke test only",
        }


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Usage: python tools/verify_frozen_quick_gpkg_v042.py <quick.gpkg>", file=sys.stderr)
        return 2
    try:
        report = verify(Path(argv[0]))
    except Exception as exc:
        print(json.dumps({"status": "FAIL", "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 1
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
