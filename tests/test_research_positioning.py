from copy import deepcopy

from core.research_positioning import assess, assign_to_view, _missing_core


def horse(grade="A", *, score=.65, mode="nar", ability_rank=3, corner=2,
          start_rank=2, jockey_rate=38, jockey_starts=150, recent=2):
    runs = [
        dict(label="前走", date="2026-11-09", finish=f"{recent}着"),
        dict(label="2走前", date="2026-10-27", finish="5着"),
    ]
    return dict(
        no="8", mode=mode, ability_rank=ability_rank, corner=corner,
        start_rank=start_rank, mark="◎", score="55.8",
        rank=2, research_sabcd_weight_class=dict(grade=grade, score=score),
        research_inputs=dict(jockey_rate=jockey_rate, jockey_n=jockey_starts),
        profile=dict(runs=runs),
        race_context=dict(venue="川崎", race_date="2026-11-14"),
    )


def test_a_with_both_factors_axis_hypothesis_and_no_bet_change():
    h = horse()
    old = deepcopy(h)
    x = assess(h)
    assert x["label"] == "軸候補"
    assert "11/11の探索条件" in x["reason"]
    assert h == old
    projected = assign_to_view([h])
    assert projected[0]["research_positioning"]["label"] == "軸候補"
    assert projected[0]["mark"] == "◎"
    assert projected[0]["research_sabcd_weight_class"]["grade"] == "A"


def test_a_caution_and_intermediate_not_auto_downgraded():
    h = horse(score=.55, jockey_rate=24)
    assert assess(h)["label"] == "軸慎重"
    h["research_sabcd_weight_class"]["score"] = .65
    assert assess(h)["label"] == "相手本線"
    assert h["research_sabcd_weight_class"]["grade"] == "A"


def test_c_and_d_with_podium_and_front_three_get_cover_only():
    for grade in ("C", "D"):
        h = horse(grade, score=.20 if grade == "C" else .09)
        assert assess(h)["label"] == "押さえ候補"
        assert "予測4角2番手" in assess(h)["reason"]
    h["corner"] = 6
    assert assess(h)["label"] is None
    h["corner"] = 3
    h["profile"]["runs"][0]["finish"] = "6着"
    assert assess(h)["label"] is None


def test_missing_rank_with_independent_front_and_jockey_has_only_reference():
    h = horse(None,score=None,ability_rank=None,jockey_rate=40)
    old = deepcopy(h)
    v = assess(h)
    assert v["label"] == "押さえ参考"
    assert v["missing_core"] == ("純能力順位",)
    assert "総合ランクは判定不可" in v["reason"]
    assert h == old
    assert h["research_sabcd_weight_class"]["grade"] is None


def test_missing_corner_is_not_replaced_by_saved_start_or_style():
    h = horse(None,score=None,corner=None)
    h["style"] = "先行"
    x = assess(h)
    assert x["label"] == "材料不足"
    assert x["missing_core"] == ("予測4角順位",)
    assert "不足順位を脚質や別の能力指数から推測して補いません" in x["reason"]
    assert _missing_core(h) == ["予測4角順位"]


def test_formal_marks_results_and_odds_are_ignored():
    h = horse()
    before = assess(h)
    h["odds"] = "999.9"
    h["actual_finish"] = 16
    h["top3"] = False
    h["mark"] = "×"
    assert assess(h) == before


def test_jra_uses_separate_course_jockey_floor():
    h = horse(mode="jra", jockey_rate=31, score=.65)
    assert assess(h)["label"] == "軸候補"
    h["research_inputs"]["jockey_n"] = 5
    assert assess(h)["label"] == "相手本線"
