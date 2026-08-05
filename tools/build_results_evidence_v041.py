from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def seconds(value: Any) -> str:
    return f"{float(value):.3f}"


def mb(value: Any) -> str:
    return f"{int(value or 0) / (1024 * 1024):.1f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build manuscript-facing v0.4.1 results from machine evidence")
    parser.add_argument("--performance", type=Path, required=True)
    parser.add_argument("--references", type=Path, required=True)
    parser.add_argument("--comparison", type=Path, required=True)
    parser.add_argument("--gui", type=Path, required=True)
    parser.add_argument("--tests", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    performance = load(args.performance)
    references = load(args.references)
    comparison = load(args.comparison)
    gui = load(args.gui)
    tests = load(args.tests)
    lines = [
        "# v0.4.1 machine-evidence results",
        "",
        "> Generated from the final local evidence files. Reference-set metrics remain provisional until independent human/domain review. QuickOSM and a same-snapshot prepared Shapefile were not available and are not simulated.",
        "",
        "## Artifact and test identity",
        "",
        f"- Software version: `{tests['software_version']}`",
        f"- Tested wheel SHA-256: `{tests['wheel']['sha256']}`",
        f"- Strict test runs: {len(tests['runs'])}; each run passed {next(iter(tests['runs'].values()))['passed']} tests with warnings treated as errors.",
        "",
        "## Four-region performance",
        "",
        "| Case | Input MiB | Scanned objects | Matched objects | Import s | Inventory s | Classification s | Preview s | Quality s | Export s | Peak RSS MiB | Output MiB |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for case, record in performance["cases"].items():
        perf = record["performance"]
        peak = max(int(stage.get("overall_peak_rss_bytes") or stage.get("peak_rss_bytes") or 0) for stage in perf.values())
        lines.append(
            "| " + " | ".join(
                (
                    case,
                    mb(record["input"]["bytes"]),
                    str(record["counts"]["scan"]["features"]),
                    str(record["counts"]["classification"]["matched_objects"]),
                    seconds(perf["import"]["wall_time_seconds"]),
                    seconds(perf["inventory_after_import"]["wall_time_seconds"]),
                    seconds(perf["classification"]["wall_time_seconds"]),
                    seconds(perf["preview"]["wall_time_seconds"]),
                    seconds(perf["quality"]["wall_time_seconds"]),
                    seconds(perf["export"]["wall_time_seconds"]),
                    mb(peak),
                    mb(record["counts"]["output_bytes"]),
                )
            ) + " |"
        )
    lines.extend([
        "",
        "All four cases require equal repeated classification counts and OSM ID sets, equal repeated export feature/layer counts, equal input/profile hashes, and `ok` SQLite/GPKG integrity. Byte-identical database files are not required.",
        "",
        "## Provisional tag-semantic reference sets",
        "",
        "| Topic | Positive | Negative | Geometry coverage | Regions | Lifecycle cases | Precision | Recall | F1 | Coverage check |",
        "|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ])
    for topic, record in references["topics"].items():
        lines.append(
            f"| {topic} | {record['counts']['positive']} | {record['counts']['negative']} | "
            f"{', '.join(record['coverage']['geometry_groups'])} | {len(record['coverage']['regions'])} | "
            f"{record['coverage']['lifecycle_cases']} | {record['metrics']['precision']:.6f} | "
            f"{record['metrics']['recall']:.6f} | {record['metrics']['f1']:.6f} | {record['coverage_status']} |"
        )
    lines.extend([
        "",
        f"Reference review status: `{references['status']}`. These metrics measure agreement with explicit OSM tag-semantic adjudication, not physical asset ground truth, and are not publication-ready accuracy claims before independent review.",
        "",
        "## Partial tool comparison",
        "",
        f"- GDAL default target OSM ID recall: {comparison['target_osm_id_recall']['recalled_by_gdal_default']}/{comparison['target_osm_id_recall']['target']} ({comparison['target_osm_id_recall']['rate']:.6f}).",
        f"- Exact tag key/value retention: {comparison['tag_retention']['exact_key_value_assignments_retained']}/{comparison['tag_retention']['comparable_original_assignments']} ({comparison['tag_retention']['rate']:.6f}).",
        f"- Target relations recalled: {comparison['relation_reconstruction']['recalled_by_gdal_default']}/{comparison['relation_reconstruction']['target_relations']}.",
        f"- Lifecycle objects with still-detectable lifecycle tags: {comparison['lifecycle_discovery']['lifecycle_tags_still_detectable']}/{comparison['lifecycle_discovery']['target_lifecycle_objects']}.",
        f"- QuickOSM: `{comparison['comparators']['quickosm']['status']}` — {comparison['comparators']['quickosm']['reason']}.",
        f"- Prepared Shapefile: `{comparison['comparators']['prepared_shapefile']['status']}` — {comparison['comparators']['prepared_shapefile']['reason']}.",
        "",
        "## Packaged GUI acceptance",
        "",
    ])
    for case, record in gui["cases"].items():
        lines.append(
            f"- `{case}`: {record['status']}; {len(record['checks'])} checks; {len(record['screenshots'])} screenshots; wall time {record['wall_time_seconds']:.3f} s."
        )
    lines.extend([
        "",
        "Acceptance was programmatic through real packaged GUI widgets and captured windows; it is not described as manual mouse testing.",
        "",
        "## Submission decision",
        "",
        "The local v0.4.1 software candidate may be frozen and hashed when all machine checks pass. Manuscript submission remains blocked by independent reference review, the complete QuickOSM/prepared-Shapefile comparison, verified authorship/affiliation/contact and competing-interest metadata, a public repository/release, Zenodo DOI, and software/data availability URLs.",
        "",
    ])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "success", "output": str(args.output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
