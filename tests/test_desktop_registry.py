from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

from desktop_backend import AUTO_BACKEND, QT_BACKEND, backend_fallback_message, normalize_backend, resolve_desktop_backend
from page_registry import hidden_page_keys, normalize_page_key, qt_nav_items


class DesktopRegistryTests(unittest.TestCase):
    def test_page_registry_exposes_qt_navigation(self):
        qt_keys = [key for key, _label in qt_nav_items()]
        self.assertIn("holdings", qt_keys)
        self.assertEqual(qt_keys[0], "dash")
        self.assertIn("fund_detail", hidden_page_keys())

    def test_normalize_page_key_supports_legacy_titles(self):
        self.assertEqual(normalize_page_key("首页"), "dash")
        self.assertEqual(normalize_page_key("组合策略"), "portfolio")
        self.assertEqual(normalize_page_key("Learning"), "review")

    def test_backend_resolution_is_qt_only(self):
        with patch("desktop_backend.pyside6_available", return_value=True):
            backend, reason = resolve_desktop_backend(AUTO_BACKEND)
            self.assertEqual((backend, reason), (QT_BACKEND, "qt_only"))
            self.assertIn("Qt desktop shell", backend_fallback_message(backend, reason))

    def test_qt_requires_pyside6(self):
        with patch("desktop_backend.pyside6_available", return_value=False):
            with self.assertRaises(ModuleNotFoundError):
                resolve_desktop_backend("qt")
            with self.assertRaises(ModuleNotFoundError):
                resolve_desktop_backend("auto")
        self.assertEqual(normalize_backend("tk_legacy"), QT_BACKEND)


if __name__ == "__main__":
    unittest.main()
