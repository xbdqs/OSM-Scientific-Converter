from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import psutil
from PySide6.QtCore import QCoreApplication, QPointF, QRectF, Qt, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout,
    QGraphicsPathItem, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPushButton,
    QProgressBar, QPlainTextEdit, QSpinBox, QSplitter, QStackedWidget, QStatusBar, QTableWidget,
    QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from osm_scientific_converter import __version__
from osm_scientific_converter.core.environment import inspect_environment
from osm_scientific_converter.core.input_inspector import inspect_input
from osm_scientific_converter.core.profiles import (
    inspect_builtin_profile,
    list_builtin_profiles,
    resolve_profile,
    resolve_profile_text,
    summarize_profile,
)
from osm_scientific_converter.core.exporter import REQUIRED_TRACEABILITY_FIELDS
from osm_scientific_converter.gui.inventory import InventoryRepository
from osm_scientific_converter.gui.project_state import GuiProject
from osm_scientific_converter.gui.quality import load_preview, run_quality_checks
from osm_scientific_converter.gui.workers import CoreWorker, classify_worker, export_worker, scan_worker


COLORS = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00", "#56B4E9", "#F0E442", "#666666"]


class DropLineEdit(QLineEdit):
    fileDropped = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setPlaceholderText("Drop an .osm/.pbf file here, or click Browse…")

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if len(urls) == 1 and Path(urls[0].toLocalFile()).suffix.lower() in {".osm", ".pbf"}:
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        path = event.mimeData().urls()[0].toLocalFile()
        self.setText(path)
        self.fileDropped.emit(path)
        event.acceptProposedAction()


class AdvancedProfileDialog(QDialog):
    """Editable advanced JSON profile with core-validator feedback."""

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Advanced JSON profile")
        self.resize(900, 700)
        self.validated_text = ""
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Edit a complete JSON profile with nested all / any / none expressions. Validation by the core rule engine is required before use."))
        self.editor = QPlainTextEdit(text)
        layout.addWidget(self.editor)
        layout.addWidget(QLabel("Validation result and parsed summary"))
        self.validation = QPlainTextEdit()
        self.validation.setReadOnly(True)
        self.validation.setMaximumHeight(180)
        layout.addWidget(self.validation)
        actions = QHBoxLayout()
        self.validate_button = QPushButton("Validate")
        self.use_button = QPushButton("Use validated profile")
        self.use_button.setEnabled(False)
        cancel = QPushButton("Cancel")
        actions.addStretch(); actions.addWidget(self.validate_button); actions.addWidget(self.use_button); actions.addWidget(cancel)
        layout.addLayout(actions)
        self.validate_button.clicked.connect(self.validate_document)
        self.use_button.clicked.connect(self.use_validated_document)
        cancel.clicked.connect(self.reject)
        self.editor.textChanged.connect(lambda: self.use_button.setEnabled(False))

    def validate_document(self) -> bool:
        try:
            resolved = resolve_profile_text(self.editor.toPlainText())
            summary = summarize_profile(resolved.data)
        except Exception as error:
            self.validated_text = ""
            self.validation.setPlainText(f"Validation failed\n{type(error).__name__}: {error}")
            self.use_button.setEnabled(False)
            return False
        self.validated_text = self.editor.toPlainText()
        self.validation.setPlainText("Validation passed\n" + json.dumps({**summary, "profile_sha256": resolved.sha256}, ensure_ascii=False, indent=2))
        self.use_button.setEnabled(True)
        return True

    def use_validated_document(self) -> None:
        if self.validated_text == self.editor.toPlainText() or self.validate_document():
            self.accept()


