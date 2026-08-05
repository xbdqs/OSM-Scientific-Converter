from __future__ import annotations

import json
import hashlib
import math
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from typing import Any


def _load_ogr():
    try:
        from osgeo import ogr
    except ImportError as error:
        raise RuntimeError("GDAL Python bindings are required for geometry quality checks") from error
    ogr.UseExceptions()
    return ogr


def _allocate_strata(counts: list[int], requested: int) -> list[int]:
    """Allocate a bounded sample with at least one item per non-empty stratum."""
    if not counts:
        return []
    target = min(sum(counts), 1000, max(requested, len(counts)))
    quotas = [1 for _ in counts]
    remaining = target - len(counts)
    capacities = [max(0, count - 1) for count in counts]
    capacity_total = sum(capacities)
    if remaining <= 0 or capacity_total == 0:
        return quotas
    raw = [remaining * capacity / capacity_total for capacity in capacities]
    additions = [min(capacities[index], int(math.floor(value))) for index, value in enumerate(raw)]
    for index, value in enumerate(additions):
        quotas[index] += value
    left = remaining - sum(additions)
    order = sorted(
        range(len(counts)),
        key=lambda index: (raw[index] - additions[index], capacities[index], -index),
        reverse=True,
    )
    while left:
        changed = False
        for index in order:
            if quotas[index] < counts[index]:
                quotas[index] += 1
                left -= 1
                changed = True
                if left == 0:
                    break
        if not changed:
            break
    return quotas


def _stratified_sample(connection: sqlite3.Connection, requested: int) -> tuple[list[sqlite3.Row], list[dict[str, Any]], str]:
    metadata = {str(row[0]): str(row[1]) for row in connection.execute("SELECT key,value FROM metadata")}
    seed = metadata.get("phase1_input_sha256", "") or metadata.get("profile_sha256", "")
    strata_rows = connection.execute(
        """SELECT m.category,o.geometry_group,COUNT(DISTINCT o.object_pk) AS object_count
           FROM objects o JOIN matches m USING(object_pk)
           GROUP BY m.category,o.geometry_group
           ORDER BY m.category,o.geometry_group"""
    ).fetchall()
    counts = [int(row["object_count"]) for row in strata_rows]
    quotas = _allocate_strata(counts, requested)

    def sample_hash(object_pk: int, category: str, geometry_group: str) -> str:
        value = f"{seed}|{int(object_pk)}|{category}|{geometry_group}".encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    connection.create_function("sample_hash", 3, sample_hash, deterministic=True)
    selected: list[sqlite3.Row] = []
    audit: list[dict[str, Any]] = []
    for row, quota in zip(strata_rows, quotas):
        category = str(row["category"])
        geometry = str(row["geometry_group"])
        sample = connection.execute(
            """SELECT o.object_pk,o.osm_id,o.osm_type,o.source_layer,o.source_fid,
                      o.geometry_group,o.tags_json,? AS category
               FROM objects o
               WHERE o.geometry_group=? AND EXISTS (
                   SELECT 1 FROM matches m WHERE m.object_pk=o.object_pk AND m.category=?
               )
               ORDER BY sample_hash(o.object_pk,?,o.geometry_group) LIMIT ?""",
            (category, geometry, category, category, quota),
        ).fetchall()
        selected.extend(sample)
        audit.append({
            "category": category,
            "geometry_group": geometry,
            "population": int(row["object_count"]),
            "sampled": len(sample),
        })
    return selected, audit, seed


def _expected_fields_by_category(profile: dict[str, Any]) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, set[str]]] = {
        str(category): {
            level: {str(field) for field in expected.get(level, [])}
            for level in ("required", "recommended", "optional")
        }
        for category, expected in profile.get("expected_fields_by_category", {}).items()
    }
    for rule in profile.get("rules", []):
        category = str(rule.get("category", ""))
        expected = rule.get("expected_fields", {})
        target = result.setdefault(category, {"required": set(), "recommended": set(), "optional": set()})
        for level in ("required", "recommended", "optional"):
            target[level].update(str(field) for field in expected.get(level, []))
    return {
        category: {level: sorted(fields) for level, fields in levels.items()}
        for category, levels in result.items()
    }


