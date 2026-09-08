from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.morning_pipeline import parse_args, run_pipeline, selected_modes


class MorningPipelineTest(unittest.TestCase):
    def test_today_and_date_are_mutually_exclusive(self) -> None:
        with self.assertRaises(SystemExit):
            parse_args(["--today", "--date", "20260908", "--mode", "nar"])

    def test_selected_modes_all_runs_jra_then_nar(self) -> None:
        self.assertEqual(selected_modes("all"), ["jra", "nar"])
        self.assertEqual(selected_modes("jra"), ["jra"])
        self.assertEqual(selected_modes("nar"), ["nar"])

    def test_pipeline_uses_mobile_collector_and_dashboard_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_root = Path(temp) / "morning"
            batch_report = SimpleNamespace(
                predicted_race_count=70,
                skipped_race_count=2,
                event_snapshot={"scope": {"race_modes": ["jra", "nar"], "venues": ["中京", "川崎"]}},
            )
            build_report = SimpleNamespace(batch_report=batch_report)
            with patch("tools.morning_pipeline.run_collector") as collector, patch(
                "tools.morning_pipeline.build_keiba_from_collected",
                return_value=build_report,
            ) as builder:
                output = run_pipeline(
                    race_date="20260908",
                    mode="all",
                    data_root=data_root,
                    mobile_root=Path(temp) / "keiba_ai_mobile",
                    overwrite=False,
                    headless=True,
                    no_pause_on_login=True,
                )

        self.assertEqual([call.kwargs["mode"] for call in collector.call_args_list], ["jra", "nar"])
        builder.assert_called_once()
        self.assertEqual(builder.call_args.kwargs["race_date"], "20260908")
        self.assertEqual(builder.call_args.kwargs["mode"], "all")
        self.assertEqual(output.name, "20260908_all.keiba")


if __name__ == "__main__":
    unittest.main()
