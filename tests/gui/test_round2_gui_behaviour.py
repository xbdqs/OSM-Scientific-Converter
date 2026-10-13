"""Run on Windows with PySide6 + pytest-qt; not executable in a Qt-free CI."""
from osm_scientific_converter.gui.main_window import SelectionPage, PreviewPage
from osm_scientific_converter.gui.workers import CoreWorker


def test_inventory_filter_is_distinct_from_enforced_classification_scope(qtbot):
    page = SelectionPage()
    qtbot.addWidget(page)
    assert page.selected_classification_source_layers() is None
    # The inventory browsing selector and classification source-layer selector
    # must be independent; 'line' group includes more than GDAL 'lines'.
    page.geometry_filter.setCurrentText("line")
    assert page.selected_classification_source_layers() is None
    page.classification_source_layer.setCurrentText("lines")
    assert page.selected_classification_source_layers() == ("lines",)
    page.set_classification_source_layers(["multilinestrings"])
    assert page.selected_classification_source_layers() == ("multilinestrings",)


def test_worker_does_not_invent_percentages_from_logs(qtbot):
    worker = CoreWorker("test", lambda progress: None)
    received = []
    worker.signals.progress.connect(lambda message, percent: received.append((message, percent)))
    worker._progress("[3/6] Importing features")
    worker._progress('@@PROGRESS {"processed": 250, "total": 1000, "operation":"classify"}')
    worker._progress("Classified 250 objects")
    assert [percent for _, percent in received] == [-1, 25, -1]


def test_preview_exposes_zoom_and_fit_controls(qtbot):
    page = PreviewPage()
    qtbot.addWidget(page)
    assert page.fit_map.text() == "Fit extent"
    assert page.zoom_selected.text() == "Zoom to selected feature"
    assert page.zoom_in.text() == "Zoom in"
    assert page.zoom_out.text() == "Zoom out"
