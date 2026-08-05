from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


GEOMETRIES = ("", "point", "line", "polygon", "relation")


class InventoryRepository:
    """Read-only, paginated access to the disk-backed Phase 1 inventory."""

    def __init__(self, project_dir: str | Path) -> None:
        self.project_dir = Path(project_dir)
        self.database = self.project_dir / "data" / "inventory.sqlite"
        if not self.database.is_file():
            raise FileNotFoundError(f"Inventory database is missing: {self.database}")

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(f"file:{self.database.as_posix()}?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        return connection

    def summary(self) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            result = {
                "tag_inventory_rows": connection.execute("SELECT COUNT(*) FROM tag_inventory").fetchone()[0],
                "unique_keys": connection.execute("SELECT COUNT(DISTINCT key) FROM tag_inventory").fetchone()[0],
                "unique_key_values": connection.execute("SELECT COUNT(*) FROM (SELECT key,value FROM tag_inventory GROUP BY key,value)").fetchone()[0],
                "lifecycle_rows": connection.execute("SELECT COUNT(*) FROM lifecycle_inventory").fetchone()[0],
                "layers": {},
            }
            for row in connection.execute("SELECT source_layer, SUM(count) count FROM key_layer_geometry GROUP BY source_layer ORDER BY source_layer"):
                result["layers"][row["source_layer"]] = int(row["count"])
            return result

    def keys(self, *, search: str = "", geometry: str = "", lifecycle: str = "", limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        clauses: list[str] = []
        parameters: list[Any] = []
        if search:
            clauses.append("t.key LIKE ? ESCAPE '\\'")
            parameters.append(f"%{search.replace('%', r'\%').replace('_', r'\_')}%")
        if geometry:
            clauses.append("t.geometry_group=?")
            parameters.append(geometry)
        if lifecycle:
            clauses.append("EXISTS (SELECT 1 FROM lifecycle_inventory l WHERE l.normalized_state=? AND (l.raw_form=t.key OR l.raw_form LIKE t.key || '=%'))")
            parameters.append(lifecycle)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        query = f"SELECT t.key, SUM(t.count) AS count, COUNT(DISTINCT t.value) AS values_count FROM tag_inventory t{where} GROUP BY t.key ORDER BY count DESC,t.key LIMIT ? OFFSET ?"
        parameters.extend([limit, offset])
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute(query, parameters)]

    def values(self, key: str, *, search: str = "", geometry: str = "", page: int = 0, page_size: int = 100) -> dict[str, Any]:
        clauses = ["key=?"]
        parameters: list[Any] = [key]
        if search:
            clauses.append("value LIKE ? ESCAPE '\\'")
            parameters.append(f"%{search.replace('%', r'\%').replace('_', r'\_')}%")
        if geometry:
            clauses.append("geometry_group=?")
            parameters.append(geometry)
        where = " AND ".join(clauses)
        with closing(self._connect()) as connection:
            total = int(connection.execute(f"SELECT COUNT(*) FROM (SELECT value FROM tag_inventory WHERE {where} GROUP BY value)", parameters).fetchone()[0])
            rows = [dict(row) for row in connection.execute(
                f"SELECT value,SUM(count) count FROM tag_inventory WHERE {where} GROUP BY value ORDER BY count DESC,value LIMIT ? OFFSET ?",
                [*parameters, page_size, page * page_size],
            )]
        return {"key": key, "page": page, "page_size": page_size, "total": total, "rows": rows}

    def lifecycle_states(self) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return [dict(row) for row in connection.execute("SELECT normalized_state,SUM(count) count FROM lifecycle_inventory GROUP BY normalized_state ORDER BY count DESC,normalized_state")]
