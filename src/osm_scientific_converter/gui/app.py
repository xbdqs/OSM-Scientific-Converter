from __future__ import annotations

import os
import sys
import json
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, qVersion
from PySide6.QtWidgets import QApplication

from osm_scientific_converter import __version__
from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.environment import inspect_environment
from osm_scientific_converter.core.exporter import export_selection
from osm_scientific_converter.core.profiles import resolve_profile
from osm_scientific_converter.core.scanner import ScanOptions, scan
from osm_scientific_converter.gui.quality import run_quality_checks
from .main_window import MainWindow


STYLE = """
QWidget { font-family: "Segoe UI", Arial, sans-serif; font-size: 10pt; }
QMainWindow { background: #f5f7fa; }
QListWidget { background: #17233b; color: #eaf1fb; border: 0; padding: 8px; }
QListWidget::item { padding: 12px 8px; border-radius: 5px; }
QListWidget::item:selected { background: #0072B2; color: white; }
QGroupBox { font-weight: 600; border: 1px solid #ccd4df; border-radius: 6px; margin-top: 10px; padding-top: 10px; background: white; }
QPushButton { padding: 6px 12px; border: 1px solid #aab5c4; border-radius: 4px; background: white; }
QPushButton:hover { border-color: #0072B2; }
QPushButton#primaryButton { background: #0072B2; color: white; border-color: #0072B2; font-weight: 600; }
QLabel#pageTitle { font-size: 18pt; font-weight: 650; color: #17233b; padding: 4px 0 10px 0; }
QLineEdit, QComboBox, QPlainTextEdit, QTreeWidget, QTableWidget { background: white; border: 1px solid #ccd4df; border-radius: 3px; padding: 3px; }
QProgressBar { border: 1px solid #aab5c4; border-radius: 4px; text-align: center; }
QProgressBar::chunk { background: #009E73; }
"""


def configure_frozen_runtime() -> None:
    """Expose bundled GDAL command-line tools/data to the unchanged core."""
    if not getattr(sys, "frozen", False):
        return
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    os.environ["PATH"] = str(bundle) + os.pathsep + os.environ.get("PATH", "")
    bundled_data = bundle / "gdal_data"
    if bundled_data.is_dir():
        os.environ.setdefault("GDAL_DATA", str(bundled_data))
    bundled_proj = bundle / "proj_data"
    if bundled_proj.is_dir():
        os.environ.setdefault("PROJ_DATA", str(bundled_proj))


def create_application(argv: list[str] | None = None) -> QApplication:
    configure_frozen_runtime()
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("OSM Scientific Converter")
    app.setOrganizationName("OSM Scientific Converter contributors")
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    return app


def _argument(arguments: list[str], name: str) -> Path:
    index = arguments.index(name)
    return Path(arguments[index + 1]).resolve()


def _save_acceptance_screenshot(app: QApplication, window: MainWindow, directory: Path, name: str) -> str:
    directory.mkdir(parents=True, exist_ok=True)
    app.processEvents()
    path = directory / name
    if not window.grab().save(str(path), "PNG"):
        raise RuntimeError(f"Could not save GUI acceptance screenshot: {path}")
    return path.name


