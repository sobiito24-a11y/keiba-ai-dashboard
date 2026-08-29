from __future__ import annotations

import copy
import hashlib
import io
import json
import unittest
import zipfile
from unittest.mock import patch

import pandas as pd

from core.models import PredictionResult
from core.prediction_snapshot import (
    KEIBA_FORMAT,
    KeibaSnapshotError,
    UnsupportedSchemaError,
    build_event_snapshot,
    keiba_bytes,
    keiba_file_name,
    load_keiba,
    race_snapshot_from_result,
    replace_race_result,
    restore_prediction_result,
    subset_event_snapshot,
    update_user_selection,
)


def result_for(
    race_id: str = "202601010501",
    *,
    mode: str = "jra",
    venue: str = "札幌",
    race_number: str = "1R",
) -> PredictionResult:
    table = pd.DataFrame(
        [
            {
                "馬番": 1,
                "馬名": "アルファ",
                "馬年齢": "牡4",
                "市場能力値": 88.5,
                "market_ability_score": 88.5,
                "market_ability_rank": 1,
                "ability_band_v2": "A",
                "current_evaluation_rank": 2,
                "ai_current_mark": "○",
                "表示印": "○",
                "value_signal": True,
                "単勝オッズ": 8.4,
                "斤量": 56.0,
                "騎手": "騎手A",
                "jockey_display_market": "騎手A（複32%）",
                "状態": "上向き",
                "pace_material_label": "差し向き ○",
                "course_material_label": "4角中団有利 ○",
                "netkeiba_favorable_label": "推定有利馬",
                "position_path_market": "中団 → 中団 → 中団",
                "training_display": "A 動き良好",
                "stable_comment_display": "状態は良い",
                "value_plus_materials": ["差し向き", "状態上向き"],
                "value_minus_materials": [],
                "距離指数": 84,
                "コース指数": 82,
                "3走前": 78,
                "2走前": 81,
                "前走": 85,
                "平均指数": 81.3,
                "★最高指数": 90,
            },
            {
                "馬番": 2,
                "馬名": "ベータ",
                "馬年齢": "牝5",
                "market_ability_score": 86.0,
                "market_ability_rank": 2,
                "ability_band_v2": "A",
                "current_evaluation_rank": 1,
                "ai_current_mark": "◎",
                "表示印": "◎",
                "value_signal": False,
                "単勝オッズ": 3.2,
                "斤量": 54.0,
                "騎手": "騎手B",
                "状態": "平行線",
            },
        ]
    )
    result = PredictionResult(
        race_mode=mode,  # type: ignore[arg-type]
        version="0.4.1",
        created_at="2026-08-14T09:00:00",
        race_name=f"{venue}{race_number}",
        race_info={
            "race_id": race_id,
            "date": "2026-08-14",
            "venue": venue,
            "race_number": race_number,
            "race_name": f"{venue}{race_number}",
            "distance": 1200,
            "surface": "芝" if mode == "jra" else "ダ",
            "head_count": 2,
        },
        overall_table=table.copy(),
        horse_evaluation=table.copy(),
        source_files={"newspaper": "newspaper.html"},
        status="ok",
        logic_version="market",
        debug_info={
            "market_compare": {
                "version": "1.1",
                "prediction_signature": "fixed-signature",
                "horses": [],
                "user_selection": {
                    "horses": ["1 アルファ"],
                    "reason": "A帯8.4倍",
                    "ticket": "単勝",
                },
            }
        },
    )
    return result


