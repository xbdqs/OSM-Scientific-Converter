"""Experimental, bounded *highway/lines* targeted extraction for round-two validation.

This workflow is a deliberately narrow alternative to the complete Phase 1 inventory:
- GDAL reconstructs OSM geometry from the local snapshot (not a zero-cost input pass).
- A GDAL SQL `highway IN (...)` predicate limits features written to an intermediate
  GPKG before the converter applies and archives reviewed semantic categories.
- The output is traceable, but this mode has NO full tag-vocabulary inventory or
  complete process-quality assessment. Never compare its timing to full audit
  as if the two workloads were identical.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osm_scientific_converter import __version__
from .profiles import ResolvedProfile

_ALLOWED_VALUE = re.compile(r"^[A-Za-z0-9_:-]{1,128}$")


def reviewed_highway_mapping(resolved: ResolvedProfile) -> tuple[list[str], dict[str, tuple[str, str]]]:
    """Fail closed for unsupported profiles or overlapping classification."""
    mapping: dict[str, tuple[str, str]] = {}
    rules = resolved.data.get("rules", [])
    if not rules:
        raise ValueError("Targeted mode requires reviewed highway rules")
    for rule in rules:
        if rule.get("source_layer") != ["lines"]:
            raise ValueError("Targeted highway mode requires every rule source_layer=['lines']")
        if set(rule) & {"lifecycle", "geometry", "osm_type"}:
            raise ValueError("Targeted mode cannot represent extra top-level rule constraints")
        expression = rule.get("expression", {})
        if expression.get("key") != "highway":
            raise ValueError("Targeted highway mode supports only highway key rules")
        op = expression.get("op")
        if op == "equals":
            values = [expression.get("value")]
        elif op == "in":
            values = expression.get("value")
        else:
            raise ValueError("Targeted highway mode currently supports only equals/in operators")
        if not isinstance(values, list) or not values:
            raise ValueError("Highway rule must contain at least one value")
        for value in values:
            if not isinstance(value, str) or not _ALLOWED_VALUE.fullmatch(value):
                raise ValueError(f"Unsupported highway value for targeted mode: {value!r}")
            if value in mapping:
                raise ValueError(f"Duplicate highway category assignment: {value}")
            mapping[value] = (str(rule["category"]), str(rule["id"]))
    return sorted(mapping), mapping


def _hash_file(source: Path) -> str:
    h = hashlib.sha256()
    with source.open("rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _gdal_osm_config(base_config: str) -> str:
    """Promote required predicates to GDAL OSM fields without changing the source."""
    if "[lines]" not in base_config:
        raise ValueError("OSM driver configuration lacks a [lines] section")
    before, after = base_config.split("[lines]", 1)
    section, sep, tail = after.partition("\n[")
    if re.search(r"^\s*attributes\s*=", section, re.M):
        raise ValueError("Base osmconf.ini already declares [lines] attributes; review manually")
    section = "\nattributes=highway,name,ref,maxspeed,oneway\n" + section.lstrip("\n")
    return before + "[lines]" + section + (("\n[" + tail) if sep else "")


def _gdal_sql(values: list[str]) -> str:
    # All whitelist literals were validated against _ALLOWED_VALUE above.
    literal_list = ",".join("'" + value + "'" for value in values)
    return (
        "SELECT osm_id, highway, name, ref, maxspeed, oneway, all_tags "
        f"FROM lines WHERE highway IN ({literal_list})"
    )


def _inject_provenance(conn: sqlite3.Connection, table: str, resolved: ResolvedProfile,
                       mapping: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Apply a reviewed 1-to-1 key/value category map, with fail-closed checks."""
    safe_table = '"' + table.replace('"','""') + '"'
    required = {"osm_id", "highway", "all_tags", "fid"}
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({safe_table})")}
    missing = required - columns
    if missing:
        raise RuntimeError(f"Direct GDAL extract lacks required columns: {sorted(missing)}")
    provenance_columns = [
        "canonical_osm_id", "osm_type", "source_layer", "category", "rule_ids",
        "profile_id", "profile_sha256", "tags_json",
    ]
    for field in provenance_columns:
        if field in columns:
            raise ValueError(f"Unexpected field collision in GDAL output: {field}")
        conn.execute(f'ALTER TABLE {safe_table} ADD COLUMN "{field}" TEXT')
    categories: Counter[str] = Counter()
    seen_ids: set[str] = set()
    for fid, osm_id, highway, tags in conn.execute(
        f"SELECT fid, osm_id, highway, all_tags FROM {safe_table} ORDER BY fid"
    ):
        key = str(highway or "")
        if key not in mapping:
            raise RuntimeError(f"GDAL output contains highway={key!r} outside the reviewed whitelist")
        if osm_id is None or not re.fullmatch(r"\d+", str(osm_id)):
            raise RuntimeError(f"Cannot establish numeric OSM way identity for {osm_id!r}")
        canonical_id = f"way/{osm_id}"
        if canonical_id in seen_ids:
            raise RuntimeError(f"Repeated canonical OSM way ID: {canonical_id}")
        seen_ids.add(canonical_id)
        if not isinstance(tags, str) or not tags:
            raise RuntimeError("Missing complete all_tags JSON in GDAL output")
        try:
            tag_data = json.loads(tags)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid all_tags JSON for {canonical_id}") from error
        if not isinstance(tag_data, dict) or str(tag_data.get("highway")) != key:
            raise RuntimeError(f"Highway tag mismatch for {canonical_id}")
        category, rule_id = mapping[key]
        conn.execute(
            f"UPDATE {safe_table} SET canonical_osm_id=?, osm_type='way', source_layer='lines', "
            "category=?, rule_ids=?, profile_id=?, profile_sha256=?, tags_json=? WHERE fid=?",
            (canonical_id, category, rule_id, resolved.id, resolved.sha256, tags, fid),
        )
        categories[category] += 1
    conn.commit()
    # A single reviewed category per highway value; no uncertain ontology inference.
    count = conn.execute(f"SELECT COUNT(*) FROM {safe_table}").fetchone()[0]
    if count != len(seen_ids):
        raise RuntimeError("Feature count and unique canonical ID count disagree")
    return {"feature_count": count, "category_counts": dict(sorted(categories.items())),
            "matched_id_sha256": hashlib.sha256(
                "".join(s + "\n" for s in sorted(seen_ids)).encode("utf-8")
            ).hexdigest()}



