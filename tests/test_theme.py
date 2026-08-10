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
            "QToolButton::menu-indicator",
            "QMenu::item:selected",
            "QMenu::item:disabled",
        )
        for fragment in required_fragments:
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, stylesheet)

        for path in theme.CONTROL_ICON_PATHS.values():
            with self.subTest(icon=path.name):
                self.assertTrue(path.is_file())

    def test_hidden_radio_indicators_disable_the_native_drawing(self) -> None:
        """Zero-sizing an indicator is not enough on macOS.

        QMacStyle keeps painting its native blue check mark unless the
        indicator is also given an explicit empty image and background, which
        showed up as a stray blue circle in the frozen app but not in a source
        checkout.
        """
        stylesheet = self.load_theme().APP_STYLESHEET

        hidden_indicators = (
            'QRadioButton[segmentItem="true"]::indicator',
            "QRadioButton#backgroundOriginal::indicator",
        )
        for selector in hidden_indicators:
            with self.subTest(selector=selector):
                start = stylesheet.index(selector)
                block = stylesheet[start : stylesheet.index("}", start)]
                self.assertIn("image: none", block)
                self.assertIn("background: transparent", block)
                self.assertIn("border: 0", block)

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
            self.assertEqual(len(bundled_theme.CONTROL_ICON_PATHS), 7)
            for path in bundled_theme.CONTROL_ICON_PATHS.values():
                with self.subTest(icon=path.name):
                    self.assertTrue(path.is_file())

    def test_add_photo_icon_exists(self) -> None:
        theme = self.load_theme()

        self.assertTrue(theme.CONTROL_ICON_PATHS["add_photo"].is_file())

    def test_stylesheet_keeps_a_one_pixel_amber_focus_state(self) -> None:
        theme = self.load_theme()

        self.assertIn("QDoubleSpinBox:focus", theme.APP_STYLESHEET)
        self.assertIn(
            f'border: 1px solid {theme.COLORS["focus"]}',
            theme.APP_STYLESHEET,
        )
        self.assertIn(theme.COLORS["focus"], theme.APP_STYLESHEET)
        self.assertNotIn("outline: none", theme.APP_STYLESHEET.lower())

    def test_error_states_use_dedicated_non_pure_red_tokens(self) -> None:
        theme = self.load_theme()

        self.assertEqual(theme.COLORS["error"], "#E05252")
        self.assertEqual(theme.COLORS["error_text"], "#F08A8A")
        self.assertNotEqual(theme.COLORS["error"], "#FF0000")
        self.assertNotEqual(theme.COLORS["error_text"], "#FF0000")
        self.assertIn('QDoubleSpinBox[invalid="true"]', theme.APP_STYLESHEET)
        self.assertIn(
            'QLabel#warningLabel[severity="error"]',
            theme.APP_STYLESHEET,
        )

    def test_header_title_and_export_menu_use_existing_theme_tokens(self) -> None:
        theme = self.load_theme()

        self.assertIn(
            "QLabel#appTitle {\n"
            f'    color: {theme.COLORS["primary"]};\n'
            "    font-size: 26px;",
            theme.APP_STYLESHEET,
        )
        self.assertNotIn("QLabel#appSubtitle", theme.APP_STYLESHEET)


if __name__ == "__main__":
    unittest.main()
