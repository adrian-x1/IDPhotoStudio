import importlib
import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication


class MainEntryTests(unittest.TestCase):
    def test_import_configures_bundled_matting_model_before_ui_imports(self) -> None:
        os.environ.pop("U2NET_HOME", None)
        os.environ.pop("MODEL_CHECKSUM_DISABLED", None)

        import main

        importlib.reload(main)

        self.assertEqual(
            Path(os.environ["U2NET_HOME"]),
            Path(__file__).resolve().parents[1] / "assets" / "models",
        )
        self.assertEqual(os.environ["MODEL_CHECKSUM_DISABLED"], "1")

    def test_qt_widgets_get_chinese_text_regardless_of_system_locale(self) -> None:
        """The catalogue is loaded by name, not by locale detection.

        macOS reports this process as English unless the bundle claims Chinese
        support, so relying on QLocale.system() would leave Qt's own strings in
        English on the very machines this app targets.
        """
        import main

        app = QApplication.instance() or QApplication([])
        translator = main.install_chinese_translations(app)
        self.addCleanup(app.removeTranslator, translator)

        self.assertIsNotNone(translator)
        self.assertEqual(
            QCoreApplication.translate("QPlatformTheme", "Cancel"),
            "取消",
        )
        self.assertEqual(
            QCoreApplication.translate("QLineEdit", "Select All"),
            "全选",
        )


if __name__ == "__main__":
    unittest.main()
