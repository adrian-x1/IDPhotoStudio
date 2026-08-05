import importlib
import os
from pathlib import Path
import unittest


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


if __name__ == "__main__":
    unittest.main()
