"""Regression coverage for JRA second-look marks: research-only, no score mutation."""
from copy import deepcopy

from core.jra_rank_second_look import annotate, render


def test_flag_conflicting_formal_top_one_and_hidden_current_top_five():
    view = [
        dict(mode="jra", no="8", name="強いとされる馬", rank="1位",
             current_evaluation_rank=8, ability_rank="9位",
             rest="中12週", training="C 追切物足りず"),
        dict(mode="jra", no="12", name="見落とし候補", rank="7位",
             current_evaluation_rank=3, ability_rank="4位",
             rest="中2週", training="B"),
        dict(mode="jra", no="2", name="その他", rank="2位",
             current_evaluation_rank=2, ability_rank="2位",
             rest="中2週", training="A"),
    ]
    before=deepcopy(view)
    actual=annotate(view)
    assert actual[0]["rank"] == before[0]["rank"]
    assert actual[0]["jra_rank_second_look"]["role"] == "軸注意"
    assert "70日以上休養＋調教C/D" in actual[0]["jra_rank_second_look"]["reasons"]
    assert actual[1]["jra_rank_second_look"]["role"] == "再確認"
    assert actual[2]["jra_rank_second_look"]["role"] is None
    note=render(actual)
    assert "JRAランク照合" in note
    assert "正式1位でも今回評価8位" in note
    assert "今回評価3位／正式7位" in note
    assert "購入推奨ではありません" in note


def test_nar_empty_or_missing_rank_does_not_invent_facts():
    nar=[dict(mode="nar", no="1", name="nar馬", rank=1,
              current_evaluation_rank=5, ability_rank=4)]
    before=deepcopy(nar)
    assert annotate(nar) == before
    assert render(nar) == ""
    assert annotate([]) == []
    jra=[dict(mode="jra", no="4", name="データ不足", rank="—",
              current_evaluation_rank=None, ability_rank=None)]
    assert render(annotate(jra)) == ""


def test_exact_saved_70days_used_even_if_display_is_approximate():
    view=[dict(mode="jra", no="3", name="休養馬", rank=2,
               current_evaluation_rank=2, ability_rank=1,
               rest="約2か月", rest_days=72, training="D")]
    annotate(view)
    assert view[0]["jra_rank_second_look"]["role"] == "軸注意"
    assert "70日以上休養＋調教C/D" in view[0]["jra_rank_second_look"]["reasons"]
    view[0]["rest_days"] = 60
    annotate(view)
    assert view[0]["jra_rank_second_look"]["role"] is None
