"""Current-evaluation Top5/✓ conservatively adjusts only displayed D→C."""
from copy import deepcopy

import pytest

from core.research_current_eval_c_floor import annotate_view, assess
from core.race_explorer_columns import columns, records


def view_horse(no, *, grade="D", current=5, mark="", runs=None):
    return dict(
        no=str(no), name=f"馬{no}", mode="nar",
        current_evaluation_rank=current, mark=mark,
        unified_sabcd=dict(grade=grade, raw_score=.12, rank=8,
                           reason="固定済み研究評価"),
        race_context=dict(race_date="2026-11-19", race_id="202644111911",
                          venue="大井", surface="ダ", distance=1600),
        profile=dict(runs=list(runs or [])), course=dict(value=86, rank=1),
        distance=dict(value=69, rank=3),
        research_sabcd_weight_class=dict(grade=grade, score=.12),
        ability_rank=7,
    )


def frozen(no, *, current=5, mark="", plus=None, state="上昇"):
    return dict(horse_no=str(no), horse_name=f"馬{no}", current_evaluation_rank=current,
                mark=mark, plus_materials=list(plus if plus is not None else
                  ["コース実績◎", "近走上昇"]), state=state)


def event(horses):
    return dict(race_id="202644111911", race_mode="nar",
                date="2026-11-19", horses=horses,
                race_results_v1=dict(race_status="final", horses=[dict(horse_no="9", finish=2)]))


def test_ooi_nine_display_c_with_saved_form_conflict_and_frozen_model():
    horse = view_horse(9, current=5)
    archived = event([frozen(9, current=5, state="弱含み")])
    before = deepcopy((horse, archived))
    annotated = annotate_view([horse], archived)[0]
    check = annotated["research_current_eval_c_floor"]
    assert check["candidate"] is True
    assert check["candidate_grade"] == "C"
    assert check["independent_family_count"] == 2
    assert check["form_conflict"] is True
    assert annotated["unified_sabcd"]["grade"] == "C"
    assert annotated["unified_sabcd"]["grade_before_current_eval"] == "D"
    assert annotated["unified_sabcd"]["current_eval_c_floor"] is True
    assert annotated["unified_sabcd"]["rank"] == 8
    assert annotated["unified_sabcd"]["raw_score"] == .12
    assert annotated["mark"] == ""
    assert annotated["research_sabcd_weight_class"] == before[0]["research_sabcd_weight_class"]
    assert archived == before[1]


def test_ooi_five_promoted_and_eight_b_excluded():
    horses = [view_horse(5, current=4, mark="✓"),
              view_horse(8, grade="B", current=6, mark="▲")]
    saved = event([frozen(5, current=4, mark="✓"), frozen(8, current=6, mark="▲")])
    annotate_view(horses, saved)
    assert horses[0]["research_current_eval_c_floor"]["candidate"] is True
    assert horses[0]["unified_sabcd"]["grade"] == "C"
    assert horses[0]["unified_sabcd"]["grade_before_current_eval"] == "D"
    assert horses[1]["research_current_eval_c_floor"]["status"] == "not_d"
    assert horses[1]["unified_sabcd"]["grade"] == "B"


def test_check_is_not_formal_top5_checkmark():
    horse = view_horse(7, current=9, mark="✔︎")
    assert assess(horse, frozen(7, current=9, mark="✔︎"))["candidate"] is False
    horse["mark"] = "✓"
    reviewed = assess(horse, frozen(7, current=9))
    assert reviewed["candidate"] is True
    assert reviewed["checked"] is True


def test_two_families_required_regardless_of_rank_or_check():
    horse = view_horse(9)
    out = assess(horse, frozen(9, plus=["コース実績◎", "距離実績◎"]))
    assert out["candidate"] is False
    assert out["independent_family_count"] == 1
    assert assess(horse, frozen(9, plus=["近走上昇"]))["candidate"] is False


def test_exact_course_prior_podium_is_third_evidence_family():
    runs = [
        dict(date="2026-10-20", race_id="202644102011", venue="大井",
             surface="ダ", distance=1600, finish="3着", time_index=50),
        dict(date="2026-10-01", race_id="202644100111", venue="大井",
             surface="ダ", distance=1800, finish="1着", time_index=70),
    ]
    h = view_horse(9, runs=runs)
    out = assess(h, frozen(9, plus=["コース実績◎"]))
    assert out["past_podium_count"] == 1
    assert out["candidate"] is True
    assert out["recent_rising"] is False


