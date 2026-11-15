"""NAR day-check: fixed research rule, not retroactively scored predictions."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from core.nar_race_day_check import annotate, race_group, render


@pytest.mark.parametrize("info,expected", [
    ({"race_name": "C1－10組"}, "C1級"),
    ({"race_name": "C2－3組"}, "C2級"),
    ({"race_name": "B2九"}, "B2級"),
    ({"race_name": "A級特別"}, "A級"),
    ({"race_name": "北國王冠３歳上", "race_data2": "重賞"}, "重賞・交流"),
    ({"race_name": "2歳5"}, "2歳戦"),
    ({"race_name": "3歳2組"}, "3歳限定"),
    ({"race_name": "3歳上 C1"}, "C1級"),
    ({"race_name": "ファーストステップ 2歳 新馬"}, "新馬"),
    ({"race_name": "条件不明", "race_data2": "ダート1400m Aコース"}, "区分不明"),
])
def test_nar_classes_do_not_inherit_jra_rules_or_rail_code(info, expected):
    assert race_group(info) == expected


def _view():
    return [
        dict(no="1", name="中位馬", mode="nar", rank="7位", formal_member=False,
             ability_rank="6位", corner=2, research_inputs={"jockey_n": 25, "jockey_rate": 39},
             mark="—", score=11.1),
        dict(no="2", name="上位後方", mode="nar", rank="1位", formal_member=True,
             ability_rank=1, corner=8, research_inputs={"jockey_n": 31, "jockey_rate": 42},
             mark="◎", score=88.1),
        dict(no="3", name="中位前", mode="nar", rank="4位", formal_member=True,
             ability_rank=5, corner=1, research_inputs={"jockey_n": 12, "jockey_rate": 55},
             mark="○", score=72.2),
        dict(no="4", name="不明", mode="nar", rank="—", formal_member=False,
             ability_rank="—", corner=None, research_inputs={}, mark="—", score=None),
    ]


def test_research_annotates_without_modifying_formal_mark_score_or_rank():
    view = _view()
    frozen = [(x["rank"], x["mark"], x["score"]) for x in view]
    assert annotate(view, {"race_name": "C1－10組"}) is view
    assert frozen == [(x["rank"], x["mark"], x["score"]) for x in view]
    assert view[0]["nar_race_day_check"]["role"] == "Top5外再確認"
    assert view[0]["nar_race_day_check"]["jockey_supported"] is True
    assert view[1]["nar_race_day_check"]["role"] == "位置予測注意"
    assert view[2]["nar_race_day_check"]["role"] == "中位×4角前"
    assert view[2]["nar_race_day_check"]["jockey_supported"] is False
    assert view[3]["nar_race_day_check"]["role"] == ""
    assert view[0]["nar_race_day_check"]["probability_calibrated"] is False
    text = render(view)
    assert "NAR研究照合" in text and "74/183頭" in text
    assert "1番中位馬" in text and "2番上位後方" in text


def test_missing_or_invalid_position_does_not_generate_false_front_flag():
    view = _view()
    view[0]["corner"] = None
    annotate(view, {})
    assert view[0]["nar_race_day_check"]["role"] == ""


def test_jra_unchanged_and_no_nar_banner():
    view = _view()
    for horse in view:
        horse["mode"] = "jra"
    original = deepcopy(view)
    assert annotate(view, {"race_name": "C1－10組"}) == original
    assert render(view) == ""


def test_html_escape():
    view = _view()
    view[0]["name"] = '<script>alert(1)</script>'
    annotate(view, {"race_name": "C2－3組"})
    html = render(view)
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_nar_research_flags_are_not_under_sabcd_cell():
    from core.race_explorer_ui import _cell
    view = _view()
    annotate(view, {"race_name": "C1－10組"})
    html = _cell(view[0], {"research_sabcd": "C"}, "research_sabcd")
    assert "research-sabcd-C" in html
    assert "N再確認" not in html and "純能力6位" not in html
    assert "N位置?" not in _cell(view[1], {"research_sabcd": "A"}, "research_sabcd")


def test_nar_header_renders_without_model_b_dependency():
    from core.game_race_ui import race_header
    info = dict(race_name="C1－10組", race_number=7, race_date="2026-11-15",
                racecourse="佐賀", distance=1400, surface="ダ",
                race_data2="サラ系3歳以上 C1")
    result = SimpleNamespace(race_name="C1－10組", race_info=info,
                             race_mode="nar", overall_table=None)
    view = _view()
    html = race_header(result, view)
    assert "NAR研究照合" in html
    assert "Top5外再確認" in html


def test_banei_is_explicitly_excluded_from_thoroughbred_fourth_corner_model():
    view = _view()
    annotate(view, {"racecourse": "帯広(ば)", "race_name": "ばんえい十勝"})
    assert all(h["nar_race_day_check"]["role"] == "" for h in view)
    assert "対象外" in render(view)
    assert "74/183" not in render(view)
