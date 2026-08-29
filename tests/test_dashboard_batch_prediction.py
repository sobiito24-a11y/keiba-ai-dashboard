from __future__ import annotations

import io
import re
import unittest
import zipfile
from unittest.mock import patch

import pandas as pd

from core.dashboard_batch import (
    BatchPredictionError,
    UploadedSource,
    expand_uploaded_sources,
    group_html_by_race,
    predict_uploaded_sources,
)
from core.models import PredictionResult
from core.prediction_input import predict_from_html_inputs
from core.prediction_snapshot import restore_prediction_result
from core.prediction_snapshot import race_snapshot_from_result


def html_page(mode: str, kind: str, race_id: str, *, extra: str = "") -> bytes:
    host = "nar.netkeiba.com" if mode == "nar" else "race.netkeiba.com"
    if kind == "style":
        path = f"/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=1"
        title = "有利な脚質 データ分析"
    elif kind == "jockey":
        path = f"/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=2"
        title = "得意な騎手 データ分析"
    else:
        path = f"/race/{kind}.html?race_id={race_id}"
        title = {"newspaper": "競馬新聞", "speed": "タイム指数", "oikiri": "調教"}[kind]
    scope = "地方競馬" if mode == "nar" else "中央競馬"
    return (
        f'<html><head><title>{title} | {scope}</title>'
        f'<link rel="canonical" href="https://{host}{path}"></head>'
        f'<body>{extra}</body></html>'
    ).encode("utf-8")


def sources_for(mode: str, race_id: str, *, include_optional: bool = False) -> list[UploadedSource]:
    kinds = ["newspaper", "speed", "style"]
    if include_optional:
        kinds.append("jockey" if mode == "nar" else "oikiri")
    return [UploadedSource(f"renamed_{race_id}_{index}.html", html_page(mode, kind, race_id)) for index, kind in enumerate(kinds)]


def fake_result(mode: str, race_id: str) -> PredictionResult:
    venue_map = {
        "202601": "札幌",
        "202604": "新潟",
        "202635": "盛岡",
        "202642": "帯広",
    }
    venue = next((name for prefix, name in venue_map.items() if race_id.startswith(prefix)), "会場")
    race_no = f"{int(race_id[-2:])}R"
    table = pd.DataFrame(
        [
            {
                "馬番": 1,
                "馬名": f"{race_id}-A",
                "market_ability_score": 91.2,
                "market_ability_rank": 1,
                "ability_band_v2": "A",
                "current_evaluation_rank": 2,
                "ai_current_mark": "○",
                "表示印": "○",
                "value_signal": True,
                "単勝オッズ": 9.8,
            },
            {
                "馬番": 2,
                "馬名": f"{race_id}-B",
                "market_ability_score": 89.0,
                "market_ability_rank": 2,
                "ability_band_v2": "A",
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "表示印": "◎",
                "value_signal": False,
                "単勝オッズ": 3.1,
            },
        ]
    )
    return PredictionResult(
        race_mode=mode,  # type: ignore[arg-type]
        created_at="2026-08-14T09:00:00",
        race_name=f"{venue}{race_no}",
        race_info={
            "race_id": race_id,
            "date": "2026-08-14",
            "venue": venue,
            "race_number": race_no,
            "race_name": f"{venue}{race_no}",
            "distance": 1200,
            "surface": "芝" if mode == "jra" else "ダ",
            "head_count": 2,
        },
        overall_table=table.copy(),
        horse_evaluation=table.copy(),
        status="ok",
        logic_version="market",
        debug_info={"market_compare": {"prediction_signature": race_id, "horses": []}},
    )


def predictor(mode: str):
    def run(_html_files, file_names, *, prediction_logic_version="market"):
        self_name = next(iter(file_names.values()))
        race_id = re.search(r"\d{12}", self_name).group(0)
        if prediction_logic_version != "market":
            raise AssertionError("Dashboard must use Mobile market mode")
        return fake_result(mode, race_id)

    return run


