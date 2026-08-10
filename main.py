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

from PySide6.QtCore import QLibraryInfo, QTranslator  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from ui.main_window import MainWindow  # noqa: E402


QT_TRANSLATION_NAME = "qtbase_zh_CN"


def _translation_directories() -> list[Path]:
    return [
        Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)),
        _resource_root() / "PySide6" / "Qt" / "translations",
    ]


def install_chinese_translations(app: QApplication) -> QTranslator | None:
    """Give Qt's own widgets Chinese text.

    Nothing here is picked up from the system locale: macOS reports this
    process as English unless the bundle claims Chinese support, which leaves
    Qt-drawn strings -- the line edit context menu, standard dialog buttons --
    in English even on a Chinese system.  Loading the catalogue by name sets
    them regardless.  The native file panel is localised separately, by the
    CFBundleLocalizations entry in build.spec.
    """
    translator = QTranslator(app)
    for directory in _translation_directories():
        if translator.load(QT_TRANSLATION_NAME, str(directory)):
            app.installTranslator(translator)
            return translator
    return None


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    # Held on the app so the catalogue outlives this function.
    app._chinese_translator = install_chinese_translations(app)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
