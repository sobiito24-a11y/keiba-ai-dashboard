from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from core.prediction_history import build_prediction_history_zip, history_zip_file_name


def write_detail(analysis_dir: Path, relative: str) -> None:
    target = analysis_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "race_mode": "jra",
                "race_name": "札幌1R",
                "race_info": {"venue": "札幌", "race_number": "1R", "distance": "芝1200m"},
                "overall_table": [
                    {
                        "馬番": 1,
                        "馬名": "アルファ",
                        "表示印": "◎",
                        "AI点": 95,
                        "能力評価値": 82.5,
                        "horse_trust_summary": "指数◎ / 騎手○",
                    }
                ],
                "horse_evaluation": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class PredictionHistoryExportTest(unittest.TestCase):
    def test_history_zip_contains_buy_hold_skip_prediction_files(self) -> None:
        summary = {
            "race_type": "jra",
            "date": "2026-08-15",
            "buy": [
                {
                    "race_id": "buy-race",
                    "venue": "札幌",
                    "race_number": "1R",
                    "decision": "BUY",
                    "ticket": "単勝 1",
                    "selected_strategy": "◎単勝",
                    "expected_roi": 155.2,
                    "detail_path": "details/buy.json",
                }
            ],
            "hold": [{"race_id": "hold-race", "venue": "札幌", "race_number": "2R", "decision": "HOLD"}],
            "skip": [{"race_id": "skip-race", "venue": "札幌", "race_number": "3R", "decision": "SKIP"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "analysis"
            write_detail(analysis, "details/buy.json")
            payload = build_prediction_history_zip(summary, analysis, source="JRA Weekend")

        with zipfile.ZipFile(BytesIO(payload)) as archive:
            names = set(archive.namelist())
            self.assertIn("jra/20260815/buy-race/prediction.json", names)
            self.assertIn("jra/20260815/hold-race/prediction.json", names)
            self.assertIn("jra/20260815/skip-race/prediction.json", names)
            loaded = json.loads(archive.read("jra/20260815/buy-race/prediction.json").decode("utf-8"))

        self.assertEqual(loaded["investment_decision"]["decision"], "BUY")
        self.assertEqual(loaded["horses"][0]["support"]["trust_summary"], "指数◎ / 騎手○")
        self.assertEqual(history_zip_file_name(summary, source="JRA Weekend"), "JRA_20260815_prediction_history.zip")


if __name__ == "__main__":
    unittest.main()
