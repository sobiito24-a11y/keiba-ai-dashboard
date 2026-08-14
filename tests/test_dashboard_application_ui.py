from __future__ import annotations

import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest


ROOT = Path(__file__).resolve().parents[1]


class DashboardApplicationUiTest(unittest.TestCase):
    def test_initial_screen_has_new_and_saved_prediction_flows(self) -> None:
        app = AppTest.from_file(ROOT / "app.py", default_timeout=15).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.title[0].value, "Keiba AI Dashboard")
        self.assertIn("新規一括予想", app.radio[0].options)
        self.assertIn("保存した予想を開く", app.radio[0].options)
        self.assertTrue(any(button.label == "一括予想データ作成" for button in app.button))


if __name__ == "__main__":
    unittest.main()