class InputPage(QWidget):
    inspectRequested = Signal(str)
    scanRequested = Signal(str, str, bool)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Step 1 · Input and environment")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        group = QGroupBox("Input")
        form = QFormLayout(group)
        input_row = QHBoxLayout()
        self.input_edit = DropLineEdit()
        browse_input = QPushButton("Browse")
        input_row.addWidget(self.input_edit)
        input_row.addWidget(browse_input)
        form.addRow("OSM file", input_row)
        project_row = QHBoxLayout()
        self.project_edit = QLineEdit()
        browse_project = QPushButton("Select")
        project_row.addWidget(self.project_edit)
        project_row.addWidget(browse_project)
        form.addRow("Project directory", project_row)
        self.keep_raw = QCheckBox("Keep raw master (required for classification and export)")
        self.keep_raw.setChecked(True)
        form.addRow("Scan options", self.keep_raw)
        self.metadata = QLabel("Input has not been inspected")
        self.metadata.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("File information", self.metadata)
        self.resources = QLabel()
        form.addRow("System resources", self.resources)
        self.environment = QPlainTextEdit()
        self.environment.setReadOnly(True)
        self.environment.setMaximumHeight(150)
        form.addRow("Environment check", self.environment)
        layout.addWidget(group)
        actions = QHBoxLayout()
        self.inspect_button = QPushButton("Inspect input and environment")
        self.scan_button = QPushButton("Start scan")
        self.scan_button.setObjectName("primaryButton")
        actions.addStretch()
        actions.addWidget(self.inspect_button)
        actions.addWidget(self.scan_button)
        layout.addLayout(actions)
        layout.addStretch()
        browse_input.clicked.connect(self._browse_input)
        browse_project.clicked.connect(self._browse_project)
        self.input_edit.fileDropped.connect(self.inspectRequested)
        self.inspect_button.clicked.connect(lambda: self.inspectRequested.emit(self.input_edit.text()))
        self.scan_button.clicked.connect(lambda: self.scanRequested.emit(self.input_edit.text(), self.project_edit.text(), self.keep_raw.isChecked()))
        self.refresh_resources()

    def _browse_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Select OSM data", "", "OSM data (*.osm *.pbf)")
        if path:
            self.input_edit.setText(path)
            self.inspectRequested.emit(path)

    def _browse_project(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select parent directory for the project")
        if path:
            default = Path(path) / (Path(self.input_edit.text()).stem + "_project_v041")
            self.project_edit.setText(str(default))

    def refresh_resources(self) -> None:
        memory = psutil.virtual_memory()
        target = Path(self.project_edit.text()).parent if self.project_edit.text() else Path.cwd()
        try:
            disk = shutil.disk_usage(target if target.exists() else target.parent)
            disk_text = f"Disk available {disk.free / 2**30:.1f} GiB"
        except OSError:
            disk_text = "Disk information unavailable"
        self.resources.setText(f"Memory available {memory.available / 2**30:.1f} GiB / {memory.total / 2**30:.1f} GiB；{disk_text}")


class OverviewPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Step 2 · Data overview (read-only, lazy queries)")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        self.summary = QLabel("The overview will appear after scanning")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        splitter = QSplitter()
        self.layers = QTableWidget(0, 2)
        self.layers.setHorizontalHeaderLabels(["OSM layer", "Objects"])
        self.top_keys = QTableWidget(0, 3)
        self.top_keys.setHorizontalHeaderLabels(["Key", "Count", "Unique values"])
        self.lifecycle = QTableWidget(0, 2)
        self.lifecycle.setHorizontalHeaderLabels(["Lifecycle", "Count"])
        splitter.addWidget(self.layers)
        splitter.addWidget(self.top_keys)
        splitter.addWidget(self.lifecycle)
        layout.addWidget(splitter)
        self.anomalies = QPlainTextEdit()
        self.anomalies.setReadOnly(True)
        self.anomalies.setMaximumHeight(130)
        layout.addWidget(QLabel("Parsing anomalies / GDAL warnings"))
        layout.addWidget(self.anomalies)

    def populate(self, project: Path, repository: InventoryRepository) -> None:
        manifest = json.loads((project / "project_manifest.json").read_text(encoding="utf-8-sig"))
        raw_inventory = json.loads((project / "raw_inventory.json").read_text(encoding="utf-8-sig"))
        layer_features = {item["name"]: int(item["feature_count"]) for item in raw_inventory.get("layers", [])}
        data = repository.summary()
        self.summary.setText(
            f"Objects {manifest.get('counts', {}).get('features', 0):,}；unique keys {data['unique_keys']:,}；"
            f"unique key/value pairs {data['unique_key_values']:,}; lifecycle records {data['lifecycle_rows']:,}."
        )
        self.layers.setRowCount(0)
        for name in ("points", "lines", "multilinestrings", "multipolygons", "other_relations"):
            row = self.layers.rowCount(); self.layers.insertRow(row)
            self.layers.setItem(row, 0, QTableWidgetItem(name))
            self.layers.setItem(row, 1, QTableWidgetItem(f"{layer_features.get(name, 0):,}"))
        keys = repository.keys(limit=50)
        self.top_keys.setRowCount(0)
        for item in keys:
            row = self.top_keys.rowCount(); self.top_keys.insertRow(row)
            self.top_keys.setItem(row, 0, QTableWidgetItem(item["key"]))
            self.top_keys.setItem(row, 1, QTableWidgetItem(f"{item['count']:,}"))
            self.top_keys.setItem(row, 2, QTableWidgetItem(f"{item['values_count']:,}"))
        self.lifecycle.setRowCount(0)
        for item in repository.lifecycle_states():
            row = self.lifecycle.rowCount(); self.lifecycle.insertRow(row)
            self.lifecycle.setItem(row, 0, QTableWidgetItem(item["normalized_state"]))
            self.lifecycle.setItem(row, 1, QTableWidgetItem(f"{item['count']:,}"))
        warnings = manifest.get("warnings", [])
        self.anomalies.setPlainText("\n".join(f"{item.get('count', 1)} × {item.get('message', item)}" for item in warnings) or "No scan warnings were recorded.")


class SelectionPage(QWidget):
    classifyRequested = Signal(str, str)
    selectedValuesChanged = Signal(dict)
    profileLoaded = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self.repository: InventoryRepository | None = None
        self.current_page = 0
        self.current_key = ""
        self.selected_values_by_key: dict[str, set[str]] = {}
        self._loading_values = False
        layout = QVBoxLayout(self)
        title = QLabel("Step 3 · Feature selection")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        splitter = QSplitter()
        profile_box = QGroupBox("Option 1 · Built-in thematic profiles")
        profile_layout = QVBoxLayout(profile_box)
        self.profile_combo = QComboBox()
        self.profile_tree = QTreeWidget()
        self.profile_tree.setHeaderLabels(["Category / rule", "Default export"])
        profile_layout.addWidget(self.profile_combo)
        profile_layout.addWidget(self.profile_tree)
        splitter.addWidget(profile_box)

        dynamic_box = QGroupBox("Option 2 · Dynamic key/value inventory (lazy + paginated)")
        dynamic_layout = QVBoxLayout(dynamic_box)
        filters = QHBoxLayout()
        self.key_search = QLineEdit(); self.key_search.setPlaceholderText("Search keys")
        self.geometry_filter = QComboBox(); self.geometry_filter.addItems(["All geometry", "point", "line", "polygon", "relation"])
        self.lifecycle_filter = QComboBox(); self.lifecycle_filter.addItem("All lifecycle", "")
        self.load_keys = QPushButton("Load keys")
        filters.addWidget(self.key_search); filters.addWidget(self.geometry_filter); filters.addWidget(self.lifecycle_filter); filters.addWidget(self.load_keys)
        dynamic_layout.addLayout(filters)
        self.key_tree = QTreeWidget(); self.key_tree.setHeaderLabels(["Key", "Count", "Values"])
        dynamic_layout.addWidget(self.key_tree)
        values_row = QHBoxLayout()
        self.value_search = QLineEdit(); self.value_search.setPlaceholderText("Search values for the current key")
        self.previous_page = QPushButton("Previous page"); self.next_page = QPushButton("Next page")
        self.page_label = QLabel("0 / 0")
        values_row.addWidget(self.value_search); values_row.addWidget(self.previous_page); values_row.addWidget(self.page_label); values_row.addWidget(self.next_page)
        dynamic_layout.addLayout(values_row)
        self.value_table = QTableWidget(0, 3); self.value_table.setHorizontalHeaderLabels(["Select", "Value", "Count"])
        dynamic_layout.addWidget(self.value_table)
        selection_actions = QHBoxLayout()
        self.selected_count = QLabel("Selected: 0")
        self.clear_current = QPushButton("Clear current key")
        self.clear_all = QPushButton("Clear all")
        selection_actions.addWidget(self.selected_count); selection_actions.addStretch(); selection_actions.addWidget(self.clear_current); selection_actions.addWidget(self.clear_all)
        dynamic_layout.addLayout(selection_actions)
        self.use_dynamic = QPushButton("Create a custom rule from selected key/value pairs")
        dynamic_layout.addWidget(self.use_dynamic)
        splitter.addWidget(dynamic_box)

        custom_box = QGroupBox("Option 3 · Simple rule builder / advanced JSON")
        custom_form = QFormLayout(custom_box)
        self.rule_id = QLineEdit("gui_custom_rule")
        self.rule_category = QLineEdit("custom")
        self.rule_key = QLineEdit("power")
        self.rule_operator = QComboBox(); self.rule_operator.addItems(["equals", "in", "contains", "regex", "exists", "numeric_any_gte"])
        self.rule_value = QLineEdit("substation")
        self.rule_preview = QPlainTextEdit(); self.rule_preview.setReadOnly(True); self.rule_preview.setMaximumHeight(220)
        self.build_rule = QPushButton("Build and validate rule")
        self.load_advanced = QPushButton("Load advanced JSON profile")
        custom_form.addRow("Rule ID", self.rule_id); custom_form.addRow("Category", self.rule_category); custom_form.addRow("Key", self.rule_key)
        custom_form.addRow("Operator", self.rule_operator); custom_form.addRow("Value", self.rule_value); custom_form.addRow(self.build_rule); custom_form.addRow(self.load_advanced); custom_form.addRow(self.rule_preview)
        splitter.addWidget(custom_box)
        splitter.setSizes([280, 520, 320])
        layout.addWidget(splitter)
        action = QHBoxLayout(); self.classify_button = QPushButton("Run classification"); self.classify_button.setObjectName("primaryButton")
        action.addStretch(); action.addWidget(self.classify_button); layout.addLayout(action)
        self.load_keys.clicked.connect(self.reload_keys)
        self.key_tree.itemClicked.connect(self._key_clicked)
        self.previous_page.clicked.connect(lambda: self._change_page(-1))
        self.next_page.clicked.connect(lambda: self._change_page(1))
        self.value_search.returnPressed.connect(lambda: self.load_values(0))
        self.value_table.itemChanged.connect(self._value_changed)
        self.clear_current.clicked.connect(self.clear_current_selection)
        self.clear_all.clicked.connect(self.clear_all_selections)
        self.build_rule.clicked.connect(self.build_custom_profile)
        self.load_advanced.clicked.connect(self.load_advanced_profile)
        self.use_dynamic.clicked.connect(self.build_dynamic_profile)
        self.profile_combo.currentTextChanged.connect(self.load_profile)
        self.classify_button.clicked.connect(self._request_classify)
        for profile in list_builtin_profiles():
            self.profile_combo.addItem(profile["id"])

    def set_repository(self, repository: InventoryRepository) -> None:
        self.repository = repository
        self.lifecycle_filter.clear(); self.lifecycle_filter.addItem("All lifecycle", "")
        for item in repository.lifecycle_states():
            self.lifecycle_filter.addItem(f"{item['normalized_state']} ({item['count']:,})", item["normalized_state"])
        QTimer.singleShot(0, self.reload_keys)

    def load_profile(self, profile_id: str) -> None:
        if not profile_id:
            return
        data = inspect_builtin_profile(profile_id)
        self.rule_preview.clear()
        self.profile_tree.clear()
        categories: dict[str, list[dict[str, Any]]] = {}
        for rule in data["rules"]:
            categories.setdefault(rule["category"], []).append(rule)
        for category, rules in sorted(categories.items()):
            top = QTreeWidgetItem([category, ""]); top.setFlags(top.flags() | Qt.ItemIsUserCheckable)
            top.setCheckState(0, Qt.Checked if any(rule.get("default_export", True) for rule in rules) else Qt.Unchecked)
            for rule in rules:
                QTreeWidgetItem(top, [rule["id"], "Yes" if rule.get("default_export", True) else "No"])
            self.profile_tree.addTopLevelItem(top)
        self.profile_tree.expandAll()
        self.profileLoaded.emit([str(value) for value in data.get("attributes", [])])

    def reload_keys(self) -> None:
        if not self.repository:
            return
        self.key_tree.clear()
        geometry = "" if self.geometry_filter.currentIndex() == 0 else self.geometry_filter.currentText()
        lifecycle = self.lifecycle_filter.currentData() or ""
        for item in self.repository.keys(search=self.key_search.text(), geometry=geometry, lifecycle=lifecycle, limit=500):
            node = QTreeWidgetItem([item["key"], f"{item['count']:,}", f"{item['values_count']:,}"])
            node.setData(0, Qt.UserRole, item["key"])
            self.key_tree.addTopLevelItem(node)

    def _key_clicked(self, item: QTreeWidgetItem) -> None:
        self.current_key = item.data(0, Qt.UserRole) or item.text(0)
        self.load_values(0)

    def load_values(self, page: int) -> None:
        if not self.repository or not self.current_key:
            return
        geometry = "" if self.geometry_filter.currentIndex() == 0 else self.geometry_filter.currentText()
        data = self.repository.values(self.current_key, search=self.value_search.text(), geometry=geometry, page=max(0, page), page_size=100)
        self.current_page = data["page"]
        pages = max(1, (data["total"] + data["page_size"] - 1) // data["page_size"])
        self.page_label.setText(f"{self.current_page + 1} / {pages} · {data['total']:,}")
        self._loading_values = True
        self.value_table.setRowCount(0)
        selected = self.selected_values_by_key.get(self.current_key, set())
        for value in data["rows"]:
            row = self.value_table.rowCount(); self.value_table.insertRow(row)
            checkbox = QTableWidgetItem(); checkbox.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable); checkbox.setCheckState(Qt.Checked if value["value"] in selected else Qt.Unchecked)
            self.value_table.setItem(row, 0, checkbox); self.value_table.setItem(row, 1, QTableWidgetItem(value["value"])); self.value_table.setItem(row, 2, QTableWidgetItem(f"{value['count']:,}"))
        self._loading_values = False
        self._update_selected_count()

    def _value_changed(self, item: QTableWidgetItem) -> None:
        if self._loading_values or item.column() != 0 or not self.current_key:
            return
        value_item = self.value_table.item(item.row(), 1)
        if value_item is None:
            return
        selected = self.selected_values_by_key.setdefault(self.current_key, set())
        if item.checkState() == Qt.Checked:
            selected.add(value_item.text())
        else:
            selected.discard(value_item.text())
        if not selected:
            self.selected_values_by_key.pop(self.current_key, None)
        self._update_selected_count()
        self.selectedValuesChanged.emit(self.selected_tag_values())

    def _update_selected_count(self) -> None:
        current = len(self.selected_values_by_key.get(self.current_key, set()))
        total = sum(len(values) for values in self.selected_values_by_key.values())
        self.selected_count.setText(f"Current key: {current} · selected overall: {total}")

    def clear_current_selection(self) -> None:
        if self.current_key:
            self.selected_values_by_key.pop(self.current_key, None)
            self.load_values(self.current_page)
            self.selectedValuesChanged.emit(self.selected_tag_values())

    def clear_all_selections(self) -> None:
        self.selected_values_by_key.clear()
        if self.current_key:
            self.load_values(self.current_page)
        self._update_selected_count()
        self.selectedValuesChanged.emit({})

    def selected_tag_values(self) -> dict[str, list[str]]:
        return {key: sorted(values) for key, values in sorted(self.selected_values_by_key.items()) if values}

    def set_selected_tag_values(self, values: dict[str, list[str]]) -> None:
        self.selected_values_by_key = {str(key): {str(value) for value in selected} for key, selected in values.items() if selected}
        if self.current_key:
            self.load_values(self.current_page)
        self._update_selected_count()

    def _change_page(self, delta: int) -> None:
        self.load_values(max(0, self.current_page + delta))

    def selected_categories(self) -> list[str]:
        return [self.profile_tree.topLevelItem(i).text(0) for i in range(self.profile_tree.topLevelItemCount()) if self.profile_tree.topLevelItem(i).checkState(0) == Qt.Checked]

    def _profile_document(self, expressions: list[dict[str, Any]], category: str | None = None) -> dict[str, Any]:
        rules = []
        for index, expression in enumerate(expressions):
            rules.append({"id": self.rule_id.text().strip() + (f"_{index+1}" if len(expressions) > 1 else ""), "category": category or self.rule_category.text().strip(), "expression": expression})
        return {"schema_version": "1.0", "id": "gui_custom", "label_en": "GUI custom profile", "label_zh": "GUI custom profile", "attributes": sorted({self.rule_key.text().strip()}), "rules": rules}

    def build_custom_profile(self) -> None:
        value: Any = self.rule_value.text()
        if self.rule_operator.currentText() == "in":
            value = [part.strip() for part in self.rule_value.text().split(",") if part.strip()]
        elif self.rule_operator.currentText() == "numeric_any_gte":
            value = float(value)
        expression = {"key": self.rule_key.text().strip(), "op": self.rule_operator.currentText()}
        if self.rule_operator.currentText() != "exists":
            expression["value"] = value
        document = self._profile_document([expression])
        text = json.dumps(document, ensure_ascii=False, indent=2)
        resolve_profile_text(text)
        self.rule_preview.setPlainText(text)

    def build_dynamic_profile(self) -> None:
        values = sorted(self.selected_values_by_key.get(self.current_key, set()))
        if not self.current_key or not values:
            QMessageBox.warning(self, "Nothing selected", "Select a key and at least one value first.")
            return
        self.rule_key.setText(self.current_key); self.rule_operator.setCurrentText("in"); self.rule_value.setText(",".join(values))
        self.build_custom_profile()

    def load_advanced_profile(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Load advanced JSON profile", "", "JSON profile (*.json);;All files (*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8-sig")
        except OSError as error:
            QMessageBox.critical(self, "Read failed", str(error))
            return
        dialog = AdvancedProfileDialog(text, self)
        dialog.validate_document()
        if dialog.exec() == QDialog.Accepted:
            self.rule_preview.setPlainText(dialog.validated_text)

    def _request_classify(self) -> None:
        if self.rule_preview.toPlainText().strip():
            self.classifyRequested.emit("custom", self.rule_preview.toPlainText())
        else:
            self.classifyRequested.emit("builtin", self.profile_combo.currentText())


class MapView(QGraphicsView):
    featureSelected = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        self.setScene(QGraphicsScene(self))
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.scene().selectionChanged.connect(self._selection_changed)

    def wheelEvent(self, event) -> None:
        self.scale(1.2 if event.angleDelta().y() > 0 else 1 / 1.2, 1.2 if event.angleDelta().y() > 0 else 1 / 1.2)

    def _selection_changed(self) -> None:
        selected = self.scene().selectedItems()
        if selected:
            self.featureSelected.emit(selected[0].data(0) or {})

    def populate(self, data: dict[str, Any]) -> None:
        self.scene().clear()
        xmin, ymin, xmax, ymax = data["bounds"]
        width = max(xmax - xmin, 1e-12); height = max(ymax - ymin, 1e-12)
        categories = sorted({item["category"] for item in data["features"]})
        palette = {category: QColor(COLORS[index % len(COLORS)]) for index, category in enumerate(categories)}
        for feature in data["features"]:
            coordinates = feature["coordinates"]
            mapped = [QPointF((x - xmin) / width * 1000, (ymax - y) / height * 700) for x, y in coordinates]
            path = QPainterPath(mapped[0])
            for point in mapped[1:]: path.lineTo(point)
            if feature["geometry_group"] == "polygon" and len(mapped) > 2: path.closeSubpath()
            item = QGraphicsPathItem(path)
            color = palette[feature["category"]]
            item.setPen(QPen(color, 1.3)); item.setBrush(QColor(color.red(), color.green(), color.blue(), 45) if feature["geometry_group"] == "polygon" else Qt.NoBrush)
            if feature["geometry_group"] == "point":
                item.setPath(QPainterPath()); item = self.scene().addEllipse(mapped[0].x()-2.5, mapped[0].y()-2.5, 5, 5, QPen(color), color)
            else:
                self.scene().addItem(item)
            item.setFlag(item.GraphicsItemFlag.ItemIsSelectable, True); item.setData(0, feature); item.setData(1, feature["category"])
        self.scene().setSceneRect(QRectF(0, 0, 1000, 700)); self.fitInView(self.scene().sceneRect(), Qt.KeepAspectRatio)

    def set_category_visible(self, category: str, visible: bool) -> None:
        for item in self.scene().items():
            if item.data(1) == category: item.setVisible(visible)


class PreviewPage(QWidget):
    previewRequested = Signal()
    qualityRequested = Signal(dict)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Step 4 · Preview and quality checks")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        buttons = QHBoxLayout(); self.refresh = QPushButton("Load / refresh bounded preview"); self.run_quality = QPushButton("Run pre-export quality checks")
        self.auto_repair = QCheckBox("Automatic repair (disabled)"); self.auto_repair.setChecked(False); self.auto_repair.setEnabled(False)
        self.sample_size = QSpinBox(); self.sample_size.setRange(10, 1000); self.sample_size.setValue(50)
        buttons.addWidget(self.refresh); buttons.addWidget(self.run_quality); buttons.addWidget(QLabel("Sample size")); buttons.addWidget(self.sample_size); buttons.addWidget(self.auto_repair); buttons.addStretch(); layout.addLayout(buttons)
        splitter = QSplitter()
        left = QWidget(); left_layout = QVBoxLayout(left); self.layers = QListWidget(); left_layout.addWidget(QLabel("Category visibility")); left_layout.addWidget(self.layers)
        self.count_label = QLabel("Not loaded"); left_layout.addWidget(self.count_label)
        self.map = MapView()
        right = QWidget(); right_layout = QVBoxLayout(right); self.tags = QPlainTextEdit(); self.tags.setReadOnly(True); self.quality = QPlainTextEdit(); self.quality.setReadOnly(True)
        right_layout.addWidget(QLabel("Complete tags")); right_layout.addWidget(self.tags); right_layout.addWidget(QLabel("Quality report")); right_layout.addWidget(self.quality)
        splitter.addWidget(left); splitter.addWidget(self.map); splitter.addWidget(right); splitter.setSizes([180, 700, 330]); layout.addWidget(splitter)
        self.refresh.clicked.connect(self.previewRequested); self.run_quality.clicked.connect(lambda: self.qualityRequested.emit({"auto_repair": False, "sample_size": self.sample_size.value()}))
        self.map.featureSelected.connect(lambda feature: self.tags.setPlainText(json.dumps(feature.get("tags", {}), ensure_ascii=False, indent=2, sort_keys=True)))
        self.layers.itemChanged.connect(lambda item: self.map.set_category_visible(item.data(Qt.UserRole), item.checkState() == Qt.Checked))

    def populate_preview(self, data: dict[str, Any]) -> None:
        self.map.populate(data); self.layers.clear()
        for category in sorted({item["category"] for item in data["features"]}):
            item = QListWidgetItem(category); item.setData(Qt.UserRole, category); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked); self.layers.addItem(item)
        self.count_label.setText(f"Showing {data['loaded']:,} / {data['total']:,} classified objects (bounded preview)")


class ExportPage(QWidget):
    exportRequested = Signal(str, str, list, str, list)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        title = QLabel("Step 5 · Export")
        title.setObjectName("pageTitle"); layout.addWidget(title)
        form_box = QGroupBox("Export settings"); form = QFormLayout(form_box)
        self.format = QComboBox(); self.format.addItems(["GPKG", "GeoJSON", "Shapefile"])
        self.crs = QComboBox(); self.crs.addItem("EPSG:4326 · WGS 84 (native frozen-core CRS)", "EPSG:4326")
        self.categories = QListWidget(); self.categories.setMaximumHeight(180)
        self.fields = QListWidget(); self.fields.setMaximumHeight(180)
        self.set_fields([])
        output_row = QHBoxLayout(); self.output = QLineEdit(); browse = QPushButton("Browse"); output_row.addWidget(self.output); output_row.addWidget(browse)
        form.addRow("Format", self.format); form.addRow("Coordinate reference system", self.crs); form.addRow("Categories", self.categories); form.addRow("Fields (traceability fields are mandatory)", self.fields); form.addRow("Output location", output_row)
        layout.addWidget(form_box)
        self.estimate = QLabel("Estimated layers and feature counts will appear after classification"); self.estimate.setWordWrap(True); layout.addWidget(self.estimate)
        self.loss_warning = QLabel(); self.loss_warning.setWordWrap(True); layout.addWidget(self.loss_warning)
        self.summary = QPlainTextEdit(); self.summary.setReadOnly(True); layout.addWidget(self.summary)
        actions = QHBoxLayout(); self.export_button = QPushButton("Export in background"); self.export_button.setObjectName("primaryButton"); self.open_folder = QPushButton("Open output folder"); self.open_folder.setEnabled(False)
        actions.addStretch(); actions.addWidget(self.export_button); actions.addWidget(self.open_folder); layout.addLayout(actions)
        browse.clicked.connect(self._browse); self.export_button.clicked.connect(self._request); self.format.currentTextChanged.connect(self._format_changed); self._format_changed(self.format.currentText())
        self.open_folder.clicked.connect(self._open_output_folder)

    def _format_changed(self, value: str) -> None:
        self.loss_warning.setText("⚠ Shapefile may incur measurable losses because of 10-character field names, DBF text widths, and Unicode compatibility. Inspect the loss report after export." if value == "Shapefile" else "GPKG/GeoJSON retain complete tags_json. The audit reports observed truncation only and does not make a universal lossless claim.")

    def _browse(self) -> None:
        if self.format.currentText() == "GPKG":
            path, _ = QFileDialog.getSaveFileName(self, "Export GeoPackage", "", "GeoPackage (*.gpkg)")
        else:
            path = QFileDialog.getExistingDirectory(self, "Select export directory")
        if path: self.output.setText(path)

    def set_categories(self, counts: dict[str, int], selected: list[str] | None = None) -> None:
        self.categories.clear()
        selected_set = set(counts if selected is None else selected)
        for category, count in sorted(counts.items()):
            item = QListWidgetItem(f"{category} ({count:,})"); item.setData(Qt.UserRole, category); item.setFlags(item.flags() | Qt.ItemIsUserCheckable); item.setCheckState(Qt.Checked if category in selected_set else Qt.Unchecked); self.categories.addItem(item)
        self.estimate.setText(f"Estimated classification records: {sum(counts.values()):,}. GPKG counts unique objects; GeoJSON/Shapefile count object-category records.")

    def set_selected_categories(self, selected: list[str]) -> None:
        selected_set = set(selected)
        for index in range(self.categories.count()):
            item = self.categories.item(index)
            item.setCheckState(Qt.Checked if item.data(Qt.UserRole) in selected_set else Qt.Unchecked)

    def selected_categories(self) -> list[str]:
        return [self.categories.item(index).data(Qt.UserRole) for index in range(self.categories.count()) if self.categories.item(index).checkState() == Qt.Checked]

    def set_fields(self, profile_attributes: list[str], selected: list[str] | None = None) -> None:
        self.fields.clear()
        selected_set = set(profile_attributes if selected is None else selected)
        for field in REQUIRED_TRACEABILITY_FIELDS:
            item = QListWidgetItem(f"{field} (required)")
            item.setData(Qt.UserRole, field)
            item.setFlags(Qt.ItemIsEnabled)
            item.setCheckState(Qt.Checked)
            self.fields.addItem(item)
        for field in profile_attributes:
            item = QListWidgetItem(field)
            item.setData(Qt.UserRole, field)
            item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if field in selected_set else Qt.Unchecked)
            self.fields.addItem(item)

    def _request(self) -> None:
        categories = self.selected_categories()
        fields = [self.fields.item(i).data(Qt.UserRole) for i in range(self.fields.count()) if self.fields.item(i).checkState() == Qt.Checked]
        self.exportRequested.emit(self.format.currentText(), self.output.text(), categories, self.crs.currentData(), fields)

    def _open_output_folder(self) -> None:
        if self.output.text():
            path = Path(self.output.text())
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path if path.is_dir() else path.parent)))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"OSM Scientific Converter {__version__}")
        self.resize(1500, 920)
        self.state = GuiProject()
        self.repository: InventoryRepository | None = None
        self.thread_pool = QThreadPool.globalInstance()
        self.current_worker: CoreWorker | None = None
        self._success_callback: Callable[[Any], None] | None = None
        self.pages = [InputPage(), OverviewPage(), SelectionPage(), PreviewPage(), ExportPage()]
        central = QWidget(); layout = QHBoxLayout(central); self.steps = QListWidget(); self.steps.setFixedWidth(205)
        for text in ("1  Input & environment", "2  Data overview", "3  Feature selection", "4  Preview & quality", "5  Export"):
            self.steps.addItem(text)
        self.stack = QStackedWidget()
        for page in self.pages: self.stack.addWidget(page)
        layout.addWidget(self.steps); layout.addWidget(self.stack); self.setCentralWidget(central)
        self.steps.currentRowChanged.connect(self.stack.setCurrentIndex); self.steps.setCurrentRow(0)
        self._build_menu(); self._build_task_panel(); self.setStatusBar(QStatusBar())
        self.pages[0].inspectRequested.connect(self.inspect_input); self.pages[0].scanRequested.connect(self.run_scan)
        self.pages[2].classifyRequested.connect(self.run_classify)
        self.pages[2].selectedValuesChanged.connect(self._selected_values_changed)
        self.pages[2].profileLoaded.connect(self.pages[4].set_fields)
        self.pages[3].previewRequested.connect(self.load_map_preview); self.pages[3].qualityRequested.connect(self.run_quality)
        self.pages[4].exportRequested.connect(self.run_export)
        initial_profile = inspect_builtin_profile(self.pages[2].profile_combo.currentText())
        self.pages[4].set_fields([str(value) for value in initial_profile.get("attributes", [])])

    def _selected_values_changed(self, values: dict[str, list[str]]) -> None:
        self.state.selected_tag_values = values

    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("Project")
        open_action = QAction("Open project.osmproject.json", self); save_action = QAction("Save project", self); quit_action = QAction("Exit", self)
        open_action.triggered.connect(self.open_project_dialog); save_action.triggered.connect(self.save_project); quit_action.triggered.connect(self.close)
        menu.addActions([open_action, save_action]); menu.addSeparator(); menu.addAction(quit_action)

    def _build_task_panel(self) -> None:
        dock = QWidget(); layout = QHBoxLayout(dock); self.task_label = QLabel("Ready"); self.progress = QProgressBar(); self.progress.setRange(0, 100); self.progress.setValue(0)
        self.cancel = QPushButton("Cancel"); self.cancel.setEnabled(False); self.cancel.clicked.connect(self.cancel_task); self.log = QPlainTextEdit(); self.log.setReadOnly(True); self.log.setMaximumHeight(90)
        left = QVBoxLayout(); left.addWidget(self.task_label); left.addWidget(self.progress); left.addWidget(self.log); layout.addLayout(left); layout.addWidget(self.cancel)
        from PySide6.QtWidgets import QDockWidget
        container = QDockWidget("Background tasks", self); container.setWidget(dock); self.addDockWidget(Qt.BottomDockWidgetArea, container)

    def start_worker(self, worker: CoreWorker, success: Callable[[Any], None]) -> None:
        if self.current_worker:
            QMessageBox.warning(self, "Task in progress", "Wait for the current background task or cancel it first.")
            return
        self.current_worker = worker; self._success_callback = success; self.cancel.setEnabled(True); self.progress.setValue(0); self.log.clear()
        worker.signals.started.connect(lambda name: self.task_label.setText(f"Running: {name}"))
        worker.signals.progress.connect(self._task_progress); worker.signals.succeeded.connect(self._task_succeeded)
        worker.signals.failed.connect(self._task_failed); worker.signals.cancelled.connect(lambda: self.statusBar().showMessage("Task cancelled; uncommitted partial results were discarded.", 8000))
        worker.signals.finished.connect(self._task_finished); self.thread_pool.start(worker)

    def _task_progress(self, message: str, percent: int) -> None:
        self.log.appendPlainText(message); self.progress.setValue(percent if percent else min(95, self.progress.value() + 2))

    def _task_succeeded(self, result: Any) -> None:
        self.progress.setValue(100)
        if self._success_callback: self._success_callback(result)

    def _task_failed(self, message: str, feedback: str, details: str) -> None:
        self.log.appendPlainText(details)
        text = message + (f"\n\nDiagnostic feedback ZIP: {feedback}" if feedback else "")
        QMessageBox.critical(self, "Task failed", text)

    def _task_finished(self) -> None:
        self.task_label.setText("Ready"); self.cancel.setEnabled(False); self.current_worker = None; self._success_callback = None

    def cancel_task(self) -> None:
        if self.current_worker:
            self.task_label.setText("Cancelling safely…"); self.current_worker.cancel()

    def inspect_input(self, path: str) -> None:
        source = Path(path)
        if not source.is_file(): QMessageBox.warning(self, "Invalid input", "Select an existing .osm/.pbf file."); return
        def execute(progress):
            progress("Computing input SHA-256 and inspecting the environment")
            return inspect_input(source), inspect_environment(require_gdal=False)
        self.start_worker(CoreWorker("inspect", execute), self._inspect_done)

    def _inspect_done(self, result: Any) -> None:
        metadata, environment = result; self.state.input_path = metadata.path; self.state.input_sha256 = metadata.sha256
        page: InputPage = self.pages[0]; page.metadata.setText(f"{metadata.format.upper()} · {metadata.size_bytes / 2**20:.2f} MiB · SHA-256 {metadata.sha256}\nBounds: {metadata.bounds}")
        page.environment.setPlainText(json.dumps(environment, ensure_ascii=False, indent=2)); page.refresh_resources()
        if not page.project_edit.text(): page.project_edit.setText(str(Path(metadata.path).parent / f"{Path(metadata.path).stem}_project_v041"))

    def run_scan(self, input_path: str, project_dir: str, keep_raw: bool) -> None:
        if not input_path or not project_dir: QMessageBox.warning(self, "Missing path", "Select an input file and a new project directory."); return
        self.state.input_path = str(Path(input_path).resolve()); self.state.project_dir = str(Path(project_dir).resolve()); self.state.keep_raw_master = keep_raw
        self.start_worker(scan_worker(Path(input_path), Path(project_dir), keep_raw), self._scan_done)

    def _scan_done(self, result: Any) -> None:
        self.state.run_results["scan"] = {"status": "success", "feedback": result.feedback_bundle.name}; self.state.save()
        self.load_project(Path(self.state.project_dir)); self.steps.setCurrentRow(1); self.statusBar().showMessage("Scan completed; the overview is available through lazy queries.", 7000)

    def load_project(self, project: Path) -> None:
        self.state.project_dir = str(project.resolve()); self.repository = InventoryRepository(project)
        self.pages[1].populate(project, self.repository); self.pages[2].set_repository(self.repository)
        self.pages[2].set_selected_tag_values(self.state.selected_tag_values)
        try:
            profile_data = inspect_builtin_profile(self.state.profile_id)
            self.pages[2].profile_combo.setCurrentText(self.state.profile_id)
            self.pages[4].set_fields([str(value) for value in profile_data.get("attributes", [])], self.state.selected_fields or None)
        except (FileNotFoundError, ValueError):
            pass
        classification_summary = project / "classification" / "classification_summary.json"
        if classification_summary.is_file():
            summary = json.loads(classification_summary.read_text(encoding="utf-8")); self.pages[4].set_categories(summary.get("counts", {}).get("categories", {}), self.state.selected_categories or None)

    def run_classify(self, source_type: str, payload: str) -> None:
        if not self.state.project_dir: QMessageBox.warning(self, "No project", "Scan data or open a project first."); return
        project = Path(self.state.project_dir)
        if source_type == "custom":
            custom = project / "profiles" / "gui_custom_profile.json"; custom.parent.mkdir(parents=True, exist_ok=True); custom.write_text(payload + "\n", encoding="utf-8")
            profile = resolve_profile(rules=custom); self.state.custom_rule_file = "profiles/gui_custom_profile.json"
            self.state.selected_tag_values = self.pages[2].selected_tag_values()
        else:
            profile = resolve_profile(profile=payload); self.state.custom_rule_file = ""
            self.state.selected_tag_values = self.pages[2].selected_tag_values()
        self.state.profile_id = profile.id; self.state.profile_sha256 = profile.sha256; self.state.selected_categories = self.pages[2].selected_categories()
        self.state.classification_rules = list(profile.data.get("rules", []))
        self.pages[4].set_fields([str(value) for value in profile.data.get("attributes", [])])
        self.start_worker(classify_worker(project, profile), self._classify_done)

    def _classify_done(self, result: Any) -> None:
        self.state.run_results["classification"] = {"status": "success", "matched_objects": result.matched_objects, "rule_matches": result.total_matches, "profile_sha256": self.state.profile_sha256}; self.state.save()
        summary = json.loads(result.summary.read_text(encoding="utf-8")); self.pages[4].set_categories(summary["counts"]["categories"], self.state.selected_categories or None); self.steps.setCurrentRow(3); self.load_map_preview()

    def load_map_preview(self) -> None:
        if not self.state.project_dir: return
        self.start_worker(CoreWorker("preview", lambda progress: (progress("Reading up to 2,000 classified geometries"), load_preview(self.state.project_dir, 2000))[1]), self.pages[3].populate_preview)

    def run_quality(self, settings: dict[str, Any]) -> None:
        if not self.state.project_dir: return
        merged = {**self.state.quality_settings, **settings, "auto_repair": False}; self.state.quality_settings = merged
        def done(report):
            self.pages[3].quality.setPlainText(json.dumps(report, ensure_ascii=False, indent=2)); self.state.run_results["quality"] = report; self.state.save()
        self.start_worker(CoreWorker("quality", lambda progress: (progress("Running bounded geometry checks and database-wide SQL checks"), run_quality_checks(self.state.project_dir, merged))[1]), done)

    def run_export(self, format_name: str, output: str, categories: list[str], crs: str, fields: list[str]) -> None:
        if not output: QMessageBox.warning(self, "Missing output", "Select an output location."); return
        project = Path(self.state.project_dir); selection = {"schema_version": "1.0", "profile": self.state.profile_id, "categories": categories, "format": format_name, "gui_crs": crs, "fields": fields}
        selection_path = project / "profiles" / "gui_export_selection.json"; selection_path.write_text(json.dumps(selection, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        destination = Path(output)
        if format_name == "GPKG" and destination.suffix.lower() != ".gpkg": destination = destination.with_suffix(".gpkg")
        self.state.export_format = format_name; self.state.crs = crs; self.state.selected_fields = fields; self.state.selected_categories = categories; self.state.export_path = str(destination)
        self.start_worker(export_worker(project, selection_path, destination), self._export_done)

    def _export_done(self, result: Any) -> None:
        audit = json.loads(result.audit.read_text(encoding="utf-8")); self.pages[4].summary.setPlainText(json.dumps(audit, ensure_ascii=False, indent=2)); self.pages[4].open_folder.setEnabled(True)
        self.state.run_results["export"] = {"status": "success", "features_written": result.features_written, "audit": "exports/export_audit.json", "feedback": result.feedback_bundle.name}; self.state.save(); self.statusBar().showMessage(f"Export completed: {result.features_written:,} features", 10000)

    def save_project(self) -> None:
        try:
            path = self.state.save(); self.statusBar().showMessage(f"Saved {path.name}", 5000)
        except Exception as error: QMessageBox.warning(self, "Could not save", str(error))

    def open_project_dialog(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Open project", "", "OSM project (*.osmproject.json)")
        if not path: return
        try:
            self.state = GuiProject.load(path); project = Path(self.state.project_dir); self.pages[0].project_edit.setText(str(project)); self.pages[0].input_edit.setText(self.state.input_path); self.load_project(project)
        except Exception as error: QMessageBox.critical(self, "Could not open project", str(error))

    def closeEvent(self, event) -> None:
        if self.current_worker:
            QMessageBox.warning(self, "A background task is running", "Cancel the background task or wait for it to finish.")
            event.ignore(); return
        if self.state.project_dir:
            try: self.state.save()
            except OSError: pass
        event.accept()
