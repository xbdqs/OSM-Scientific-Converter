from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osm_scientific_converter.core.lifecycle import detect_lifecycle
from osm_scientific_converter.core.tag_scanner import parse_tags


LAYERS = ("points", "lines", "multilinestrings", "multipolygons", "other_relations")
IDENTITY_COLUMNS = {"fid", "osm_id", "osm_way_id"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identity(layer: str, fid: int, osm_id: Any, osm_way_id: Any = None) -> str:
    if layer == "multipolygons":
        if osm_id not in (None, ""):
            return f"relation/{osm_id}"
        if osm_way_id not in (None, ""):
            return f"way/{osm_way_id}"
        return f"unknown/{fid}"
    if layer == "points":
        return f"node/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}"
    if layer == "lines":
        return f"way/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}"
    return f"relation/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}"


def target_objects(thematic: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    with sqlite3.connect(f"file:{thematic.as_posix()}?mode=ro", uri=True) as connection:
        for osm_id, source_layer, tags_json, lifecycle in connection.execute(
            "SELECT osm_id, source_layer, tags_json, lifecycle FROM objects ORDER BY osm_id"
        ):
            result[str(osm_id)] = {
                "source_layer": str(source_layer),
                "tags": json.loads(tags_json),
                "lifecycle": json.loads(lifecycle),
            }
    return result


def geometry_columns(connection: sqlite3.Connection) -> set[str]:
    try:
        return {str(row[0]) for row in connection.execute("SELECT column_name FROM gpkg_geometry_columns")}
    except sqlite3.Error:
        return set()


def default_tags(columns: list[str], row: tuple[Any, ...], geometry: set[str]) -> dict[str, str]:
    values = dict(zip(columns, row, strict=True))
    tags: dict[str, str] = {}
    for key, value in values.items():
        if key in IDENTITY_COLUMNS or key in geometry or value in (None, ""):
            continue
        if key in {"other_tags", "all_tags"}:
            parsed, _ = parse_tags(value)
            tags.update(parsed)
        else:
            tags[key] = str(value)
    return tags


def inspect_default(database: Path, targets: dict[str, dict[str, Any]]) -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    with sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True) as connection:
        geometry = geometry_columns(connection)
        tables = {str(row[0]) for row in connection.execute("SELECT table_name FROM gpkg_contents")}
        for layer in LAYERS:
            if layer not in tables:
                continue
            columns = [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{layer}")')]
            select_columns = [column for column in columns if column not in geometry]
            quoted = ",".join(f'"{column}"' for column in select_columns)
            for row in connection.execute(f'SELECT {quoted} FROM "{layer}"'):
                values = dict(zip(select_columns, row, strict=True))
                sid = identity(
                    layer,
                    int(values.get("fid") or 0),
                    values.get("osm_id"),
                    values.get("osm_way_id"),
                )
                if sid in targets:
                    found[sid] = default_tags(select_columns, row, geometry)
    return found


def run_import(input_path: Path, output: Path, ogr2ogr: Path, gdal_data: Path) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f".{output.name}.partial")
    partial.unlink(missing_ok=True)
    command = [
        str(ogr2ogr),
        "-f",
        "GPKG",
        str(partial),
        str(input_path),
        "--config",
        "GDAL_DATA",
        str(gdal_data),
        "--config",
        "OGR2OGR_USE_ARROW_API",
        "NO",
    ]
    environment = os.environ.copy()
    environment.pop("OSM_CONFIG_FILE", None)
    started = time.perf_counter()
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    peak_rss = 0
    try:
        import psutil

        monitored = psutil.Process(process.pid)
    except (ImportError, OSError):
        monitored = None
    while process.poll() is None:
        if monitored is not None:
            try:
                rss = monitored.memory_info().rss + sum(
                    child.memory_info().rss for child in monitored.children(recursive=True)
                )
                peak_rss = max(peak_rss, rss)
            except (OSError, psutil.Error):
                pass
        time.sleep(0.05)
    stdout, stderr = process.communicate()
    if process.returncode != 0 or not partial.is_file():
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"GDAL default import failed ({process.returncode}): {stderr}")
    os.replace(partial, output)
    default_config = gdal_data / "osmconf.ini"
    return {
        "command": command,
        "default_osmconf": str(default_config),
        "default_osmconf_sha256": sha256(default_config) if default_config.is_file() else None,
        "wall_time_seconds": round(time.perf_counter() - started, 6),
        "peak_rss_bytes": peak_rss or None,
        "output_bytes": output.stat().st_size,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Partial same-snapshot comparison with GDAL default osmconf")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--thematic", type=Path, required=True)
    parser.add_argument("--ogr2ogr", type=Path, required=True)
    parser.add_argument("--gdal-data", type=Path, required=True)
    parser.add_argument("--output-database", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()

    targets = target_objects(args.thematic)
    performance = run_import(args.input, args.output_database, args.ogr2ogr, args.gdal_data)
    found = inspect_default(args.output_database, targets)
    target_ids = set(targets)
    found_ids = set(found)
    relations = {key for key in target_ids if key.startswith("relation/")}
    lifecycle = {key for key, value in targets.items() if value["lifecycle"]}
    lifecycle_detectable = {
        key for key in lifecycle & found_ids if detect_lifecycle(found[key])
    }
    total_assignments = 0
    retained_assignments = 0
    for key in target_ids & found_ids:
        for tag_key, tag_value in targets[key]["tags"].items():
            total_assignments += 1
            retained_assignments += found[key].get(tag_key) == str(tag_value)

    report = {
        "schema_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "software_version": "0.4.1",
        "scope": "Berlin power target objects; identical local PBF snapshot; GDAL default osmconf partial comparator",
        "input": {"file": args.input.name, "bytes": args.input.stat().st_size, "sha256": sha256(args.input)},
        "comparators": {
            "gdal_default_osmconf": {"status": "executed", "performance": performance},
            "osm_scientific_converter_v0.4.1": {
                "status": "executed",
                "profile": "power",
                "explainable_versioned_rules": True,
                "export_loss_audit": True,
            },
            "quickosm": {"status": "not_executed", "reason": "QGIS/QuickOSM is not installed locally"},
            "prepared_shapefile": {
                "status": "not_executed",
                "reason": "No product, version, same-snapshot date, or matching extent was supplied",
                "treated_as_reality_truth": False,
            },
        },
        "target_osm_id_recall": {
            "target": len(target_ids),
            "recalled_by_gdal_default": len(target_ids & found_ids),
            "rate": round(len(target_ids & found_ids) / len(target_ids), 6) if target_ids else 0.0,
        },
        "tag_retention": {
            "comparable_original_assignments": total_assignments,
            "exact_key_value_assignments_retained": retained_assignments,
            "rate": round(retained_assignments / total_assignments, 6) if total_assignments else 0.0,
        },
        "relation_reconstruction": {
            "target_relations": len(relations),
            "recalled_by_gdal_default": len(relations & found_ids),
        },
        "lifecycle_discovery": {
            "target_lifecycle_objects": len(lifecycle),
            "recalled_objects": len(lifecycle & found_ids),
            "lifecycle_tags_still_detectable": len(lifecycle_detectable),
        },
        "scientific_limitations": [
            "This is a partial two-tool comparison, not the required complete four-way comparison.",
            "Target membership is the v0.4.1 power rule result and is not physical real-world ground truth.",
            "GDAL and v0.4.1 both use the GDAL OSM driver; the comparison isolates default versus custom configuration and downstream audit behavior.",
        ],
        "status": "partial_comparison_complete_external_comparators_pending",
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "target": len(target_ids), "recalled": len(target_ids & found_ids)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
