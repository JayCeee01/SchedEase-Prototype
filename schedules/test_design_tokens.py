"""Static palette contracts; these do not replace browser/AT verification."""
from pathlib import Path
import re

from django.conf import settings
from django.test import SimpleTestCase


def palettes():
    css = (Path(settings.BASE_DIR) / "static/css/app.css").read_text()
    blocks = [re.search(selector + r"\s*\{([^}]+)\}", css).group(1)
              for selector in (r":root", r'\[data-theme="dark"\]')]
    return [dict(re.findall(r"--([\w-]+):\s*([^;]+);", block)) for block in blocks]


def contrast(a, b):
    def luminance(value):
        values = [int(value[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [v / 12.92 if v <= .04045 else ((v + .055) / 1.055) ** 2.4 for v in values]
        return sum(v * weight for v, weight in zip(linear, (.2126, .7152, .0722)))
    left, right = sorted((luminance(a), luminance(b)))
    return (right + .05) / (left + .05)


class DesignTokenTests(SimpleTestCase):
    def test_both_themes_have_readable_text_and_button_states(self):
        pairs = [
            ('ink', 'surface'), ('muted', 'surface'), ('ink', 'surface-soft'),
            ('muted', 'bg'), ('muted', 'surface-soft'),
            ('text-secondary', 'surface'), ('on-primary', 'primary-button'),
            ('on-primary', 'primary-button-hover'), ('on-primary', 'primary-button-active'),
            ('button-text', 'button-surface'), ('button-text', 'button-hover'),
            ('button-text', 'button-active'), ('disabled-text', 'disabled-surface'),
            ('success', 'success-surface'), ('amber', 'warning-surface'),
            ('danger', 'danger-surface'), ('info', 'info-surface'),
            ('tooltip-text', 'tooltip-surface'), ('sidebar-text', 'sidebar'),
            ('on-destructive', 'destructive'), ('on-destructive', 'destructive-hover'),
            ('on-destructive', 'destructive-active'),
        ]
        for name, palette in zip(('light', 'dark'), palettes()):
            for foreground, background in pairs:
                with self.subTest(theme=name, foreground=foreground, background=background):
                    self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 4.5)

    def test_focus_and_control_boundaries_have_nontext_contrast(self):
        for name, palette in zip(('light', 'dark'), palettes()):
            for foreground in ('focus', 'control-border'):
                for background in ('surface', 'surface-soft', 'bg'):
                    with self.subTest(theme=name, foreground=foreground, background=background):
                        self.assertGreaterEqual(contrast(palette[foreground], palette[background]), 3)

    def test_theme_palette_complete_and_primary_uses_foreground_token(self):
        light, dark = palettes()
        # Shared dimensions inherit; all newly introduced semantic colors are explicit.
        for key in ('on-primary', 'primary-active', 'disabled-text', 'disabled-surface',
                    'button-surface', 'button-hover', 'button-active', 'button-text',
                    'control-border', 'focus', 'topbar-surface', 'text-secondary',
                    'success', 'success-surface', 'success-border', 'amber',
                    'warning-surface', 'warning-border', 'danger', 'danger-surface',
                    'danger-border', 'info', 'info-surface', 'info-border',
                    'tooltip-text', 'tooltip-surface', 'on-destructive'):
            self.assertIn(key, light)
            self.assertIn(key, dark)
        css = (Path(settings.BASE_DIR) / "static/css/app.css").read_text()
        block = re.search(r"\.primary, \.button-primary\s*\{([^}]+)\}", css).group(1)
        self.assertIn("color: var(--on-primary)", block)


    def test_primary_buttons_remain_distinct_from_surfaces(self):
        for palette in palettes():
            for state in ('primary-button', 'primary-button-hover', 'primary-button-active'):
                with self.subTest(state=state, background=palette['surface']):
                    self.assertGreaterEqual(contrast(palette[state], palette['surface']), 3)

    def test_light_sidebar_scrollbar_has_visible_thumb(self):
        light, dark = palettes()
        for state in ('nav-scrollbar-thumb', 'nav-scrollbar-hover'):
            self.assertGreaterEqual(contrast(light[state], light['nav-scrollbar-track']), 3)
        # Dark scrollbar aliases retain the existing palette independently.
        self.assertEqual(dark['nav-scrollbar-thumb'], 'var(--scrollbar-thumb)')

    def test_shared_shell_loads_table_scroll_utility_once(self):
        shell = (Path(settings.BASE_DIR) / 'templates/base.html').read_text()
        self.assertEqual(shell.count("static 'js/table-scroll.js'"), 1)
