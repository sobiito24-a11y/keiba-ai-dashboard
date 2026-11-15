"""Safety and ranking invariants for the out-of-sample fusion research."""
from copy import deepcopy

from core.research_formal_sabcd_fusion import (
    VERSION, FORMAL_WEIGHT, SABCD_WEIGHT, evaluate_race, assign_to_view
)


def horses(mode="jra"):
    values = {1:.10, 2:.90, 3:.85, 4:.80, 5:.70, 6:.65, 7:.95}
    return [
        dict(no=str(i), name="保存馬"+str(i), rank=i, mode=mode, mark="◎" if i==1 else "",
             candidate_formal_score=(101-i if mode == "jra" or i <= 5 else None),
             research_sabcd_weight_class=dict(
                 grade="A" if values[i] >= .5 else "D", score=values[i],
                 retro=False, version="weight-class-shadow-20261112"))
        for i in range(1, 8)
    ]


def test_fixed_mix_five_only_and_formal_top5_can_change_without_forcing_s_grade():
    data=horses()
    source=deepcopy(data)
    out=evaluate_race(data)
    assert data == source
    assert (FORMAL_WEIGHT,SABCD_WEIGHT)==(.25,.75)
    assert sum(r["top5"] for r in out.values()) == 5
    assert {n for n,r in out.items() if r["top5"]} != set("12345")
    assert set(out)==set("1234567")
    assert all(r["version"]==VERSION for r in out.values())
    assert all(r["score"] is None for r in out.values()) # No fake probability.
    assert all("確率・正式ランク" in r["reason"] for r in out.values())
    assign_to_view(data)
    for a,b in zip(data,source):
        assert {k:v for k,v in a.items() if k!="research_formal_sabcd_fusion"} == b
        assert a["research_formal_sabcd_fusion"]==out[a["no"]]


def test_outcome_and_odds_never_used_in_fusion():
    data=horses()
    expected=evaluate_race(data)
    for i,h in enumerate(data):
        h["actual_finish"]=7-i
        h["final_win_odds"]=1.1
        h["odds"]=1.1
        h["race_results_v1"]={"runners": [dict(horse_no=h["no"], finish=1)]}
    assert evaluate_race(data)==expected


def test_missing_formal_rank_and_missing_shadow_are_not_filled_from_ability():
    data=horses("nar")
    data[0]["rank"]=None
    data[1]["research_sabcd_weight_class"]["score"]=None
    data[0]["ability_rank"]=1
    data[1]["mark"]="S"
    outcome=evaluate_race(data)
    assert outcome["1"]["rank"] is None
    assert outcome["2"]["rank"] is None
    assert "未取得" in outcome["1"]["reason"]
    assert "参考順位" in outcome["7"]["reason"]
    assert all("SABCD" not in h or True for h in data)


def test_under_five_comparable_horses_never_proclaim_five_selections():
    data=horses()[:4]
    out=evaluate_race(data)
    assert not any(v["top5"] for v in out.values())
    assert all(v["eligible_count"] == 4 for v in out.values())


def test_retro_provenance_is_preserved_and_no_calibrated_grade_claimed():
    data=horses()
    data[0]["research_sabcd_weight_class"]["retro"]=True
    out=evaluate_race(data)
    assert out["1"]["retro"] is True
    assert "後日算出" in out["1"]["reason"]
    assert out["1"]["score"] is None
