from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osm_scientific_converter import __version__


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass
class GuiProject:
    schema_version: str = "1.0"
    software_version: str = __version__
    input_path: str = ""
    input_sha256: str = ""
    project_dir: str = ""
    keep_raw_master: bool = True
    profile_id: str = "power"
    profile_sha256: str = ""
    custom_rule_file: str = ""
    classification_rules: list[dict[str, Any]] = field(default_factory=list)
    selected_categories: list[str] = field(default_factory=list)
    selected_tag_values: dict[str, list[str]] = field(default_factory=dict)
    export_format: str = "GPKG"
    crs: str = "EPSG:4326"
    selected_fields: list[str] = field(default_factory=list)
    export_path: str = ""
    quality_settings: dict[str, Any] = field(default_factory=lambda: {
        "auto_repair": False,
        "sample_size": 50,
        "check_empty_geometry": True,
        "check_invalid_geometry": True,
        "check_duplicate_osm_ids": True,
        "check_missing_fields": True,
        "check_numeric_failures": True,
    })
    run_results: dict[str, Any] = field(default_factory=dict)
    saved_at_utc: str = ""

    @property
    def project_file(self) -> Path:
        if not self.project_dir:
            raise ValueError("Project directory is not selected")
        return Path(self.project_dir) / "project.osmproject.json"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["software_version"] = __version__
        payload["saved_at_utc"] = _utc_now()
        return payload

    def save(self, path: str | Path | None = None) -> Path:
        destination = Path(path) if path else self.project_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp = destination.with_name(f".{destination.name}.partial-{uuid.uuid4().hex}")
        temp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temp, destination)
        self.saved_at_utc = _utc_now()
        return destination

    @classmethod
    def load(cls, path: str | Path) -> "GuiProject":
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8-sig"))
        if data.get("schema_version") != "1.0":
            raise ValueError("Unsupported .osmproject schema version")
        allowed = cls.__dataclass_fields__.keys()
        state = cls(**{key: value for key, value in data.items() if key in allowed})
        if not state.project_dir:
            state.project_dir = str(source.parent.resolve())
        return state
