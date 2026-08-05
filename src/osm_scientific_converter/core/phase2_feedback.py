from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .path_privacy import contains_absolute_path, redact_absolute_paths_in_text, sanitize_paths


def build_phase2_feedback(project_dir: str | Path, timestamp: datetime | None = None) -> Path:
    """Build an aggregate-only Phase 2 feedback archive."""
    project = Path(project_dir)
    stamp = (timestamp or datetime.now(timezone.utc)).strftime("%Y%m%d_%H%M%S")
    feedback_dir = project / "feedback"
    feedback_dir.mkdir(parents=True, exist_ok=True)
    destination = feedback_dir / f"Phase2_Feedback_{stamp}.zip"
    allowed_names = {
        "classification_summary.json",
        "matched_rules.csv",
        "unmatched_summary.csv",
        "classification.log",
        "resolved_profile.json",
        "export_audit.json",
        "field_mapping.csv",
        "shapefile_field_mapping.csv",
        "shapefile_loss_report.json",
    }
    files: list[tuple[Path, Path]] = []
    for root in ("classification", "profiles", "exports"):
        base = project / root
        if not base.exists():
            continue
        for path in sorted(base.rglob("*"), key=lambda item: item.as_posix()):
            if path.is_file() and path.name in allowed_names:
                files.append((path, path.relative_to(project)))
    manifest = {
        "project": ".",
        "privacy": (
            "Original OSM/PBF, geometry, classification databases, object-level matches, "
            "raw tags, and thematic datasets are intentionally excluded."
        ),
        "included_files": [relative.as_posix() for _, relative in files],
        "excluded_object_level_data": True,
    }
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        archive.writestr(
            "feedback_bundle_manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        for path, relative in files:
            if path.suffix.lower() == ".json":
                payload = sanitize_paths(json.loads(path.read_text(encoding="utf-8-sig")))
                if contains_absolute_path(payload):
                    raise ValueError(f"Absolute path remained in feedback JSON: {relative}")
                archive.writestr(
                    relative.as_posix(),
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                )
            elif path.suffix.lower() in {".csv", ".log", ".txt"}:
                text = redact_absolute_paths_in_text(path.read_text(encoding="utf-8-sig", errors="replace"))
                archive.writestr(relative.as_posix(), text)
            else:
                archive.write(path, relative.as_posix())
    return destination
