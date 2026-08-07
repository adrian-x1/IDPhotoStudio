from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WindowsOneClickTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.script = (PROJECT_ROOT / "ONE-CLICK-WINDOWS.cmd").read_text(
            encoding="utf-8"
        )
        cls.normalized = cls.script.lower()

    def test_checks_python_313_x64_and_required_payload(self) -> None:
        self.assertIn("sys.version_info[:2] == (3, 13)", self.script)
        self.assertIn("struct.calcsize('P') * 8 == 64", self.script)
        self.assertIn('if not exist "windows-wheels\\"', self.normalized)
        for model_name in (
            "isnet-general-use.onnx",
            "face_landmarker.task",
            "blaze_face_short_range.tflite",
        ):
            self.assertIn(model_name, self.normalized)

    def test_installs_and_validates_entirely_offline(self) -> None:
        self.assertIn('python -m venv ".venv"', self.normalized)
        self.assertIn("--no-index", self.normalized)
        self.assertIn('--find-links="%cd%\\windows-wheels"', self.normalized)
        self.assertIn("-r requirements.txt -r requirements-build.txt", self.normalized)
        self.assertIn("-m pip check", self.normalized)
        for module_name in (
            "mediapipe",
            "onnxruntime",
            "pyside6",
            "rembg",
            "pymatting",
            "cv2",
            "pil",
        ):
            self.assertIn(module_name, self.normalized)

    def test_runs_tests_then_builds_only_the_current_project(self) -> None:
        tests = "-m unittest discover -s tests -v"
        build = "-m pyinstaller --clean --noconfirm build.spec"
        self.assertIn(tests, self.normalized)
        self.assertIn('rmdir /s /q "%cd%\\build"', self.normalized)
        self.assertIn('rmdir /s /q "%cd%\\dist"', self.normalized)
        self.assertIn(build, self.normalized)
        self.assertLess(self.normalized.index(tests), self.normalized.index(build))

    def test_verifies_starts_and_logs_the_onedir_executable(self) -> None:
        executable = "%cd%\\dist\\idphoto\\idphoto.exe"
        self.assertIn(executable, self.normalized)
        self.assertIn('start "" "%cd%\\dist\\idphoto\\idphoto.exe"', self.normalized)
        self.assertIn("windows-one-click.log", self.normalized)
        self.assertIn(":fail", self.normalized)
        self.assertIn("pause", self.normalized)

    def test_manual_contains_one_click_flow_before_troubleshooting(self) -> None:
        manual = (PROJECT_ROOT / "WINDOWS.md").read_text(encoding="utf-8")
        self.assertIn("ONE-CLICK-WINDOWS.cmd", manual)
        self.assertIn("windows-wheels", manual)
        self.assertLess(manual.index("首选快速流程"), manual.index("手动排错流程"))


if __name__ == "__main__":
    unittest.main()
