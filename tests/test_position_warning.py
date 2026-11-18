from copy import deepcopy

from core.position_warning import find_position_conflicts


def test_early_style_and_back_start_is_warning_without_modifying_snapshot():
    race = {"mobile_snapshot": {"market_compare": {"horses": [
        {"馬番": "7", "馬名": "テストA", "running_style_market": "先", "position_start_label_market": "後方"},
        {"馬番": "2", "馬名": "テストB", "running_style_market": "逃", "position_start_label_market": "後方"},
        {"馬番": "1", "馬名": "テストC", "running_style_market": "先", "position_start_label_market": "先団"},
        {"馬番": "3", "馬名": "テストD", "running_style_market": "差", "position_start_label_market": "後方"},
    ]}}}
    before = deepcopy(race)
    flagged = find_position_conflicts(race)
    assert [h["horse_no"] for h in flagged] == ["2", "7"]
    assert race == before


def test_unknown_data_does_not_flag():
    assert find_position_conflicts({}) == []
    assert find_position_conflicts({"mobile_snapshot": {"market_compare": {"horses": [
        {"馬番": "1", "馬名": "名前だけ"},
        {"馬番": "2", "馬名": "不明", "running_style_market": "先"},
    ]}}}) == []
