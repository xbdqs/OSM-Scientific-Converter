from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
import traceback
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib.resources import as_file, files
from pathlib import Path
from typing import Callable

from osm_scientific_converter import __version__

from .environment import inspect_environment
from .feedback import build_feedback_bundle
from .hashing import sha256_file
from .input_inspector import inspect_input
from .models import ScanResult
from .raw_importer import import_osm
from .reports import write_json, write_lifecycle_inventory, write_summary, write_tag_inventory
from .resource_monitor import ResourceMonitor
from .tag_scanner import scan_geopackage


@dataclass(frozen=True)
class ScanOptions:
    keep_raw_master: bool = False
    temp_dir: Path | None = None
    temp_mb: int = 100
    overwrite: bool = False
    inventory_chunk_unique_limit: int = 50_000


class ScanExecutionError(RuntimeError):
    def __init__(self, message: str, diagnostic_dir: Path | None = None, feedback_bundle: Path | None = None):
        super().__init__(message)
        self.diagnostic_dir = diagnostic_dir
        self.feedback_bundle = feedback_bundle


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file()) if path.exists() else 0


def _commit(staging: Path, destination: Path, overwrite: bool) -> None:
    if not destination.exists():
        os.replace(staging, destination)
        return
    if not overwrite:
        raise FileExistsError(f"Project directory already exists: {destination}")
    backup = destination.with_name(f".{destination.name}.backup-{uuid.uuid4().hex}")
    os.replace(destination, backup)
    try:
        os.replace(staging, destination)
    except Exception:
        os.replace(backup, destination)
        raise
    # The new project is already committed. A backup-cleanup failure must not
    # turn a successful scan into a reported failure.
    shutil.rmtree(backup, ignore_errors=True)


