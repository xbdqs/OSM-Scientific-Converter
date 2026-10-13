from __future__ import annotations

import shutil
from pathlib import Path
import pytest

pytest.importorskip('PySide6')
from osm_scientific_converter.gui.workers import quick_highway_worker


@pytest.mark.skipif(not shutil.which('ogr2ogr'), reason='Requires ogr2ogr on the configured Windows GDAL environment')
def test_gui_worker_uses_real_quick_cli_without_scan(tmp_path):
    root = Path(__file__).resolve().parents[2]
    input_file = root / 'examples' / 'round2_roads_small.osm'
    rules = root / 'src/osm_scientific_converter/resources/profiles/reviewer_roads_lines_v1.json'
    destination = tmp_path / 'gui_quick_roads.gpkg'
    worker = quick_highway_worker(input_file, rules, destination)
    result = worker.function(lambda message: None)
    assert result['audit']['status'] == 'success'
    assert result['audit']['feature_count'] == 4
    assert result['audit']['source_layer'] == 'lines'
    assert destination.is_file()
    assert Path(str(destination) + '.audit.json').is_file()
    # Exercise the actual GDAL/OGR GeoPackage preview on the Windows runtime,
    # not just the export worker. Regression for missing ogr.wkbFlatten.
    from osm_scientific_converter.gui.quick_preview import load_quick_preview
    preview = load_quick_preview(destination, limit=400)
    assert preview['loaded'] == 4
    assert preview['total'] == 4
    assert {f['geometry_group'] for f in preview['features']} == {'line'}
    assert all(len(f['coordinates']) >= 2 for f in preview['features'])
    assert len({f['canonical_osm_id'] for f in preview['features']}) == 4
