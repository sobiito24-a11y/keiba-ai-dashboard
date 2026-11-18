"""Frozen same-age suitability regression and non-leakage checks."""
from copy import deepcopy

import pytest

from core.ai_evaluation_memo import evaluation_memo
from core.research_age_suitability import assign_to_view, evaluate_race


def previous(day, finish, index=25, *, race_id=None, venue="園田",
             surface="ダ", distance=1400):
    return dict(date=day, race_id=race_id or "202650"+day[5:7]+day[8:10]+"05",
                venue=venue, surface=surface, distance=distance,
                finish=str(finish)+"着", time_index=index)


def horse(no, age, course, distance, *, original="D", runs=None):
    return dict(
        no=str(no), name=f"保存馬{no}", mode="nar",
        age=("牝" if no == 6 else "牡")+str(age),
        course=dict(value=course, rank=None),
        distance=dict(value=distance, rank=None),
        profile=dict(state="注意" if no == 6 else "横ばい",
                     class_shift="判定不可",
                     runs=list(runs if runs is not None else [])),
        race_context=dict(race_date="2026-11-18", venue="園田",
                          surface="ダ", distance=1400,
                          race_data2="サラ系３歳以上 C2"),
        unified_sabcd=dict(grade=original, rank=8, raw_score=.1078,
                           strength=.22, original_grade="D"),
        research_sabcd_weight_class=dict(grade="D", score=.1078),
        mark="", rank=None, odds="8.9",
    )


def field():
    view = [
        horse(1, 3, 23, 52), horse(6, 3, 29, 29,
              runs=[previous("2026-10-30", 1, 20),
                    previous("2026-10-09", 6, 27),
                    previous("2026-09-16", 3, 27)]),
        horse(8, 3, 24, 24),
        horse(7, 3, 19, 19),
        horse(10, 4, 38, 69, original="A"),
        horse(5, 4, 50, 46, original="A"),
        horse(9, 4, 36, 36),
        horse(2, 6, 55, 55),
        horse(3, 6, 46, 57),
    ]
    return view


def test_sonoda_6_promotes_only_display_grade_with_saved_prestart_evidence():
    view = field()
    before = deepcopy(view)
    result = evaluate_race(view)
    target = result["6"]
    assert target["qualified"] is True
    assert (target["age"], target["cohort_n"]) == (3, 4)
    assert (target["course_age_rank"], target["distance_age_rank"]) == (1, 2)
    assert (target["exact_starts"], target["exact_podiums"]) == (3, 2)
    assert view == before
    adjusted = assign_to_view(view)
    six = next(h for h in adjusted if h["no"] == "6")
    assert six["unified_sabcd"]["grade"] == "C"
    assert six["unified_sabcd"]["grade_before_suitability"] == "D"
    assert six["unified_sabcd"]["age_cohort_c_floor"] is True
    assert six["unified_sabcd"]["rank"] == 8
    assert six["unified_sabcd"]["raw_score"] == .1078
    assert six["research_sabcd_weight_class"]["grade"] == "D"
    assert six["mark"] == ""
    assert evaluation_memo(six) == (
        "3歳内 コース1位・距離2位\n"
        "同場同距離3戦2回3着内／近走下降注意"
    )


def test_does_not_upgrade_a_or_b_or_c_or_unrelated_older_cohort():
    view = field()
    assign_to_view(view)
    assert next(h for h in view if h["no"] == "10")["unified_sabcd"]["grade"] == "A"
    assert next(h for h in view if h["no"] == "2")["unified_sabcd"]["grade"] == "D"
    assert next(h for h in view if h["no"] == "7")["unified_sabcd"]["grade"] == "D"
    assert next(h for h in view if h["no"] == "6")["unified_sabcd"]["grade"] == "C"
    assign_to_view(view)
    six = next(h for h in view if h["no"] == "6")
    assert six["unified_sabcd"]["grade"] == "C"
    assert six["unified_sabcd"]["reason"].count("【同年齢適性補正】") == 1


def test_original_d_is_not_promoted_without_two_unique_exact_podiums():
    view = field()
    six = next(h for h in view if h["no"] == "6")
    six["profile"]["runs"][2]["venue"] = "姫路"
    assert evaluate_race(view)["6"]["exact_podiums"] == 1
    assign_to_view(view)
    assert six["unified_sabcd"]["grade"] == "D"


def test_prior_race_id_duplicates_and_future_finish_are_never_counted():
    view = field()
    six = next(h for h in view if h["no"] == "6")
    single = previous("2026-10-30", 1, race_id="202650103005")
    six["profile"]["runs"] = [
        single, dict(single),
        previous("2026-11-18", 1, race_id="202650111801")]
    six["actual_finish"], six["final_odds"] = 1, 12.8
    assert evaluate_race(view)["6"]["exact_podiums"] == 1
    assert not evaluate_race(view)["6"]["qualified"]
    assign_to_view(view)
    assert six["unified_sabcd"]["grade"] == "D"


def test_missing_index_in_same_age_peer_cancels_promotion():
    view = field()
    next(h for h in view if h["no"] == "8")["course"]["value"] = None
    assert not evaluate_race(view)["6"]["qualified"]


def test_one_or_two_age_peers_are_insufficient_to_claim_top2():
    view = [h for h in field() if h["no"] not in ("7", "8")]
    assert not evaluate_race(view)["6"]["qualified"]


def test_three_years_only_is_not_mixed_race():
    view = [h for h in field() if h["age"].endswith("3")]
    assert not evaluate_race(view)["6"]["qualified"]


def test_no_explicit_age_open_header_no_promotion():
    view = field()
    for h in view:
        h["race_context"]["race_data2"] = "サラ系３歳限定 C2"
    assert not evaluate_race(view)["6"]["qualified"]


def test_rank3_is_not_promoted_even_with_two_podiums():
    view = field()
    six = next(h for h in view if h["no"] == "6")
    six["course"]["value"] = 22
    assert not evaluate_race(view)["6"]["qualified"]


def test_exact_distance_not_plus_minus_200():
    view = field()
    six = next(h for h in view if h["no"] == "6")
    six["profile"]["runs"][0]["distance"] = 1200
    assert evaluate_race(view)["6"]["exact_podiums"] == 1


def test_independent_of_real_result_fields():
    view = field()
    initial = evaluate_race(view)["6"]
    for h in view:
        h["actual_finish"] = 1
        h["result"] = {"finish": 1, "corner4": 2}
        h["final_win_odds"] = 10.0
    assert evaluate_race(view)["6"] == initial


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_same_prestart_rule_for_both_modes(mode):
    view = field()
    for h in view:
        h["mode"] = mode
    assert evaluate_race(view)["6"]["qualified"] is True
