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