def _sqlite_literal(value: str) -> str:
    """Quote a single text literal for SQLite SQL executed by OGR."""
    return "'" + str(value).replace("'", "''") + "'"


def _preflight_gpkg_records(conn: sqlite3.Connection, table: str,
                            mapping: dict[str, tuple[str, str]]) -> dict[str, Any]:
    """Read-only examination before altering a GeoPackage feature table.

    This uses standard sqlite3 safely because SELECT does not activate the
    GeoPackage geometry/spatial-index UPDATE triggers.  No spatial triggers are
    dropped or replaced.  The OGR driver performs the actual modification.
    """
    safe_table = '"' + table.replace('"', '""') + '"'
    required = {"osm_id", "highway", "all_tags", "fid"}
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({safe_table})")}
    missing = required - columns
    if missing:
        raise RuntimeError(f"Direct GDAL extract lacks required columns: {sorted(missing)}")
    evidence_columns = {
        "canonical_osm_id", "osm_type", "source_layer", "category", "rule_ids",
        "profile_id", "profile_sha256", "tags_json",
    }
    collisions = evidence_columns & columns
    if collisions:
        raise RuntimeError(f"Unexpected provenance field collision: {sorted(collisions)}")

    counts: Counter[str] = Counter()
    known: set[str] = set()
    for fid, osm_id, highway, tags in conn.execute(
        f"SELECT fid, osm_id, highway, all_tags FROM {safe_table} ORDER BY fid"
    ):
        key = str(highway or "")
        if key not in mapping:
            raise RuntimeError(f"GDAL output contains highway={key!r} outside reviewed whitelist")
        if osm_id is None or not re.fullmatch(r"\d+", str(osm_id)):
            raise RuntimeError(f"Cannot establish numeric OSM way identity for {osm_id!r}")
        canonical_id = f"way/{osm_id}"
        if canonical_id in known:
            raise RuntimeError(f"Repeated canonical OSM way ID: {canonical_id}")
        known.add(canonical_id)
        if not isinstance(tags, str) or not tags:
            raise RuntimeError(f"Missing complete all_tags JSON for {canonical_id}")
        try:
            decoded = json.loads(tags)
        except json.JSONDecodeError as error:
            raise RuntimeError(f"Invalid all_tags JSON for {canonical_id}") from error
        if not isinstance(decoded, dict) or str(decoded.get("highway")) != key:
            raise RuntimeError(f"Highway tag mismatch for {canonical_id}")
        counts[mapping[key][0]] += 1
    count = conn.execute(f"SELECT COUNT(*) FROM {safe_table}").fetchone()[0]
    if count != len(known):
        raise RuntimeError("Feature count and distinct OSM way ID count disagree")
    return {
        "feature_count": count,
        "category_counts": dict(sorted(counts.items())),
        "matched_id_sha256": hashlib.sha256(
            "".join(s + "\n" for s in sorted(known)).encode("utf-8")
        ).hexdigest(),
    }


