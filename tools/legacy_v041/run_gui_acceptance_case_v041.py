from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one packaged-EXE GUI acceptance case in a clean process")
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--case", choices=("berlin_power", "south_korea_aeroway", "new_york_pipeline"), required=True)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()

    case_root = args.root / args.case
    case_root.mkdir(parents=True, exist_ok=True)
    report = case_root / "report.json"
    execution = case_root / "process_execution.json"
    command = [
        str(args.exe.resolve()),
        "--gui-acceptance-case",
        args.case,
        "--gui-acceptance-project",
        str(args.project.resolve()),
        "--gui-acceptance-output-dir",
        str((case_root / "outputs").resolve()),
        "--gui-acceptance-report",
        str(report.resolve()),
        "--gui-acceptance-screenshots",
        str((case_root / "screenshots").resolve()),
    ]
    system_root = Path(os.environ.get("SystemRoot", r"C:\Windows"))
    environment = os.environ.copy()
    environment["PATH"] = os.pathsep.join(
        (str(args.exe.resolve().parent), str(system_root / "System32"), str(system_root))
    )
    environment["QT_QPA_PLATFORM"] = "offscreen"
    environment["QT_QPA_FONTDIR"] = str(system_root / "Fonts")
    environment["OSM_SCI_CLEAN_ENV"] = "1"
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    started_at = utc_now()
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        check=False,
    )
    stdout_text = completed.stdout.decode("utf-8", errors="replace")
    stderr_ascii_summary = (
        f"{len(completed.stderr.splitlines())} captured diagnostic line(s); "
        "raw bytes are retained as Base64 and SHA-256. Shapefile loss details are in the export audit."
        if completed.stderr else ""
    )
    record = {
        "schema_version": "1.0",
        "case": args.case,
        "software_version": "0.4.1",
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "wall_time_seconds": round(time.perf_counter() - started, 6),
        "command": command,
        "executable_sha256": sha256(args.exe),
        "environment_policy": {
            "isolated_path": True,
            "pythonpath_removed": True,
            "pythonhome_removed": True,
            "qt_platform": "offscreen",
            "qt_font_directory": str(system_root / "Fonts"),
            "clean_environment_flag": True,
            "captured_output_policy": "stdout decoded as UTF-8; stderr preserved losslessly as Base64 plus SHA-256 because GDAL may emit locale-dependent bytes",
        },
        "returncode": completed.returncode,
        "stdout": stdout_text,
        "stderr_summary": stderr_ascii_summary,
        "stderr_bytes": len(completed.stderr),
        "stderr_sha256": hashlib.sha256(completed.stderr).hexdigest(),
        "stderr_base64": base64.b64encode(completed.stderr).decode("ascii"),
        "acceptance_report_exists": report.is_file(),
        "status": "success" if completed.returncode == 0 and report.is_file() else "failed",
    }
    execution.write_text(json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": record["status"], "case": args.case, "returncode": completed.returncode}))
    return 0 if record["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
