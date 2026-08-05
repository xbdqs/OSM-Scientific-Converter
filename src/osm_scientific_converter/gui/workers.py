from __future__ import annotations

import shutil
import traceback
from pathlib import Path
from typing import Any, Callable

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from osm_scientific_converter.core.classifier import classify_project
from osm_scientific_converter.core.exporter import export_selection
from osm_scientific_converter.core.profiles import ResolvedProfile
from osm_scientific_converter.core.scanner import ScanExecutionError, ScanOptions, scan


class TaskCancelled(RuntimeError):
    pass


class WorkerSignals(QObject):
    started = Signal(str)
    progress = Signal(str, int)
    succeeded = Signal(object)
    failed = Signal(str, str, str)
    cancelled = Signal()
    finished = Signal()


class CoreWorker(QRunnable):
    """Runs frozen core operations off the GUI thread with cooperative cancellation."""

    def __init__(self, operation: str, function: Callable[[Callable[[str], None]], Any]) -> None:
        super().__init__()
        self.operation = operation
        self.function = function
        self.signals = WorkerSignals()
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def _progress(self, message: str) -> None:
        if self._cancelled:
            raise TaskCancelled("Operation cancelled by user")
        percent = 0
        if message.startswith("[") and "/" in message:
            try:
                step, total = message[1:message.index("]")].split("/")
                percent = int(int(step) / int(total) * 100)
            except (ValueError, ZeroDivisionError):
                percent = 0
        self.signals.progress.emit(message, percent)

    @Slot()
    def run(self) -> None:
        self.signals.started.emit(self.operation)
        try:
            result = self.function(self._progress)
            if self._cancelled:
                raise TaskCancelled("Operation cancelled by user")
            self.signals.succeeded.emit(result)
        except ScanExecutionError as error:
            if self._cancelled:
                if error.diagnostic_dir and error.diagnostic_dir.exists():
                    shutil.rmtree(error.diagnostic_dir, ignore_errors=True)
                self.signals.cancelled.emit()
            else:
                self.signals.failed.emit(str(error), str(error.feedback_bundle or ""), traceback.format_exc())
        except TaskCancelled:
            self.signals.cancelled.emit()
        except Exception as error:
            feedback = getattr(error, "feedback_bundle", "")
            self.signals.failed.emit(str(error), str(feedback or ""), traceback.format_exc())
        finally:
            self.signals.finished.emit()


def scan_worker(input_path: Path, project: Path, keep_raw: bool) -> CoreWorker:
    existed = project.exists()

    def execute(progress):
        try:
            return scan(input_path, project, ScanOptions(keep_raw_master=keep_raw), progress=progress)
        except ScanExecutionError:
            if not existed and project.exists():
                manifest = project / "project_manifest.json"
                if manifest.is_file() and '"status": "failed"' in manifest.read_text(encoding="utf-8", errors="ignore"):
                    shutil.rmtree(project, ignore_errors=True)
            raise

    return CoreWorker("scan", execute)


def classify_worker(project: Path, profile: ResolvedProfile) -> CoreWorker:
    return CoreWorker("classify", lambda progress: classify_project(project, profile, progress=progress))


def export_worker(project: Path, selection: Path, output: Path) -> CoreWorker:
    return CoreWorker("export", lambda progress: export_selection(project, selection, output, progress=progress))
