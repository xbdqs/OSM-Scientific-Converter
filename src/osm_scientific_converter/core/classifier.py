from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from osm_scientific_converter import __version__

from .lifecycle import detect_lifecycle
from .path_privacy import portable_profile_source
from .phase2_feedback import build_phase2_feedback
from .profiles import ResolvedProfile
from .resource_monitor import ResourceMonitor
from .rules import condition_summary, evaluate_expression, rule_context_matches
from .tag_scanner import LAYER_SPECS, parse_tags


@dataclass(frozen=True)
class ClassificationResult:
    project_dir: Path
    database: Path
    summary: Path
    feedback_bundle: Path
    matched_objects: int
    total_matches: int


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _quote(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _database_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
        CREATE TABLE objects (
            object_pk INTEGER PRIMARY KEY,
            osm_id TEXT NOT NULL,
            osm_type TEXT NOT NULL,
            source_layer TEXT NOT NULL,
            source_fid INTEGER NOT NULL,
            geometry_group TEXT NOT NULL,
            tags_json TEXT NOT NULL,
            lifecycle TEXT NOT NULL,
            UNIQUE(source_layer, source_fid)
        );
        CREATE TABLE matches (
            match_pk INTEGER PRIMARY KEY,
            object_pk INTEGER NOT NULL REFERENCES objects(object_pk),
            profile_id TEXT NOT NULL,
            category TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            match_summary TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,
            profile_sha256 TEXT NOT NULL,
            UNIQUE(object_pk, profile_id, rule_id)
        );
        CREATE TABLE numeric_parse_failures (
            failure_pk INTEGER PRIMARY KEY,
            osm_id TEXT NOT NULL,
            source_layer TEXT NOT NULL,
            source_fid INTEGER NOT NULL,
            rule_id TEXT NOT NULL,
            tag_key TEXT NOT NULL,
            raw_value TEXT NOT NULL,
            token TEXT NOT NULL,
            reason TEXT NOT NULL
        );
        CREATE INDEX idx_objects_source ON objects(source_layer, source_fid);
        CREATE INDEX idx_objects_osm ON objects(osm_type, osm_id);
        CREATE INDEX idx_matches_profile_category ON matches(profile_id, category, object_pk);
        CREATE INDEX idx_matches_rule ON matches(rule_id, object_pk);
        """
    )


def _object_identity(layer: str, fid: int, osm_id: Any, osm_way_id: Any = None) -> tuple[str, str]:
    if layer == "multipolygons":
        if osm_id not in (None, ""):
            return f"relation/{osm_id}", "relation"
        if osm_way_id not in (None, ""):
            return f"way/{osm_way_id}", "way"
        return f"unknown/{fid}", "unknown"
    if layer == "points":
        return f"node/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}", "node"
    if layer == "lines":
        return f"way/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}", "way"
    return f"relation/{osm_id}" if osm_id not in (None, "") else f"unknown/{fid}", "relation"


def _matched_id_hash(connection: sqlite3.Connection) -> str:
    digest = hashlib.sha256()
    for (osm_id,) in connection.execute("SELECT DISTINCT osm_id FROM objects ORDER BY osm_id"):
        digest.update(str(osm_id).encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _write_reports(
    output: Path,
    connection: sqlite3.Connection,
    summary: Mapping[str, Any],
    layer_totals: Mapping[str, int],
    layer_matches: Mapping[str, int],
) -> None:
    _write_json(output / "classification_summary.json", summary)
    with (output / "matched_rules.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["profile_id", "category", "rule_id", "source_layer", "geometry_group", "match_count"])
        writer.writerows(connection.execute(
            """
            SELECT m.profile_id, m.category, m.rule_id, o.source_layer, o.geometry_group, COUNT(*)
            FROM matches m JOIN objects o ON o.object_pk = m.object_pk
            GROUP BY m.profile_id, m.category, m.rule_id, o.source_layer, o.geometry_group
            ORDER BY m.profile_id, m.category, m.rule_id, o.source_layer, o.geometry_group
            """
        ))
    with (output / "unmatched_summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["source_layer", "scanned_objects", "matched_objects", "unmatched_objects"])
        for layer in LAYER_SPECS:
            total = int(layer_totals.get(layer, 0))
            matched = int(layer_matches.get(layer, 0))
            writer.writerow([layer, total, matched, total - matched])


def _replace_directory(source: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.backup-{uuid.uuid4().hex}")
    had_destination = destination.exists()
    if had_destination:
        os.replace(destination, backup)
    try:
        os.replace(source, destination)
    except Exception:
        if had_destination and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup, ignore_errors=True)


def classify_project(
    project_dir: str | Path,
    resolved_profile: ResolvedProfile,
    *,
    progress: Callable[[str], None] | None = None,
) -> ClassificationResult:
    project = Path(project_dir).expanduser().resolve()
    manifest_path = project / "project_manifest.json"
    raw_master = project / "data" / "raw_master.gpkg"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Phase 1 project manifest is missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("status") != "success":
        raise ValueError("Phase 1 project status is not success")
    if not raw_master.is_file():
        raise FileNotFoundError(
            "Phase 2 classification requires data/raw_master.gpkg; rescan with --keep-raw-master "
            "or use the extract command"
        )

    staging_root = project / f".phase2-classify.partial-{uuid.uuid4().hex}"
    classification_dir = staging_root / "classification"
    profiles_dir = staging_root / "profiles"
    classification_dir.mkdir(parents=True)
    existing_profiles = project / "profiles"
    if existing_profiles.is_dir():
        shutil.copytree(existing_profiles, profiles_dir, dirs_exist_ok=True)
    else:
        profiles_dir.mkdir()

    log_handle = (classification_dir / "classification.log").open("w", encoding="utf-8", newline="\n")

    def announce(message: str) -> None:
        log_handle.write(message + "\n")
        log_handle.flush()
        if progress:
            progress(message)

    started_clock = time.perf_counter()
    started_utc = _utc_now()
    monitor = ResourceMonitor([staging_root])
    monitor.start()
    database = classification_dir / "classification.sqlite"
    scanned = 0
    matched_objects = 0
    total_matches = 0
    numeric_failures = 0
    category_counts: Counter[str] = Counter()
    rule_counts: Counter[str] = Counter()
    layer_totals: Counter[str] = Counter()
    layer_matches: Counter[str] = Counter()
    anomalies: Counter[str] = Counter()
    classified_at = _utc_now()

    try:
        announce(f"Resolving profile {resolved_profile.id} ({resolved_profile.sha256})")
        output_profile = {
            **resolved_profile.data,
            "profile_sha256": resolved_profile.sha256,
            "resolved_source": portable_profile_source(resolved_profile.source),
            "resolved_at_utc": classified_at,
            "software_version": __version__,
        }
        _write_json(profiles_dir / "resolved_profile.json", output_profile)

        source: sqlite3.Connection | None = None
        target: sqlite3.Connection | None = None
        try:
            source = sqlite3.connect(f"file:{raw_master.as_posix()}?mode=ro", uri=True)
            target = sqlite3.connect(database)
            _database_schema(target)
            metadata = {
                "schema_version": "1.0",
                "software_version": __version__,
                "profile_id": resolved_profile.id,
                "profile_sha256": resolved_profile.sha256,
                "phase1_project": ".",
                "phase1_input_sha256": str(manifest.get("input", {}).get("sha256", "")),
                "classified_at_utc": classified_at,
            }
            target.executemany("INSERT INTO metadata(key, value) VALUES (?, ?)", metadata.items())
            tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            for layer, (geometry_group, _) in LAYER_SPECS.items():
                if layer not in tables:
                    announce(f"Skipping absent layer {layer}")
                    continue
                columns = {row[1] for row in source.execute(f"PRAGMA table_info({_quote(layer)})")}
                if "fid" not in columns or "all_tags" not in columns:
                    raise ValueError(f"Raw layer {layer} lacks fid or all_tags")
                select_columns = ["fid", "osm_id"]
                if "osm_way_id" in columns:
                    select_columns.append("osm_way_id")
                select_columns.append("all_tags")
                query = f"SELECT {', '.join(_quote(value) for value in select_columns)} FROM {_quote(layer)} ORDER BY fid"
                layer_scanned = 0
                layer_matched = 0
                for row in source.execute(query):
                    record = dict(zip(select_columns, row))
                    fid = int(record["fid"])
                    sid, osm_type = _object_identity(layer, fid, record.get("osm_id"), record.get("osm_way_id"))
                    raw_tags = record.get("all_tags")
                    tags, anomaly = parse_tags(raw_tags)
                    if anomaly:
                        anomalies[anomaly] += 1
                    lifecycle_pairs = detect_lifecycle(tags)
                    lifecycle_states = sorted({state for state, _ in lifecycle_pairs})
                    context = {
                        "source_layer": layer,
                        "geometry_group": geometry_group,
                        "osm_type": osm_type,
                        "lifecycle": lifecycle_states,
                    }
                    matches: list[tuple[Mapping[str, Any], str]] = []
                    for rule in resolved_profile.data["rules"]:
                        if not rule_context_matches(rule, context):
                            continue
                        result = evaluate_expression(rule["expression"], tags, context)
                        for failure in result.numeric_failures:
                            target.execute(
                                """
                                INSERT INTO numeric_parse_failures
                                (osm_id, source_layer, source_fid, rule_id, tag_key, raw_value, token, reason)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                                """,
                                (sid, layer, fid, rule["id"], failure.key, failure.raw_value, failure.token, failure.reason),
                            )
                            numeric_failures += 1
                        if result.matched:
                            matches.append((rule, condition_summary(rule)))
                    scanned += 1
                    layer_scanned += 1
                    if matches:
                        tags_json = raw_tags.decode("utf-8", errors="replace") if isinstance(raw_tags, bytes) else str(raw_tags or "")
                        cursor = target.execute(
                            """
                            INSERT INTO objects
                            (osm_id, osm_type, source_layer, source_fid, geometry_group, tags_json, lifecycle)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (sid, osm_type, layer, fid, geometry_group, tags_json, json.dumps(lifecycle_states, ensure_ascii=False)),
                        )
                        object_pk = int(cursor.lastrowid)
                        matched_objects += 1
                        layer_matched += 1
                        for rule, summary_text in matches:
                            target.execute(
                                """
                                INSERT INTO matches
                                (object_pk, profile_id, category, rule_id, match_summary, classified_at_utc, profile_sha256)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                """,
                                (
                                    object_pk,
                                    resolved_profile.id,
                                    rule["category"],
                                    rule["id"],
                                    summary_text,
                                    classified_at,
                                    resolved_profile.sha256,
                                ),
                            )
                            total_matches += 1
                            category_counts[str(rule["category"])] += 1
                            rule_counts[str(rule["id"])] += 1
                    if scanned % 5000 == 0:
                        target.commit()
                target.commit()
                layer_totals[layer] = layer_scanned
                layer_matches[layer] = layer_matched
                announce(f"Classified {layer_scanned} objects from {layer}; matched {layer_matched}")

            integrity = target.execute("PRAGMA integrity_check").fetchone()[0]
            matched_hash = _matched_id_hash(target)
            monitor.stop()
            elapsed = time.perf_counter() - started_clock
            summary = {
                "schema_version": "1.0",
                "software": {"name": "osm-scientific-converter", "version": __version__},
                "status": "success",
                "started_at_utc": started_utc,
                "finished_at_utc": _utc_now(),
                "phase1_project": ".",
                "phase1_input_sha256": manifest.get("input", {}).get("sha256"),
                "profile": {
                    "id": resolved_profile.id,
                    "sha256": resolved_profile.sha256,
                    "source": portable_profile_source(resolved_profile.source),
                },
                "counts": {
                    "scanned_objects": scanned,
                    "matched_objects": matched_objects,
                    "total_rule_matches": total_matches,
                    "numeric_parse_failures": numeric_failures,
                    "categories": dict(sorted(category_counts.items())),
                    "rules": dict(sorted(rule_counts.items())),
                    "layers": {
                        layer: {"scanned": int(layer_totals[layer]), "matched": int(layer_matches[layer])}
                        for layer in LAYER_SPECS
                    },
                    "tag_parse_anomalies": dict(sorted(anomalies.items())),
                },
                "determinism": {"matched_osm_ids_sha256": matched_hash},
                "database": {"path": "classification/classification.sqlite", "integrity_check": integrity},
                "performance": {
                    "wall_time_seconds": round(elapsed, 6),
                    **monitor.metrics(),
                },
            }
            _write_reports(classification_dir, target, summary, layer_totals, layer_matches)
        finally:
            if source is not None:
                source.close()
            if target is not None:
                target.close()
            monitor.stop()
            log_handle.close()

        _replace_directory(classification_dir, project / "classification")
        _replace_directory(profiles_dir, project / "profiles")
        if staging_root.exists():
            shutil.rmtree(staging_root, ignore_errors=True)
        feedback = build_phase2_feedback(project)
        return ClassificationResult(
            project,
            project / "classification" / "classification.sqlite",
            project / "classification" / "classification_summary.json",
            feedback,
            matched_objects,
            total_matches,
        )
    except Exception:
        monitor.stop()
        if not log_handle.closed:
            log_handle.close()
        shutil.rmtree(staging_root, ignore_errors=True)
        raise
