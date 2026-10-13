"""Regression: preview must use the available GDAL 3.x Python geometry-type API."""
from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

from osm_scientific_converter.gui.quick_preview import load_quick_preview


class FakeGeometry:
    def __init__(self, kind: int, coords: list[tuple[float, float]]):
        self.kind = kind
        self.coords = coords

    def IsEmpty(self):
        return not self.coords

    def GetGeometryType(self):
        return self.kind

    def GetPointCount(self):
        return len(self.coords)

    def GetX(self, index):
        return self.coords[index][0]

    def GetY(self, index):
        return self.coords[index][1]


class FakeFeature:
    def __init__(self, geom, **fields):
        self.geom = geom
        self.fields = fields

    def GetGeometryRef(self):
        return self.geom

    def GetField(self, name):
        return self.fields.get(name)


class FakeLayer:
    def __init__(self, records):
        self.records = records

    def GetFeatureCount(self):
        return len(self.records)

    def __iter__(self):
        return iter(self.records)


class FakeDataset:
    def __init__(self, layer):
        self.layer = layer

    def GetLayerByName(self, name):
        return self.layer if name == 'highway_lines' else None


def test_preview_uses_gt_flatten_supported_by_gdal_python(monkeypatch):
    # In GDAL 3.x osgeo.ogr.GT_Flatten is supported, while wkbFlatten
    # is not necessarily exposed. Do not provide wkbFlatten in this fake API.
    line_kind = 2
    line_z_kind = 1002
    fake_ogr = SimpleNamespace(
        wkbLineString=line_kind,
        GT_Flatten=lambda kind: kind - 1000 if kind >= 1000 else kind,
        Open=lambda path, mode: FakeDataset(FakeLayer([
            FakeFeature(FakeGeometry(line_z_kind, [(-46.6, -23.5), (-46.61, -23.51)]),
                        category='residential_and_service',
                        tags_json='{"highway": "residential"}',
                        canonical_osm_id='way/42'),
            FakeFeature(FakeGeometry(1, [(-46.7, -23.6)]),
                        category='ignored', tags_json='{}'),
        ])),
    )
    module = ModuleType('osgeo')
    module.ogr = fake_ogr
    monkeypatch.setitem(sys.modules, 'osgeo', module)
    result = load_quick_preview(Path('fake.gpkg'))
    assert result['total'] == 2
    assert result['loaded'] == 1
    assert result['features'][0]['canonical_osm_id'] == 'way/42'
    assert result['features'][0]['tags']['highway'] == 'residential'
    assert result['features'][0]['coordinates'] == [(-46.6, -23.5), (-46.61, -23.51)]
    assert result['bounds'] == [-46.61, -23.51, -46.6, -23.5]
