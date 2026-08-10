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

    def test_qt_translations_are_left_to_the_pyinstaller_hook(self) -> None:
        """Naming the catalogue here would hardcode a path that moves.

        PyInstaller's Qt hook collects the "qtbase" catalogue declared by
        QtCore into PySide6/Qt/translations on every platform except Windows,
        where it lands in PySide6/translations.  An explicit entry pointing at
        the macOS layout silently collected nothing on Windows and failed this
        suite before PyInstaller ever ran.
        """
        datas = load_build_inputs()["datas"]
        bundled_sources = {Path(source).name for source, _ in datas}

        self.assertFalse({name for name in bundled_sources if name.endswith(".qm")})

    def test_app_version_comes_from_the_release_tag(self) -> None:
        namespace = load_build_inputs()
        self.assertEqual(namespace["app_version"], "0.0.0")

        source = (PROJECT_ROOT / "build.spec").read_text(encoding="utf-8")
        self.assertIn('"CFBundleShortVersionString": app_version', source)
        self.assertIn('"CFBundleVersion": app_version', source)

        workflow = (
            PROJECT_ROOT / ".github" / "workflows" / "release.yml"
        ).read_text(encoding="utf-8")
        self.assertEqual(workflow.count("APP_VERSION: ${{ github.ref_name }}"), 2)

    def test_mac_bundle_declares_chinese_only_for_the_native_panel(self) -> None:
        """macOS picks the panel language from CFBundleLocalizations.

        Without the declaration AppKit serves the open/save panel in English
        even on a Chinese system.  Chinese must also be the *only* entry:
        listing "en" alongside it makes AppKit hand an English panel to every
        user whose system is not Chinese, while the rest of the app stays
        Chinese.
        """
        source = (PROJECT_ROOT / "build.spec").read_text(encoding="utf-8")
        _, separator, bundle_section = source.partition("if sys.platform == \"darwin\":")
        self.assertTrue(separator, "macOS BUNDLE block not found in build.spec")

        self.assertIn('"CFBundleLocalizations": ["zh_CN"]', bundle_section)
        self.assertIn('"CFBundleDevelopmentRegion": "zh_CN"', bundle_section)

    def test_matting_dependencies_are_declared_as_hidden_imports(self) -> None:
        hiddenimports = load_build_inputs()["hiddenimports"]

        for module_name in ("numpy", "PIL", "onnxruntime"):
            with self.subTest(module=module_name):
                self.assertIn(module_name, hiddenimports)


if __name__ == "__main__":
    unittest.main()
