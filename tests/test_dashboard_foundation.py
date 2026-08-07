from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from core.summary_loader import SummaryLoadError, load_summary, summary_counts, summary_date, summary_venues


ROOT = Path(__file__).resolve().parents[1]


class DashboardFoundationTest(unittest.TestCase):
    def test_missing_summary_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(load_summary(Path(tmp) / "missing.json"))

    def test_summary_helpers_support_counts_lists_and_venues(self) -> None:
        summary = {
            "date": "2026-08-08",
            "buy": [{"race_id": "1"}, {"race_id": "2"}],
            "hold": [{"race_id": "3"}],
            "skip": [],
            "venues": ["門別", "大井", "門別", ""],
        }
        self.assertEqual(summary_date(summary), "2026-08-08")
        self.assertEqual(summary_counts(summary), (2, 1, 0))
        self.assertEqual(summary_venues(summary), ("門別", "大井"))

    def test_explicit_counts_are_loaded_from_valid_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text(
                json.dumps({"counts": {"buy": 5, "hold": 3, "skip": 28}}),
                encoding="utf-8",
            )
            summary = load_summary(path)
            self.assertIsNotNone(summary)
            self.assertEqual(summary_counts(summary or {}), (5, 3, 28))

    def test_invalid_summary_json_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "summary.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(SummaryLoadError):
                load_summary(path)

    def test_required_project_structure_exists(self) -> None:
        required = [
            "app.py",
            "requirements.txt",
            "README.md",
            "pages/1_JRA_Weekend.py",
            "pages/2_NAR_Daily.py",
            "core",
            "tools",
            "assets/analysis",
            "collected_html/jra",
            "collected_html/nar",
            "results",
            "tests",
        ]
        for relative in required:
            self.assertTrue((ROOT / relative).exists(), relative)

    def test_top_page_reads_only_weekend_and_daily_summaries(self) -> None:
        source = (ROOT / "app.py").read_text(encoding="utf-8")
        self.assertIn('"JRA Weekend"', source)
        self.assertIn('"NAR Daily"', source)
        self.assertIn('"weekend_summary.json"', source)
        self.assertIn('"nar_daily_summary.json"', source)
        self.assertIn('st.info("データがありません")', source)

    def test_dashboard_has_no_mobile_prediction_dependencies(self) -> None:
        production_files = [
            ROOT / "app.py",
            ROOT / "pages" / "1_JRA_Weekend.py",
            ROOT / "pages" / "2_NAR_Daily.py",
            ROOT / "core" / "summary_loader.py",
            ROOT / "core" / "daily_summary.py",
        ]
        source = "\n".join(path.read_text(encoding="utf-8") for path in production_files)
        for forbidden in ("PredictionResult", "mobile_png", "jra_notebook_logic", "nar_notebook_logic", "Parser"):
            self.assertNotIn(forbidden, source)

    def test_summary_builder_is_an_explicit_future_placeholder(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools" / "build_daily_summary.py")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("次のPhase", result.stdout)


if __name__ == "__main__":
    unittest.main()
