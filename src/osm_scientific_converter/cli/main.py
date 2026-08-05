from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from osm_scientific_converter import __version__
from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.exporter import export_selection
from osm_scientific_converter.core.profiles import (
    inspect_builtin_profile,
    list_builtin_profiles,
    resolve_profile,
)
from osm_scientific_converter.core.scanner import ScanExecutionError, ScanOptions, scan


def _add_profile_source(parser: argparse.ArgumentParser) -> None:
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--profile", help="built-in profile id")
    source.add_argument("--rules", type=Path, help="custom JSON profile or rule")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="osm-sci",
        description="Scan, classify, and export auditable OSM scientific datasets",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)

    scan_parser = commands.add_parser("scan", help="scan one .osm/.pbf input")
    scan_parser.add_argument("input", type=Path)
    scan_parser.add_argument("--project", type=Path, required=True, help="new output project directory")
    scan_parser.add_argument("--keep-raw-master", action="store_true", help="retain data/raw_master.gpkg")
    scan_parser.add_argument("--temp-dir", type=Path, help="parent directory for GDAL temporary files")
    scan_parser.add_argument("--temp-mb", type=int, default=100, help="GDAL in-memory temporary threshold in MB")
    scan_parser.add_argument("--overwrite", action="store_true", help="atomically replace an existing project")
    scan_parser.add_argument(
        "--inventory-chunk-unique-limit",
        type=int,
        default=50000,
        help="maximum in-memory unique aggregate rows before SQLite flush",
    )

    profile_parser = commands.add_parser("profile", help="list or inspect built-in profiles")
    profile_actions = profile_parser.add_subparsers(dest="profile_action", required=True)
    profile_actions.add_parser("list", help="list built-in profiles")
    inspect_parser = profile_actions.add_parser("inspect", help="show a resolved built-in profile")
    inspect_parser.add_argument("profile_name")

    classify_parser = commands.add_parser("classify", help="classify one retained Phase 1 project")
    classify_parser.add_argument("project", type=Path)
    _add_profile_source(classify_parser)

    export_parser = commands.add_parser("export", help="export a classification selection")
    export_parser.add_argument("project", type=Path)
    export_parser.add_argument("--selection", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)

    extract_parser = commands.add_parser("extract", help="run scan, classify, and export as explicit stages")
    extract_parser.add_argument("input", type=Path)
    _add_profile_source(extract_parser)
    extract_parser.add_argument("--output", type=Path, required=True)
    extract_parser.add_argument("--project", type=Path, help="intermediate auditable project directory")
    extract_parser.add_argument("--format", choices=["GPKG", "GeoJSON", "Shapefile"])
    extract_parser.add_argument("--temp-dir", type=Path)
    extract_parser.add_argument("--temp-mb", type=int, default=100)
    extract_parser.add_argument("--overwrite", action="store_true")
    extract_parser.add_argument("--inventory-chunk-unique-limit", type=int, default=50000)
    return parser


def _run_scan(args: argparse.Namespace) -> int:
    result = scan(
        args.input,
        args.project,
        ScanOptions(
            args.keep_raw_master,
            args.temp_dir,
            args.temp_mb,
            args.overwrite,
            args.inventory_chunk_unique_limit,
        ),
        progress=lambda message: print(message, flush=True),
    )
    print(f"Scan completed: {result.project_dir}")
    print(f"Upload this feedback bundle: {result.feedback_bundle}")
    return 0


def _run_classify(args: argparse.Namespace) -> int:
    resolved = resolve_profile(profile=args.profile, rules=args.rules)
    result = classify_project(args.project, resolved, progress=lambda message: print(message, flush=True))
    print(f"Classification completed: {result.database}")
    print(f"Matched objects: {result.matched_objects}; rule matches: {result.total_matches}")
    print(f"Upload this feedback bundle: {result.feedback_bundle}")
    return 0


def _run_export(args: argparse.Namespace) -> int:
    result = export_selection(
        args.project,
        args.selection,
        args.output,
        progress=lambda message: print(message, flush=True),
    )
    print(f"Export completed: {result.output}")
    print(f"Features written: {result.features_written}")
    print(f"Export audit: {result.audit}")
    print(f"Upload this feedback bundle: {result.feedback_bundle}")
    return 0


def _run_extract(args: argparse.Namespace) -> int:
    output = args.output.expanduser().resolve()
    project = (
        args.project.expanduser().resolve()
        if args.project
        else output.parent / f"{output.stem}_project_v041"
    )
    print("[stage 1/3] scan", flush=True)
    scan_result = scan(
        args.input,
        project,
        ScanOptions(True, args.temp_dir, args.temp_mb, args.overwrite, args.inventory_chunk_unique_limit),
        progress=lambda message: print(message, flush=True),
    )
    print("[stage 2/3] classify", flush=True)
    resolved = resolve_profile(profile=args.profile, rules=args.rules)
    classify_project(project, resolved, progress=lambda message: print(message, flush=True))
    selection = {
        "schema_version": "1.0",
        "profile": resolved.id,
        "categories": [],
    }
    if args.format:
        selection["format"] = args.format
    selection_path = project / "profiles" / "extract_selection.json"
    selection_path.write_text(
        json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print("[stage 3/3] export", flush=True)
    export_result = export_selection(
        project,
        selection_path,
        output,
        progress=lambda message: print(message, flush=True),
    )
    print(f"Extract completed: {export_result.output}")
    print(f"Auditable project: {scan_result.project_dir}")
    print(f"Upload this feedback bundle: {export_result.feedback_bundle}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "scan":
            return _run_scan(args)
        if args.command == "profile":
            if args.profile_action == "list":
                print(json.dumps(list_builtin_profiles(), ensure_ascii=False, indent=2, sort_keys=True))
            else:
                print(json.dumps(inspect_builtin_profile(args.profile_name), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "classify":
            return _run_classify(args)
        if args.command == "export":
            return _run_export(args)
        if args.command == "extract":
            return _run_extract(args)
    except KeyboardInterrupt:
        print("ERROR: operation cancelled", file=sys.stderr)
        return 130
    except ScanExecutionError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        if error.feedback_bundle:
            print(f"Diagnostic feedback bundle: {error.feedback_bundle}", file=sys.stderr)
        return 1
    except (ValueError, FileExistsError, FileNotFoundError, RuntimeError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
