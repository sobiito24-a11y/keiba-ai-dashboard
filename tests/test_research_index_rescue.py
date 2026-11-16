"""Pre-race, read-only index rescue; no grade or betting changes."""
from copy import deepcopy

from core.research_index_rescue import assess, assign_to_view


def sample(no="8", grade="D", mode="nar", runs=None):
    if runs is None:
        runs = [
            dict(date="2026-10-27", venue="大井", surface="ダ", distance="1600m", finish="8着", time_index=42),
            dict(date="2026-04-16", venue="大井", surface="ダ", distance="1800m", finish="9着", time_index=48),
            dict(date="2026-03-12", venue="大井", surface="ダ", distance="2000m", finish="1着", time_index=57),
        ]
    return dict(
        no=no, mode=mode, course=dict(rank=1), distance=dict(rank=2),
        unified_sabcd=dict(grade=grade, rank=7, raw_score=.077), mark="",
        profile=dict(runs=runs, state="注意", class_shift="判定不可"),
        race_context=dict(race_date="2026-11-16", venue="大井", surface="ダ", distance=1800),
        caution="近走下降",
    )


def test_ooi_eight_saved_prestart_evidence_is_found():
    horse = sample()
    prior = deepcopy(horse)
    result = assess(horse)
    assert result["label"] == "適性再点検"
    assert result["historical_success_starts"] == 1
    assert result["ranked_index_signal"] == 1
    assert result["class_status"] == "比較不可"
    assert result["recent_decline"] is True
    assert horse == prior


def test_same_past_start_is_not_counted_twice():
    horse = sample()
    horse["profile"]["runs"].append(deepcopy(horse["profile"]["runs"][-1]))
    assert assess(horse)["historical_success_starts"] == 1


def test_current_and_future_results_are_excluded():
    horse = sample(runs=[
        dict(date="2026-11-16", venue="大井", surface="ダ", distance=1800, finish="1着"),
        dict(date="2026-11-17", venue="大井", surface="ダ", distance=1800, finish="1着"),
    ])
    horse["actual_finish"] = 1
    assert assess(horse)["label"] is None


def test_rank_and_marks_are_never_mutated():
    horse = sample()
    result = assign_to_view([horse])[0]
    assert result["research_index_rescue"]["label"] == "適性再点検"
    assert result["unified_sabcd"] == {"grade": "D", "rank": 7, "raw_score": .077}
    assert result["mark"] == ""


def test_top_grade_and_no_index_signal_are_excluded():
    assert assess(sample(grade="A"))["label"] is None
    horse = sample()
    horse["course"]["rank"] = 5
    horse["distance"]["rank"] = 8
    assert assess(horse)["label"] is None


def test_research_rule_applies_to_jra_too():
    assert assess(sample(mode="jra"))["label"] == "適性再点検"


def test_recent_high_requires_sufficient_field():
    h = sample(runs=[dict(date="2026-10-27", venue="大井", surface="ダ",
                          distance=1600, finish="8着", time_index=99)])
    assert assign_to_view([h])[0]["research_index_rescue"]["label"] is None


def test_high_index_alternative_without_win():
    horses = [
        sample(no=str(i), runs=[dict(date="2026-10-27", venue="大井",
               surface="ダ", distance=1600, finish="8着", time_index=i)])
        for i in range(1, 7)
    ]
    assign_to_view(horses)
    assert horses[-1]["research_index_rescue"]["label"] == "適性再点検"
    assert horses[0]["research_index_rescue"]["label"] is None


def test_postrace_data_does_not_change_result():
    horse = sample()
    original = assess(horse)
    horse.update(actual_finish=1, result="win", final_odds=40)
    assert assess(horse) == original