def _provenance_update_sql(table: str,
                           resolved: ResolvedProfile,
                           mapping: dict[str, tuple[str, str]]) -> str:
    """One bulk SQL UPDATE, executed via the GPKG-aware GDAL driver."""
    safe_table = '"' + table.replace('"', '""') + '"'
    def case_for(index: int) -> str:
        clauses = " ".join(
            f"WHEN {_sqlite_literal(value)} THEN {_sqlite_literal(pair[index])}"
            for value, pair in sorted(mapping.items())
        )
        return f'(CASE "highway" {clauses} ELSE NULL END)'
    return (
        f"UPDATE {safe_table} SET "
        '"canonical_osm_id" = \'way/\' || CAST("osm_id" AS TEXT), '
        '"osm_type" = \'way\', '
        '"source_layer" = \'lines\', '
        f'"category" = {case_for(0)}, '
        f'"rule_ids" = {case_for(1)}, '
        f'"profile_id" = {_sqlite_literal(resolved.id)}, '
        f'"profile_sha256" = {_sqlite_literal(resolved.sha256)}, '
        '"tags_json" = "all_tags"'
    )


def _inject_provenance_ogr(path: Path, table: str, resolved: ResolvedProfile,
                           mapping: dict[str, tuple[str, str]], *,
                           deferred_spatial_index: bool = False) -> dict[str, Any]:
    """Populate GPKG attributes using its native GDAL/OGR connection.

    GeoPackage RTREE and geometry-type triggers invoke e.g. ST_IsEmpty on
    UPDATE.  Raw sqlite3 connections do NOT register these spatial functions.
    OGR does, and its native SQLite execution can run one bulk UPDATE rather
    than committing an individual Python statement for every OSM feature.
    """
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        summary = _preflight_gpkg_records(conn, table, mapping)

    try:
        from osgeo import ogr
    except ImportError as exc:
        raise RuntimeError(
            "GeoPackage provenance update requires GDAL Python bindings (osgeo.ogr) "
            "from the same environment as ogr2ogr"
        ) from exc

    ogr.UseExceptions()
    dataset = ogr.Open(str(path), update=1)
    if dataset is None:
        raise RuntimeError(f"GDAL cannot reopen staging GeoPackage for update: {path}")
    columns = (
        "canonical_osm_id", "osm_type", "source_layer", "category", "rule_ids",
        "profile_id", "profile_sha256", "tags_json",
    )
    try:
        layer = dataset.GetLayerByName(table)
        if layer is None:
            raise RuntimeError(f"Staging GeoPackage missing layer: {table}")
        for name in columns:
            result = layer.CreateField(ogr.FieldDefn(name, ogr.OFTString))
            if result != ogr.OGRERR_NONE:
                raise RuntimeError(f"Unable to add GeoPackage field {name}: OGR code {result}")
        if dataset.StartTransaction() != ogr.OGRERR_NONE:
            raise RuntimeError("OGR could not start GeoPackage update transaction")
        try:
            # GeoPackage driver registers ST_IsEmpty, ST_MinX, and other
            # functions needed by the RTree and geometry constraints.
            dataset.ExecuteSQL(_provenance_update_sql(table, resolved, mapping), dialect="SQLITE")
            if dataset.CommitTransaction() != ogr.OGRERR_NONE:
                raise RuntimeError("OGR could not commit GeoPackage provenance transaction")
        except BaseException:
            dataset.RollbackTransaction()
            raise
        if deferred_spatial_index:
            # Rebuild the *same* GeoPackage RTree extension after the bulk
            # attribute UPDATE. GDAL installs standard RTree tables/triggers.
            # Do not accept a GeoPackage without the promised spatial index.
            sql = "SELECT CreateSpatialIndex('highway_lines','geom')"
            result_layer = dataset.ExecuteSQL(sql, dialect="SQLITE")
            if result_layer is None:
                raise RuntimeError("GeoPackage deferred spatial index creation returned no result")
            try:
                feature = result_layer.GetNextFeature()
                if feature is None or int(feature.GetField(0)) != 1:
                    raise RuntimeError("GeoPackage deferred spatial index creation did not return success")
            finally:
                dataset.ReleaseResultSet(result_layer)
    finally:
        # SWIG-backed OGR handles and Windows GPKG locks must be released.
        layer = None
        dataset = None

    # Verification after closing GDAL handle: no spatial mutation is needed.
    safe_table = '"' + table.replace('"', '""') + '"'
    with closing(sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)) as conn:
        row = conn.execute(
            f'SELECT COUNT(*), COUNT("canonical_osm_id"), COUNT("category"), '
            f'COUNT("rule_ids"), COUNT("tags_json") FROM {safe_table}'
        ).fetchone()
        if row != (summary["feature_count"],) * 5:
            raise RuntimeError(f"GDAL provenance UPDATE incomplete: {row}")
        got = dict(conn.execute(
            f'SELECT "category", COUNT(*) FROM {safe_table} GROUP BY "category"'
        ).fetchall())
        if got != summary["category_counts"]:
            raise RuntimeError(f"GDAL provenance categories differ from preflight: {got}")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("GeoPackage SQLite integrity check failed")
        if deferred_spatial_index:
            # Both the RTree table and its maintenance triggers are required;
            # the extension is not equivalent to a naked SQLite RTree.
            rtree = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='rtree_highway_lines_geom'"
            ).fetchone()
            triggers = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='trigger' "
                "AND name LIKE 'rtree_highway_lines_geom_%'"
            ).fetchone()[0]
            if not rtree or triggers < 3:
                raise RuntimeError("Deferred GeoPackage spatial index lacks RTree or triggers")
            indexed = conn.execute(
                'SELECT COUNT(*) FROM "rtree_highway_lines_geom"'
            ).fetchone()[0]
            nonempty_geom = conn.execute(
                'SELECT COUNT(*) FROM "highway_lines" WHERE geom IS NOT NULL'
            ).fetchone()[0]
            if indexed != nonempty_geom:
                raise RuntimeError(
                    f"Deferred spatial index count mismatch: {indexed} vs {nonempty_geom}"
                )
            summary["spatial_index"] = {"mode": "deferred_then_created", "indexed_rows": indexed, "trigger_count": triggers}
        else:
            summary["spatial_index"] = {"mode": "default_gdal_creation"}
    return summary