def scan(
    input_path: str | Path,
    project_dir: str | Path,
    options: ScanOptions | None = None,
    progress: Callable[[str], None] | None = None,
) -> ScanResult:
    options = options or ScanOptions()
    if options.temp_mb < 1:
        raise ValueError("temp_mb must be at least 1")
    if options.inventory_chunk_unique_limit < 1:
        raise ValueError("inventory_chunk_unique_limit must be at least 1")
    destination = Path(project_dir).expanduser().resolve()
    if destination.exists() and not options.overwrite:
        raise FileExistsError(f"Project directory already exists (use --overwrite to replace it): {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.with_name(f".{destination.name}.partial-{uuid.uuid4().hex}")
    staging.mkdir(parents=True)
    (staging / "logs").mkdir()
    (staging / "data").mkdir()

    logger = logging.getLogger(f"osm_sci.scan.{uuid.uuid4().hex}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    handler = logging.FileHandler(staging / "logs" / "scan.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", datefmt="%Y-%m-%dT%H:%M:%S")
    formatter.converter = time.gmtime
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    handler_closed = False

    def close_handler() -> None:
        nonlocal handler_closed
        if not handler_closed:
            handler.flush()
            logger.removeHandler(handler)
            handler.close()
            handler_closed = True

    def announce(message: str) -> None:
        logger.info(message)
        if progress:
            progress(message)

    started_at = _utc_now()
    started_clock = time.perf_counter()
    metadata_dict: dict = {}
    raw_inventory: dict = {}
    feedback: Path | None = None
    temp_context = None
    work_temp: Path | None = None
    resource_monitor: ResourceMonitor | None = None
    try:
        announce("[1/6] Validating input and computing SHA-256")
        metadata = inspect_input(input_path)
        metadata_dict = metadata.to_dict()
        write_json(staging / "input_metadata.json", metadata_dict)

        announce("[2/6] Inspecting Python, SQLite, and GDAL environment")
        environment = inspect_environment(require_gdal=True)
        write_json(staging / "environment.json", environment)
        ogr2ogr = environment["gdal"]["ogr2ogr"]
        metadata_dict["gdal_version"] = environment["gdal"]["version"]
        write_json(staging / "input_metadata.json", metadata_dict)

        if options.temp_dir:
            work_temp = Path(options.temp_dir).expanduser().resolve() / f"osm-sci-{uuid.uuid4().hex}"
            work_temp.mkdir(parents=True, exist_ok=False)
        else:
            temp_context = tempfile.TemporaryDirectory(prefix="osm-sci-")
            work_temp = Path(temp_context.name)

        resource_monitor = ResourceMonitor([staging, work_temp])
        resource_monitor.start()

        announce("[3/6] Reconstructing five GDAL OSM layers into GeoPackage")
        raw_master = staging / "data" / "raw_master.gpkg"
        resource = files("osm_scientific_converter").joinpath("resources/osmconf.ini")
        with as_file(resource) as config_path:
            import_metrics, import_warnings = import_osm(
                Path(metadata.path), raw_master, ogr2ogr, Path(config_path), work_temp, options.temp_mb, announce,
                environment["gdal"].get("data_path"),
            )

        announce("[4/6] Streaming tag and lifecycle inventories with disk-backed aggregation")
        inventory_db = staging / "data" / "inventory.sqlite"
        raw_inventory, lifecycle_count, warnings = scan_geopackage(
            raw_master,
            inventory_db,
            announce,
            chunk_unique_limit=options.inventory_chunk_unique_limit,
        )
        warnings = import_warnings + warnings
        raw_inventory["raw_master"] = {
            "path": "data/raw_master.gpkg",
            "size_bytes": raw_master.stat().st_size,
            "sha256": sha256_file(raw_master),
            "retained": options.keep_raw_master,
        }
        raw_inventory["inventory_database"] = {
            "path": "data/inventory.sqlite",
            "size_bytes": inventory_db.stat().st_size,
            "sha256": sha256_file(inventory_db),
            "retained": True,
        }
        write_json(staging / "raw_inventory.json", raw_inventory)
        write_tag_inventory(staging, inventory_db)
        write_lifecycle_inventory(staging, inventory_db)

        announce("[5/6] Writing deterministic reports and project manifest")
        elapsed = time.perf_counter() - started_clock
        write_summary(staging, metadata_dict, raw_inventory, lifecycle_count, warnings, elapsed)
        manifest = {
            "schema_version": "1.0",
            "software": {"name": "osm-scientific-converter", "version": __version__},
            "status": "success",
            "started_at_utc": started_at,
            "finished_at_utc": _utc_now(),
            "input": metadata_dict,
            "options": {
                "keep_raw_master": options.keep_raw_master,
                "temp_dir": str(options.temp_dir.resolve()) if options.temp_dir else None,
                "temp_mb": options.temp_mb,
                "inventory_chunk_unique_limit": options.inventory_chunk_unique_limit,
            },
            "environment_file": "environment.json",
            "counts": {
                "features": raw_inventory["total_features"],
                "tag_assignments": raw_inventory["total_tag_assignments"],
                "unique_keys": raw_inventory["unique_keys"],
                "unique_key_values": raw_inventory["unique_key_values"],
                "lifecycle_inventory_rows": lifecycle_count,
            },
            "warnings": warnings,
            "errors": [],
            "performance": {
                "wall_time_seconds": round(elapsed, 6),
                **_merge_performance_metrics(
                    import_metrics,
                    resource_monitor.metrics() if resource_monitor else {},
                ),
                "temporary_bytes_after_scan": _directory_size(work_temp),
            },
            "outputs": [
                "project_manifest.json", "environment.json", "input_metadata.json", "raw_inventory.json",
                "tag_inventory.csv", "tag_inventory.json", "lifecycle_inventory.csv", "scan_summary.md", "logs/scan.log",
                "data/inventory.sqlite",
            ] + (["data/raw_master.gpkg"] if options.keep_raw_master else []),
        }
        if not options.keep_raw_master:
            raw_master.unlink()
        write_json(staging / "project_manifest.json", manifest)

        if resource_monitor:
            resource_monitor.stop()
        announce("[6/6] Building privacy-minimized feedback bundle")
        close_handler()
        feedback = build_feedback_bundle(staging)
        _commit(staging, destination, options.overwrite)
        final_feedback = destination / feedback.relative_to(staging)
        return ScanResult(destination, final_feedback, metadata_dict, raw_inventory)
    except Exception as error:
        logger.exception("Scan failed")
        try:
            environment_path = staging / "environment.json"
            if not environment_path.exists():
                write_json(environment_path, inspect_environment(require_gdal=False))
            (staging / "logs" / "traceback.txt").write_text(traceback.format_exc(), encoding="utf-8")
            write_json(staging / "project_manifest.json", {
                "schema_version": "1.0",
                "software": {"name": "osm-scientific-converter", "version": __version__},
                "status": "failed",
                "started_at_utc": started_at,
                "finished_at_utc": _utc_now(),
                "input": metadata_dict,
                "errors": [{"type": type(error).__name__, "message": str(error)}],
            })
            close_handler()
            feedback = build_feedback_bundle(staging)
            if not destination.exists():
                os.replace(staging, destination)
                diagnostic = destination
                feedback = destination / feedback.relative_to(staging)
            else:
                diagnostic = destination.with_name(f"{destination.name}.failed-{datetime.now().strftime('%Y%m%d_%H%M%S')}")
                os.replace(staging, diagnostic)
                feedback = diagnostic / feedback.relative_to(staging)
        except Exception:
            diagnostic = staging if staging.exists() else None
        raise ScanExecutionError(str(error), diagnostic, feedback) from error
    finally:
        if resource_monitor:
            resource_monitor.stop()
        close_handler()
        if temp_context:
            temp_context.cleanup()
        elif work_temp and work_temp.exists():
            shutil.rmtree(work_temp, ignore_errors=True)
def _merge_performance_metrics(
    import_metrics: dict[str, int | float | None],
    monitor_metrics: dict[str, int],
) -> dict[str, int | float | None]:
    """Merge sampled metrics while preserving the meaning of an overall peak."""
    metrics: dict[str, int | float | None] = {**import_metrics, **monitor_metrics}
    import_peak = metrics.get("import_peak_rss_bytes")
    overall_peak = metrics.get("overall_peak_rss_bytes")
    if isinstance(import_peak, int):
        metrics["overall_peak_rss_bytes"] = max(
            overall_peak if isinstance(overall_peak, int) else 0,
            import_peak,
        )
    return metrics

