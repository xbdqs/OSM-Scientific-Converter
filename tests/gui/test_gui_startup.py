from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent

from osm_scientific_converter.gui.main_window import AdvancedProfileDialog, DropLineEdit, MainWindow


def test_gui_starts_with_five_steps(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.stack.count() == 5
    assert window.steps.count() == 5
    assert "0.4.1" in window.windowTitle()


def test_profile_tree_and_custom_rule_builder(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    page = window.pages[2]
    page.profile_combo.setCurrentText("pipeline")
    assert page.profile_tree.topLevelItemCount() >= 10
    page.rule_id.setText("gui_test")
    page.rule_category.setText("test_category")
    page.rule_key.setText("power")
    page.rule_operator.setCurrentText("equals")
    page.rule_value.setText("substation")
    qtbot.mouseClick(page.build_rule, Qt.LeftButton)
    text = page.rule_preview.toPlainText()
    assert '"id": "gui_custom"' in text
    assert '"value": "substation"' in text


def test_high_dpi_style_and_auto_repair_default(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    assert window.pages[3].auto_repair.isChecked() is False
    assert window.pages[3].auto_repair.isEnabled() is False
    assert window.styleSheet() or window.parent() is None


def test_osm_file_drop_emits_path(qtbot, tmp_path):
    source = tmp_path / "拖放数据.osm"
    source.write_text("<osm version='0.6'/>", encoding="utf-8")
    edit = DropLineEdit(); qtbot.addWidget(edit)
    mime = QMimeData(); mime.setUrls([QUrl.fromLocalFile(str(source))])
    event = QDropEvent(QPointF(2, 2), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    with qtbot.waitSignal(edit.fileDropped, timeout=1000) as signal:
        edit.dropEvent(event)
    assert Path(signal.args[0]) == source


def test_advanced_json_editor_validates_nested_profile_and_reports_errors(qtbot):
    valid = """{
      "schema_version":"1.0","id":"advanced","attributes":["power"],
      "rules":[{"id":"nested","category":"power","expression":{"all":[
        {"key":"power","op":"exists"},{"none":[{"key":"power","op":"equals","value":"minor_line"}]}
      ]}}]
    }"""
    dialog = AdvancedProfileDialog(valid)
    qtbot.addWidget(dialog)
    assert dialog.validate_document() is True
    assert "Validation passed" in dialog.validation.toPlainText()
    assert '"nested_logical_rules": 1' in dialog.validation.toPlainText()
    dialog.editor.setPlainText('{"schema_version":"1.0"}')
    assert dialog.validate_document() is False
    assert "Validation failed" in dialog.validation.toPlainText()


def test_export_field_controls_lock_traceability_and_offer_profile_subset(qtbot):
    window = MainWindow(); qtbot.addWidget(window)
    page = window.pages[4]
    page.set_fields(["voltage", "operator"])
    assert page.fields.count() == 12
    assert not bool(page.fields.item(0).flags() & Qt.ItemIsUserCheckable)
    assert page.fields.item(10).data(Qt.UserRole) == "voltage"
    page.fields.item(10).setCheckState(Qt.Unchecked)
    selected = [page.fields.item(i).data(Qt.UserRole) for i in range(page.fields.count()) if page.fields.item(i).checkState() == Qt.Checked]
    assert "osm_id" in selected and "voltage" not in selected and "operator" in selected
