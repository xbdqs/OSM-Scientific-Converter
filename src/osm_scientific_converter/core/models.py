from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class InputMetadata:
    path: str
    sha256: str
    format: str
    size_bytes: int
    bounds: list[float] | None
    modified_time_utc: str
    scan_time_utc: str
    gdal_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TagInventoryRecord:
    key: str
    value: str
    source_layer: str
    geometry_group: str
    count: int = 0
    sample_osm_ids: list[str] = field(default_factory=list)

    def observe(self, osm_id: str, sample_limit: int = 5) -> None:
        self.count += 1
        if osm_id not in self.sample_osm_ids and len(self.sample_osm_ids) < sample_limit:
            self.sample_osm_ids.append(osm_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class LifecycleInventoryRecord:
    normalized_state: str
    raw_form: str
    source_layer: str
    geometry_group: str
    count: int = 0
    sample_osm_ids: list[str] = field(default_factory=list)

    def observe(self, osm_id: str, sample_limit: int = 5) -> None:
        self.count += 1
        if osm_id not in self.sample_osm_ids and len(self.sample_osm_ids) < sample_limit:
            self.sample_osm_ids.append(osm_id)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ScanResult:
    project_dir: Path
    feedback_bundle: Path
    input_metadata: dict[str, Any]
    raw_inventory: dict[str, Any]