def zip_bytes(files: list[UploadedSource]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in files:
            archive.writestr(f"collection/{item.file_name}", item.data)
        archive.writestr("manifest.csv", "ignored")
    return buffer.getvalue()


class DashboardBatchPredictionTest(unittest.TestCase):
    def test_mixed_jra_nar_multiple_race_ids_and_venues(self) -> None:
        sources = []
        for mode, race_id in (
            ("jra", "202601010501"),
            ("jra", "202604020501"),
            ("nar", "202635081001"),
            ("nar", "202642081001"),
        ):
            sources.extend(sources_for(mode, race_id))
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")) as jra, patch(
            "core.prediction_input.predict_nar", side_effect=predictor("nar")
        ) as nar:
            report = predict_uploaded_sources(sources)
        self.assertEqual(report.predicted_race_count, 4)
        self.assertEqual(jra.call_count, 2)
        self.assertEqual(nar.call_count, 2)
        self.assertEqual(report.event_snapshot["scope"]["race_modes"], ["jra", "nar"])
        self.assertEqual(set(report.event_snapshot["scope"]["venues"]), {"札幌", "新潟", "盛岡", "帯広"})

    def test_zip_input_is_expanded_and_predicted(self) -> None:
        html_sources = sources_for("jra", "202601010501", include_optional=True)
        archive = UploadedSource("anything.zip", zip_bytes(html_sources))
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")):
            report = predict_uploaded_sources([archive])
        self.assertEqual(report.input_file_count, 1)
        self.assertEqual(report.html_file_count, 4)
        self.assertEqual(report.predicted_race_count, 1)
        self.assertIn("oikiri", report.event_snapshot["races"][0]["input_summary"]["kinds"])

    def test_optional_jockey_and_oikiri_are_not_required(self) -> None:
        sources = sources_for("jra", "202601010501") + sources_for("nar", "202635081001")
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")), patch(
            "core.prediction_input.predict_nar", side_effect=predictor("nar")
        ):
            report = predict_uploaded_sources(sources)
        self.assertEqual(report.predicted_race_count, 2)
        self.assertFalse(report.errors)

    def test_complete_36_race_batch_uses_mobile_market_mode_for_every_race(self) -> None:
        sources: list[UploadedSource] = []
        for race_index in range(1, 37):
            sources.extend(sources_for("jra", f"20260403{race_index:04d}"))
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")) as jra:
            report = predict_uploaded_sources(sources)
        self.assertEqual(report.predicted_race_count, 36)
        self.assertEqual(report.skipped_race_count, 0)
        self.assertEqual(jra.call_count, 36)

    def test_batch_retries_without_past_detail_when_one_race_prediction_fails(self) -> None:
        calls: list[bool | None] = []

        def flaky_predictor(_html_files, file_names, *, prediction_logic_version="market", fetch_past_detail=True):
            calls.append(fetch_past_detail)
            if fetch_past_detail is not False:
                raise RuntimeError("past detail timeout")
            self_name = next(iter(file_names.values()))
            race_id = re.search(r"\d{12}", self_name).group(0)
            if prediction_logic_version != "market":
                raise AssertionError("Dashboard must use Mobile market mode")
            return fake_result("jra", race_id)

        with patch("core.prediction_input.predict_jra", side_effect=flaky_predictor):
            report = predict_uploaded_sources(sources_for("jra", "202601010501"))
        self.assertEqual(report.predicted_race_count, 1)
        self.assertEqual(report.skipped_race_count, 0)
        self.assertEqual(calls, [True, False])
        self.assertTrue(any("過去走詳細取得を省略" in message for message in report.warnings))

    def test_filename_changes_do_not_affect_content_classification(self) -> None:
        entries = [
            UploadedSource("a.html", html_page("jra", "newspaper", "202601010501")),
            UploadedSource("b.html", html_page("jra", "speed", "202601010501")),
            UploadedSource("c.html", html_page("jra", "style", "202601010501")),
        ]
        bundles, _warnings, errors, recognized = group_html_by_race(entries)
        self.assertFalse(errors)
        self.assertEqual(recognized, 3)
        self.assertEqual(set(bundles["202601010501"].html_files), {"newspaper", "speed", "style"})

    def test_result_page_is_not_misclassified_as_oikiri(self) -> None:
        race_id = "202601010501"
        result_html = (
            '<html><head><title>結果・払戻 | 中央競馬</title>'
            f'<link rel="canonical" href="https://race.netkeiba.com/race/result.html?race_id={race_id}">'
            '</head><body id="Netkeiba_Race_Result"><div class="Oikiri">menu only</div></body></html>'
        ).encode()
        entries = sources_for("jra", race_id, include_optional=True)
        entries.append(UploadedSource("renamed.html", result_html))
        bundles, warnings, errors, _recognized = group_html_by_race(entries)
        self.assertFalse(errors)
        self.assertEqual(set(bundles[race_id].html_files), {"newspaper", "speed", "style", "oikiri"})
        self.assertTrue(any("確定結果HTML" in message for message in warnings))

    def test_duplicate_same_kind_is_not_silently_overwritten(self) -> None:
        sources = sources_for("jra", "202601010501")
        sources.append(
            UploadedSource(
                "different_speed.html",
                html_page("jra", "speed", "202601010501", extra="different"),
            )
        )
        with self.assertRaises(BatchPredictionError):
            predict_uploaded_sources(sources)

    def test_identical_duplicate_html_is_deduplicated(self) -> None:
        sources = sources_for("jra", "202601010501")
        sources.append(UploadedSource("copy.html", sources[0].data))
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")):
            report = predict_uploaded_sources(sources)
        self.assertEqual(report.predicted_race_count, 1)
        self.assertTrue(any("同一HTML重複" in message for message in report.warnings))

    def test_missing_mobile_required_html_skips_only_that_race(self) -> None:
        complete = sources_for("jra", "202601010501")
        incomplete = sources_for("jra", "202604020501")[:2]
        with patch("core.prediction_input.predict_jra", side_effect=predictor("jra")):
            report = predict_uploaded_sources(complete + incomplete)
        self.assertEqual(report.predicted_race_count, 1)
        self.assertEqual(report.skipped_race_count, 1)
        self.assertTrue(any("Mobile必須HTML不足" in message for message in report.errors))

    def test_dashboard_snapshot_matches_returned_mobile_prediction_result(self) -> None:
        expected = fake_result("jra", "202601010501")
        with patch("core.prediction_input.predict_jra", return_value=expected):
            report = predict_uploaded_sources(sources_for("jra", "202601010501"))
        restored = restore_prediction_result(report.event_snapshot["races"][0])
        columns = [
            "market_ability_score",
            "market_ability_rank",
            "ability_band_v2",
            "current_evaluation_rank",
            "ai_current_mark",
            "value_signal",
        ]
        pd.testing.assert_frame_equal(
            expected.overall_table[columns],
            restored.overall_table[columns],
            check_dtype=False,
        )

    def test_mobile_direct_and_dashboard_batch_match_all_required_horse_fields(self) -> None:
        race_id = "202635081001"
        expected = fake_result("nar", race_id)
        html_files = {
            kind: html_page("nar", kind, race_id).decode()
            for kind in ("newspaper", "speed", "style")
        }
        file_names = {kind: f"{race_id}_{kind}.html" for kind in html_files}
        sources = [
            UploadedSource(file_names[kind], html_files[kind].encode())
            for kind in html_files
        ]
        with patch("core.prediction_input.predict_nar", return_value=expected):
            direct = predict_from_html_inputs(
                "nar",
                html_files,
                file_names,
                prediction_logic_version="market",
            )
            report = predict_uploaded_sources(sources, prediction_logic_version="market")
        direct_horses = race_snapshot_from_result(
            direct,
            source_files=file_names,
        )["horses"]
        batch_horses = report.event_snapshot["races"][0]["horses"]
        fields = (
            "horse_no",
            "horse_name",
            "ability_value",
            "ability_rank",
            "ability_band",
            "current_evaluation_rank",
            "mark",
            "value_signal",
        )
        self.assertEqual(
            [tuple(horse.get(field) for field in fields) for horse in direct_horses],
            [tuple(horse.get(field) for field in fields) for horse in batch_horses],
        )

    def test_empty_zip_and_path_traversal_are_rejected(self) -> None:
        empty = io.BytesIO()
        with zipfile.ZipFile(empty, "w"):
            pass
        with self.assertRaises(BatchPredictionError):
            expand_uploaded_sources([UploadedSource("empty.zip", empty.getvalue())])

        bad = io.BytesIO()
        with zipfile.ZipFile(bad, "w") as archive:
            archive.writestr("../race.html", b"bad")
        with self.assertRaises(BatchPredictionError):
            expand_uploaded_sources([UploadedSource("bad.zip", bad.getvalue())])


if __name__ == "__main__":
    unittest.main()
