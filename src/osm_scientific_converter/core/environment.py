from __future__ import annotations

import importlib.util
import ctypes
import os
import platform
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class EnvironmentError(RuntimeError):
    pass


def _run(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout, check=False)


def _gdal_version(executable: str) -> str:
    for command in ([executable, "--version"], [executable, "--help-general"]):
        result = _run(command)
        text = (result.stdout + "\n" + result.stderr).strip()
        for line in text.splitlines():
            if "GDAL" in line.upper() and any(char.isdigit() for char in line):
                return line.strip()
    if platform.system() == "Windows":
        executable_dir = Path(executable).resolve().parent
        for library in sorted(executable_dir.glob("gdal*.dll")):
            try:
                handle = os.add_dll_directory(str(executable_dir))
                dll = ctypes.CDLL(str(library))
                function = dll.GDALVersionInfo
                function.argtypes = [ctypes.c_char_p]
                function.restype = ctypes.c_char_p
                value = function(b"--version")
                handle.close()
                if value:
                    return value.decode("utf-8", errors="replace")
            except (AttributeError, OSError):
                continue
    return "unknown"


def _gdal_data_path(executable: str | None) -> str | None:
    configured = os.environ.get("GDAL_DATA")
    if configured and Path(configured).is_dir():
        return str(Path(configured).resolve())
    if not executable:
        return None
    prefix = Path(executable).resolve().parent.parent
    for candidate in (prefix / "share" / "gdal", prefix / "share" / "GDAL_DATA"):
        if candidate.is_dir():
            return str(candidate)
    return None


def inspect_environment(require_gdal: bool = True) -> dict[str, Any]:
    ogr2ogr = shutil.which("ogr2ogr")
    ogrinfo = shutil.which("ogrinfo")
    formats_text = ""
    drivers = {"OSM": False, "GPKG": False}
    if ogr2ogr:
        result = _run([ogr2ogr, "--formats"])
        formats_text = result.stdout + "\n" + result.stderr
        drivers = {name: any(line.strip().startswith(name + " ") for line in formats_text.splitlines()) for name in drivers}
    problems = []
    if not ogr2ogr:
        problems.append("ogr2ogr was not found on PATH")
    for driver, available in drivers.items():
        if not available:
            problems.append(f"GDAL {driver} driver is unavailable")
    gdal_version = _gdal_version(ogr2ogr) if ogr2ogr else None
    reproducibility_warnings = []
    if gdal_version and any(marker in gdal_version.lower() for marker in ("dev", "dirty")):
        reproducibility_warnings.append(
            "GDAL reports a development or dirty build; rerun formal benchmarks with a stable release build."
        )
    info = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "python": {"version": platform.python_version(), "executable": sys.executable},
        "os": {"system": platform.system(), "release": platform.release(), "version": platform.version(), "machine": platform.machine()},
        "sqlite": {"version": sqlite3.sqlite_version},
        "gdal": {
            "ogr2ogr": str(Path(ogr2ogr).resolve()) if ogr2ogr else None,
            "ogrinfo": str(Path(ogrinfo).resolve()) if ogrinfo else None,
            "version": gdal_version,
            "data_path": _gdal_data_path(ogr2ogr),
            "python_bindings": importlib.util.find_spec("osgeo") is not None,
            "drivers": drivers,
        },
        "temporary_directory": os.environ.get("TEMP") or os.environ.get("TMP"),
        "problems": problems,
        "reproducibility_warnings": reproducibility_warnings,
    }
    if require_gdal and problems:
        raise EnvironmentError("; ".join(problems))
    return info