def test_neither_current_race_result_nor_future_history_enters_rule():
    prior = [dict(date="2026-11-19", venue="大井", surface="ダ",
                  distance=1600, finish="1着", time_index=100)]
    h = view_horse(9, runs=prior)
    source = event([frozen(9, plus=["コース実績◎"])])
    before = assess(h, source["horses"][0])
    assert before["candidate"] is False
    source["race_results_v1"] = dict(horses=[dict(horse_no="9", finish=1, odds=1000)])
    h["result"] = dict(finish=1, corner4=1)
    h["actual_finish"] = 1
    h["final_odds"] = 1000
    assert assess(h, source["horses"][0]) == before
    assert annotate_view([h], source)[0]["research_current_eval_c_floor"]["candidate"] is False


@pytest.mark.parametrize("key,newvalue", [
    ("race_id", "202644111912"),
    ("date", "2026-11-18"),
    ("race_mode", "jra"),
])
def test_mismatching_archive_abstains(key, newvalue):
    h = view_horse(9)
    source = event([frozen(9)])
    source[key] = newvalue
    assert annotate_view([h], source)[0]["research_current_eval_c_floor"]["candidate"] is False


def test_frozen_rank_conflict_abstains():
    h = view_horse(9, current=5)
    a = assess(h, frozen(9, current=7))
    assert a["status"] == "conflicting_rank"
    assert not a["candidate"]


def test_missing_frozen_archived_material_is_not_derived_from_live_price():
    h = view_horse(9)
    h["odds"] = "10.0"
    h["actual_finish"] = 1
    assert annotate_view([h], None)[0]["research_current_eval_c_floor"]["status"] == "insufficient_source"
    assert assess(h, {"horse_no": "9", "current_evaluation_rank": 5})["status"] == "missing_materials"


def test_shadow_visible_only_as_hidden_audit_field():
    h = view_horse(9)
    annotate_view([h], event([frozen(9)]))
    before = deepcopy(h)
    cols = columns([h])
    by_key = {v["key"]: v for v in cols}
    assert by_key["research_current_eval_c_candidate"]["table_hidden"] is True
    assert by_key["research_current_eval_c_reason"]["table_hidden"] is True
    result = records([h])["9"]
    assert result["research_current_eval_c_candidate"] is True
    assert result["research_current_eval_c_conflict"] is False
    assert result["research_sabcd"] == "C"
    assert h == before


def test_same_shadow_rule_for_jra():
    h = view_horse(9)
    h["mode"] = "jra"
    archived = event([frozen(9)])
    archived["race_mode"] = "jra"
    assert annotate_view([h], archived)[0]["research_current_eval_c_floor"]["candidate"]



def test_repeated_render_is_idempotent():
    horse = view_horse(9, current=5)
    archived = event([frozen(9, state="弱含み")])
    annotate_view([horse], archived)
    first = deepcopy(horse["unified_sabcd"])
    annotate_view([horse], archived)
    assert horse["unified_sabcd"] == first
    assert horse["research_current_eval_c_floor"]["candidate"] is True
    assert horse["unified_sabcd"]["reason"].count("【今回評価C補正】") == 1


def test_other_races_same_rule_when_identifiers_match():
    other = view_horse(3, current=2)
    other["race_context"]["race_id"] = "202650111904"
    record = event([frozen(3, current=2)])
    record["race_id"] = "202650111904"
    assert annotate_view([other], record)[0]["unified_sabcd"]["grade"] == "C"


def test_insufficient_evidence_and_grade_c_no_double_promotion():
    weak = view_horse(2, current=6)
    included = view_horse(4, grade="C", current=2)
    a = event([frozen(2, current=6), frozen(4, current=2)])
    annotate_view([weak, included], a)
    assert weak["unified_sabcd"]["grade"] == "D"
    assert included["unified_sabcd"]["grade"] == "C"
    assert included["unified_sabcd"].get("current_eval_c_floor") is None
