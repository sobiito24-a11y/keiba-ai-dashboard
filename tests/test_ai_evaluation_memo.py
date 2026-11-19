"""Pre-race AI evaluation memo is factual, two-line, and display-only."""
from copy import deepcopy
from bs4 import BeautifulSoup

from core.ai_evaluation_memo import evaluation_memo
from core.race_explorer_columns import columns, records
from core.race_explorer_ui import _cell


def ooi_eight():
    return dict(
        no="8", name="セイエイ", mode="nar", ability_rank=9,
        course=dict(value=91, rank=1),
        distance=dict(value=91, rank=2),
        unified_sabcd=dict(grade="C", grade_before_suitability="D"),
        training=None, corner=5, mark="",
        caution="近走下降",
        profile=dict(state="注意", runs=[
            dict(date="2026-10-27", venue="大井", surface="ダ", distance="1600m",
                 finish="8着", time_index=42),
            dict(date="2026-04-16", venue="大井", surface="ダ", distance="1800m",
                 finish="9着", time_index=48),
            dict(date="2026-03-12", venue="大井", surface="ダ", distance="2000m",
                 finish="1着", time_index=57),
        ]),
        race_context=dict(race_date="2026-11-16", venue="大井", surface="ダ", distance=1800),
    )


def test_ooi_eight_memo_is_two_line_factual_and_not_a_recommendation():
    horse = ooi_eight()
    prior = deepcopy(horse)
    result = evaluation_memo(horse)
    assert result == "コース指数1位・距離指数2位\n同場近似距離1勝／近走下降注意"
    assert result.count("\n") == 1
    assert all(term not in result for term in ("買い", "推奨", "軸", "勝つ", "的中"))
    assert horse == prior


def test_last_visible_column_and_record_use_same_evidence_for_both_modes():
    for mode in ("jra", "nar"):
        horse = ooi_eight()
        horse["mode"] = mode
        specs = columns([horse])
        visible = [col["key"] for col in specs if not col.get("table_hidden")]
        assert visible[-2:] == ["class_attention", "ai_memo"]
        assert next(col["label"] for col in specs if col["key"] == "ai_memo") == "AI評価メモ"
        before = deepcopy(horse)
        data = records([horse])["8"]
        assert data["ai_memo"] == evaluation_memo(horse)
        assert horse == before


def test_missing_evidence_stays_neutral_without_inventing_a_reason():
    horse = dict(mode="nar", course=dict(value=None, rank=1), distance=dict(value=None, rank=1))
    assert evaluation_memo(horse) == "特記材料なし"


def test_future_finish_result_and_final_odds_never_enter_memo():
    horse = ooi_eight()
    original = evaluation_memo(horse)
    horse["profile"]["runs"].append(dict(
        date="2026-11-16", venue="大井", surface="ダ",
        distance=1800, finish="1着", time_index=100))
    horse.update(actual_finish=1, final_odds=99, result="1着")
    assert evaluation_memo(horse) == original


def test_unsuitable_prior_win_is_not_mislabeled_same_venue():
    horse = ooi_eight()
    horse["profile"]["runs"] = [
        dict(date="2026-10-27", venue="船橋", surface="ダ",
             distance=1200, finish="1着", time_index=70)]
    result = evaluation_memo(horse)
    assert result.startswith("コース指数1位・距離指数2位")
    assert "近3走1勝" in result
    assert "同場近似距離" not in result


def test_jra_training_and_corner_are_fact_fallbacks():
    assert evaluation_memo(dict(mode="jra", training="A")) == "調教A"
    assert evaluation_memo(dict(mode="nar", corner=2)) == "4角2番手想定"


def test_horse_list_render_escapes_text_and_keeps_two_lines():
    horse = ooi_eight()
    memo = evaluation_memo(horse)
    html = _cell(horse, {"ai_memo": memo}, "ai_memo")
    root = BeautifulSoup(html, "html.parser")
    assert root.select_one(".ai-evaluation-memo strong").text == "コース指数1位・距離指数2位"
    assert root.select_one(".ai-evaluation-memo small").text == "同場近似距離1勝／近走下降注意"
    unsafe = _cell(horse, {"ai_memo": "<script>alert(1)</script>\n危険"}, "ai_memo")
    assert "<script>" not in unsafe
    assert not BeautifulSoup(unsafe, "html.parser").select("script")



