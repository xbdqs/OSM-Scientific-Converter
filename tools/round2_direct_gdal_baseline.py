"""Single-pass direct GDAL/OGR *minimal-output* road extraction benchmark.

IMPORTANT: This does NOT provide the converter's full inventory, category,
provenance or quality-audit outputs. Its wall clock time is not evidence of
workflow equivalence. Intended to isolate direct GDAL cost and verify object
selection on the same snapshot, not to prove one method superior.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024*1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def load_highway_values(path: Path) -> list[str]:
    """Fail closed unless the supplied profile is an exact lines/highway equality whitelist."""
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    values = []
    for rule in data.get("rules", []):
        if rule.get("source_layer") != ["lines"]:
            raise ValueError("All baseline rules must be restricted to exact source_layer=['lines']")
        expr = rule.get("expression", {})
        if expr.get("key") != "highway":
            raise ValueError("Baseline only supports highway key")
        op = expr.get("op")
        if op == "in" and isinstance(expr.get("value"), list):
            values.extend(expr["value"])
        elif op == "equals" and isinstance(expr.get("value"), str):
            values.append(expr["value"])
        else:
            raise ValueError("Rule uses unsupported operator for strictly equivalent key/value predicate")
    if not values or any(not isinstance(v, str) or not v or "'" in v for v in values):
        raise ValueError("Invalid or empty highway vocabulary")
    duplicates = [v for v,n in Counter(values).items() if n>1]
    if duplicates:
        raise ValueError(f"Overlapping category values require explicit disambiguation: {duplicates}")
    return sorted(set(values))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--rules", required=True, type=Path)
    ap.add_argument("--base-config", required=True, type=Path)
    ap.add_argument("--output", required=True, type=Path)
    ap.add_argument("--report", required=True, type=Path)
    ap.add_argument("--ogr2ogr", default="ogr2ogr")
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()

    if not args.input.is_file() or not args.rules.is_file() or not args.base_config.is_file():
        ap.error("input, rules and base-config must be existing files")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and not args.overwrite:
        ap.error("output already exists; pass --overwrite to allow replacement")

    values = load_highway_values(args.rules)
    config = args.base_config.read_text(encoding="utf-8-sig")
    if "[lines]" not in config:
        raise ValueError("Source osmconf.ini has no [lines] section")
    if "attributes=" in config.split("[lines]",1)[1].split("[",1)[0]:
        raise ValueError("Base config already declares lines attributes; review before benchmarking")
    config = config.replace("[lines]", "[lines]\nattributes=highway,name,ref,maxspeed,oneway", 1)

    predicate = ",".join("'"+v+"'" for v in values)
    sql = ("SELECT osm_id,highway,name,ref,maxspeed,oneway "
           "FROM lines WHERE highway IN ("+predicate+")")
    start = time.perf_counter()
    when = datetime.now(timezone.utc).isoformat()
    result = None
    with tempfile.TemporaryDirectory(prefix="osm_round2_gdal_") as tmp:
        ini = Path(tmp)/"baseline_osmconf.ini"
        ini.write_text(config, encoding="utf-8")
        staging = Path(tmp)/"gdal_direct_baseline.gpkg"
        command = [args.ogr2ogr, "-f", "GPKG", str(staging), str(args.input),
                   "-oo", f"CONFIG_FILE={ini}", "-oo", "TAGS_FORMAT=JSON",
                   "--config", "OGR2OGR_USE_ARROW_API", "NO",
                   "-sql", sql, "-dialect", "OGRSQL", "-nln", "highway_lines",
                   "-lco", "GEOMETRY_NAME=geom"]
        # Unredirected stderr on failure is also captured in the report.
        proc = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, errors="replace")
        duration = round(time.perf_counter()-start, 3)
        if proc.returncode == 0 and staging.is_file():
            if args.output.exists():
                args.output.unlink()
            shutil.copy2(staging, args.output)
        result = {
            "mode": "direct_gdal_minimal_selection_baseline",
            "equivalent_to_converter_full_workflow": False,
            "limits": ["No complete tag vocabulary inventory",
                       "No versioned profile/audit output",
                       "No per-rule provenance or validated category mapping",
                       "Does not prove feature equivalence without OSM ID/geometry comparison"],
            "timestamp_utc": when,
            "input_file": args.input.name,
            "input_sha256": sha256(args.input),
            "rules_sha256": sha256(args.rules),
            "config_sha256": sha256(args.base_config),
            "filtered_highway_values": values,
            "source_layer": "lines",
            "output_file": args.output.name,
            "wall_seconds_including_gdal_startup_and_copy": duration,
            "exit_code": proc.returncode,
            "gdal_stdout_tail": proc.stdout[-1500:],
            "gdal_stderr_tail": proc.stderr[-3000:],
            "note": "Benchmark only; do not interpret as equally audited software workflow."
        }
    args.report.write_text(json.dumps(result, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["exit_code"] == 0 else 1

if __name__ == "__main__":
    raise SystemExit(main())
