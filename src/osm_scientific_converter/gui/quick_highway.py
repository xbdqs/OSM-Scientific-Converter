"""Bounded, explicitly labelled GUI entry point for the experimental highway fast path."""
from __future__ import annotations

from importlib.resources import files
from pathlib import Path

from PySide6.QtWidgets import (QDialog, QFileDialog, QFormLayout, QHBoxLayout,
                                QLabel, QLineEdit, QMessageBox, QPushButton,
                                QPlainTextEdit, QVBoxLayout)

from osm_scientific_converter.core.profiles import resolve_profile
from osm_scientific_converter.core.targeted import reviewed_highway_mapping


def packaged_road_profile() -> Path:
    """The same reviewed rule profile as the verified CLI case, packaged in wheels."""
    return Path(str(files('osm_scientific_converter').joinpath('resources/profiles/reviewer_roads_lines_v1.json')))


class QuickHighwayDialog(QDialog):
    """A separate, no-inventory GUI workflow; never imply the full audit was run."""

    def __init__(self, input_file: str = '', parent=None):
        super().__init__(parent)
        self.setWindowTitle('Quick road extraction — experimental, no full scan')
        self.resize(730, 400)
        layout = QVBoxLayout(self)
        introduction = QLabel(
            "Direct, bounded highway-key extraction from the exact GDAL 'lines' source layer. "
            "No tag vocabulary inventory or complete pre-export geometry/quality audit is performed."
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)
        form = QFormLayout()
        self.input_edit = QLineEdit(input_file)
        self.output_edit = QLineEdit()
        self.rules_edit = QLineEdit(str(packaged_road_profile()))
        self._output_was_edited = False
        self._update_suggested_output(input_file)
        for label, edit, caption, callback in (
            ('OSM input', self.input_edit, 'Browse', self._choose_input),
            ('Output GeoPackage', self.output_edit, 'Save as', self._choose_output),
            ('Reviewed rule profile', self.rules_edit, 'Browse', self._choose_rules),
        ):
            row = QHBoxLayout()
            row.addWidget(edit)
            button = QPushButton(caption)
            button.clicked.connect(callback)
            row.addWidget(button)
            form.addRow(label, row)
        self.output_edit.textEdited.connect(lambda _: setattr(self, '_output_was_edited', True))
        self.input_edit.textChanged.connect(self._update_suggested_output)
        layout.addLayout(form)
        self.validation = QPlainTextEdit()
        self.validation.setReadOnly(True)
        self.validation.setMaximumHeight(125)
        layout.addWidget(self.validation)
        actions = QHBoxLayout()
        check = QPushButton('Validate highway rules')
        self.run_button = QPushButton('Start quick extraction')
        cancel = QPushButton('Cancel')
        actions.addWidget(check)
        actions.addStretch()
        actions.addWidget(cancel)
        actions.addWidget(self.run_button)
        layout.addLayout(actions)
        check.clicked.connect(self._validate_profile)
        cancel.clicked.connect(self.reject)
        self.run_button.clicked.connect(self._accept_checked)
        self._validate_profile()

    def _update_suggested_output(self, text: str) -> None:
        if not text or self._output_was_edited:
            return
        source = Path(text)
        self.output_edit.setText(str(source.parent / f'{source.stem}_quick_roads.gpkg'))

    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Select OSM file', '', 'OSM data (*.osm *.pbf)')
        if path:
            self.input_edit.setText(path)

    def _choose_output(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, 'Choose a NEW GeoPackage', self.output_edit.text(), 'GeoPackage (*.gpkg)')
        if path:
            self._output_was_edited = True
            self.output_edit.setText(path)

    def _choose_rules(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, 'Select reviewed highway rule profile', '', 'JSON profiles (*.json)')
        if path:
            self.rules_edit.setText(path)
            self._validate_profile()

    def _validate_profile(self) -> bool:
        try:
            rules = Path(self.rules_edit.text().strip())
            if not rules.is_file():
                raise FileNotFoundError(f'Rule profile not found: {rules}')
            resolved = resolve_profile(rules=rules)
            values, mapping = reviewed_highway_mapping(resolved)
            categories = sorted({category for category, _ in mapping.values()})
        except (FileNotFoundError, ValueError, KeyError, TypeError) as error:
            self.validation.setPlainText(f'INVALID profile: {type(error).__name__}: {error}')
            return False
        self.validation.setPlainText(
            f'VALID reviewed subset: key=highway; exact source layer=lines; '
            f'{len(values)} accepted values; {len(categories)} exclusive categories.\n'
            f'Categories: {", ".join(categories)}\n'
            f'Profile SHA-256: {resolved.sha256}\n'
            'No full vocabulary inventory, GUI map-based completeness check or full quality audit.'
        )
        return True

    def _accept_checked(self) -> None:
        source = Path(self.input_edit.text().strip())
        output = Path(self.output_edit.text().strip())
        if not source.is_file() or source.suffix.lower() not in ('.osm', '.pbf'):
            QMessageBox.warning(self, 'Invalid OSM input', 'Select an existing .osm or .pbf file.')
            return
        if not self.output_edit.text().strip() or output.suffix.lower() != '.gpkg':
            QMessageBox.warning(self, 'Invalid GeoPackage destination', 'Choose a new .gpkg output path.')
            return
        if output.resolve() == source.resolve():
            QMessageBox.warning(self, 'Invalid destination', 'Input and output files must differ.')
            return
        if output.exists() or Path(str(output) + '.audit.json').exists():
            QMessageBox.warning(self, 'Output exists', 'Choose a new output filename. Quick GUI does not overwrite existing data.')
            return
        if not self._validate_profile():
            QMessageBox.warning(self, 'Invalid profile', self.validation.toPlainText())
            return
        self.accept()

    def arguments(self) -> tuple[Path, Path, Path]:
        return (Path(self.input_edit.text()).resolve(),
                Path(self.rules_edit.text()).resolve(),
                Path(self.output_edit.text()).resolve())
