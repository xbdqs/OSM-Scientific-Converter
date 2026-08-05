from __future__ import annotations

import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Callable

from .inventory_store import InventoryStore
from .lifecycle import detect_lifecycle

LAYER_SPECS = {
    "points": ("point", "node"),
    "lines": ("line", "way"),
    "multilinestrings": ("line", "relation"),
    "multipolygons": ("polygon", "way_or_relation"),
    "other_relations": ("other", "relation"),
}

_HSTORE_PAIR = re.compile(r'"((?:[^"\\]|\\.)*)"\s*=>\s*"((?:[^"\\]|\\.)*)"')


def _unescape_hstore(value: str) -> str:
    return value.replace(r'\"', '"').replace(r"\\", "\\")


def parse_tags(raw: Any) -> tuple[dict[str, str], str | None]:
    if raw is None or raw == "":
        return {}, "empty_all_tags"
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(str(raw))
    except (json.JSONDecodeError, TypeError, ValueError):
        matches = _HSTORE_PAIR.findall(str(raw))
        if matches:
            tags = {_unescape_hstore(key): _unescape_hstore(value) for key, value in matches}
            return tags, "legacy_hstore"
        return {}, "malformed_all_tags"
    if not isinstance(parsed, dict):
        return {}, "non_object_all_tags"
    tags: dict[str, str] = {}
    anomaly = None
    for key, value in parsed.items():
        if not isinstance(key, str):
            key = str(key)
        if value is None:
            tags[key] = ""
            anomaly = anomaly or "null_tag_value"
        elif isinstance(value, str):
            tags[key] = value
        else:
            tags[key] = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            anomaly = anomaly or "non_string_tag_value"
    return tags, anomaly


def _quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in connection.execute(f"PRAGMA table_info({_quote_identifier(table)})")}


def _sample_json(samples: list[str]) -> str:
    return json.dumps(samples[:5], ensure_ascii=False, separators=(",", ":"))


