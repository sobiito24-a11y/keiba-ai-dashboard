"""Integrated shadow/formal research grade safety and consistency tests."""
from collections import Counter
from copy import deepcopy

import pytest

from core.unified_sabcd import (
    VERSION, SHADOW_WEIGHT, FORMAL_WEIGHT, _formal_top5_rank,
    evaluate_race, assign_to_view,
)


def horse(no, score, grade="B", rank=None, *, mode="jra", retro=False):
    return dict(
        no=str(no), name=f"保存馬{no}", mode=mode, rank=rank,
        score=100-no, mark="◎" if no == 1 else "―",
        ability_rank=no, odds="10.0", corner=no,
        research_sabcd_weight_class=dict(
            grade=grade, score=score, retro=retro, version="frozen-shadow"
        ),
    )


def test_weights_are_bounded_and_not_derived_from_race_outcome():
    assert SHADOW_WEIGHT == pytest.approx(.9)
    assert FORMAL_WEIGHT == pytest.approx(.1)
    assert SHADOW_WEIGHT + FORMAL_WEIGHT == pytest.approx(1.0)
    assert VERSION.startswith("unified-")


def test_integrated_grades_reorder_without_forcing_s_or_extra_a():
    view = [
        horse(1, .35, "B", rank=8),
        horse(2, .34, "B", rank=7),
        horse(3, .33, "B", rank=6),
        horse(4, .32, "B", rank=5),
        horse(5, .34, "B", rank=1),
        horse(6, .20, "C", rank=2),
    ]
    saved = deepcopy(view)
    result = evaluate_race(view)
    assert view == saved
    assert Counter(x["grade"] for x in result.values()) == Counter(
        x["research_sabcd_weight_class"]["grade"] for x in view)
    assert "S" not in [x["grade"] for x in result.values()]
    assert result["5"]["rank"] < result["2"]["rank"]  # equal research score; formal breaks tie
    assert result["5"]["formal_top5_rank"] == 1
    assert result["1"]["formal_top5_rank"] is None
    assert all(x["status"] == "integrated" for x in result.values())
    assert all("確率ではなく" in x["reason"] for x in result.values())


def test_no_formal_top5_keeps_old_grade_and_model_score_order():
    view = [horse(1, .52, "A"), horse(2, .23, "C"), horse(3, .11, "D")]
    result = evaluate_race(view)
    assert [result[str(i)]["grade"] for i in (1,2,3)] == ["A","C","D"]
    assert [result[str(i)]["rank"] for i in (1,2,3)] == [1,2,3]
    assert all(r["status"] == "shadow_only" for r in result.values())


@pytest.mark.parametrize("raw", [None, 0, 6, "8", "―", True, float("nan")])
def test_unverified_formal_rank_does_not_boost(raw):
    assert _formal_top5_rank(horse(1, .4, rank=raw)) is None


def test_reference_nar_rank_without_formal_score_is_not_top5_evidence():
    h=horse(1, .4, rank=1, mode="nar")
    h["candidate_formal_score"] = None
    assert _formal_top5_rank(h) is None
    h["candidate_formal_score"] = 25.
    assert _formal_top5_rank(h) == 1


def test_missing_research_cannot_be_replaced_by_formal_grade():
    view=[horse(1, None, None, rank=1), horse(2, .35, "B", rank=2)]
    out=evaluate_race(view)
    assert out["1"]["grade"] is None
    assert out["1"]["rank"] is None
    assert out["1"]["status"] == "missing_research_score"
    assert out["2"]["grade"] == "B"


def test_unified_ignores_outcome_odds_and_preserves_formal_predictions():
    view=[horse(i,score,grade,rank=i) for i,score,grade in (
        (1,.65,"A"),(2,.48,"B"),(3,.31,"B"),(4,.14,"D"),
        (5,.11,"D"),(6,.09,"D")
    )]
    initial=deepcopy(view)
    assign_to_view(view)
    first=deepcopy([h["unified_sabcd"] for h in view])
    for h in view:
        h["postrace_finish"] = 1
        h["odds"] = "1000.0"
        h["final_win_odds"] = 1.2
        h["corner4_actual"] = 1
    assign_to_view(view)
    assert [h["unified_sabcd"] for h in view] == first
    for h,saved in zip(view,initial):
        assert all(h[k] == saved[k] for k in saved if k != "odds")
    assert [x["rank"] for x in first] == list(range(1,7))


def test_posthoc_provenance_is_retained_and_not_presented_as_frozen():
    view=[horse(1,.65,"A",1,retro=True),horse(2,.29,"C",2,retro=True)]
    out=evaluate_race(view)
    assert all(x["retro"] for x in out.values())


def test_only_visible_one_grade_source():
    from core.race_explorer_columns import columns, records
    view=[horse(1,.6,"A",1),horse(2,.31,"B",2),horse(3,.12,"D",3)]
    # Minimal source fields for comparison rows
    for h in view:
        h["explorer_facts"]={"metrics":{}}
    assign_to_view(view)
    visible=[x["key"] for x in columns(view) if not x.get("table_hidden")]
    assert "research_sabcd" in visible
    assert "rank" not in visible
    assert "research_sabcd_weight_class" not in visible
    assert "unified_sabcd_rank" not in visible
    assert next(x["label"] for x in columns(view) if x["key"]=="research_sabcd")=="統合SABCD"
    rows=records(view)
    assert rows["1"]["research_sabcd"] == view[0]["unified_sabcd"]["grade"]
