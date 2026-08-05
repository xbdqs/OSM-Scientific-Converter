from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any, Iterable, Iterator

from .inventory_store import InventoryStore, LIFECYCLE_FIELDS, TAG_FIELDS


def _atomic_replace(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    partial.write_text(content, encoding="utf-8", newline="")
    os.replace(partial, path)


def write_json(path: Path, value: Any) -> None:
    _atomic_replace(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _write_json_array(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("w", encoding="utf-8", newline="") as stream:
        stream.write("[\n")
        first = True
        for row in rows:
            if not first:
                stream.write(",\n")
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
            first = False
        stream.write("\n]\n")
    os.replace(partial, path)


def _write_csv(path: Path, fieldnames: list[str], rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    with partial.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            normalized = dict(row)
            if "sample_osm_ids" in normalized:
                normalized["sample_osm_ids"] = json.dumps(
                    normalized["sample_osm_ids"], ensure_ascii=False, separators=(",", ":")
                )
            writer.writerow(normalized)
    os.replace(partial, path)


def write_tag_inventory(project: Path, inventory_db: Path) -> None:
    with InventoryStore(inventory_db) as store:
        _write_json_array(project / "tag_inventory.json", store.iter_tags())
    with InventoryStore(inventory_db) as store:
        _write_csv(project / "tag_inventory.csv", list(TAG_FIELDS), store.iter_tags())


def write_lifecycle_inventory(project: Path, inventory_db: Path) -> None:
    with InventoryStore(inventory_db) as store:
        _write_csv(project / "lifecycle_inventory.csv", list(LIFECYCLE_FIELDS), store.iter_lifecycle())


def _warning_lines(warnings: list[dict[str, Any]]) -> list[str]:
    if not warnings:
        return ["- None"]
    lines = []
    for warning in warnings:
        count = int(warning.get("count", 1))
        suffix = f" (count={count})" if count != 1 else ""
        lines.append(f"- {warning.get('message', 'Unknown warning')}{suffix}")
    return lines


def write_summary(
    project: Path,
    metadata: dict[str, Any],
    inventory: dict[str, Any],
    lifecycle_count: int,
    warnings: list[dict[str, Any]],
    elapsed: float,
) -> None:
    layer_lines = [
        f"| {item['name']} | {str(item['present']).lower()} | {item['geometry_group']} | {item['feature_count']} |"
        for item in inventory.get("layers", [])
    ]
    content = "\n".join([
        "# OSM scan summary",
        "",
        f"- Input: `{metadata['path']}`",
        f"- Format: `{metadata['format']}`",
        f"- Size: {metadata['size_bytes']} bytes",
        f"- SHA-256: `{metadata['sha256']}`",
        f"- Total reconstructed features: {inventory.get('total_features', 0)}",
        f"- Tag assignments: {inventory.get('total_tag_assignments', 0)}",
        f"- Tag inventory rows: {inventory.get('tag_inventory_rows', 0)}",
        f"- Unique keys: {inventory.get('unique_keys', 0)}",
        f"- Unique key/value pairs: {inventory.get('unique_key_values', 0)}",
        f"- Lifecycle inventory rows: {lifecycle_count}",
        f"- Scan wall time: {elapsed:.3f} seconds",
        "",
        "## GDAL OSM layers",
        "",
        "| Layer | Present | Geometry group | Features |",
        "|---|---:|---|---:|",
        *layer_lines,
        "",
        "## Tag parsing anomalies",
        "",
        "```json",
        json.dumps(inventory.get("tag_parse_anomalies", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "```",
        "",
        "## Warnings",
        "",
        *_warning_lines(warnings),
        "",
        "> Counts describe the supplied OSM file, not real-world infrastructure completeness.",
        "",
    ])
    _atomic_replace(project / "scan_summary.md", content)