def raw_keiba(snapshot: dict) -> bytes:
    payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    manifest = {
        "format": KEIBA_FORMAT,
        "schema_version": snapshot.get("schema_version"),
        "snapshot_sha256": hashlib.sha256(payload).hexdigest(),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.writestr("snapshot.json", payload)
    return buffer.getvalue()


class PredictionSnapshotTest(unittest.TestCase):
    def test_prediction_result_round_trip_preserves_mobile_outputs(self) -> None:
        result = result_for()
        race = race_snapshot_from_result(result, source_files={"newspaper": "race.html"})
        restored = restore_prediction_result(race)
        columns = [
            "market_ability_score",
            "market_ability_rank",
            "ability_band_v2",
            "current_evaluation_rank",
            "ai_current_mark",
            "value_signal",
        ]
        pd.testing.assert_frame_equal(
            result.overall_table[columns].reset_index(drop=True),
            restored.overall_table[columns].reset_index(drop=True),
            check_dtype=False,
        )
        self.assertEqual(restored.logic_version, "market")
        self.assertEqual(restored.created_at, "2026-08-14T09:00:00")

    def test_event_save_and_reload_is_identical(self) -> None:
        race = race_snapshot_from_result(result_for())
        event = build_event_snapshot([race])
        loaded = load_keiba(keiba_bytes(event))
        self.assertEqual(loaded, event)
        self.assertEqual(loaded["schema_version"], 1)
        self.assertEqual(loaded["races"][0]["mobile_snapshot"], race["mobile_snapshot"])

    def test_snapshot_has_machine_matchable_display_fields(self) -> None:
        race = race_snapshot_from_result(result_for())
        horse = race["horses"][0]
        self.assertEqual(horse["horse_no"], "1")
        self.assertEqual(horse["sex_age"], "牡4")
        self.assertEqual(horse["ability_value"], 88.5)
        self.assertEqual(horse["ability_rank"], 1)
        self.assertEqual(horse["ability_band"], "A")
        self.assertEqual(horse["current_evaluation_rank"], 2)
        self.assertEqual(horse["mark"], "○")
        self.assertTrue(horse["value_signal"])
        self.assertEqual(horse["netkeiba_favorable"], "推定有利馬")
        self.assertEqual(horse["training_short"], "A 動き良好")
        self.assertEqual(horse["stable_comment_summary"], "状態は良い")

    def test_race_navigation_number_comes_from_race_id_not_age_in_race_name(self) -> None:
        result = result_for()
        result.race_name = "3歳未勝利"
        result.race_info.pop("race_number")
        race = race_snapshot_from_result(result)
        self.assertEqual(race["race_number"], "1R")

    def test_saved_prediction_is_not_recalculated_by_current_predictor(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        data = keiba_bytes(event)
        with patch("core.jra_predictor.predict_jra", side_effect=AssertionError("再計算禁止")):
            loaded = load_keiba(data)
            restored = restore_prediction_result(loaded["races"][0])
        self.assertEqual(restored.overall_table.loc[0, "ai_current_mark"], "○")
        self.assertEqual(restored.overall_table.loc[0, "market_ability_score"], 88.5)

    def test_jra_candidate_b_display_aliases_survive_save_and_reload(self) -> None:
        result = result_for()
        result.overall_table.loc[0, "market_ability_score"] = 50
        result.overall_table.loc[0, "ability_band_v2"] = "C"
        result.overall_table.loc[0, "current_evaluation_rank"] = 1
        result.overall_table.loc[0, "ai_current_mark"] = "◎"
        result.overall_table.loc[0, "表示印"] = "◎"
        result.overall_table.loc[1, "market_ability_score"] = 80
        result.overall_table.loc[1, "ability_band_v2"] = "A"
        result.overall_table.loc[1, "current_evaluation_rank"] = 2
        result.overall_table.loc[1, "ai_current_mark"] = "○"
        result.overall_table.loc[1, "表示印"] = "○"
        result.overall_table.loc[1, "training_display"] = "A 好気配"
        result.overall_table.loc[1, "stable_comment_display"] = "順調に仕上がった。"
        result.horse_evaluation = result.overall_table.copy()

        race = race_snapshot_from_result(result)
        event = build_event_snapshot([race])
        restored = restore_prediction_result(load_keiba(keiba_bytes(event))["races"][0])
        restored_by_no = {str(row["馬番"]): row for row in restored.overall_table.to_dict("records")}

        self.assertEqual(restored_by_no["1"]["baseline_ver3_final_mark"], "◎")
        self.assertEqual(restored_by_no["1"]["baseline_ver3_current_evaluation_rank"], 1)
        self.assertEqual(restored_by_no["2"]["shadow_ver3_candidate"], "jra_candidate_b")
        self.assertEqual(restored_by_no["2"]["ver3_final_mark"], "◎")
        self.assertEqual(restored_by_no["2"]["ver3_current_evaluation_rank"], 1)
        self.assertIn("shadow_ver3_candidate_reason", restored.overall_table.columns)
        self.assertEqual(restored_by_no["2"]["market_ability_score"], 80)
        self.assertEqual(restored_by_no["2"]["ability_band_v2"], "A")

    def test_user_selection_survives_save_and_reload(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        loaded = load_keiba(keiba_bytes(event))
        selection = loaded["races"][0]["mobile_snapshot"]["market_compare"]["user_selection"]
        self.assertEqual(selection["horses"], ["1 アルファ"])
        self.assertEqual(selection["reason"], "A帯8.4倍")

    def test_replace_race_result_saves_later_user_selection(self) -> None:
        result = result_for()
        event = build_event_snapshot([race_snapshot_from_result(result)])
        result.debug_info["market_compare"]["user_selection"] = {
            "horses": ["2 ベータ"],
            "reason": "今回条件",
            "ticket": "複勝",
        }
        updated = replace_race_result(event, "202601010501", result)
        loaded = load_keiba(keiba_bytes(updated))
        selection = loaded["races"][0]["mobile_snapshot"]["market_compare"]["user_selection"]
        self.assertEqual(selection["horses"], ["2 ベータ"])

    def test_user_selection_update_does_not_rebuild_prediction_values(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        before = copy.deepcopy(event["races"][0]["prediction_result"])
        updated = update_user_selection(
            event,
            "202601010501",
            {"horses": ["2 ベータ"], "reason": "メモ", "ticket": "ワイド"},
        )
        after = copy.deepcopy(updated["races"][0]["prediction_result"])
        before["debug_info"]["market_compare"]["user_selection"] = after["debug_info"]["market_compare"]["user_selection"]
        self.assertEqual(after, before)

    def test_venue_subset_contains_multiple_races_without_other_venue(self) -> None:
        races = [
            race_snapshot_from_result(result_for("202601010501", venue="札幌", race_number="1R")),
            race_snapshot_from_result(result_for("202601010502", venue="札幌", race_number="2R")),
            race_snapshot_from_result(result_for("202604020501", venue="新潟", race_number="1R")),
        ]
        event = build_event_snapshot(races)
        subset = subset_event_snapshot(event, race_date="2026-08-14", race_mode="jra", venue="札幌")
        self.assertEqual([item["race_id"] for item in subset["races"]], ["202601010501", "202601010502"])
        self.assertEqual(keiba_file_name(subset), "2026-08-14_JRA_札幌.keiba")

    def test_keiba_does_not_embed_source_html(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        with zipfile.ZipFile(io.BytesIO(keiba_bytes(event))) as archive:
            self.assertEqual(set(archive.namelist()), {"manifest.json", "snapshot.json"})
            self.assertNotIn("<html", archive.read("snapshot.json").decode("utf-8").lower())

    def test_empty_and_broken_files_are_rejected(self) -> None:
        with self.assertRaises(KeibaSnapshotError):
            load_keiba(b"")
        with self.assertRaises(KeibaSnapshotError):
            load_keiba(b"not-a-zip")

    def test_old_schema_is_rejected_with_clear_error(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        old = copy.deepcopy(event)
        old["schema_version"] = 0
        with self.assertRaises(UnsupportedSchemaError):
            load_keiba(raw_keiba(old))

    def test_future_schema_is_rejected(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        future = copy.deepcopy(event)
        future["schema_version"] = 99
        with self.assertRaises(UnsupportedSchemaError):
            load_keiba(raw_keiba(future))

    def test_duplicate_race_id_is_rejected(self) -> None:
        race = race_snapshot_from_result(result_for())
        with self.assertRaises(KeibaSnapshotError):
            build_event_snapshot([race, copy.deepcopy(race)])

    def test_checksum_tampering_is_rejected(self) -> None:
        event = build_event_snapshot([race_snapshot_from_result(result_for())])
        data = keiba_bytes(event)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            snapshot = archive.read("snapshot.json")
        manifest["snapshot_sha256"] = "0" * 64
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("manifest.json", json.dumps(manifest))
            archive.writestr("snapshot.json", snapshot)
        with self.assertRaises(KeibaSnapshotError):
            load_keiba(buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
