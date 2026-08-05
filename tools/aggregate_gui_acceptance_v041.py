from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


CASES = ("berlin_power", "south_korea_aeroway", "new_york_pipeline")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate packaged-EXE GUI acceptance evidence")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cases: dict[str, Any] = {}
    all_passed = True
    for case in CASES:
        report_path = args.root / case / "report.json"
        execution_path = args.root / case / "process_execution.json"
        report = load(report_path)
        execution = load(execution_path)
        screenshots = []
        for item in report.get("screenshots", []):
            path = Path(item)
            screenshots.append(path if path.is_absolute() else report_path.parent / "screenshots" / path)
        screenshot_records = [
            {"file": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in screenshots
            if path.is_file()
        ]
        checks = report.get("checks", [])
        passed = (
            report.get("status") == "success"
            and report.get("case") == case
            and report.get("software_version") == "0.4.1"
            and report.get("packaged_exe") is True
            and report.get("clean_environment") is True
            and execution.get("status") == "success"
            and execution.get("returncode") == 0
            and execution.get("executable_sha256") == sha256(args.exe)
            and bool(execution.get("environment_policy", {}).get("qt_font_directory"))
            and len(screenshot_records) == 4
            and all(item["bytes"] > 10_000 for item in screenshot_records)
            and checks
            and all(item.get("passed") is True for item in checks)
        )
        all_passed = all_passed and bool(passed)
        cases[case] = {
            "status": "success" if passed else "failed",
            "report": str(report_path),
            "report_sha256": sha256(report_path),
            "process_execution": str(execution_path),
            "process_execution_sha256": sha256(execution_path),
            "wall_time_seconds": execution.get("wall_time_seconds"),
            "automation_disclosure": report.get("automation_disclosure"),
            "checks": checks,
            "classification": {
                "matched_objects": report.get("classification", {}).get("counts", {}).get("matched_objects"),
                "profile": report.get("classification", {}).get("profile"),
            },
            "preview": report.get("preview"),
            "exports": report.get("exports"),
            "screenshots": screenshot_records,
        }

    aggregate = {
        "schema_version": "1.0",
        "software_version": "0.4.1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "executable": {"file": str(args.exe), "bytes": args.exe.stat().st_size, "sha256": sha256(args.exe)},
        "method": "Programmatic acceptance through real packaged GUI widgets with captured window screenshots; not a manual mouse-session claim.",
        "cases": cases,
        "status": "success" if all_passed else "failed",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": aggregate["status"], "cases": list(cases)}))
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
