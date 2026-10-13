"""Regression tests for picking thin road linework in the Qt quick preview."""
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtWidgets import QGraphicsView

from osm_scientific_converter.gui.main_window import MapView, PreviewPage


def road_data():
    return {
        "total": 2, "loaded": 2, "bounds": [0, 0, 10, 10],
        "features": [
            {"category": "pedestrian", "geometry_group": "line",
             "coordinates": [[0, 0], [10, 10]],
             "tags": {"highway": "pedestrian", "name": "Main footpath"}},
            {"category": "residential_and_service", "geometry_group": "line",
             "coordinates": [[0, 10], [10, 0]],
             "tags": {"highway": "residential", "name": "Local street"}},
        ],
    }


def test_map_click_near_thin_line_selects_correct_osm_tags(qtbot):
    view = MapView()
    qtbot.addWidget(view)
    view.resize(720, 520)
    view.show()
    view.populate(road_data())
    picked = []
    view.featureSelected.connect(lambda feature: picked.append(feature))
    assert view.dragMode() == QGraphicsView.ScrollHandDrag
    # At (250,525) scene units only the pedestrian diagonal is nearby;
    # offset the actual click 6 display pixels so this tests hit tolerance.
    point = view.mapFromScene(QPointF(250, 525)) + QPoint(0, 6)
    qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=point)
    assert picked and picked[-1]["tags"]["highway"] == "pedestrian"
    assert len(view.scene().selectedItems()) == 1


def test_preview_map_click_fills_complete_tags_panel(qtbot):
    page = PreviewPage()
    qtbot.addWidget(page)
    page.resize(1200, 700)
    page.show()
    page.populate_quick_preview(road_data())
    qtbot.wait(20)  # permit queued post-layout fit
    point = page.map.mapFromScene(QPointF(250, 525))
    qtbot.mouseClick(page.map.viewport(), Qt.LeftButton, pos=point)
    assert '"highway": "pedestrian"' in page.tags.toPlainText()
    assert 'Main footpath' in page.tags.toPlainText()
    # Category highlighting is not the same as selecting a map feature.
    page.layers.setCurrentRow(0)
    assert 'Main footpath' in page.tags.toPlainText()


def test_click_on_empty_map_clears_selection(qtbot):
    view = MapView()
    qtbot.addWidget(view)
    view.resize(720, 520)
    view.show()
    view.populate(road_data())
    picked = []
    view.featureSelected.connect(lambda feature: picked.append(feature))
    qtbot.mouseClick(view.viewport(), Qt.LeftButton,
                     pos=view.mapFromScene(QPointF(250, 525)))
    assert picked and picked[-1]
    qtbot.mouseClick(view.viewport(), Qt.LeftButton,
                     pos=view.mapFromScene(QPointF(100, 100)))
    assert not view.scene().selectedItems()
    assert picked[-1] == {}
