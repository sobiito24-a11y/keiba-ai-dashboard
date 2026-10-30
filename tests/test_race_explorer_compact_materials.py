"""No-clipping, no-repetition tests for compact JRA/NAR materials."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.race_explorer_compact_materials import compact_materials_html, pickup_feature_html
from core.race_explorer_signal_rules import compact_label, badge_html
from core.race_explorer_ui import lineup_html
from core.race_explorer_columns import records


def show(html):
    return BeautifulSoup(html, "html.parser")


def test_jra_exemplar_is_short_and_preserves_unique_extra():
    tags = (dict(level="reference", label="2歳：能力Top3×調教AB×4角前方",
                 detail="対象67頭中43頭3着以内"),)
    source = "今回調教B / 近走同回り好走"
    parsed = show(compact_materials_html(tags, source, "", training="B"))
    visible = parsed.get_text(" ")
    assert "能力Top3×調教AB×4角前方" in visible
    assert "近走同回り好走" in visible
    for redundant in ("今回調教B", "保存材料", "参考：", "2歳：", "ほか"):
        assert redundant not in visible
    # The study's limitations remain in hover / full detail and accessible text.
    assert "対象67頭中43頭" in parsed.select_one(".evidence-reference")["title"]
    assert "事後探索" not in visible
    assert source == "今回調教B / 近走同回り好走"


def test_research_mark_is_still_accessibly_classified_and_detail_unchanged():
    tags = (dict(level="match", label="2歳：能力1位×調教AB×4角前方",
                 detail="過去26頭中20頭、保証なし"),)
    compact = show(badge_html(tags, compact=True))
    full = show(badge_html(tags))
    assert compact.get_text(" ") == "能力1位×調教AB×4角前方"
    assert "条件一致" in compact.select_one(".evidence-match")["aria-label"]
    assert "＋ 条件一致：2歳：" in full.get_text(" ")
    assert "過去26頭中20頭" in compact.select_one(".evidence-match")["title"]


def test_no_false_merge_when_material_has_additional_content():
    tags = (dict(level="reference", label="2歳：能力Top3×調教AB×4角前方", detail="sample"),)
    result = show(compact_materials_html(
        tags, "今回調教B / Hペース想定×4角6番手 / 近走同回り好走", "", training="B"))
    assert "Hペース想定×4角6番手" in result.get_text()
    assert "近走同回り好走" in result.get_text()
    assert "今回調教B" not in result.get_text()
    assert "ほか" not in result.get_text()


def test_only_duplicated_grade_is_removed_not_grade_change():
    a = show(compact_materials_html((), "今回調教B / 調教C→B昇格 / 前走比較改善", "", training="B"))
    assert "調教C→B昇格" in a.get_text(" ")
    assert "前走比較改善" in a.get_text(" ")
    assert "今回調教B" not in a.get_text()
    b = show(compact_materials_html((), "今回調教A", "", training="B"))
    assert "調教A" in b.get_text(" ")  # conflicting evidence must not vanish


def test_nar_separate_positive_and_caution_with_more_count():
    raw_plus = "近走同回り好走 / 4角先団 / 近走同回り好走 / 斤量減"
    raw_caution = "△ 休養明け / △ 斤量増+2kg"
    output = show(compact_materials_html((), raw_plus, raw_caution))
    text = output.get_text(" ")
    assert "保存材料" not in text
    assert text.count("近走同回り好走") == 1
    assert "4角先団" in text
    assert "注意：休養明け" in text
    assert "ほか2件" in text
    hidden = output.select_one(".evidence-more")["title"]
    assert "斤量減" in hidden and "斤量増+2kg" in hidden
    assert "近走同回り好走" in raw_plus  # source never mutated


def test_nar_course_counts_are_distinct_and_cautions_not_hidden_by_positive():
    raw_plus = "東京ダ1400m：3戦2回3着以内（近3走の範囲） / 東京ダ1400m：3戦2回3着以内（近3走の範囲）"
    markup = show(compact_materials_html((), raw_plus, "▲ 斤量+2kg"))
    txt = markup.get_text(" ")
    assert txt.count("3戦2回3着内") == 1
    assert "近3走の範囲" not in txt
    assert "注意：" in txt and "斤量+2kg" in txt


def test_pickup_removes_training_already_in_current_state_only():
    features = ["東京ダ1600m：2戦1回3着以内", "距離変更", "調教A"]
    result = show(pickup_feature_html(features, grade="A"))
    assert len(result.select(".evidence-chip")) == 2
    assert "調教A" not in result.get_text()
    with_no_training = show(pickup_feature_html(features, grade=None))
    assert "調教A" in with_no_training.get_text()


def test_display_shortening_keeps_full_original_in_title_escaped():
    long_fact = "特別な長い根拠" * 7 + '<script>alert("x")</script>'
    output = compact_materials_html((), long_fact, "")
    parsed = show(output)
    assert len(parsed.get_text(" ")) <= 24
    assert "<script>" not in str(parsed)
    assert long_fact in parsed.select_one(".evidence-chip")["title"]


def test_no_marks_mutated_and_raw_list_filter_value_retained():
    horse = dict(
        no="1", name="研究対象馬", age="牝2", mode="jra",
        rank=1, mark="—", formal_member=True, candidate_formal_score=75.0,
        race_context={"race_name":"2歳未勝利", "race_data2":"2歳 未勝利"},
        final_metrics=dict(ability=dict(value=72.1,rank=2),
                           course=dict(value=50,rank=4),distance=dict(value=60,rank=1),
                           corner=4,style="差し",average=44, maximum=66),
        explorer_facts=dict(
            metrics=dict(ability=dict(value=72.1,rank=2),corner=4,course=dict(value=50,rank=4),distance=dict(value=60,rank=1)),
            training="B", current_jockey="テスト騎手", plus="今回調教B / 近走同回り好走",
            caution="△ 休養明け", runs=[], current_weight=55))
    before=deepcopy(horse)
    doc=show(lineup_html([horse]))
    txt=doc.select_one("td.col-materials").get_text(" ")
    assert "能力Top3×調教AB×4角前方" in txt
    assert "近走同回り好走" in txt
    assert "今回調教B" not in txt
    assert "注意：休養明け" in txt
    full=records([horse])["1"]
    assert "今回調教B" in full["plus"]  # sorting/filter source stays as before
    assert horse == before
