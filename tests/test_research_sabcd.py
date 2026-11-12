from copy import deepcopy

import pytest
from core.research_sabcd import (
    VERSION, MODEL, CUTOFFS, assign_to_view, evaluate_race,
    feature_vector, grade_from_probability, model_probability,
)


def horse(rank, *, mode="nar", date="2026-11-14", corner=None, no=None):
    return {
        "no": str(no if no is not None else rank),
        "name": "テスト馬" + str(rank),
        "mode": mode,
        "mark": "◎" if rank == 1 else "—",
        "score": 900-rank,
        "ability": 80-rank,
        "ability_rank": rank,
        "corner": corner if corner is not None else rank,
        "start_rank": rank,
        "training": "B" if mode=="jra" else "",
        "research_inputs": {"jockey_n": 320, "jockey_rate": 40},
        "race_context": {
            "race_date": date, "venue": "高知", "surface": "ダ", "distance": 1400
        },
        "profile": {"runs": [
            dict(label="前走", date="2026-10-30", venue="高知", surface="ダ",
                 distance="1400", finish="2着"),
            dict(label="2走前", date="2026-10-10", venue="高知", surface="ダ",
                 distance="1400", finish="4着"),
        ]},
    }


@pytest.mark.parametrize("p,expected",[
    (.71,"S"),(.7,"S"),(.6999,"A"),(.5,"A"),(.4999,"B"),
    (.3,"B"),(.2999,"C"),(.15,"C"),(.1499,"D"),
])
def test_locked_grade_cutoffs(p,expected):
    assert grade_from_probability(p)==expected


def test_frozen_model_matches_offline_sklearn_training_predictions():
    # Directly derived from the stored coefficients. Prevent unannounced
    # feature order changes or altered standardization at runtime.
    ja = [0,8,0,0,.71,5/7,0,0]
    na = [1/7,8,0,0,.4,0,3,1]
    assert model_probability("jra",ja)==pytest.approx(.7757365916162509,abs=1e-9)
    assert model_probability("nar",na)==pytest.approx(.8157114836341972,abs=1e-9)


@pytest.mark.parametrize("mode",["jra","nar"])
def test_one_s_two_a_three_b_cap_and_no_scores_marks_modified(mode,monkeypatch):
    import core.research_sabcd as mod
    view=[horse(i,mode=mode) for i in range(1,11)]
    before=deepcopy(view)
    # Deliberately create >1 raw-S candidate and enough A/B overflow.
    monkeypatch.setattr(mod,"model_probability",lambda _mode, vec: .90 - .03*(vec[0]*9))
    outcomes=evaluate_race(view)
    assert outcomes["1"]["grade"]=="S"
    assert outcomes["2"]["raw_grade"]=="S" and outcomes["2"]["grade"]=="A"
    assert outcomes["3"]["grade"]=="A"
    assert outcomes["4"]["grade"]=="B"
    assert outcomes["5"]["grade"]=="B"
    assert outcomes["6"]["grade"]=="B"
    counts={g:sum(r["grade"]==g for r in outcomes.values()) for g in "SABCD"}
    assert counts["S"]<=1 and counts["A"]<=2 and counts["B"]<=3
    assert sum(counts.values())==10
    assert view==before
    projected=assign_to_view(view)
    assert projected is view
    assert all(h["score"]==before[i]["score"] and h["mark"]==before[i]["mark"] for i,h in enumerate(view))
    assert all(h["research_sabcd"]["version"]==VERSION for h in view)


def test_jra_nar_same_features_have_different_model():
    vec=(.3,12,.2,.2,.3,.3,1,0)
    assert model_probability("jra",vec)!=model_probability("nar",vec)


def test_midfront_previous_podium_jockey_fit_and_position_question_tags():
    j=horse(5,mode="jra",corner=2)
    x,tags=feature_vector(j,12)
    assert "中位×4角前" in tags and "前走好走" in tags
    n=horse(5,mode="nar",corner=2)
    _,tags=feature_vector(n,12)
    assert "中位×4角前" in tags and "騎手適性" in tags
    j=horse(1,mode="jra",corner=8)
    _,tags=feature_vector(j,12)
    assert "位置?" in tags


def test_missing_core_rank_never_converts_to_d_or_assumed_s():
    view=[horse(1),horse(2)]
    view[1]["corner"]=None
    outcomes=evaluate_race(view)
    assert outcomes["2"]["grade"] is None
    assert "判定不可" in outcomes["2"]["reason"]


def test_old_archive_is_marked_as_posthoc_and_future_is_not():
    old=evaluate_race([horse(1,date="2026-11-08")])
    assert old["1"]["retro"] is True
    assert "後付け" in old["1"]["reason"]
    future=evaluate_race([horse(1,date="2026-11-14")])
    assert future["1"]["retro"] is False
    assert "後付け" not in future["1"]["reason"]


def test_course_history_requires_explicit_same_venue_ground_distance():
    h=horse(2)
    x,_=feature_vector(h,10)
    assert x[7]==1.
    h["profile"]["runs"][0]["venue"]="園田"
    h["profile"]["runs"][1]["venue"]="川崎"
    x,_=feature_vector(h,10)
    assert x[7]==0.
    h["race_context"]["venue"]=None
    x,_=feature_vector(h,10)
    assert x[7]==0.
