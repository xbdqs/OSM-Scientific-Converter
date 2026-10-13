"""A deliberately bounded visual *sample* of quick-mode GeoPackage output."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_quick_preview(gpkg: str | Path, limit: int = 400) -> dict[str, Any]:
    """Read a small, ordered slice for on-screen inspection, NOT a quality audit."""
    from osgeo import ogr  # optional outside a configured GDAL runtime

    limit = max(1, min(int(limit), 2000))
    ds = ogr.Open(str(gpkg), 0)
    if ds is None:
        raise RuntimeError(f'Cannot open quick GeoPackage: {gpkg}')
    try:
        layer = ds.GetLayerByName('highway_lines')
        if layer is None:
            raise RuntimeError('Quick output does not contain highway_lines')
        total = layer.GetFeatureCount()
        features = []
        xs: list[float] = []
        ys: list[float] = []
        for feature in layer:
            geom = feature.GetGeometryRef()
            if geom is None or geom.IsEmpty():
                continue
            # GDAL Python exposes GT_Flatten, not wkbFlatten (a C-API name).
            # Correctly recognises 2D and Z/M LineStrings in GDAL 3.x.
            if ogr.GT_Flatten(geom.GetGeometryType()) != ogr.wkbLineString:
                continue
            n = geom.GetPointCount()
            if n <= 1:
                continue
            indices = list(range(0, n, max(1, (n - 1) // 120)))
            if indices[-1] != n - 1:
                indices.append(n - 1)
            coords = [(float(geom.GetX(i)), float(geom.GetY(i))) for i in indices]
            xs.extend(x for x, y in coords)
            ys.extend(y for x, y in coords)
            try:
                tags = json.loads(feature.GetField('tags_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                tags = {}
            features.append({
                'category': feature.GetField('category') or '(unclassified)',
                'geometry_group': 'line',
                'coordinates': coords,
                'tags': tags,
                'canonical_osm_id': feature.GetField('canonical_osm_id'),
            })
            if len(features) >= limit:
                break
        if not features:
            raise RuntimeError('Quick output contains no previewable LineStrings')
        return {
            'features': features, 'loaded': len(features), 'total': int(total),
            'bounds': [min(xs), min(ys), max(xs), max(ys)],
            'preview_scope': 'first N exported lines only; not spatially representative or a completeness check',
        }
    finally:
        # GeoPackage must not remain open after either success or a read error.
        ds = None