def run_gui_acceptance(app: QApplication, window: MainWindow, arguments: list[str]) -> int:
    """Run a reproducible packaged-EXE user-acceptance case through GUI state.

    This mode is intentionally visible in the evidence report.  It manipulates
    the same widgets and core functions as the desktop workflow, captures the
    actual window, and does not claim manual mouse operation.
    """
    case = arguments[arguments.index("--gui-acceptance-case") + 1]
    project = _argument(arguments, "--gui-acceptance-project")
    output_dir = _argument(arguments, "--gui-acceptance-output-dir")
    report_path = _argument(arguments, "--gui-acceptance-report")
    screenshots_dir = _argument(arguments, "--gui-acceptance-screenshots")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, object] = {
        "schema_version": "1.0",
        "case": case,
        "software_version": __version__,
        "packaged_exe": bool(getattr(sys, "frozen", False)),
        "clean_environment": os.environ.get("OSM_SCI_CLEAN_ENV") == "1" and not os.environ.get("PYTHONPATH"),
        "automation_disclosure": "Programmatic acceptance through the real packaged GUI widgets; not a manual mouse-session claim.",
        "screenshots": [],
        "checks": [],
    }

    def check(name: str, passed: bool, detail: object) -> None:
        report["checks"].append({"name": name, "passed": bool(passed), "detail": detail})

    try:
        window.show()
        window.load_project(project)
        window.pages[0].project_edit.setText(str(project))
        window.steps.setCurrentRow(0)
        report["screenshots"].append(_save_acceptance_screenshot(app, window, screenshots_dir, "01_project_open.png"))
        selection_page = window.pages[2]

        if case == "berlin_power":
            selected_values = {"power": ["line", "substation"]}
            selection_page.profile_combo.setCurrentText("power")
            selection_page.key_search.setText("power")
            selection_page.current_key = "power"
            selection_page.value_search.setText("")
            selection_page.set_selected_tag_values(selected_values)
            custom_document = {
                "schema_version": "1.0", "id": "berlin_power_selected",
                "label_en": "Berlin selected power", "label_zh": "Berlin selected power",
                "attributes": ["voltage", "operator", "owner", "network"],
                "expected_fields_by_category": {
                    "line": {"required": ["power"], "recommended": ["voltage"], "optional": ["operator", "owner", "network"]},
                    "substation": {"required": ["power"], "recommended": ["voltage", "operator"], "optional": ["owner", "network"]},
                },
                "rules": [
                    {"id": "selected_line", "category": "line", "geometry": ["line"], "expression": {"key": "power", "op": "equals", "value": "line"}},
                    {"id": "selected_substation", "category": "substation", "geometry": ["point", "polygon"], "expression": {"key": "power", "op": "equals", "value": "substation"}},
                ],
            }
            custom_text = json.dumps(custom_document, ensure_ascii=False, indent=2)
            selection_page.rule_preview.setPlainText(custom_text)
            custom_path = project / "profiles" / "gui_acceptance_berlin_power.json"
            custom_path.parent.mkdir(parents=True, exist_ok=True)
            custom_path.write_text(custom_text + "\n", encoding="utf-8")
            profile = resolve_profile(rules=custom_path)
            categories = ["line", "substation"]
        elif case == "south_korea_aeroway":
            selection_page.profile_combo.setCurrentText("aeroway")
            selection_page.set_selected_tag_values({"aeroway": ["runway", "aerodrome", "taxiway"]})
            profile = resolve_profile(profile="aeroway")
            categories = ["runway", "aerodrome", "taxiway"]
        elif case == "new_york_pipeline":
            selection_page.profile_combo.setCurrentText("pipeline")
            profile = resolve_profile(profile="pipeline")
            categories = []
        else:
            raise ValueError(f"Unknown GUI acceptance case: {case}")

        window.steps.setCurrentRow(2)
        report["screenshots"].append(_save_acceptance_screenshot(app, window, screenshots_dir, "02_selection.png"))
        classification = classify_project(project, profile)
        summary = json.loads(classification.summary.read_text(encoding="utf-8"))
        window.state.profile_id = profile.id
        window.state.profile_sha256 = profile.sha256
        window.state.classification_rules = list(profile.data["rules"])
        window.state.selected_tag_values = selection_page.selected_tag_values()
        window.pages[4].set_categories(summary["counts"]["categories"])

        preview = run_preview = None
        from osm_scientific_converter.gui.quality import load_preview
        run_preview = load_preview(project, 2000)
        window.pages[3].populate_preview(run_preview)
        if run_preview["features"]:
            window.pages[3].tags.setPlainText(json.dumps(run_preview["features"][0]["tags"], ensure_ascii=False, indent=2))
        quality = run_quality_checks(project, {"sample_size": 50, "auto_repair": False})
        window.pages[3].quality.setPlainText(json.dumps(quality, ensure_ascii=False, indent=2))
        window.steps.setCurrentRow(3)
        report["screenshots"].append(_save_acceptance_screenshot(app, window, screenshots_dir, "03_preview_quality.png"))

        formats = [("GPKG", output_dir / f"{case}.gpkg")]
        if case == "berlin_power":
            formats.append(("Shapefile", output_dir / "berlin_power_shapefile"))
        elif case == "south_korea_aeroway":
            formats = [("GeoJSON", output_dir / "south_korea_aeroway_geojson")]
        exports: list[dict[str, object]] = []
        for format_name, output in formats:
            selection_path = project / "profiles" / f"gui_acceptance_{case}_{format_name.lower()}.json"
            selection_path.write_text(json.dumps({
                "schema_version": "1.0", "profile": profile.id, "categories": categories,
                "format": format_name, "fields": list(profile.data.get("attributes", [])),
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            exported = export_selection(project, selection_path, output)
            audit = json.loads(exported.audit.read_text(encoding="utf-8"))
            exports.append({
                "format": format_name,
                "features_written": exported.features_written,
                "output": str(exported.output),
                "selection": audit["selection"],
                "loss_audit": audit["loss_audit"],
            })
        resolved_for_gui = list(exports[0]["selection"]["resolved_categories"])
        window.pages[4].set_selected_categories(resolved_for_gui)
        window.pages[4].summary.setPlainText(json.dumps(exports, ensure_ascii=False, indent=2))
        window.steps.setCurrentRow(4)
        report["screenshots"].append(_save_acceptance_screenshot(app, window, screenshots_dir, "04_export.png"))

        check("packaged v0.4.1 EXE", report["packaged_exe"] and __version__ == "0.4.1", __version__)
        check("clean environment", bool(report["clean_environment"]), inspect_environment(require_gdal=False)["gdal"])
        check("bounded preview", 0 < run_preview["loaded"] <= 2000, {"loaded": run_preview["loaded"], "total": run_preview["total"]})
        check("stratified quality", "category × geometry_group" in quality["scope"]["sampling"] and all(item["sampled"] > 0 for item in quality["scope"]["strata"]), quality["scope"]["strata"])
        check("exports created", all(item["features_written"] > 0 and Path(item["output"]).exists() for item in exports), exports)
        visible_categories = window.pages[4].selected_categories()
        check(
            "GUI categories match applied export selection",
            bool(resolved_for_gui) and set(visible_categories) == set(resolved_for_gui),
            {"gui": visible_categories, "resolved": resolved_for_gui},
        )
        if case == "berlin_power":
            check("line/substation cross-page state", selection_page.selected_tag_values() == {"power": ["line", "substation"]}, selection_page.selected_tag_values())
            check("GPKG and Shapefile", {item["format"] for item in exports} == {"GPKG", "Shapefile"}, [item["format"] for item in exports])
        elif case == "south_korea_aeroway":
            check("selected aeroway categories", set(exports[0]["selection"].get("categories", [])) == set(categories), exports[0]["selection"])
            geojson_dir = Path(exports[0]["output"])
            non_ascii = any(
                any(ord(character) > 127 for character in path.read_text(encoding="utf-8-sig"))
                for path in geojson_dir.rglob("*.geojson")
            )
            check("Unicode preserved in GeoJSON", non_ascii, {"output": str(geojson_dir), "features": exports[0]["features_written"]})
        else:
            candidate_counts = {key: value for key, value in summary["counts"]["categories"].items() if key.endswith("_candidate")}
            resolved_categories = exports[0]["selection"].get("resolved_categories", [])
            check("confirmed/candidate comparison", bool(candidate_counts), candidate_counts)
            check("storage_candidate excluded by default", "storage_candidate" not in resolved_categories, resolved_categories)

        report["classification"] = summary
        report["preview"] = {"loaded": run_preview["loaded"], "total": run_preview["total"]}
        report["quality"] = quality
        report["exports"] = exports
        report["status"] = "success" if all(item["passed"] for item in report["checks"]) else "failed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = {"type": type(error).__name__, "message": str(error), "traceback": traceback.format_exc()}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    window.close()
    return 0 if report["status"] == "success" else 2


def main(argv: list[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv)
    app = create_application(arguments)
    window = MainWindow()
    if "--gui-acceptance-case" in arguments:
        return run_gui_acceptance(app, window, arguments)
    if "--smoke-test" in arguments:
        report = {
            "status": "success",
            "software_version": __version__,
            "qt_version": qVersion(),
            "five_step_pages": window.stack.count(),
            "environment": inspect_environment(require_gdal=False),
            "frozen": bool(getattr(sys, "frozen", False)),
            "clean_environment": os.environ.get("OSM_SCI_CLEAN_ENV") == "1" and not os.environ.get("PYTHONPATH"),
        }
        if "--workflow-input" in arguments:
            try:
                def argument(name: str) -> Path:
                    index = arguments.index(name)
                    return Path(arguments[index + 1])
                input_path = argument("--workflow-input")
                project = argument("--workflow-project")
                output = argument("--workflow-output")
                scan_result = scan(input_path, project, ScanOptions(keep_raw_master=True))
                profile = resolve_profile(profile="power")
                classification = classify_project(project, profile)
                selection = project / "profiles" / "standalone_smoke_selection.json"
                selection.write_text(json.dumps({"schema_version": "1.0", "profile": "power", "categories": [], "format": "GPKG", "fields": ["voltage"]}, indent=2) + "\n", encoding="utf-8")
                exported = export_selection(project, selection, output)
                audit = json.loads(exported.audit.read_text(encoding="utf-8"))
                quality = run_quality_checks(project, {"sample_size": 1, "auto_repair": False})
                report["workflow"] = {
                    "scan_status": "success",
                    "input_sha256": scan_result.input_metadata["sha256"],
                    "matched_objects": classification.matched_objects,
                    "features_written": exported.features_written,
                    "export_exists": exported.output.is_file(),
                    "field_selection_applied": audit["selection"]["field_selection_applied"],
                    "selected_profile_attributes": audit["selection"]["selected_profile_attributes"],
                    "quality_sampling": quality["scope"]["sampling"],
                    "quality_strata": quality["scope"]["strata"],
                }
            except Exception as error:
                report["status"] = "failed"
                report["workflow"] = {"error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc()}
        if "--smoke-report" in arguments:
            index = arguments.index("--smoke-report")
            Path(arguments[index + 1]).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        window.close()
        return 0 if report["status"] == "success" else 2
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
