import importlib
import importlib.util
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch


def relative_luminance(color: str) -> float:
    channels = [int(color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [
        value / 12.92
        if value <= 0.04045
        else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def contrast_ratio(foreground: str, background: str) -> float:
    lighter, darker = sorted(
        (relative_luminance(foreground), relative_luminance(background)),
        reverse=True,
    )
    return (lighter + 0.05) / (darker + 0.05)


class ThemeTests(unittest.TestCase):
    def load_theme(self):
        spec = importlib.util.find_spec("ui.theme")
        self.assertIsNotNone(spec, "ui.theme must centralize the visual tokens")
        return importlib.import_module("ui.theme")

    def test_darkroom_theme_colors_meet_aa_contrast(self) -> None:
        theme = self.load_theme()

        expected = {
            "background": "#17181A",
            "surface": "#1F2124",
            "control": "#282B2F",
            "control_hover": "#31353A",
            "border": "#34383D",
            "text": "#E8E6E3",
            "muted_text": "#9A9A96",
            "primary": "#E8B04B",
            "focus": "#E8B04B",
        }
        for name, color in expected.items():
            with self.subTest(token=name):
                self.assertEqual(theme.COLORS[name], color)

        self.assertGreaterEqual(
            contrast_ratio(theme.COLORS["text"], theme.COLORS["surface"]),
            4.5,
        )
        self.assertGreaterEqual(
            contrast_ratio(
                theme.COLORS["muted_text"],
                theme.COLORS["surface"],
            ),
            4.5,
        )
        self.assertGreaterEqual(
            contrast_ratio(theme.COLORS["background"], theme.COLORS["primary"]),
            4.5,
        )

    def test_native_controls_are_fully_redrawn(self) -> None:
        theme = self.load_theme()

        stylesheet = theme.APP_STYLESHEET
        required_fragments = (
            "QComboBox::down-arrow",
            "chevron-down.svg",
            "QDoubleSpinBox::up-arrow",
            "spin-up.svg",
            "QDoubleSpinBox::down-arrow",
            "spin-down.svg",
            'QRadioButton[segment="true"]',
            'QWidget[segmentedControl="true"]',
            'QPushButton[segmentItem="true"]',
            'QRadioButton[segmentItem="true"]',
            'QRadioButton[segmentItem="true"]:checked:focus',
            'QFrame[segmentDivider="true"]',
            "QCheckBox::indicator:checked",
            "checkmark.svg",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, stylesheet)

        for path in theme.CONTROL_ICON_PATHS.values():
            with self.subTest(icon=path.name):
                self.assertTrue(path.is_file())

    def test_control_icons_resolve_from_pyinstaller_bundle(self) -> None:
        theme = self.load_theme()

        with TemporaryDirectory() as bundle_root:
            bundled_icon_dir = Path(bundle_root) / "ui" / "icons"
            bundled_icon_dir.mkdir(parents=True)
            for source_path in theme.CONTROL_ICON_PATHS.values():
                shutil.copy2(source_path, bundled_icon_dir / source_path.name)

            spec = importlib.util.spec_from_file_location(
                "ui._bundled_theme_test",
                theme.__file__,
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            bundled_theme = importlib.util.module_from_spec(spec)
            with patch.object(sys, "_MEIPASS", bundle_root, create=True):
                spec.loader.exec_module(bundled_theme)

            self.assertEqual(bundled_theme._ICON_DIR, bundled_icon_dir)
            self.assertEqual(len(bundled_theme.CONTROL_ICON_PATHS), 6)
            for path in bundled_theme.CONTROL_ICON_PATHS.values():
                with self.subTest(icon=path.name):
                    self.assertTrue(path.is_file())

    def test_stylesheet_keeps_a_one_pixel_amber_focus_state(self) -> None:
        theme = self.load_theme()

        self.assertIn("QDoubleSpinBox:focus", theme.APP_STYLESHEET)
        self.assertIn(
            f'border: 1px solid {theme.COLORS["focus"]}',
            theme.APP_STYLESHEET,
        )
        self.assertIn(theme.COLORS["focus"], theme.APP_STYLESHEET)
        self.assertNotIn("outline: none", theme.APP_STYLESHEET.lower())


if __name__ == "__main__":
    unittest.main()
