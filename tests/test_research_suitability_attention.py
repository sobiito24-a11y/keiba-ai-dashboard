"""Observed C/D contradictory six factors are *evidence*, never new grades."""
from copy import deepcopy

from core.research_positioning import assess as axis_assess, assign_to_view
from core.research_suitability_attention import assess


def sample(grade="C", *, score=.1768, mode="nar"):
    return dict(
        no="5", name="ティンバリートス", mode=mode, age="牝2",
        ability_rank=6, corner=6, start_rank=7, mark="—",
        research_sabcd_weight_class=dict(grade=grade,score=score),
        research_inputs=dict(jockey_rate=34,jockey_n=32),
        race_context=dict(venue="川崎",race_date="2026-11-12",
                          distance="1600m",surface="ダ",netkeiba_pace="H"),
        profile=dict(runs=[
            dict(label="前走",date="2026-10-13",venue="川崎",distance="1500m",
                 surface="ダ",finish="1着"),
            dict(label="2走前",date="2026-08-27",venue="門別",distance="1700m",
                 surface="ダ",finish="2着"),
            dict(label="3走前",date="2026-08-13",venue="門別",distance="1600m",
                 surface="ダ",finish="3着"),
        ],class_shift="判定不可"))


def test_screenshot_juvenile_C_with_two_S_stays_C_but_visible():
    horse=sample()
    old=deepcopy(horse)
    result=assess(horse)
    assert result["label"]=="適性注目"
    assert result["distance_grade"]=="S"
    assert result["recent_grade"]=="S"
    assert result["distinct_podium_starts"]==3
    assert "買い目への追加は行いません" in result["reason"]
    assert axis_assess(horse)["label"] is None  # corner 6: old front-3 cover not triggered
    assert horse==old
    final=assign_to_view([horse])
    assert final[0]["research_suitability_attention"]["label"]=="適性注目"
    assert final[0]["research_sabcd_weight_class"]["grade"]=="C"
    assert final[0]["ability_rank"]==6 and final[0]["mark"]=="—"


def test_duplicate_past_run_does_not_make_two_independent_podiums():
    horse=sample()
    horse["profile"]["runs"]=horse["profile"]["runs"][:1]
    horse["profile"]["extended_history"]=[dict(horse["profile"]["runs"][0])]
    assert assess(horse)["label"] is None


def test_a_single_podium_and_many_unplaced_are_not_promoted():
    horse=sample()
    horse["profile"]["runs"][1]["finish"]="9着"
    horse["profile"]["runs"][2]["finish"]="11着"
    assert assess(horse)["label"] is None


def test_jra_not_enabled_without_separate_validation():
    horse=sample(mode="jra")
    assert assess(horse)["label"] is None


def test_future_or_same_day_result_is_excluded():
    horse=sample()
    horse["profile"]["runs"][1]["date"]="2026-11-12"
    horse["profile"]["runs"][2]["date"]="2026-11-13"
    assert assess(horse)["label"] is None


def test_research_grade_S_is_not_always_axis_and_A_can_be_axis():
    s=sample("S",score=.81)
    a=sample("A",score=.64)
    s["research_inputs"].update(jockey_rate=22,jockey_n=100)
    a["research_inputs"].update(jockey_rate=41,jockey_n=85)
    assert axis_assess(s)["label"]=="軸比較"
    assert axis_assess(a)["label"]=="軸候補"
    before=(deepcopy(s),deepcopy(a))
    final=assign_to_view([s,a])
    assert [h["research_positioning"]["label"] for h in final]==["軸比較","軸候補"]
    assert [h["research_sabcd_weight_class"]["grade"] for h in final]==["S","A"]
    assert [s["ability_rank"],a["ability_rank"]]==[6,6]
    assert before[0]["mark"]==s["mark"] and before[1]["mark"]==a["mark"]


def test_no_forced_S_and_multiple_A_axes_allowed():
    a,b=sample("A",score=.61),sample("A",score=.65)
    for h in (a,b):
        h["research_inputs"].update(jockey_rate=45,jockey_n=125)
    final=assign_to_view([a,b])
    assert [h["research_positioning"]["label"] for h in final]==["軸候補","軸候補"]
    assert [h["research_sabcd_weight_class"]["grade"] for h in final]==["A","A"]


def test_grade_S_can_be_axis_with_same_rule_but_no_special_exemption():
    s=sample("S",score=.83)
    s["research_inputs"].update(jockey_rate=36,jockey_n=80)
    assert axis_assess(s)["label"]=="軸候補"
    s["research_inputs"]["jockey_n"]=8
    assert axis_assess(s)["label"]=="軸比較"


def test_attention_can_coexist_with_existing_front_cover():
    h=sample("D",score=.08)
    h["corner"]=2
    h["start_rank"]=2
    v=assign_to_view([h])[0]
    assert v["research_positioning"]["label"]=="押さえ候補"
    assert v["research_suitability_attention"]["label"]=="適性注目"
    assert v["research_sabcd_weight_class"]["grade"]=="D"


def test_no_results_odds_or_other_horse_grade_used_as_input():
    h=sample()
    before=assess(h)
    h["odds"]=92
    h["actual_finish"]=1
    h["result"]="1着"
    h["final_odds"]=87
    assert assess(h)==before
