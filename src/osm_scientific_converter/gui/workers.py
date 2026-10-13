from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import psutil
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
        # -1 means indeterminate. Step numbers and log counts are NOT
        # percentages of processed objects or features written.
        percent = -1
        if message.startswith("@@PROGRESS "):
            try:
                payload = json.loads(message[len("@@PROGRESS "):])
                done, total = int(payload["processed"]), int(payload["total"])
                if total > 0 and 0 <= done <= total:
                    percent = min(99, int(100 * done / total))
            except (ValueError, TypeError, KeyError, json.JSONDecodeError):
                pass
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


def classify_worker(
    project: Path, profile: ResolvedProfile, source_layers: tuple[str, ...] | None = None,
) -> CoreWorker:
    return CoreWorker(
        "classify",
        lambda progress: classify_project(project, profile, progress=progress, source_layers=source_layers),
    )


def export_worker(project: Path, selection: Path, output: Path) -> CoreWorker:
    return CoreWorker("export", lambda progress: export_selection(project, selection, output, progress=progress))


def _stop_process_tree(process: subprocess.Popen) -> None:
    """Ensure cancellation also stops ogr2ogr spawned by the CLI subprocess."""
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in reversed(children):
            try: child.terminate()
            except psutil.Error: pass
        try: parent.terminate()
        except psutil.Error: pass
        _, alive = psutil.wait_procs(children + [parent], timeout=3)
        for node in alive:
            try: node.kill()
            except psutil.Error: pass
    except psutil.NoSuchProcess:
        pass
    except psutil.Error:
        try: process.kill()
        except OSError: pass
    try:
        process.wait(timeout=5)
    except (subprocess.TimeoutExpired, OSError):
        try: process.kill()
        except OSError: pass


def quick_highway_worker(input_path: Path, rules: Path, output: Path) -> CoreWorker:
    """Run verified CLI implementation off-thread; abort child GDAL on cancellation.

    Exit status and audited sidecar are both required before reporting success.
    The GUI never fabricates a fractional progress denominator.
    """
    def execute(progress):
        progress('Quick highway extraction: GDAL scan and enrichment (duration unknown)')
        sidecar = Path(str(output) + '.audit.json')
        if output.exists() or sidecar.exists():
            raise FileExistsError('Quick output exists; overwrite is disabled in the GUI')
        # A frozen GUI executable is NOT a Python interpreter: launch its own
        # constrained, headless CLI entry instead of the unsupported `-m` flag.
        prefix = ([sys.executable, '--headless-cli'] if getattr(sys, 'frozen', False)
                  else [sys.executable, '-m', 'osm_scientific_converter.cli.main'])
        command = prefix + ['quick-extract', str(input_path), '--rules', str(rules),
                            '--output', str(output)]
        with tempfile.TemporaryDirectory(prefix='osm-quick-gui-') as tempdir:
            logfile = Path(tempdir) / 'cli.log'
            with logfile.open('w+', encoding='utf-8', errors='replace') as log:
                process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                           stdin=subprocess.DEVNULL)
                try:
                    while process.poll() is None:
                        time.sleep(0.35)
                        progress('')  # cooperative cancellation; no bogus percent/log spam
                    progress('')  # catch late cancellation before reporting success
                except BaseException:
                    _stop_process_tree(process)
                    raise
                log.flush()
                log.seek(0)
                transcript = log.read()
                if process.returncode != 0:
                    raise RuntimeError(
                        f'Quick extraction failed (exit={process.returncode}).\n'
                        + transcript[-3500:]
                    )
        if not output.is_file() or not sidecar.is_file():
            raise RuntimeError('Quick CLI exited successfully without GeoPackage and audit sidecar')
        audit = json.loads(sidecar.read_text(encoding='utf-8'))
        if audit.get('status') != 'success' or audit.get('source_layer') != 'lines':
            raise RuntimeError('Quick extraction audit did not confirm successful lines-only export')
        if audit.get('experimental_deferred_index', False):
            raise RuntimeError('GUI quick mode must use the verified default index, not experimental mode')
        return {'audit': audit, 'output': str(output), 'sidecar': str(sidecar)}

    return CoreWorker('quick highway extraction (indeterminate)', execute)
