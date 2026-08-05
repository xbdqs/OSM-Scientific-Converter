from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path


FULL_INVENTORY_FILES = {
    "tag_inventory.csv",
    "tag_inventory.json",
    "lifecycle_inventory.csv",
}


def build_feedback_bundle(project_dir: str | Path, timestamp: datetime | None = None) -> Path:
    project = Path(project_dir)
    stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    feedback_dir = project / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    destination = feedback_dir / f"Phase1_Feedback_{stamp}.zip"
    excluded_suffixes = {".gpkg", ".osm", ".pbf", ".sqlite", ".db"}
    excluded_roots = {"feedback", "data"}
    files = []
    for path in sorted(project.rglob("*"), key=lambda value: value.as_posix()):
        relative = path.relative_to(project)
        if not path.is_file():
            continue
        if relative.parts[0] in excluded_roots:
            continue
        if path.suffix.lower() in excluded_suffixes or relative.as_posix() in FULL_INVENTORY_FILES:
            continue
        files.append((path, relative))
    manifest = {
        "privacy": (
            "Original OSM/PBF, geometry databases, inventory databases, and full tag/lifecycle "
            "inventories are intentionally excluded."
        ),
        "excluded_full_inventories": sorted(FULL_INVENTORY_FILES),
        "included_files": [relative.as_posix() for _, relative in files],
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(
            "feedback_bundle_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        for path, relative in files:
            archive.write(path, relative.as_posix())
    return destination
