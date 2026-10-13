from __future__ import annotations

import argparse
from pathlib import Path

from PySide6.QtWidgets import QApplication

from osm_scientific_converter.gui.main_window import MainWindow


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    app = QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    passed = window.grab().save(str(args.output), "PNG")
    window.close()
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
