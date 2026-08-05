from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


EXPECTED_CASES = {
    "berlin_power",
    "south_korea_aeroway",
    "new_york_pipeline",
    "quebec_power",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Strictly finalize a completed v0.4.1 performance checkpoint."
    )
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    report = json.loads(args.report.read_text(encoding="utf-8-sig"))
    if report.get("software_version") != "0.4.1":
        raise RuntimeError("Performance report is not for v0.4.1")
    cases = report.get("cases", {})
    if set(cases) != EXPECTED_CASES:
        raise RuntimeError(f"Incomplete case set: {sorted(cases)}")
    for name, case in cases.items():
        if case.get("status") != "success" or not case.get("finished_at_utc"):
            raise RuntimeError(f"Incomplete case: {name}")
        reproducibility = case.get("reproducibility", {})
        required_true = (
            "input_sha256_equal",
            "profile_sha256_equal",
            "classification_counts_equal",
            "classification_osm_id_set_equal",
            "export_feature_count_equal",
            "export_layer_counts_equal",
        )
        if not all(reproducibility.get(key) is True for key in required_true):
            raise RuntimeError(f"Reproducibility failure: {name}")
        if reproducibility.get("classification_sqlite_integrity") != "ok":
            raise RuntimeError(f"SQLite integrity failure: {name}")
        if reproducibility.get("output_gpkg_integrity") != "ok":
            raise RuntimeError(f"GeoPackage integrity failure: {name}")
    report["status"] = "success"
    report["finished_at_utc"] = max(case["finished_at_utc"] for case in cases.values())
    report["checkpoint_finalization"] = {
        "method": "strict recovery from four complete per-case checkpoints",
        "validated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "required_cases": sorted(EXPECTED_CASES),
        "all_case_statuses_success": True,
        "all_reproducibility_checks_passed": True,
        "all_database_integrity_checks_passed": True,
    }
    args.report.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"status": "success", "report": str(args.report)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
