"""Desktop entry point for the ID-photo application."""

from __future__ import annotations

import os
from pathlib import Path
import sys


def _resource_root() -> Path:
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root is not None:
        return Path(bundle_root)
    return Path(__file__).resolve().parent


def _configure_model_environment() -> None:
    os.environ["U2NET_HOME"] = str(_resource_root() / "assets" / "models")
    os.environ["MODEL_CHECKSUM_DISABLED"] = "1"


_configure_model_environment()

from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
