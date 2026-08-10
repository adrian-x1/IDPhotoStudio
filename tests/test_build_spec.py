from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_build_inputs() -> dict:
    spec_path = PROJECT_ROOT / "build.spec"
    source = spec_path.read_text(encoding="utf-8")
    prefix, separator, _ = source.partition("\na = Analysis(")
    if not separator:
        raise AssertionError("Analysis marker not found in build.spec")
    namespace: dict = {}
    exec(compile(prefix, str(spec_path), "exec"), namespace)
    return namespace


class BuildSpecTests(unittest.TestCase):
    def test_face_models_are_bundled_for_landmarker_and_windows_fallback(self) -> None:
        datas = load_build_inputs()["datas"]
        bundled_sources = {Path(source).name for source, _ in datas}

        self.assertIn("face_landmarker.task", bundled_sources)
        self.assertIn("blaze_face_short_range.tflite", bundled_sources)

    def test_retired_rembg_dependency_chain_stays_out_of_the_bundle(self) -> None:
        inputs = load_build_inputs()

        self.assertNotIn("pymatting", inputs["hiddenimports"])
        for module_name in ("llvmlite", "numba", "pymatting", "rembg", "scipy", "skimage"):
            with self.subTest(module=module_name):
                self.assertIn(module_name, inputs["excludes"])

    def test_matplotlib_is_kept_because_mediapipe_imports_it(self) -> None:
        self.assertNotIn("matplotlib", load_build_inputs()["excludes"])

    def test_qt_chinese_catalogue_is_bundled_for_the_translator(self) -> None:
        datas = load_build_inputs()["datas"]
        bundled = {Path(source).name: destination for source, destination in datas}

        self.assertIn("qtbase_zh_CN.qm", bundled)
        self.assertEqual(bundled["qtbase_zh_CN.qm"], "PySide6/Qt/translations")

    def test_mac_bundle_declares_chinese_so_the_native_panel_is_localised(self) -> None:
        """macOS picks the panel language from CFBundleLocalizations.

        Without the declaration AppKit serves the open/save panel in English
        even on a Chinese system, so this is the only thing standing between
        the packaged app and an English Finder dialog.
        """
        source = (PROJECT_ROOT / "build.spec").read_text(encoding="utf-8")
        _, separator, bundle_section = source.partition("if sys.platform == \"darwin\":")
        self.assertTrue(separator, "macOS BUNDLE block not found in build.spec")

        self.assertIn('"CFBundleLocalizations": ["zh_CN", "en"]', bundle_section)
        self.assertIn('"CFBundleDevelopmentRegion": "zh_CN"', bundle_section)

    def test_matting_dependencies_are_declared_as_hidden_imports(self) -> None:
        hiddenimports = load_build_inputs()["hiddenimports"]

        for module_name in ("numpy", "PIL", "onnxruntime"):
            with self.subTest(module=module_name):
                self.assertIn(module_name, hiddenimports)


if __name__ == "__main__":
    unittest.main()
