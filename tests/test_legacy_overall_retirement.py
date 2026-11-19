"""Retired archive grades cannot re-enter newly generated predictions."""
import pandas as pd
import pytest

from core.audit_features import add_audit_evaluation_columns, build_audit_export_table
from core.form_rank import LEGACY_OVERALL_COLUMNS, add_form_rank_columns, power_group_for_row


@pytest.mark.parametrize("mode", ["jra", "nar"])
@pytest.mark.parametrize("evaluate", [add_form_rank_columns, add_audit_evaluation_columns])
@pytest.mark.parametrize("empty", [False, True])
def test_new_evaluation_drops_legacy_grades_without_mutating_archive(mode, evaluate, empty):
    source = pd.DataFrame([dict(
        馬番=1, 馬名="保存馬", AI点=91., _raw_score=83., 能力評価値=83.,
        最終印="◎", overall_rank="D", overall_rank_reason="旧評価",
        総合ランク="D", 総合ランク理由="旧評価",
        **{"3走前": 38, "2走前": 45, "前走": 50},
    )])
    if empty:
        source = source.iloc[:0]
    before = source.copy(deep=True)
    updated = evaluate(source, race_type=mode)
    assert not set(LEGACY_OVERALL_COLUMNS).intersection(updated.columns)
    pd.testing.assert_frame_equal(source, before)
    for key in ["AI点", "_raw_score", "能力評価値", "最終印"]:
        pd.testing.assert_series_equal(updated[key], source[key])
    assert "momentum_rank" in updated and "power_group" in updated
    archive_export = build_audit_export_table(source)
    if not empty:
        assert set(LEGACY_OVERALL_COLUMNS).issubset(archive_export.columns)


def test_old_s_cannot_promote_power_group_to_axis():
    row = pd.Series(dict(ability_band="上位帯", ability_rank="A", overall_rank="S"))
    assert power_group_for_row(row) == ("A", "相手本線")
    row["overall_rank"] = "D"
    assert power_group_for_row(row) == ("A", "相手本線")
    row["表示印"] = "◎"
    assert power_group_for_row(row) == ("SS", "軸")