def scan_geopackage(
    path: str | Path,
    inventory_db: str | Path,
    log: Callable[[str], None] | None = None,
    *,
    chunk_unique_limit: int = 50_000,
) -> tuple[dict[str, Any], int, list[dict[str, Any]]]:
    """Scan a reconstructed GeoPackage with bounded-memory SQLite aggregation."""
    if chunk_unique_limit < 1:
        raise ValueError("chunk_unique_limit must be at least 1")

    anomalies: Counter[str] = Counter()
    warnings: list[dict[str, Any]] = []
    layers: list[dict[str, Any]] = []
    total_features = 0
    total_assignments = 0
    object_type_counts: Counter[str] = Counter()

    tag_chunk: dict[tuple[str, str, str, str], list[Any]] = {}
    lifecycle_chunk: dict[tuple[str, str, str, str], list[Any]] = {}
    key_cross_chunk: Counter[tuple[str, str, str]] = Counter()

    def observe(target: dict[tuple[str, str, str, str], list[Any]], key: tuple[str, str, str, str], sid: str) -> None:
        value = target.get(key)
        if value is None:
            target[key] = [1, [sid]]
            return
        value[0] += 1
        if sid not in value[1] and len(value[1]) < 5:
            value[1].append(sid)

    with InventoryStore(inventory_db, create=True) as store:
        def flush() -> None:
            if tag_chunk:
                store.upsert_tags(
                    (key, value, layer, geometry, int(data[0]), _sample_json(data[1]))
                    for (key, value, layer, geometry), data in tag_chunk.items()
                )
                tag_chunk.clear()
            if lifecycle_chunk:
                store.upsert_lifecycle(
                    (state, raw_form, layer, geometry, int(data[0]), _sample_json(data[1]))
                    for (state, raw_form, layer, geometry), data in lifecycle_chunk.items()
                )
                lifecycle_chunk.clear()
            if key_cross_chunk:
                store.upsert_key_cross(
                    (key, layer, geometry, int(count))
                    for (key, layer, geometry), count in key_cross_chunk.items()
                )
                key_cross_chunk.clear()
            store.commit()

        connection = sqlite3.connect(f"file:{Path(path).resolve().as_posix()}?mode=ro", uri=True)
        try:
            tables = _table_names(connection)
            for layer_name, (geometry_group, osm_type) in LAYER_SPECS.items():
                if layer_name not in tables:
                    warnings.append({"message": f"Expected GDAL OSM layer is missing: {layer_name}", "count": 1})
                    layers.append({
                        "name": layer_name,
                        "present": False,
                        "feature_count": 0,
                        "geometry_group": geometry_group,
                        "osm_type": osm_type,
                    })
                    continue
                columns = _columns(connection, layer_name)
                count = int(connection.execute(
                    f"SELECT COUNT(*) FROM {_quote_identifier(layer_name)}"
                ).fetchone()[0])
                total_features += count
                if layer_name == "multipolygons" and "osm_way_id" in columns and "osm_id" in columns:
                    relation_count = int(connection.execute(
                        f"SELECT COUNT(*) FROM {_quote_identifier(layer_name)} WHERE osm_id IS NOT NULL"
                    ).fetchone()[0])
                    way_count = int(connection.execute(
                        f"SELECT COUNT(*) FROM {_quote_identifier(layer_name)} WHERE osm_way_id IS NOT NULL"
                    ).fetchone()[0])
                    layer_object_counts = {"relation": relation_count, "way": way_count}
                else:
                    layer_object_counts = {osm_type: count}
                object_type_counts.update(layer_object_counts)
                layers.append({
                    "name": layer_name,
                    "present": True,
                    "feature_count": count,
                    "geometry_group": geometry_group,
                    "osm_type": osm_type,
                    "object_type_counts": layer_object_counts,
                })
                if "all_tags" not in columns:
                    warnings.append({"message": f"Layer {layer_name} has no all_tags column", "count": 1})
                    continue
                if layer_name == "multipolygons" and "osm_way_id" in columns and "osm_id" in columns:
                    id_expression = (
                        "CASE WHEN osm_id IS NOT NULL THEN 'relation/' || osm_id "
                        "WHEN osm_way_id IS NOT NULL THEN 'way/' || osm_way_id "
                        "ELSE 'unknown/' || rowid END"
                    )
                elif "osm_id" in columns:
                    prefix = "node" if layer_name == "points" else ("way" if layer_name == "lines" else "relation")
                    id_expression = f"'{prefix}/' || osm_id"
                else:
                    id_expression = "'unknown/' || rowid"
                query = (
                    f"SELECT {id_expression}, {_quote_identifier('all_tags')} "
                    f"FROM {_quote_identifier(layer_name)} ORDER BY {id_expression}"
                )
                processed = 0
                for osm_id, raw_tags in connection.execute(query):
                    processed += 1
                    tags, anomaly = parse_tags(raw_tags)
                    if anomaly:
                        anomalies[anomaly] += 1
                    sid = str(osm_id)
                    for key, value in sorted(tags.items()):
                        total_assignments += 1
                        if key == "":
                            anomalies["empty_tag_key"] += 1
                        if value == "":
                            anomalies["empty_tag_value"] += 1
                        observe(tag_chunk, (key, value, layer_name, geometry_group), sid)
                        key_cross_chunk[(key, layer_name, geometry_group)] += 1
                    for state, raw_form in detect_lifecycle(tags):
                        observe(lifecycle_chunk, (state, raw_form, layer_name, geometry_group), sid)
                    if len(tag_chunk) + len(lifecycle_chunk) + len(key_cross_chunk) >= chunk_unique_limit:
                        flush()
                flush()
                if log:
                    log(f"Scanned {processed} features from {layer_name}")
        finally:
            connection.close()

        counts = store.counts()
        raw_inventory = {
            "expected_layers": list(LAYER_SPECS),
            "layers": layers,
            "total_features": total_features,
            "object_count_scope": (
                "Counts are reconstructed GDAL features exposed in the five OSM layers; "
                "they are not raw totals of all base nodes, ways, and relations."
            ),
            "reconstructed_osm_object_types": dict(sorted(object_type_counts.items())),
            "osm_object_types": dict(sorted(object_type_counts.items())),
            "total_tag_assignments": total_assignments,
            "tag_inventory_rows": counts["tag_inventory_rows"],
            "unique_keys": counts["unique_keys"],
            "unique_key_values": counts["unique_key_values"],
            "tag_parse_anomalies": dict(sorted(anomalies.items())),
            "key_layer_geometry": store.key_layer_geometry(),
            "aggregation": {
                "backend": "SQLite",
                "chunk_unique_limit": chunk_unique_limit,
                "inventory_database": "data/inventory.sqlite",
            },
        }
        lifecycle_count = counts["lifecycle_inventory_rows"]
    return raw_inventory, lifecycle_count, warnings
