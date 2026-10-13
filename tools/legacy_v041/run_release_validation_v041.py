from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from osm_scientific_converter import __version__
from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.environment import inspect_environment
from osm_scientific_converter.core.exporter import export_selection
from osm_scientific_converter.core.hashing import sha256_file
from osm_scientific_converter.core.profiles import load_builtin_profile
from osm_scientific_converter.core.resource_monitor import ResourceMonitor
from osm_scientific_converter.core.scanner import ScanOptions, scan
from osm_scientific_converter.gui.quality import load_preview, run_quality_checks


CASES = {
    "berlin_power": ("berlin-260802.osm.pbf", "power"),
    "south_korea_aeroway": ("south-korea-260802.osm.pbf", "aeroway"),
    "new_york_pipeline": ("new-york-260802.osm.pbf", "pipeline"),
    "quebec_power": ("quebec-260802.osm.pbf", "power"),
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def json_read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def measured(project: Path, operation: Callable[[], Any]) -> tuple[Any, dict[str, Any]]:
    monitor = ResourceMonitor([project])
    started = time.perf_counter()
    monitor.start()
    try:
        result = operation()
    finally:
        monitor.stop()
    return result, {"wall_time_seconds": round(time.perf_counter() - started, 6), **monitor.metrics()}


def integrity(path: Path) -> str:
    with sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True) as connection:
        return str(connection.execute("PRAGMA integrity_check").fetchone()[0])


def run_case(name: str, input_path: Path, profile_id: str, project: Path) -> dict[str, Any]:
    started = utc_now()
    scan(input_path, project, ScanOptions(keep_raw_master=True))
    manifest = json_read(project / "project_manifest.json")
    profile = load_builtin_profile(profile_id)

    first_classification = classify_project(project, profile)
    first_summary = json_read(first_classification.summary)
    first_ids_hash = first_summary["determinism"]["matched_osm_ids_sha256"]
    first_counts = first_summary["counts"]

    preview, preview_perf = measured(project, lambda: load_preview(project, 2000))
    quality, quality_perf = measured(project, lambda: run_quality_checks(project, {"sample_size": 50, "auto_repair": False}))

    selection_path = project / "profiles" / "release_validation_selection.json"
    selection = {"schema_version": "1.0", "profile": profile_id, "categories": [], "format": "GPKG", "fields": list(profile.data.get("attributes", []))}
    selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    output = project / "thematic" / f"{name}.gpkg"
    first_export = export_selection(project, selection_path, output)
    first_audit = json_read(first_export.audit)

    second_classification = classify_project(project, profile)
    second_summary = json_read(second_classification.summary)
    second_export = export_selection(project, selection_path, output)
    second_audit = json_read(second_export.audit)

    reproducibility = {
        "classification_osm_id_set_equal": first_ids_hash == second_summary["determinism"]["matched_osm_ids_sha256"],
        "classification_counts_equal": first_counts == second_summary["counts"],
        "export_feature_count_equal": first_export.features_written == second_export.features_written,
        "export_layer_counts_equal": first_audit["counts"]["layers"] == second_audit["counts"]["layers"],
        "input_sha256_equal": manifest["input"]["sha256"] == second_summary["phase1_input_sha256"],
        "profile_sha256_equal": profile.sha256 == second_summary["profile"]["sha256"],
        "selection_sha256": sha256_file(selection_path),
        "classification_sqlite_integrity": integrity(project / "classification" / "classification.sqlite"),
        "output_gpkg_integrity": integrity(output),
        "byte_identical_output_required": False,
    }
    successful = all(value is True or value == "ok" or key in {"selection_sha256", "byte_identical_output_required"} for key, value in reproducibility.items())
    scan_perf = manifest["performance"]
    performance = {
        "import": {
            "wall_time_seconds": scan_perf["import_wall_time_seconds"],
            "peak_rss_bytes": scan_perf["import_peak_rss_bytes"],
            "working_disk_peak_bytes": scan_perf["import_temporary_disk_peak_bytes"],
        },
        "inventory_after_import": {
            "wall_time_seconds": round(scan_perf["wall_time_seconds"] - scan_perf["import_wall_time_seconds"], 6),
            "overall_peak_rss_bytes": scan_perf["overall_peak_rss_bytes"],
            "working_disk_peak_bytes": scan_perf["working_disk_peak_bytes"],
        },
        "classification": first_summary["performance"],
        "preview": preview_perf,
        "quality": quality_perf,
        "export": first_audit["performance"],
    }
    return {
        "status": "success" if successful else "failed",
        "started_at_utc": started,
        "finished_at_utc": utc_now(),
        "input": {"file": input_path.name, "sha256": manifest["input"]["sha256"], "bytes": input_path.stat().st_size},
        "profile": {"id": profile_id, "sha256": profile.sha256},
        "counts": {
            "scan": manifest["counts"],
            "classification": first_counts,
            "preview_loaded": preview["loaded"],
            "quality_sample": quality["scope"]["sample_size"],
            "export_features": first_export.features_written,
            "output_bytes": output.stat().st_size,
        },
        "quality": {
            "status": quality["status"],
            "sampling": quality["scope"]["sampling"],
            "strata": quality["scope"]["strata"],
            "missing_thematic_fields": quality["missing_thematic_fields"]["summary"],
        },
        "performance": performance,
        "reproducibility": reproducibility,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasets", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / "FINAL_RELEASE_PERFORMANCE_AND_REPRODUCIBILITY.json"
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "software_version": __version__,
        "environment": inspect_environment(require_gdal=True),
        "cases": {},
        "status": "running",
    }
    if __version__ != "0.4.1":
        raise RuntimeError(f"Expected installed v0.4.1, found {__version__}")
    for name, (filename, profile_id) in CASES.items():
        input_path = args.datasets / filename
        project = args.output / name
        if project.exists():
            raise FileExistsError(f"Validation project already exists: {project}")
        report["cases"][name] = run_case(name, input_path, profile_id, project)
        # Make the last per-case checkpoint self-finalizing.  This avoids a
        # complete multi-hour run being left marked "running" if the launcher
        # disappears in the few milliseconds between the last checkpoint and
        # the final summary write.
        if set(report["cases"]) == set(CASES):
            report["status"] = "success" if all(case["status"] == "success" for case in report["cases"].values()) else "failed"
            report["finished_at_utc"] = utc_now()
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"case": name, "status": report["cases"][name]["status"], "finished_at_utc": utc_now()}), flush=True)
    report["status"] = "success" if all(case["status"] == "success" for case in report["cases"].values()) else "failed"
    report["finished_at_utc"] = utc_now()
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
