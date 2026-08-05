from __future__ import annotations

from PySide6.QtCore import Qt

from osm_scientific_converter.gui.main_window import MapView


def test_map_preview_renders_and_filters(qtbot):
    view = MapView(); qtbot.addWidget(view)
    data = {
        "total": 2,
        "loaded": 2,
        "bounds": [0, 0, 10, 10],
        "features": [
            {"osm_id": "node/1", "category": "point", "geometry_group": "point", "coordinates": [[1, 1]], "tags": {"name": "中文"}},
            {"osm_id": "way/2", "category": "line", "geometry_group": "line", "coordinates": [[0, 0], [10, 10]], "tags": {"name": "한국어"}},
        ],
    }
    view.populate(data)
    assert len(view.scene().items()) == 2
    view.set_category_visible("line", False)
    assert len([item for item in view.scene().items() if item.data(1) == "line" and item.isVisible()]) == 0
