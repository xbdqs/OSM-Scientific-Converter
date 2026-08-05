from __future__ import annotations

import time

from PySide6.QtCore import QThreadPool

from osm_scientific_converter.gui.workers import CoreWorker


def test_background_worker_success(qtbot):
    worker = CoreWorker("test", lambda progress: (progress("[1/1] done"), 42)[1])
    with qtbot.waitSignal(worker.signals.succeeded, timeout=3000) as signal:
        QThreadPool.globalInstance().start(worker)
    assert signal.args == [42]


def test_background_cancel_is_cooperative(qtbot):
    def task(progress):
        for index in range(100):
            time.sleep(0.005)
            progress(f"step {index}")
        return True
    worker = CoreWorker("cancel-test", task)
    with qtbot.waitSignal(worker.signals.cancelled, timeout=5000):
        QThreadPool.globalInstance().start(worker)
        qtbot.wait(30)
        worker.cancel()


def test_background_failure_reports_traceback(qtbot):
    def fail(progress):
        raise RuntimeError("scientific failure")
    worker = CoreWorker("failure-test", fail)
    with qtbot.waitSignal(worker.signals.failed, timeout=3000) as signal:
        QThreadPool.globalInstance().start(worker)
    assert signal.args[0] == "scientific failure"
    assert "RuntimeError" in signal.args[2]
