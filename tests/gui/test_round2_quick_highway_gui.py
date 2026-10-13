from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog
from osm_scientific_converter.gui.main_window import MainWindow
from osm_scientific_converter.gui.quick_highway import QuickHighwayDialog, packaged_road_profile


def test_quick_dialog_requires_no_scanned_project(qtbot, tmp_path):
    source = tmp_path / 'tiny.osm'
    source.write_text('<osm version="0.6"/>', encoding='utf-8')
    dialog = QuickHighwayDialog(str(source))
    qtbot.addWidget(dialog)
    assert 'VALID reviewed subset' in dialog.validation.toPlainText()
    assert dialog.output_edit.text().endswith('tiny_quick_roads.gpkg')
    assert Path(packaged_road_profile()).is_file()
    qtbot.mouseClick(dialog.run_button, Qt.LeftButton)
    assert dialog.result() == QDialog.Accepted
    src, profile, out = dialog.arguments()
    assert src == source.resolve()
    assert out.suffix == '.gpkg'
    assert profile.is_file()


def test_gui_has_separate_quick_road_button_and_preview(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.stack.count() == 5
    assert window.pages[0].quick_button.isEnabled()
    assert 'no scan' in window.pages[0].quick_button.text().lower()
    assert not window.pages[3].quick_preview_button.isEnabled()
    assert window.progress.format() == 'Idle — no active task'


def test_quick_complete_enables_bounded_preview_without_full_project(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    # Suppress auto-loading actual GeoPackage in a fast GUI state test.
    monkeypatch.setattr(window, 'load_quick_map_preview', lambda: None)
    output = tmp_path / 'roads.gpkg'
    audit = {'status':'success', 'feature_count': 4, 'source_layer':'lines', 'scope_limitations':['No full inventory']}
    window._quick_extraction_done({'output':str(output), 'audit':audit})
    assert window.quick_output_path == output
    assert window.steps.currentRow() == 3
    assert window.pages[3].quick_preview_button.isEnabled()
    assert not window.pages[3].run_quality.isEnabled()
    assert not window.pages[4].export_button.isEnabled()
    assert 'output already created' in window.pages[4].quick_result_facts.text()
    assert window.pages[4].form_box.isHidden()
    assert not window.pages[4].quick_result_panel.isHidden()
    assert window.pages[4].export_button.isHidden()
    assert 'full OSM vocabulary inventory' in window.pages[4].quick_result_limitations.text()


def test_quick_result_contains_real_counts_and_reverts_to_full_export(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, 'load_quick_map_preview', lambda: None)
    path = tmp_path / 'results.gpkg'
    audit = {
        'status': 'success', 'feature_count': 4,
        'source_layer': 'lines', 'tag_key': 'highway',
        'profile_id': 'reviewer_roads_lines_v1',
        'category_counts': {
            'motorways_and_trunks': 1, 'pedestrian': 1,
            'primary_secondary_tertiary': 1, 'residential_and_service': 1,
        },
        'timings_seconds': {'total_before_final_copy': .418},
    }
    window._quick_extraction_done({'output': str(path), 'audit': audit})
    page = window.pages[4]
    assert page.title.text() == 'Step 5 · Quick extraction result'
    assert window.steps.item(4).text() == '5  Quick result'
    assert 'Exported road features: 4' in page.quick_result_facts.text()
    assert 'primary_secondary_tertiary: 1' in page.quick_result_facts.text()
    assert 'Internal processing before final copy: 0.418 s' in page.quick_result_facts.text()
    assert str(path) in page.quick_result_facts.text()
    assert 'already exported' not in page.summary.toPlainText().lower()
    assert page.open_folder.isEnabled()
    assert page.export_button.isHidden()
    assert page.form_box.isHidden()

    page.reset_quick_result()
    assert page.title.text() == 'Step 5 · Export'
    assert page.quick_result_panel.isHidden()
    assert not page.form_box.isHidden()
    assert not page.export_button.isHidden()
    assert page.export_button.isEnabled()
    assert not page.open_folder.isEnabled()
    assert not page.output.text()


def test_quick_result_cannot_trigger_full_export_button(qtbot, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, 'load_quick_map_preview', lambda: None)
    events = []
    window.pages[4].exportRequested.connect(lambda *args: events.append(args))
    window._quick_extraction_done({
        'output': str(tmp_path / 'result.gpkg'),
        'audit': {'status': 'success', 'feature_count': 4,
                  'category_counts': {'residential_and_service': 4}}
    })
    window.pages[4].export_button.click()
    assert not events
    assert not window.pages[4].export_button.isEnabled()
