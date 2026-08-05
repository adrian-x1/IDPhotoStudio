import importlib
import importlib.util
import unittest


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

    def test_locked_theme_colors_meet_aa_contrast(self) -> None:
        theme = self.load_theme()

        self.assertEqual(theme.COLORS["background"], "#F7F4ED")
        self.assertEqual(theme.COLORS["primary"], "#B85C3B")
        self.assertEqual(theme.COLORS["muted_text"], "#6F6A61")
        self.assertGreaterEqual(
            contrast_ratio("#FFFFFF", theme.COLORS["primary"]),
            4.5,
        )
        self.assertGreaterEqual(
            contrast_ratio(
                theme.COLORS["muted_text"],
                theme.COLORS["background"],
            ),
            4.5,
        )

    def test_primary_interaction_colors_only_get_darker(self) -> None:
        theme = self.load_theme()

        primary = relative_luminance(theme.COLORS["primary"])
        hover = relative_luminance(theme.COLORS["primary_hover"])
        pressed = relative_luminance(theme.COLORS["primary_pressed"])
        self.assertLessEqual(hover, primary)
        self.assertLessEqual(pressed, hover)

    def test_stylesheet_keeps_a_visible_warm_focus_state(self) -> None:
        theme = self.load_theme()

        self.assertIn("QDoubleSpinBox:focus", theme.APP_STYLESHEET)
        self.assertIn(theme.COLORS["focus"], theme.APP_STYLESHEET)
        self.assertNotIn("outline: none", theme.APP_STYLESHEET.lower())


if __name__ == "__main__":
    unittest.main()
