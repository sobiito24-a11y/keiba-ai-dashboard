from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.morning_pipeline import (
    COLLECTOR_NO_RACES_EXIT_CODE,
    CollectorRunResult,
    PipelinePaths,
    parse_args,
    run_collector,
    run_pipeline,
    selected_modes,
)


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
                collector.side_effect = [
                    CollectorRunResult(mode="jra", no_races=False),
                    CollectorRunResult(mode="nar", no_races=False),
                ]
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

    def test_all_continues_when_jra_has_no_races_and_nar_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_root = Path(temp) / "morning"
            batch_report = SimpleNamespace(
                predicted_race_count=12,
                skipped_race_count=0,
                event_snapshot={"scope": {"race_modes": ["nar"], "venues": ["川崎"]}},
            )
            build_report = SimpleNamespace(batch_report=batch_report)
            with patch("tools.morning_pipeline.run_collector") as collector, patch(
                "tools.morning_pipeline.build_keiba_from_collected",
                return_value=build_report,
            ) as builder:
                collector.side_effect = [
                    CollectorRunResult(mode="jra", no_races=True),
                    CollectorRunResult(mode="nar", no_races=False),
                ]
                output = run_pipeline(
                    race_date="20260909",
                    mode="all",
                    data_root=data_root,
                    mobile_root=Path(temp) / "keiba_ai_mobile",
                    overwrite=False,
                    headless=True,
                    no_pause_on_login=True,
                )

        self.assertEqual([call.kwargs["mode"] for call in collector.call_args_list], ["jra", "nar"])
        builder.assert_called_once()
        self.assertEqual(builder.call_args.kwargs["mode"], "all")
        self.assertEqual(output.name, "20260909_all.keiba")

    def test_all_continues_when_nar_has_no_races_and_jra_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_root = Path(temp) / "morning"
            batch_report = SimpleNamespace(
                predicted_race_count=36,
                skipped_race_count=0,
                event_snapshot={"scope": {"race_modes": ["jra"], "venues": ["中京"]}},
            )
            build_report = SimpleNamespace(batch_report=batch_report)
            with patch("tools.morning_pipeline.run_collector") as collector, patch(
                "tools.morning_pipeline.build_keiba_from_collected",
                return_value=build_report,
            ) as builder:
                collector.side_effect = [
                    CollectorRunResult(mode="jra", no_races=False),
                    CollectorRunResult(mode="nar", no_races=True),
                ]
                output = run_pipeline(
                    race_date="20260909",
                    mode="all",
                    data_root=data_root,
                    mobile_root=Path(temp) / "keiba_ai_mobile",
                    overwrite=False,
                    headless=True,
                    no_pause_on_login=True,
                )

        self.assertEqual([call.kwargs["mode"] for call in collector.call_args_list], ["jra", "nar"])
        builder.assert_called_once()
        self.assertEqual(output.name, "20260909_all.keiba")

    def test_all_with_no_races_on_both_modes_skips_build(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            data_root = Path(temp) / "morning"
            with patch("tools.morning_pipeline.run_collector") as collector, patch(
                "tools.morning_pipeline.build_keiba_from_collected",
            ) as builder:
                collector.side_effect = [
                    CollectorRunResult(mode="jra", no_races=True),
                    CollectorRunResult(mode="nar", no_races=True),
                ]
                output = run_pipeline(
                    race_date="20260909",
                    mode="all",
                    data_root=data_root,
                    mobile_root=Path(temp) / "keiba_ai_mobile",
                    overwrite=False,
                    headless=True,
                    no_pause_on_login=True,
                )

        self.assertIsNone(output)
        builder.assert_not_called()

    def test_collector_no_races_exit_code_is_not_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            mobile_root = Path(temp) / "mobile"
            tools_dir = mobile_root / "tools"
            tools_dir.mkdir(parents=True)
            (tools_dir / "netkeiba_html_collector.py").write_text("# fake", encoding="utf-8")
            paths = PipelinePaths(
                data_root=Path(temp) / "morning",
                date_root=Path(temp) / "morning" / "20260909",
                html_root=Path(temp) / "morning" / "20260909" / "html",
                logs_root=Path(temp) / "morning" / "20260909" / "logs",
                output_path=Path(temp) / "morning" / "20260909" / "20260909_all.keiba",
            )
            paths.html_root.mkdir(parents=True)
            paths.logs_root.mkdir(parents=True)
            completed = SimpleNamespace(returncode=COLLECTOR_NO_RACES_EXIT_CODE)
            with patch("tools.morning_pipeline.subprocess.run", return_value=completed):
                result = run_collector(
                    mobile_root=mobile_root,
                    mode="jra",
                    race_date="20260909",
                    paths=paths,
                    overwrite=False,
                    headless=True,
                    no_pause_on_login=True,
                )

        self.assertTrue(result.no_races)

    def test_collector_real_error_is_still_fatal(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            mobile_root = Path(temp) / "mobile"
            tools_dir = mobile_root / "tools"
            tools_dir.mkdir(parents=True)
            (tools_dir / "netkeiba_html_collector.py").write_text("# fake", encoding="utf-8")
            paths = PipelinePaths(
                data_root=Path(temp) / "morning",
                date_root=Path(temp) / "morning" / "20260909",
                html_root=Path(temp) / "morning" / "20260909" / "html",
                logs_root=Path(temp) / "morning" / "20260909" / "logs",
                output_path=Path(temp) / "morning" / "20260909" / "20260909_all.keiba",
            )
            paths.html_root.mkdir(parents=True)
            paths.logs_root.mkdir(parents=True)
            completed = SimpleNamespace(returncode=2)
            with patch("tools.morning_pipeline.subprocess.run", return_value=completed):
                with self.assertRaises(SystemExit):
                    run_collector(
                        mobile_root=mobile_root,
                        mode="jra",
                        race_date="20260909",
                        paths=paths,
                        overwrite=False,
                        headless=True,
                        no_pause_on_login=True,
                    )


if __name__ == "__main__":
    unittest.main()