def run_quality_checks(project_dir: str | Path, settings: dict[str, Any]) -> dict[str, Any]:
    project = Path(project_dir)
    database = project / "classification" / "classification.sqlite"
    raw_master = project / "data" / "raw_master.gpkg"
    profile_path = project / "profiles" / "resolved_profile.json"
    if not database.is_file() or not raw_master.is_file() or not profile_path.is_file():
        raise FileNotFoundError("Quality checks require classification.sqlite, raw_master.gpkg, and resolved_profile.json")
    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    expected_by_category = _expected_fields_by_category(profile)
    checks: dict[str, Any] = {}
    sample_size = max(1, min(int(settings.get("sample_size", 50)), 1000))

    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        duplicate_rows = connection.execute("SELECT osm_id,COUNT(*) count FROM objects GROUP BY osm_id HAVING COUNT(*)>1 ORDER BY count DESC LIMIT 100").fetchall()
        numeric = int(connection.execute("SELECT COUNT(*) FROM numeric_parse_failures").fetchone()[0])
        selected, strata_audit, sampling_seed = _stratified_sample(connection, sample_size)
        total_objects = int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0])

    ogr = _load_ogr()
    dataset = ogr.Open(str(raw_master), 0)
    if dataset is None:
        raise RuntimeError(f"Could not open {raw_master}")
    empty = 0
    invalid = 0
    missing_source = 0
    missing_fields: dict[str, dict[str, Counter[str]]] = {}
    applicable_counts = Counter()
    relation_way_warnings = 0
    samples: list[dict[str, Any]] = []
    for row in selected:
        layer = dataset.GetLayerByName(str(row["source_layer"]))
        feature = layer.GetFeature(int(row["source_fid"])) if layer else None
        geometry = feature.GetGeometryRef() if feature else None
        if feature is None:
            missing_source += 1
        elif geometry is None or geometry.IsEmpty():
            empty += 1
        elif not geometry.IsValid():
            invalid += 1
        tags = json.loads(row["tags_json"] or "{}")
        category = str(row["category"])
        applicable_counts[category] += 1
        missing_fields.setdefault(category, {"required": Counter(), "recommended": Counter()})
        expected = expected_by_category.get(category, {"required": [], "recommended": [], "optional": []})
        for level in ("required", "recommended"):
            for attribute in expected[level]:
                if attribute not in tags or tags.get(attribute) in (None, ""):
                    missing_fields[category][level][attribute] += 1
        if row["osm_type"] in {"relation", "way"} and (geometry is None or geometry.IsEmpty()):
            relation_way_warnings += 1
        samples.append({
            "osm_id": row["osm_id"],
            "category": category,
            "geometry_group": row["geometry_group"],
            "tag_count": len(tags),
            "geometry_present": geometry is not None and not geometry.IsEmpty(),
            "geometry_valid": bool(geometry is not None and geometry.IsValid()),
        })
        feature = None
    dataset = None
    missing_report: dict[str, Any] = {}
    required_missing = 0
    recommended_missing = 0
    for category, expected in sorted(expected_by_category.items()):
        denominator = int(applicable_counts.get(category, 0))
        levels: dict[str, Any] = {}
        for level in ("required", "recommended"):
            counts = missing_fields.get(category, {}).get(level, Counter())
            levels[level] = {
                field: {"missing": int(counts.get(field, 0)), "denominator": denominator}
                for field in expected[level]
            }
        required_missing += sum(item["missing"] for item in levels["required"].values())
        recommended_missing += sum(item["missing"] for item in levels["recommended"].values())
        missing_report[category] = {
            "applicable_objects": denominator,
            "required": levels["required"],
            "recommended": levels["recommended"],
            "optional_not_scored": expected["optional"],
        }

    checks.update({
        "scope": {
            "classified_objects": total_objects,
            "requested_sample_size": sample_size,
            "sample_size": len(samples),
            "sampling": "deterministic category × geometry_group stratification; SHA-256 order within each stratum",
            "sampling_seed_sha256": sampling_seed,
            "strata": strata_audit,
        },
        "empty_geometry": {"count": empty, "sampled": True},
        "invalid_geometry": {"count": invalid, "sampled": True},
        "missing_source_feature": {"count": missing_source, "sampled": True},
        "relation_way_resolution_warnings": {"count": relation_way_warnings, "sampled": True},
        "duplicate_osm_ids": {"count": len(duplicate_rows), "examples": [dict(row) for row in duplicate_rows]},
        "missing_thematic_fields": {
            "by_category": missing_report,
            "summary": {
                "required_missing": required_missing,
                "recommended_missing": recommended_missing,
                "optional_missing_is_error": False,
            },
            "denominator_semantics": "Each field is scored only for sampled objects in its applicable category.",
        },
        "numeric_parse_failures": {"count": numeric},
        "sample_audit": samples,
        "auto_repair": {"enabled": bool(settings.get("auto_repair", False)), "performed": False, "note": "Automatic repair is disabled by default and is not implemented in v0.4.1."},
    })
    checks["status"] = "warning" if any((empty, invalid, missing_source, relation_way_warnings, len(duplicate_rows), numeric, required_missing, recommended_missing)) else "success"
    return checks


