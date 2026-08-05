from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator


TAG_FIELDS = ("key", "value", "source_layer", "geometry_group", "count", "sample_osm_ids")
LIFECYCLE_FIELDS = (
    "normalized_state",
    "raw_form",
    "source_layer",
    "geometry_group",
    "count",
    "sample_osm_ids",
)


def _merge_samples(existing: str | None, incoming: str | None, limit: int = 5) -> str:
    merged: list[str] = []
    for raw in (existing, incoming):
        if not raw:
            continue
        try:
            values = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            values = []
        if not isinstance(values, list):
            values = []
        for value in values:
            text = str(value)
            if text not in merged:
                merged.append(text)
                if len(merged) >= limit:
                    return json.dumps(merged, ensure_ascii=False, separators=(",", ":"))
    return json.dumps(merged, ensure_ascii=False, separators=(",", ":"))


class InventoryStore:
    """Disk-backed aggregate store for high-cardinality OSM tag inventories."""

    def __init__(self, path: str | Path, *, create: bool = False) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if create and self.path.exists():
            self.path.unlink()
        self.connection = sqlite3.connect(self.path)
        self.connection.create_function("merge_samples", 2, _merge_samples)
        self.connection.execute("PRAGMA journal_mode=MEMORY")
        self.connection.execute("PRAGMA synchronous=OFF")
        self.connection.execute("PRAGMA temp_store=FILE")
        self.connection.execute("PRAGMA cache_size=-32768")
        if create:
            self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE tag_inventory (
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                source_layer TEXT NOT NULL,
                geometry_group TEXT NOT NULL,
                count INTEGER NOT NULL,
                sample_osm_ids TEXT NOT NULL,
                PRIMARY KEY (key, value, source_layer, geometry_group)
            ) WITHOUT ROWID;

            CREATE TABLE lifecycle_inventory (
                normalized_state TEXT NOT NULL,
                raw_form TEXT NOT NULL,
                source_layer TEXT NOT NULL,
                geometry_group TEXT NOT NULL,
                count INTEGER NOT NULL,
                sample_osm_ids TEXT NOT NULL,
                PRIMARY KEY (normalized_state, raw_form, source_layer, geometry_group)
            ) WITHOUT ROWID;

            CREATE TABLE key_layer_geometry (
                key TEXT NOT NULL,
                source_layer TEXT NOT NULL,
                geometry_group TEXT NOT NULL,
                count INTEGER NOT NULL,
                PRIMARY KEY (key, source_layer, geometry_group)
            ) WITHOUT ROWID;

            CREATE INDEX idx_tag_key_value ON tag_inventory(key, value);
            CREATE INDEX idx_tag_layer ON tag_inventory(source_layer, geometry_group);
            """
        )
        self.connection.commit()

    def close(self) -> None:
        self.connection.commit()
        self.connection.close()

    def __enter__(self) -> "InventoryStore":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        self.connection.close()

    def upsert_tags(self, rows: Iterable[tuple[str, str, str, str, int, str]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO tag_inventory
                (key, value, source_layer, geometry_group, count, sample_osm_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(key, value, source_layer, geometry_group) DO UPDATE SET
                count = tag_inventory.count + excluded.count,
                sample_osm_ids = merge_samples(tag_inventory.sample_osm_ids, excluded.sample_osm_ids)
            """,
            rows,
        )

    def upsert_lifecycle(self, rows: Iterable[tuple[str, str, str, str, int, str]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO lifecycle_inventory
                (normalized_state, raw_form, source_layer, geometry_group, count, sample_osm_ids)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(normalized_state, raw_form, source_layer, geometry_group) DO UPDATE SET
                count = lifecycle_inventory.count + excluded.count,
                sample_osm_ids = merge_samples(lifecycle_inventory.sample_osm_ids, excluded.sample_osm_ids)
            """,
            rows,
        )

    def upsert_key_cross(self, rows: Iterable[tuple[str, str, str, int]]) -> None:
        self.connection.executemany(
            """
            INSERT INTO key_layer_geometry (key, source_layer, geometry_group, count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key, source_layer, geometry_group) DO UPDATE SET
                count = key_layer_geometry.count + excluded.count
            """,
            rows,
        )

    def commit(self) -> None:
        self.connection.commit()

    def scalar(self, query: str, parameters: tuple[Any, ...] = ()) -> int:
        row = self.connection.execute(query, parameters).fetchone()
        return int(row[0]) if row else 0

    def iter_tags(self) -> Iterator[dict[str, Any]]:
        cursor = self.connection.execute(
            """
            SELECT key, value, source_layer, geometry_group, count, sample_osm_ids
            FROM tag_inventory
            ORDER BY key, value, source_layer, geometry_group
            """
        )
        for key, value, layer, geometry, count, samples in cursor:
            yield {
                "key": key,
                "value": value,
                "source_layer": layer,
                "geometry_group": geometry,
                "count": int(count),
                "sample_osm_ids": json.loads(samples),
            }

    def iter_lifecycle(self) -> Iterator[dict[str, Any]]:
        cursor = self.connection.execute(
            """
            SELECT normalized_state, raw_form, source_layer, geometry_group, count, sample_osm_ids
            FROM lifecycle_inventory
            ORDER BY normalized_state, raw_form, source_layer, geometry_group
            """
        )
        for state, raw_form, layer, geometry, count, samples in cursor:
            yield {
                "normalized_state": state,
                "raw_form": raw_form,
                "source_layer": layer,
                "geometry_group": geometry,
                "count": int(count),
                "sample_osm_ids": json.loads(samples),
            }

    def key_layer_geometry(self) -> list[dict[str, Any]]:
        return [
            {
                "key": key,
                "source_layer": layer,
                "geometry_group": geometry,
                "count": int(count),
            }
            for key, layer, geometry, count in self.connection.execute(
                """
                SELECT key, source_layer, geometry_group, count
                FROM key_layer_geometry
                ORDER BY key, source_layer, geometry_group
                """
            )
        ]

    def counts(self) -> dict[str, int]:
        return {
            "tag_inventory_rows": self.scalar("SELECT COUNT(*) FROM tag_inventory"),
            "lifecycle_inventory_rows": self.scalar("SELECT COUNT(*) FROM lifecycle_inventory"),
            "unique_keys": self.scalar("SELECT COUNT(DISTINCT key) FROM tag_inventory"),
            "unique_key_values": self.scalar(
                "SELECT COUNT(*) FROM (SELECT key, value FROM tag_inventory GROUP BY key, value)"
            ),
        }
