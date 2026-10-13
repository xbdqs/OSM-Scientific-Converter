"""Compare OSM object identities across converter and direct-GDAL GeoPackages.

A converter may store osm_id as 'way/1001' while the GDAL OSM 'lines'
layer stores '1001'. Normalize with an explicit source-layer provenance
assumption; never erase node/way/relation type in general comparisons.

This script checks canonical OSM-ID multisets and actual geometry-type
histograms. It does NOT establish full geometry, tag or schema equivalence.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re

QUALIFIED_ID = re.compile(r"^(node|way|relation)/([0-9]+)$")
NUMERIC_ID = re.compile(r"^[0-9]+$")
VALID_TYPES = {"node", "way", "relation"}
# GDAL's `lines` OSM layer contains lines constructed from OSM ways.
OSM_TYPE_FOR_GDAL_LAYER = {"lines": "way", "points": "node"}


def normalize_id(raw_id: object, *, declared_osm_type: object = None,
                 assumed_osm_type: str | None = None) -> str:
    """Return explicit 'type/id' identity, rejecting ambiguous or contradictory IDs.

    For naked numeric IDs, an OSM type MUST be supplied explicitly or inferred
    from a verified GDAL OSM source-layer context. Avoid converting IDs just by
    dropping 'way/' as IDs of different object types may be numerically equal.
    """
    if raw_id is None:
        raise ValueError("null osm_id")
    value = str(raw_id).strip()
    if not value or value.lower() == "none":
        raise ValueError("empty osm_id")
    metadata_type = (str(declared_osm_type).strip().lower()
                     if declared_osm_type is not None else "")
    if metadata_type and metadata_type not in VALID_TYPES:
        raise ValueError(f"invalid osm_type metadata: {declared_osm_type!r}")
    if assumed_osm_type is not None and assumed_osm_type not in VALID_TYPES:
        raise ValueError(f"invalid assumed type: {assumed_osm_type!r}")
    m = QUALIFIED_ID.fullmatch(value)
    if m:
        typ, number = m.groups()
        if metadata_type and metadata_type != typ:
            raise ValueError(f"OSM type metadata conflicts with osm_id: {metadata_type} vs {typ}")
        if assumed_osm_type and assumed_osm_type != typ:
            raise ValueError(f"source-layer assumption conflicts with osm_id: {assumed_osm_type} vs {typ}")
        return f"{typ}/{int(number)}"
    if NUMERIC_ID.fullmatch(value):
        if metadata_type and assumed_osm_type and metadata_type != assumed_osm_type:
            raise ValueError(f"OSM type metadata conflicts with layer assumption: {metadata_type} vs {assumed_osm_type}")
        typ = metadata_type or assumed_osm_type
        if typ is None:
            raise ValueError(f"naked numeric OSM ID {value} has no verified OSM object type")
        return f"{typ}/{int(value)}"
    raise ValueError(f"unsupported OSM ID format: {value!r}")


def inspect_gpkg(path: Path, *, assumed_source_layer: str | None = None,
                 retain_geometry: bool = False, max_geometry_objects: int = 10000):
    from osgeo import ogr
    ogr.UseExceptions()
    ds = ogr.Open(str(path), update=0)
    if ds is None:
        raise RuntimeError(f"Unable to open GeoPackage: {path}")
    normalized = Counter()
    raw = Counter()
    geometries = Counter()
    source_layers = Counter()
    geom_by_canonical_id = {} if retain_geometry else None
    srs_wkt = []
    examples = []
    errors = []
    count = 0
    for layer_idx in range(ds.GetLayerCount()):
        layer = ds.GetLayer(layer_idx)
        layer_name = layer.GetName()
        sr = layer.GetSpatialRef()
        srs_wkt.append(sr.ExportToWkt() if sr else None)
        names = {layer.GetLayerDefn().GetFieldDefn(i).GetName()
                 for i in range(layer.GetLayerDefn().GetFieldCount())}
        if "osm_id" not in names:
            raise ValueError(f"{path.name}/{layer_name} missing required osm_id")
        source_field = next((key for key in ("src_layer", "source_layer") if key in names), None)
        type_field = next((key for key in ("osm_type", "obj_type") if key in names), None)
        for feature in layer:
            count += 1
            raw_id = feature.GetField("osm_id")
            src = (str(feature.GetField(source_field)) if source_field else
                   assumed_source_layer)
            if src:
                source_layers[src] += 1
            if assumed_source_layer and src != assumed_source_layer:
                errors.append(f"{layer_name}: unexpected source_layer={src!r}; expected {assumed_source_layer!r}")
            metadata_type = feature.GetField(type_field) if type_field else None
            assumed_type = OSM_TYPE_FOR_GDAL_LAYER.get(assumed_source_layer or src or "")
            try:
                canonical = normalize_id(raw_id, declared_osm_type=metadata_type,
                                         assumed_osm_type=assumed_type)
                normalized[canonical] += 1
                raw[str(raw_id)] += 1
                if retain_geometry:
                    if count > max_geometry_objects:
                        raise ValueError(f"Geometry coordinate check limited to {max_geometry_objects} objects; rerun without --compare-geometries for large datasets")
                    if canonical in geom_by_canonical_id:
                        raise ValueError(f"Duplicate object identity prevents one-to-one geometry comparison: {canonical}")
                    geometry_ref = feature.GetGeometryRef()
                    geom_by_canonical_id[canonical] = (geometry_ref.ExportToWkb() if geometry_ref else None)
                if len(examples) < 5:
                    examples.append({"raw": str(raw_id), "canonical": canonical})
            except ValueError as exc:
                errors.append(f"{layer_name}/FID {feature.GetFID()}: {exc}")
            geometry = feature.GetGeometryRef()
            label = ("EMPTY" if geometry is None or geometry.IsEmpty()
                     else ogr.GeometryTypeToName(ogr.GT_Flatten(geometry.GetGeometryType())).upper().replace(" ", ""))
            geometries[label] += 1
    ds = None
    return {"count": count, "raw": raw, "canonical": normalized,
            "geometry_types": geometries, "source_layers": source_layers,
            "id_examples": examples, "errors": errors,
            "wkb_by_canonical_id": geom_by_canonical_id, "srs_wkt": srs_wkt}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--converter", required=True, type=Path)
    ap.add_argument("--baseline", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--compare-geometries", action="store_true",
                    help="Also compare geometry for each canonical OSM ID (small datasets only)")
    ap.add_argument("--max-geometry-objects", type=int, default=10000)
    ap.add_argument("--source-layer", default="lines", choices=["lines"],
                    help="Verified GDAL source layer for both comparison outputs")
    args = ap.parse_args()
    result = {}
    try:
        converter = inspect_gpkg(args.converter, assumed_source_layer=args.source_layer,
                                 retain_geometry=args.compare_geometries,
                                 max_geometry_objects=args.max_geometry_objects)
        baseline = inspect_gpkg(args.baseline, assumed_source_layer=args.source_layer,
                                retain_geometry=args.compare_geometries,
                                max_geometry_objects=args.max_geometry_objects)
        c1 = converter["canonical"]
        c2 = baseline["canonical"]
        errors = converter["errors"] + baseline["errors"]
        same_count = converter["count"] == baseline["count"]
        same_ids = c1 == c2
        same_geom_hist = converter["geometry_types"] == baseline["geometry_types"]
        geometry_comparison = {"performed": False, "note": "Not requested"}
        if args.compare_geometries:
            from osgeo import ogr, osr
            cgeom = converter["wkb_by_canonical_id"]
            bgeom = baseline["wkb_by_canonical_id"]
            mismatched = []
            comparable = sorted(set(cgeom) & set(bgeom))
            for osm_identity in comparable:
                wa, wb = cgeom[osm_identity], bgeom[osm_identity]
                if wa is None or wb is None:
                    equal = wa is None and wb is None
                else:
                    ga = ogr.CreateGeometryFromWkb(wa)
                    gb = ogr.CreateGeometryFromWkb(wb)
                    equal = bool(ga.Equals(gb))
                if not equal:
                    mismatched.append(osm_identity)
            # Compare CRS, not coordinate values alone.
            sw1 = [v for v in converter["srs_wkt"] if v]
            sw2 = [v for v in baseline["srs_wkt"] if v]
            same_crs = bool(sw1 and sw2) and all(
                bool(osr.SpatialReference(wkt=a).IsSame(osr.SpatialReference(wkt=b)))
                for a in sw1 for b in sw2
            )
            if mismatched:
                errors.append(f"Geometry equality failed for {len(mismatched)} matching OSM identities")
            if not same_crs:
                errors.append("Output CRSs are not demonstrably equivalent")
            geometry_comparison = {
                "performed": True,
                "checked_common_canonical_id_count": len(comparable),
                "CRS_equivalent": same_crs,
                "geometries_equal_by_canonical_id": not bool(mismatched) and len(comparable) == converter["count"] == baseline["count"],
                "mismatched_id_sample": mismatched[:20],
                "method": "OGR topology-based Equals by normalized OSM identity; CRS checked with OSR IsSame"
            }
        status = "PASS" if not errors and same_count and same_ids and same_geom_hist else "DIFFERENCE"
        result = {
            "status": status,
            "comparison_scope": "canonical OSM-ID multiset and actual geometry-type counts; optional per-ID geometry comparison; not full attribute, rule/category or audit equivalence",
            "normalization_policy": "type-qualified IDs retained; numeric GDAL lines osm_id resolved as way/{id} only because source layer is explicitly lines",
            "source_layer": args.source_layer,
            "converter_count": converter["count"],
            "baseline_count": baseline["count"],
            "raw_id_multiset_equal": converter["raw"] == baseline["raw"],
            "canonical_id_multiset_equal": same_ids,
            "geometry_type_histogram_equal": same_geom_hist,
            "geometry_equality": geometry_comparison,
            "converter_geometry_types": dict(sorted(converter["geometry_types"].items())),
            "baseline_geometry_types": dict(sorted(baseline["geometry_types"].items())),
            "converter_source_layers": dict(sorted(converter["source_layers"].items())),
            "baseline_assumed_source_layer": args.source_layer,
            "converter_id_examples": converter["id_examples"],
            "baseline_id_examples": baseline["id_examples"],
            "only_in_converter_canonical_ids_sample": sorted((c1-c2).elements())[:20],
            "only_in_baseline_canonical_ids_sample": sorted((c2-c1).elements())[:20],
            "issues": errors[:30],
        }
    except Exception as exc:
        result = {"status": "ERROR", "error": str(exc), "comparison_scope": "OSM identity validation"}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
