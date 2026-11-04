"""Guardrails for NAR recent-form reference; no outcomes in the evaluator."""
from types import SimpleNamespace

import pandas as pd

from core.nar_recent_form_reference import (
    attach_nar_form_reference,
    evaluate_nar_rows,
    neutralize_unverified_nar_pace,
)


def example(no=1, ability=50, rank=1, last_corner=None):
    last = {
        "key": "race1", "race_date": "2026-11-01",
        "position": 1, "value": 25, "venue": "船橋", "distance": 1200,
    }
    if last_corner is not None:
        last["corner4_rank"] = last_corner
    return {
        "馬番": no, "馬名": f"馬{no}",
        "market_ability_score": ability, "market_ability_rank": rank,
        "netkeiba_corner4_rank": rank,
        "_lap_prediction_status": "HTML内に実値なし", "_netkeiba_pace": "H",
        "_past_runs": [last],
    }


def test_finish_position_is_not_fourth_corner():
    result = evaluate_nar_rows(
        [example(1, 50, 1), example(2, 49, 2)],
        {"venue": "船橋", "distance": 1200, "date": "2026-11-04"},
    )
    assert all(row["nar_form_ref_prior_corner"] is None for row in result)
    assert all(row["nar_form_ref_pace"] == "未取得" for row in result)
    assert {row["nar_form_ref_rank"] for row in result} == {1, 2}


def test_explicit_past_fourth_corner_and_source_unchanged():
    rows = [example(1, 50, 1), example(2, 49, 2, 2)]
    data = evaluate_nar_rows(rows, {"date": "2026-11-04"})
    assert data[1]["nar_form_ref_prior_corner"] == 2
    assert "前走4角3位内" in data[1]["nar_form_ref_reason"]
    assert "nar_form_ref_rank" not in rows[1]


def test_missing_pace_is_neutralized_only_in_nar():
    original = pd.DataFrame([example()])
    nar = SimpleNamespace(
        race_mode="nar", overall_table=original.copy(), horse_evaluation=original.copy()
    )
    neutralize_unverified_nar_pace(nar)
    assert nar.overall_table["_netkeiba_pace"].iat[0] == ""
    assert original["_netkeiba_pace"].iat[0] == "H"
    jra = SimpleNamespace(
        race_mode="jra", overall_table=original.copy(), horse_evaluation=original.copy()
    )
    neutralize_unverified_nar_pace(jra)
    assert jra.overall_table["_netkeiba_pace"].iat[0] == "H"


def test_race_day_data_does_not_leak_into_past_features():
    row = example()
    row["_past_runs"][0]["race_date"] = "2026-11-04"
    data = evaluate_nar_rows([row], {"date": "2026-11-04"})
    assert data[0]["nar_form_ref_status"] == "過去走情報不足"


def test_reference_does_not_mutate_ability_or_formal_marks():
    original = pd.DataFrame([dict(example(), nar_final_rank=4, 表示印="")])
    nar = SimpleNamespace(
        race_mode="nar", race_info={"date": "2026-11-04"},
        overall_table=original.copy(), horse_evaluation=original.copy(), debug_info={},
    )
    attach_nar_form_reference(nar)
    assert nar.overall_table["market_ability_score"].iat[0] == 50
    assert nar.overall_table["nar_final_rank"].iat[0] == 4
    assert nar.overall_table["表示印"].iat[0] == ""
    assert nar.overall_table["nar_form_ref_rank"].iat[0] == 1
    assert nar.debug_info["nar_form_reference"]["research_only"] is True
