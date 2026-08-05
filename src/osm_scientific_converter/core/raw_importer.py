from __future__ import annotations

import os
import subprocess
import time
from collections import Counter
from pathlib import Path
from typing import Any, Callable


class ImportFailure(RuntimeError):
    pass


def _aggregate_warnings(text: str) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter(
        line.strip() for line in text.splitlines() if "warning" in line.lower() and line.strip()
    )
    return [{"message": message, "count": count} for message, count in sorted(counts.items())]


def import_osm(
    input_path: Path,
    output_path: Path,
    ogr2ogr: str,
    config_path: Path,
    temp_dir: Path,
    temp_mb: int,
    log: Callable[[str], None],
    gdal_data: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_name("." + output_path.stem + ".partial.gpkg")
    if partial.exists():
        partial.unlink()
    command = [
        ogr2ogr,
        "-f", "GPKG",
        str(partial),
        str(input_path),
        "-oo", f"CONFIG_FILE={config_path}",
        "-oo", "TAGS_FORMAT=JSON",
        "-oo", f"MAX_TMPFILE_SIZE={temp_mb}",
        "--config", "CPL_TMPDIR", str(temp_dir),
        "--config", "OGR2OGR_USE_ARROW_API", "NO",
        "-dsco", "VERSION=1.2",
    ]
    if gdal_data:
        command[command.index("-dsco"):command.index("-dsco")] = ["--config", "GDAL_DATA", gdal_data]
    log("Running GDAL import: " + subprocess.list2cmdline(command))
    stdout_path = temp_dir / "ogr2ogr.stdout.txt"
    stderr_path = temp_dir / "ogr2ogr.stderr.txt"
    peak_rss = None
    peak_temp = 0
    started = time.perf_counter()
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open("w", encoding="utf-8") as stderr:
        process = subprocess.Popen(command, stdout=stdout, stderr=stderr, text=True)
        try:
            import psutil
            monitored = psutil.Process(process.pid)
        except (ImportError, OSError):
            monitored = None
        while process.poll() is None:
            try:
                peak_temp = max(
                    peak_temp,
                    sum(item.stat().st_size for item in temp_dir.rglob("*") if item.is_file()),
                )
            except OSError:
                pass
            if monitored:
                try:
                    rss = monitored.memory_info().rss + sum(
                        child.memory_info().rss for child in monitored.children(recursive=True)
                    )
                    peak_rss = max(peak_rss or 0, rss)
                except Exception:
                    pass
            time.sleep(0.05)
        returncode = process.wait()
    stdout_text = stdout_path.read_text(encoding="utf-8", errors="replace").strip()
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace").strip()
    warnings = _aggregate_warnings(stderr_text)
    if stdout_text:
        log("ogr2ogr stdout: " + stdout_text)
    if stderr_text:
        if returncode != 0:
            log("ogr2ogr stderr: " + stderr_text)
        else:
            non_warning_lines = [
                line.strip() for line in stderr_text.splitlines()
                if line.strip() and "warning" not in line.lower()
            ]
            if non_warning_lines:
                log("ogr2ogr stderr: " + "\n".join(non_warning_lines))
            for warning in warnings:
                log(f"ogr2ogr warning: {warning['message']} (count={warning['count']})")
    if returncode != 0 or not partial.exists():
        partial.unlink(missing_ok=True)
        raise ImportFailure(f"ogr2ogr failed with exit code {returncode}: {stderr_text}")
    os.replace(partial, output_path)
    return {
        "import_wall_time_seconds": round(time.perf_counter() - started, 6),
        "import_peak_rss_bytes": peak_rss,
        "import_temporary_disk_peak_bytes": peak_temp,
    }, warnings
