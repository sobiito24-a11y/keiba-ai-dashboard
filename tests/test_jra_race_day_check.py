"""JRA V3 race-day lens: class awareness without rewriting frozen formal ranks."""
from copy import deepcopy
from types import SimpleNamespace
import pytest

from core.jra_race_day_check import annotate, class_group, render
from core.game_race_ui import race_header


@pytest.mark.parametrize("condition,label,surface,expected", [
    ("サラ系2歳 未勝利", "未勝利", "芝", "2歳未勝利"),
    ("サラ系3歳以上 1勝クラス", "A級", "芝", "1勝"),
    ("サラ系3歳以上 2勝クラス", "B級", "芝", "2勝"),
    ("サラ系3歳以上 3勝クラス", "B級", "芝", "3勝"),
    ("サラ系3歳以上 オープン", "G1", "芝", "OP・重賞"),
    ("サラ系3歳以上 オープン", "OP", "ダ", "OP・重賞"),
    ("障害3歳以上 未勝利", "未勝利", "障", "障害"),
    ("サラ系3歳以上 未勝利", "未勝利", "芝", "未勝利（その他）"),
    ("サラ系2歳 新馬", "新馬", "芝", "新馬"),
    ("サラ系3歳以上 定量", "A級", "芝", ""),
])
def test_class_is_from_race_conditions_not_old_rail_artifact(condition, label, surface, expected):
    assert class_group(dict(race_data2=condition, class_label=label, surface=surface)) == expected


def _race_view():
    return [
        dict(mode="jra", no="1", name="本線", rank="1位",
             current_evaluation_rank=2, ability_rank=1,
             training="A", rest="中3週", internal_score=97.3, mark="◎"),
        dict(mode="jra", no="2", name="別評価注目", rank="7位",
             current_evaluation_rank=3, ability_rank=4,
             training="B", rest="中2週", internal_score=76.1, mark="—"),
        dict(mode="jra", no="3", name="低評価", rank="6位",
             current_evaluation_rank=10, ability_rank=11,
             training="C", rest="中4週", internal_score=53.2, mark="—"),
        dict(mode="jra", no="4", name="正式2位", rank="2位",
             current_evaluation_rank=6, ability_rank=2,
             training="A", rest="中5週", internal_score=83.1, mark="○"),
        dict(mode="jra", no="5", name="正式3位", rank="3位",
             current_evaluation_rank=1, ability_rank=3,
             training="A", rest="中2週", internal_score=82.1, mark="▲"),
        dict(mode="jra", no="6", name="その他6", rank="4位",
             current_evaluation_rank=4, ability_rank=5,
             training="A", rest="中3週", internal_score=81.1, mark="✔"),
        dict(mode="jra", no="7", name="その他7", rank="5位",
             current_evaluation_rank=5, ability_rank=6,
             training="A", rest="中3週", internal_score=80.1, mark="△"),
    ]


def _model(*, rank_order=None, **overrides):
    order = rank_order or [1, 2, 4, 5, 6, 7, 3]
    mapped = {str(no): n for n, no in enumerate(order, 1)}
    return dict(status="ready", mode="jra",
                horses=[{"no": str(no), "rank": mapped[str(no)]} for no in range(1, 8)],
                **overrides)


def test_day_of_race_agreement_recheck_and_same_source_rank():
    view = _race_view()
    frozen = [(h["rank"], h["mark"], h["internal_score"]) for h in view]
    result = annotate(view, _model(), dict(race_data2="サラ系3歳以上 1勝クラス"))
    assert result is view
    assert [(h["rank"], h["mark"], h["internal_score"]) for h in view] == frozen
    assert view[0]["jra_race_day_check"]["role"] == "3評価一致"
    assert view[1]["jra_race_day_check"]["role"] == "取りこぼし再確認"
    assert view[1]["jra_race_day_check"]["model_b_rank"] == 2
    assert view[1]["jra_race_day_check"]["probability_calibrated"] is False
    assert view[1]["jra_race_day_check"]["rank_changed"] is False
    html = render(view)
    assert "保存済み28R" in html and "正式Top5の勝ち馬捕捉12/28" in html
    assert "2番別評価注目" in html and "3評価一致" in html
    assert "正式ランク・印は維持" in html


def test_high_rank_conflict_sets_axis_caution():
    view = _race_view()
    annotate(view, _model(rank_order=[2, 4, 5, 6, 7, 1, 3]),
             dict(race_data2="サラ系3歳以上 1勝クラス"))
    assert view[0]["jra_race_day_check"]["role"] == "軸注意"
    assert "1番本線" in render(view)


@pytest.mark.parametrize("unsafe", [
    {"status": "unavailable", "mode": "jra", "horses": []},
    _model(historical_recalculation=True),
    _model(prediction_origin="retrospective_recalculation"),
    _model(rank_order=[1, 2, 4, 5, 6, 7, 3], mode="nar") if False else {"status": "ready", "mode": "nar", "horses": []},
    {"status": "ready", "mode": "jra", "horses": [{"no": "1", "rank": 1}]},
])
def test_unsafe_or_retrospective_b_never_automatically_enters_picks(unsafe):
    view = _race_view()
    annotate(view, unsafe, dict(race_data2="サラ系2歳 未勝利"))
    assert all(h["jra_race_day_check"]["model_b_rank"] is None for h in view)
    assert "研究B未照合" in render(view)


def test_nar_unmodified_and_unknown_jra_does_not_invent_class():
    view = [dict(mode="nar", no="1", rank=1, name="地方馬")]
    original = deepcopy(view)
    assert annotate(view, _model(), {"race_data2": "A級"}) == original
    assert render(view) == ""
    jra = [dict(mode="jra", no="1", rank="1位", name="中央馬")]
    annotate(jra, None, {"race_data2": "芝1800m 右 A", "class_label": "A級"})
    assert jra[0]["jra_race_day_check"]["class_group"] == ""
    assert "判定不可" in render(jra)


def test_html_escape_is_not_bypassed():
    view = _race_view()
    view[1]["name"] = '<img src=x onerror=alert(1)>'
    annotate(view, _model(), {"race_data2": "1勝クラス"})
    html = render(view)
    assert "<img" not in html and "&lt;img" in html


def test_existing_race_header_invokes_v3_and_handles_unavailable_b(monkeypatch):
    from core import model_b
    monkeypatch.setattr(model_b, "resolve", lambda _result: {"status": "unavailable"})
    info = dict(race_name="未勝利", race_date="2026-11-15",
                racecourse="東京", distance="芝1600m", surface="芝",
                race_data2="サラ系2歳 未勝利", going="良")
    result = SimpleNamespace(race_name="未勝利", race_info=info, race_mode="jra",
                             overall_table=None)
    view = _race_view()
    html = race_header(result, view)
    assert "JRA V3・当日照合" in html
    assert "2歳未勝利" in html
    assert "研究B未照合" in html
    assert view[0]["rank"] == "1位"