def load_preview(project_dir: str | Path, limit: int = 2000) -> dict[str, Any]:
    """Load a bounded set of simplified geometries for QGraphicsScene rendering."""
    project = Path(project_dir)
    database = project / "classification" / "classification.sqlite"
    raw_master = project / "data" / "raw_master.gpkg"
    ogr = _load_ogr()
    with closing(sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT o.object_pk,o.osm_id,o.source_layer,o.source_fid,o.geometry_group,o.tags_json,
                      GROUP_CONCAT(DISTINCT m.category) category
               FROM objects o JOIN matches m USING(object_pk)
               GROUP BY o.object_pk ORDER BY o.object_pk LIMIT ?""",
            (max(1, min(limit, 10000)),),
        ).fetchall()
        total = int(connection.execute("SELECT COUNT(*) FROM objects").fetchone()[0])
    dataset = ogr.Open(str(raw_master), 0)
    features: list[dict[str, Any]] = []
    bounds: list[float] | None = None

    def points(geometry) -> list[list[float]]:
        flat = ogr.GT_Flatten(geometry.GetGeometryType())
        if flat == ogr.wkbPoint:
            return [[geometry.GetX(), geometry.GetY()]]
        if flat == ogr.wkbLineString or flat == ogr.wkbLinearRing:
            return [[point[0], point[1]] for point in geometry.GetPoints()]
        result: list[list[float]] = []
        for index in range(geometry.GetGeometryCount()):
            result.extend(points(geometry.GetGeometryRef(index)))
        return result

    for row in rows:
        layer = dataset.GetLayerByName(str(row["source_layer"]))
        feature = layer.GetFeature(int(row["source_fid"])) if layer else None
        geometry = feature.GetGeometryRef() if feature else None
        if geometry is None or geometry.IsEmpty():
            continue
        coordinates = points(geometry)
        if not coordinates:
            continue
        envelope = geometry.GetEnvelope()
        current = [envelope[0], envelope[2], envelope[1], envelope[3]]
        if bounds is None:
            bounds = current
        else:
            bounds = [min(bounds[0], current[0]), min(bounds[1], current[1]), max(bounds[2], current[2]), max(bounds[3], current[3])]
        features.append({
            "osm_id": row["osm_id"],
            "category": row["category"],
            "geometry_group": row["geometry_group"],
            "coordinates": coordinates[:500],
            "tags": json.loads(row["tags_json"] or "{}"),
        })
        feature = None
    dataset = None
    return {"total": total, "loaded": len(features), "bounds": bounds or [-180, -90, 180, 90], "features": features}