def targeted_highway_extract(input_path: str | Path, output_path: str | Path,
                            resolved_profile: ResolvedProfile, *,
                            base_config: str | Path, ogr2ogr: str = "ogr2ogr",
                            overwrite: bool = False,
                            experimental_deferred_index: bool = False) -> dict[str, Any]:
    """Run direct GDAL SQL selective export and add rule/provenance evidence.

    A sidecar JSON reports stage timing and selected source layer. This is not a
    replacement for the full inventory + deterministic geometry-quality audit.
    """
    source = Path(input_path).expanduser().resolve()
    destination = Path(output_path).expanduser().resolve()
    conf = Path(base_config).expanduser().resolve()
    if not source.is_file() or not conf.is_file():
        raise FileNotFoundError("Input PBF/OSM file and base config must exist")
    if source.suffix.lower() not in {".osm", ".pbf"}:
        raise ValueError("Only .osm/.pbf local inputs supported")
    if destination.suffix.lower() != ".gpkg":
        raise ValueError("Targeted mode currently supports GeoPackage output only")
    if destination.exists() and not overwrite:
        raise FileExistsError(f"Output exists: {destination} (use --overwrite)")
    values, mapping = reviewed_highway_mapping(resolved_profile)
    config = _gdal_osm_config(conf.read_text(encoding="utf-8-sig"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    clock_start = time.perf_counter()
    digest = _hash_file(source)
    t_hash = time.perf_counter()
    started = datetime.now(timezone.utc).isoformat()
    with tempfile.TemporaryDirectory(prefix=".osm-sci-targeted-", dir=destination.parent) as tmp:
        workspace = Path(tmp)
        temp_config = workspace / "targeted_osmconf.ini"
        temp_config.write_text(config, encoding="utf-8")
        temp_output = workspace / "selected.gpkg"
        sql = _gdal_sql(values)
        command = [ogr2ogr, "-f", "GPKG", str(temp_output), str(source),
                   "-oo", f"CONFIG_FILE={temp_config}", "-oo", "TAGS_FORMAT=JSON",
                   "--config", "OGR2OGR_USE_ARROW_API", "NO",
                   "-sql", sql, "-dialect", "OGRSQL", "-nln", "highway_lines",
                   "-lco", "GEOMETRY_NAME=geom"]
        if experimental_deferred_index:
            command += ["-lco", "SPATIAL_INDEX=NO"]
        completed = subprocess.run(command, capture_output=True, text=True, errors="replace")
        t_gdal = time.perf_counter()
        if completed.returncode != 0 or not temp_output.is_file():
            raise RuntimeError(f"GDAL targeted extraction failed (exit={completed.returncode}): "
                               + completed.stderr[-1800:])
        # Use GDAL/OGR for a GeoPackage feature-table UPDATE. Native OGR
        # registers the spatial SQL functions required by GPKG triggers.
        # Do not use raw sqlite3 to UPDATE actual GPKG geometries/attributes.
        if experimental_deferred_index:
            output_info = _inject_provenance_ogr(
                temp_output, "highway_lines", resolved_profile, mapping,
                deferred_spatial_index=True,
            )
        else:
            output_info = _inject_provenance_ogr(
                temp_output, "highway_lines", resolved_profile, mapping
            )
        t_audit = time.perf_counter()
        audit = {
            "status": "success", "workflow": "experimental_targeted_highway_v1",
            "experimental_deferred_index": bool(experimental_deferred_index),
            "software_version": __version__, "started_at_utc": started,
            "input_name": source.name, "input_sha256": digest,
            "profile_id": resolved_profile.id, "profile_sha256": resolved_profile.sha256,
            "source_layer": "lines", "tag_key": "highway", "allowed_values": values,
            "format": "GPKG", "output_name": destination.name,
            **output_info,
            "timings_seconds": {
                "input_hash": round(t_hash - clock_start, 3),
                "gdal_selective_import": round(t_gdal - t_hash, 3),
                "category_and_provenance": round(t_audit - t_gdal, 3),
                "total_before_final_copy": round(t_audit - clock_start, 3),
            },
            "scope_limitations": [
                "No full OSM tag-vocabulary inventory",
                "No complete deterministic pre-export geometry/quality audit",
                "When used through the GUI, preview is limited to the first 400 exported objects; it is not a spatial completeness check",
                "GDAL still reconstructs OSM geometry and may read non-matching data",
                "Only reviewed highway equals/in rules on exact 'lines' layer",
                "Only GPKG output supported",
            ],
        }
        # Write report atomically in the same filesystem. Finalize only after
        # successful GDAL process, integrity checks, and category assignment.
        audit["timings_seconds"]["total_end_to_end"] = round(time.perf_counter() - clock_start, 3)
        temp_audit = workspace / "targeted_audit.json"
        temp_audit.write_text(json.dumps(audit, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        shutil.copy2(temp_output, workspace / destination.name)
        staged_output = workspace / destination.name
        sidecar = Path(str(destination) + ".audit.json")
        if sidecar.exists() and not overwrite:
            raise FileExistsError(f"Audit report already exists: {sidecar} (use --overwrite)")
        # Sidecar is a lightweight execution record, not a full quality certificate.
        os.replace(staged_output, destination)
        os.replace(temp_audit, sidecar)
    return audit