def sonoda_seven():
    """Saved pre-start facts behind 2026/11/19 Sonoda 4R number 7."""
    from core.research_age_suitability import assign_to_view

    def item(no, age, course, distance, runs=None):
        return dict(
            no=str(no), name="ベラジオカムイ" if no == 7 else "同年齢比較馬",
            mode="nar", age=f"牡{age}", course=dict(value=course, rank=1),
            distance=dict(value=distance, rank=3),
            profile=dict(class_shift="判定不可", state="横ばい",
                         runs=list(runs or [])),
            race_context=dict(
                race_date="2026-11-19", venue="園田", surface="ダ",
                distance=1400,
                raw_class_text="サラ系3歳以上 C3二"),
            unified_sabcd=dict(grade="D", rank=8, raw_score=.1455),
            research_sabcd_weight_class=dict(grade="D", score=.1455),
            mark="", rank=None,
        )

    recent = [
        dict(date="2026-10-28", venue="園田", surface="ダ", distance=1400,
             finish="10着", class_raw="C2一", time_index=-33),
        dict(date="2026-10-09", venue="園田", surface="ダ", distance=1400,
             finish="8着", class_raw="C2二", time_index=19),
        dict(date="2026-07-01", venue="園田", surface="ダ", distance=1230,
             finish="4着", class_raw="C2二", time_index=18),
    ]
    view = [
        item(7, 3, 58, 58, recent),
        item(4, 3, 22, 51),
        item(2, 3, 44, 46),
        item(1, 4, 58, 58),
    ]
    assign_to_view(view)
    return view


def test_sonoda_seven_memo_shows_good_and_bad_without_changing_grade():
    view = sonoda_seven()
    horse = view[0]
    original = deepcopy(view)
    flag = horse["research_age_suitability"]
    assert (flag["course_age_rank"], flag["distance_age_rank"]) == (1, 1)
    assert flag["qualified"] is False
    assert evaluation_memo(horse) == (
        "3歳内 コース1位・距離1位\n"
        "C2→C3降級／近2走10着・8着"
    )
    assert horse["unified_sabcd"] == {"grade": "D", "rank": 8, "raw_score": .1455}
    assert horse["mark"] == ""
    assert view == original


def test_memo_does_not_invent_drop_for_unknown_or_conflicting_classes():
    horse = sonoda_seven()[0]
    horse["profile"]["runs"][0]["class_raw"] = "前走クラス不明"
    horse["profile"]["runs"][1]["class_raw"] = "前走クラス不明"
    assert "降級" not in evaluation_memo(horse)
    assert "近2走10着・8着" in evaluation_memo(horse)
    horse["profile"]["runs"][0]["class_raw"] = "C2/C3混合"
    assert "降級" not in evaluation_memo(horse)


def test_memo_does_not_invent_drop_across_venues_or_future_results():
    horse = sonoda_seven()[0]
    horse["profile"]["runs"][0]["venue"] = "姫路"
    assert "降級" not in evaluation_memo(horse)
    horse["profile"]["runs"][0]["date"] = "2026-11-19"
    horse["profile"]["runs"][1]["class_raw"] = "級未取得"
    assert "降級" not in evaluation_memo(horse)
    horse["actual_finish"] = 1
    horse["final_win_odds"] = 200
    assert "降級" not in evaluation_memo(horse)


def test_single_good_age_rank_without_class_or_bad_finishes_does_not_override_memo():
    horse = sonoda_seven()[0]
    horse["profile"]["runs"] = [
        dict(date="2026-10-28", venue="園田", surface="ダ",
             distance=1400, finish="1着", class_raw="C3"),
        dict(date="2026-10-09", venue="園田", surface="ダ",
             distance=1400, finish="2着", class_raw="C3")]
    assert evaluation_memo(horse) == "コース指数1位・距離指数3位\n同場近似距離1勝"


def test_age_top2_memo_for_nar_and_jra_requires_only_prestart_evidence():
    view = sonoda_seven()
    horse = view[0]
    horse["mode"] = "jra"
    assert evaluation_memo(horse) == (
        "3歳内 コース1位・距離1位\n近2走10着・8着"
    )
