from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import shutil
import sqlite3
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

from osm_scientific_converter import __version__

from .environment import inspect_environment
from .path_privacy import portable_project_path
from .phase2_feedback import build_phase2_feedback
from .resource_monitor import ResourceMonitor
from .tag_scanner import parse_tags


@dataclass(frozen=True)
class ExportResult:
    output: Path
    audit: Path
    feedback_bundle: Path
    features_written: int


GENERIC_FIELDS = [
    "osm_id",
    "osm_type",
    "source_layer",
    "geometry_group",
    "category",
    "rule_ids",
    "lifecycle",
    "profile_id",
    "profile_sha256",
    "tags_json",
]

# These fields are the minimum scientific provenance contract.  A field
# selection may reduce profile attributes, but it must never remove the
# information required to trace an exported feature back to its OSM object,
# classification rule, input profile, and original tags.
REQUIRED_TRACEABILITY_FIELDS = tuple(GENERIC_FIELDS)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_name(value: str, maximum: int = 63) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", value).strip("_").lower() or "field"
    if name[0].isdigit():
        name = "f_" + name
    return name[:maximum]


def _unique_field_names(source_fields: Iterable[str], *, shapefile: bool) -> dict[str, str]:
    maximum = 10 if shapefile else 63
    used: set[str] = set()
    result: dict[str, str] = {}
    preferred = {
        "source_layer": "src_layer",
        "geometry_group": "geom_grp",
        "profile_id": "profile",
        "profile_sha256": "prof_sha",
    }
    for source in source_fields:
        base = _safe_name(preferred.get(source, source), maximum)
        candidate = base
        counter = 2
        while candidate.lower() in used:
            suffix = str(counter)
            candidate = base[: maximum - len(suffix)] + suffix
            counter += 1
        used.add(candidate.lower())
        result[source] = candidate
    return result


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _load_selection(path: str | Path, default_profile: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"Selection file does not exist: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise ValueError(f"Invalid selection JSON: {error}") from error
    if not isinstance(data, dict) or str(data.get("schema_version", "")) != "1.0":
        raise ValueError("Selection must be a JSON object with schema_version 1.0")
    data.setdefault("profile", default_profile)
    categories = data.get("categories")
    if categories is not None and (
        not isinstance(categories, list) or any(not isinstance(item, str) for item in categories)
    ):
        raise ValueError("Selection categories must be a list of strings")
    fields = data.get("fields", data.get("gui_selected_fields"))
    if fields is not None and (
        not isinstance(fields, list) or any(not isinstance(item, str) for item in fields)
    ):
        raise ValueError("Selection fields must be a list of strings")
    return data


def _resolve_export_fields(selection: dict[str, Any], profile_attributes: list[str]) -> tuple[list[str], list[str]]:
    """Resolve a real profile-attribute subset while enforcing provenance.

    Missing ``fields`` retains all profile attributes for CLI/backward
    compatibility.  When a selection is supplied, generic traceability fields
    are accepted but always forced, and only explicitly selected profile
    attributes are added.
    """
    requested = selection.get("fields", selection.get("gui_selected_fields"))
    if requested is None:
        selected_attributes = list(profile_attributes)
    else:
        allowed = set(REQUIRED_TRACEABILITY_FIELDS).union(profile_attributes)
        unknown = sorted(set(requested) - allowed)
        if unknown:
            raise ValueError(f"Selection contains unknown fields: {', '.join(unknown)}")
        requested_set = set(requested)
        selected_attributes = [field for field in profile_attributes if field in requested_set]
    return list(REQUIRED_TRACEABILITY_FIELDS), selected_attributes


def _format_and_destination(output: Path, requested: str | None) -> tuple[str, Path]:
    normalized = (requested or "").strip().lower()
    suffix = output.suffix.lower()
    if normalized in {"gpkg", "geopackage"} or suffix == ".gpkg":
        return "GPKG", output
    if normalized in {"geojson", "json"} or suffix in {".geojson", ".json"}:
        return "GeoJSON", output.with_suffix("") if suffix else output
    if normalized in {"shp", "shapefile", "esri shapefile"} or suffix == ".shp":
        return "Shapefile", output.with_suffix("") if suffix else output
    if requested is None and not suffix:
        raise ValueError("A directory output requires selection.format to be GeoJSON or Shapefile")
    raise ValueError(f"Unsupported export format: {requested or suffix}")


def _replace_path(source: Path, destination: Path) -> None:
    backup = destination.with_name(f".{destination.name}.backup-{uuid.uuid4().hex}")
    existed = destination.exists()
    if existed:
        os.replace(destination, backup)
    try:
        os.replace(source, destination)
    except Exception:
        if existed and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.is_dir():
        shutil.rmtree(backup, ignore_errors=True)
    elif backup.exists():
        backup.unlink(missing_ok=True)


def _load_ogr():
    try:
        from osgeo import gdal, ogr
    except ImportError as error:  # pragma: no cover - environment dependent
        raise RuntimeError("GDAL Python bindings are required for thematic export") from error
    data_path = inspect_environment(require_gdal=True)["gdal"].get("data_path")
    if data_path:
        gdal.SetConfigOption("GDAL_DATA", str(data_path))
    gdal.UseExceptions()
    return gdal, ogr


def _classification_metadata(connection: sqlite3.Connection) -> dict[str, str]:
    return {str(key): str(value) for key, value in connection.execute("SELECT key, value FROM metadata")}


def _selection_query(categories: list[str], *, separate_categories: bool) -> tuple[str, list[str]]:
    parameters: list[str] = []
    category_clause = ""
    if categories:
        placeholders = ",".join("?" for _ in categories)
        category_clause = f" AND m.category IN ({placeholders})"
        parameters.extend(categories)
    if separate_categories:
        query = f"""
            SELECT o.source_layer, o.source_fid, o.osm_id, o.osm_type, o.geometry_group,
                   o.tags_json, o.lifecycle, m.category, GROUP_CONCAT(DISTINCT m.rule_id)
            FROM objects o JOIN matches m ON m.object_pk = o.object_pk
            WHERE m.profile_id = ? {category_clause}
            GROUP BY o.object_pk, m.category
            ORDER BY m.category, o.geometry_group, o.source_layer, o.source_fid
        """
    else:
        query = f"""
            SELECT o.source_layer, o.source_fid, o.osm_id, o.osm_type, o.geometry_group,
                   o.tags_json, o.lifecycle, GROUP_CONCAT(DISTINCT m.category),
                   GROUP_CONCAT(DISTINCT m.rule_id)
            FROM objects o JOIN matches m ON m.object_pk = o.object_pk
            WHERE m.profile_id = ? {category_clause}
            GROUP BY o.object_pk
            ORDER BY o.geometry_group, o.source_layer, o.source_fid
        """
    return query, parameters


class _OgrWriter:
    def __init__(
        self,
        format_name: str,
        staging: Path,
        profile_id: str,
        profile_attributes: list[str],
        source_layers: dict[str, Any],
    ) -> None:
        _, self.ogr = _load_ogr()
        self.format_name = format_name
        self.staging = staging
        self.profile_id = profile_id
        self.attributes = profile_attributes
        self.source_layers = source_layers
        self.shapefile = format_name == "Shapefile"
        self.field_names = _unique_field_names(GENERIC_FIELDS + profile_attributes, shapefile=self.shapefile)
        self.mapping_rows: list[list[Any]] = []
        self.layers: dict[str, tuple[Any, Any]] = {}
        self.datasets: dict[str, Any] = {}
        self.truncated_values = 0
        self.long_value_risks = 0
        self.null_values = 0
        self.feature_counts: Counter[str] = Counter()
        if format_name == "GPKG":
            driver = self.ogr.GetDriverByName("GPKG")
            dataset = driver.CreateDataSource(str(staging))
            if dataset is None:
                raise RuntimeError(f"Could not create GeoPackage: {staging}")
            self.datasets["__gpkg__"] = dataset
        elif format_name == "Shapefile":
            staging.mkdir(parents=True)
            driver = self.ogr.GetDriverByName("ESRI Shapefile")
            dataset = driver.CreateDataSource(str(staging))
            if dataset is None:
                raise RuntimeError(f"Could not create Shapefile directory: {staging}")
            self.datasets["__shp__"] = dataset
        else:
            staging.mkdir(parents=True)

    def _layer_name(self, category: str, geometry_group: str) -> str:
        geometry = "area" if geometry_group == "polygon" else geometry_group
        if self.format_name == "GPKG":
            return _safe_name(f"{self.profile_id}_{geometry}")
        return _safe_name(f"{self.profile_id}_{category}_{geometry}")

    def _create_fields(self, layer: Any, layer_name: str) -> None:
        for source in GENERIC_FIELDS + self.attributes:
            output = self.field_names[source]
            field = self.ogr.FieldDefn(output, self.ogr.OFTString)
            if self.shapefile:
                field.SetWidth(254 if source == "tags_json" else 200)
            if layer.CreateField(field) != 0:
                raise RuntimeError(f"Could not create field {output} in {layer_name}")
            self.mapping_rows.append([
                self.format_name,
                layer_name,
                source,
                output,
                source != output,
                len(_safe_name(source, 63)) > (10 if self.shapefile else 63),
            ])

    def _get_layer(self, category: str, geometry_group: str, source_layer: Any) -> tuple[Any, Any]:
        name = self._layer_name(category, geometry_group)
        if name in self.layers:
            return self.layers[name]
        srs = source_layer.GetSpatialRef()
        if self.format_name == "GeoJSON":
            driver = self.ogr.GetDriverByName("GeoJSON")
            path = self.staging / f"{name}.geojson"
            dataset = driver.CreateDataSource(str(path))
            if dataset is None:
                raise RuntimeError(f"Could not create GeoJSON: {path}")
            layer = dataset.CreateLayer(name, srs=srs, geom_type=self.ogr.wkbUnknown, options=["RFC7946=YES"])
            self.datasets[name] = dataset
        else:
            dataset = self.datasets["__gpkg__" if self.format_name == "GPKG" else "__shp__"]
            options = ["SPATIAL_INDEX=YES"] if self.format_name == "GPKG" else ["ENCODING=UTF-8"]
            layer = dataset.CreateLayer(name, srs=srs, geom_type=self.ogr.wkbUnknown, options=options)
        if layer is None:
            raise RuntimeError(f"Could not create output layer {name}")
        self._create_fields(layer, name)
        self.layers[name] = (dataset, layer)
        return dataset, layer

    def write(
        self,
        *,
        source_layer_name: str,
        source_feature: Any,
        osm_id: str,
        osm_type: str,
        geometry_group: str,
        tags_json: str,
        lifecycle: str,
        category: str,
        rule_ids: str,
        profile_sha256: str,
    ) -> None:
        source_layer = self.source_layers[source_layer_name]
        _, layer = self._get_layer(category, geometry_group, source_layer)
        feature = self.ogr.Feature(layer.GetLayerDefn())
        geometry = source_feature.GetGeometryRef()
        if geometry is not None:
            feature.SetGeometry(geometry.Clone())
        tags, _ = parse_tags(tags_json)
        values: dict[str, Any] = {
            "osm_id": osm_id,
            "osm_type": osm_type,
            "source_layer": source_layer_name,
            "geometry_group": geometry_group,
            "category": category,
            "rule_ids": rule_ids,
            "lifecycle": lifecycle,
            "profile_id": self.profile_id,
            "profile_sha256": profile_sha256,
            "tags_json": tags_json,
        }
        values.update({key: tags.get(key) for key in self.attributes})
        for source, value in values.items():
            if value is None:
                self.null_values += 1
                continue
            text = str(value)
            if self.shapefile and len(text) > (254 if source == "tags_json" else 200):
                self.long_value_risks += 1
                text = text[: 254 if source == "tags_json" else 200]
                self.truncated_values += 1
            feature.SetField(self.field_names[source], text)
        if layer.CreateFeature(feature) != 0:
            raise RuntimeError(f"Could not create output feature {osm_id}")
        feature = None
        self.feature_counts[layer.GetName()] += 1

    def close(self) -> None:
        self.layers.clear()
        for key in list(self.datasets):
            self.datasets[key] = None
        self.datasets.clear()


def export_selection(
    project_dir: str | Path,
    selection_path: str | Path,
    output_path: str | Path,
    *,
    progress: Callable[[str], None] | None = None,
) -> ExportResult:
    project = Path(project_dir).expanduser().resolve()
    raw_master = project / "data" / "raw_master.gpkg"
    classification_db = project / "classification" / "classification.sqlite"
    profile_path = project / "profiles" / "resolved_profile.json"
    if not raw_master.is_file():
        raise FileNotFoundError("Export requires data/raw_master.gpkg")
    if not classification_db.is_file():
        raise FileNotFoundError("Run classify before export; classification.sqlite is missing")
    if not profile_path.is_file():
        raise FileNotFoundError("Resolved profile is missing")

    profile = json.loads(profile_path.read_text(encoding="utf-8-sig"))
    context_connection = sqlite3.connect(f"file:{classification_db.as_posix()}?mode=ro", uri=True)
    try:
        metadata = _classification_metadata(context_connection)
        selection = _load_selection(selection_path, metadata["profile_id"])
        if selection["profile"] != metadata["profile_id"]:
            raise ValueError("Selection profile does not match classification database")
        requested_categories = selection.get("categories") or []
        available = {row[0] for row in context_connection.execute(
            "SELECT DISTINCT category FROM matches WHERE profile_id = ?", (metadata["profile_id"],)
        )}
        if not requested_categories:
            default_categories = {
                str(rule["category"])
                for rule in profile.get("rules", [])
                if rule.get("default_export", True)
            }
            categories = sorted(default_categories.intersection(available))
        else:
            categories = list(requested_categories)
        unknown = sorted(set(requested_categories) - available)
        if unknown:
            raise ValueError(f"Selection contains unavailable categories: {', '.join(unknown)}")
        # Record the effective category set on every path.  In particular, an
        # explicit selection must not be mistaken for an empty/default result
        # by the GUI or by downstream release evidence.
        selection = {**selection, "resolved_categories": list(categories)}
    finally:
        context_connection.close()

    output = Path(output_path).expanduser().resolve()
    format_name, destination = _format_and_destination(output, selection.get("format"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if format_name == "GPKG":
        staging = destination.with_name(f".{destination.stem}.partial-{uuid.uuid4().hex}.gpkg")
    else:
        staging = destination.with_name(f".{destination.name}.partial-{uuid.uuid4().hex}")

    _, ogr = _load_ogr()
    source_dataset = ogr.Open(str(raw_master), 0)
    if source_dataset is None:
        raise RuntimeError(f"Could not open raw master: {raw_master}")
    source_layers = {
        name: source_dataset.GetLayerByName(name)
        for name in ("points", "lines", "multilinestrings", "multipolygons", "other_relations")
    }
    if any(layer is None for layer in source_layers.values()):
        source_dataset = None
        raise RuntimeError("Raw master is missing one or more expected OSM layers")

    profile_attributes = [str(field) for field in profile.get("attributes", [])]
    traceability_fields, selected_attributes = _resolve_export_fields(selection, profile_attributes)
    selection = {
        **selection,
        "fields": traceability_fields + selected_attributes,
        "required_traceability_fields": traceability_fields,
        "selected_profile_attributes": selected_attributes,
        "field_selection_applied": True,
    }
    writer = _OgrWriter(format_name, staging, metadata["profile_id"], selected_attributes, source_layers)
    monitor = ResourceMonitor([staging])
    started = time.perf_counter()
    started_utc = _utc_now()
    missing_features = 0
    written = 0
    separate = format_name != "GPKG"
    query, category_parameters = _selection_query(categories, separate_categories=separate)
    parameters = [metadata["profile_id"], *category_parameters]
    connection = sqlite3.connect(f"file:{classification_db.as_posix()}?mode=ro", uri=True)
    try:
        monitor.start()
        if progress:
            progress(f"Exporting {metadata['profile_id']} as {format_name}")
        for row in connection.execute(query, parameters):
            source_layer_name, fid, osm_id, osm_type, geometry_group, tags_json, lifecycle, category, rule_ids = row
            source_layer = source_layers[str(source_layer_name)]
            feature = source_layer.GetFeature(int(fid))
            if feature is None:
                missing_features += 1
                continue
            writer.write(
                source_layer_name=str(source_layer_name),
                source_feature=feature,
                osm_id=str(osm_id),
                osm_type=str(osm_type),
                geometry_group=str(geometry_group),
                tags_json=str(tags_json),
                lifecycle=str(lifecycle),
                category=str(category),
                rule_ids=str(rule_ids),
                profile_sha256=metadata["profile_sha256"],
            )
            feature = None
            written += 1
            if progress and written % 10_000 == 0:
                progress(f"Exported {written} features")
        writer.close()
        source_dataset = None
        connection.close()
        monitor.stop()
        if missing_features:
            raise RuntimeError(f"Export could not retrieve {missing_features} classified source features")
        _replace_path(staging, destination)

        exports_dir = project / "exports"
        exports_dir.mkdir(exist_ok=True)
        mapping_name = "shapefile_field_mapping.csv" if format_name == "Shapefile" else "field_mapping.csv"
        mapping_temp = exports_dir / f".{mapping_name}.partial-{uuid.uuid4().hex}"
        with mapping_temp.open("w", encoding="utf-8", newline="") as handle:
            csv_writer = csv.writer(handle, lineterminator="\n")
            csv_writer.writerow(["format", "output_layer", "source_field", "output_field", "renamed", "truncated_name"])
            csv_writer.writerows(writer.mapping_rows)
        os.replace(mapping_temp, exports_dir / mapping_name)

        output_files = [destination] if destination.is_file() else sorted(path for path in destination.rglob("*") if path.is_file())
        audit = {
            "schema_version": "1.0",
            "software": {"name": "osm-scientific-converter", "version": __version__},
            "status": "success",
            "started_at_utc": started_utc,
            "finished_at_utc": _utc_now(),
            "profile": {"id": metadata["profile_id"], "sha256": metadata["profile_sha256"]},
            "selection": selection,
            "format": format_name,
            "output": portable_project_path(destination, project, external_label="external-output"),
            "counts": {
                "features_written": written,
                "feature_count_semantics": (
                    "unique classified objects grouped across selected categories"
                    if format_name == "GPKG"
                    else "object-category records; a multi-category object appears once in each category layer"
                ),
                "layers": dict(sorted(writer.feature_counts.items())),
                "missing_source_features": missing_features,
                "null_attribute_values": writer.null_values,
            },
            "loss_audit": {
                "attribute_truncation_detected": writer.truncated_values > 0,
                "field_name_truncation_detected": any(bool(row[5]) for row in writer.mapping_rows),
                "full_tags_json_preserved": format_name != "Shapefile",
                "geometry_conversion": "copied through GDAL/OGR into target format",
                "field_name_mapping_file": mapping_name,
                "truncated_values": writer.truncated_values,
                "long_value_truncation_risks": writer.long_value_risks,
                "tags_json_handling": "full" if format_name != "Shapefile" else "UTF-8 text truncated to 254 characters when necessary",
                "unicode": "UTF-8 requested; downstream DBF reader support may vary" if format_name == "Shapefile" else "UTF-8",
                "mixed_geometry": "split by category and geometry" if separate else "split by geometry group",
            },
            "performance": {
                "wall_time_seconds": round(time.perf_counter() - started, 6),
                **monitor.metrics(),
            },
            "output_files": [
                {
                    "path": str(path.relative_to(destination.parent)),
                    "bytes": path.stat().st_size,
                    "sha256": _hash_file(path),
                }
                for path in output_files
            ],
        }
        audit_temp = exports_dir / f".export_audit.partial-{uuid.uuid4().hex}.json"
        audit_temp.write_text(json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(audit_temp, exports_dir / "export_audit.json")
        if format_name == "Shapefile":
            loss = {
                "schema_version": "1.0",
                "lossless": False,
                "field_name_limit": 10,
                "text_width_limit": 254,
                "field_mapping": "shapefile_field_mapping.csv",
                "field_renames": sum(1 for row in writer.mapping_rows if row[4]),
                "field_name_truncations": sum(1 for row in writer.mapping_rows if row[5]),
                "value_truncations": writer.truncated_values,
                "long_value_truncation_risks": writer.long_value_risks,
                "tags_json": "may be truncated; full tags remain in classification.sqlite and raw master",
                "unicode": "UTF-8 encoding requested; consumer compatibility is not guaranteed",
                "nulls": "preserved where supported by DBF; consumer behavior may vary",
                "mixed_geometry": "split into category/geometry-specific Shapefiles",
                "unsupported_field_types": "all exported attributes are serialized as text",
            }
            loss_temp = exports_dir / f".shapefile_loss.partial-{uuid.uuid4().hex}.json"
            loss_temp.write_text(json.dumps(loss, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            os.replace(loss_temp, exports_dir / "shapefile_loss_report.json")
        feedback = build_phase2_feedback(project)
        return ExportResult(destination, exports_dir / "export_audit.json", feedback, written)
    except Exception:
        writer.close()
        monitor.stop()
        connection.close()
        source_dataset = None
        if staging.is_dir():
            shutil.rmtree(staging, ignore_errors=True)
        elif staging.exists():
            staging.unlink(missing_ok=True)
        raise
