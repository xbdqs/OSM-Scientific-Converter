from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Iterable


def _directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:
                pass
    return total


class ResourceMonitor:
    """Sample the current Python process, descendants, and working directories."""

    def __init__(self, paths: Iterable[Path] = (), interval_seconds: float = 0.20) -> None:
        self.paths = [Path(path) for path in paths]
        self.interval_seconds = interval_seconds
        self.peak_rss_bytes = 0
        self.peak_disk_bytes = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="osm-sci-resource-monitor", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        try:
            import psutil

            process = psutil.Process(os.getpid())
        except (ImportError, OSError):
            process = None
        while not self._stop.is_set():
            if process is not None:
                try:
                    rss = process.memory_info().rss
                    for child in process.children(recursive=True):
                        try:
                            rss += child.memory_info().rss
                        except (OSError, RuntimeError, psutil.Error):
                            pass
                    self.peak_rss_bytes = max(self.peak_rss_bytes, rss)
                except (OSError, RuntimeError, psutil.Error):
                    pass
            try:
                disk = sum(_directory_size(path) for path in self.paths)
                self.peak_disk_bytes = max(self.peak_disk_bytes, disk)
            except OSError:
                pass
            self._stop.wait(self.interval_seconds)

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(2.0, self.interval_seconds * 5))
            self._thread = None

    def metrics(self) -> dict[str, int]:
        return {
            "overall_peak_rss_bytes": self.peak_rss_bytes,
            "working_disk_peak_bytes": self.peak_disk_bytes,
        }
