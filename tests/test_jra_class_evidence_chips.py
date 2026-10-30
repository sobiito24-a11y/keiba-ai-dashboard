"""Regression tests for read-only research evidence UI."""
from copy import deepcopy
from bs4 import BeautifulSoup

from core.race_explorer_signal_rules import race_group, signals, badge_html
from core.race_explorer_cards import pickup_html, detail_html
from core.race_explorer_columns import records
from core.race_explorer_ui import lineup_html


def make_horse(race_data2="4回 東京 サラ系２歳 未勝利", mode="jra", ability=1,
               grade="A", corner=4, course=2, last="2着"):
    metrics = dict(ability=dict(value=72.4, rank=ability), course=dict(value=50, rank=course),
                   distance=dict(value=65, rank=2), style="先行", corner=corner,
                   average=55, maximum=71, plus="調教確認", caution="斤量増")
    return dict(no="1", name="検証馬", age="牡2", mode=mode,
                rank=1, candidate_formal_score=70, formal_member=True,
                frame=1, jockey="テスト騎手", mark="—",
                race_context={"race_date":"2026-10-30", "race_name":"架空レース",
                              "race_data2":race_data2},
                final_metrics=metrics,
                explorer_facts=dict(metrics=deepcopy(metrics),
                    training=grade, current_jockey="テスト騎手",
                    rest_label="中3週", weight_delta_label="+1kg", weight_label="56kg",
                    runs=[{"label":"前走", "finish":last, "date":"2026-10-20"}],
                    plus="調教確認", caution="斤量増"))


def tag(horse):
    return signals(horse, records([horse])["1"])


def test_two_maiden_match_and_no_changes_to_saved_horse():
    h = make_horse()
    before = deepcopy(h)
    badges = tag(h)
    assert len(badges) == 1 and badges[0]["level"] == "match"
    assert "能力1位" in badges[0]["label"]
    assert before == h


def test_two_maiden_missing_training_or_corner_does_not_match():
    assert tag(make_horse(grade="未取得")) == ()
    assert tag(make_horse(corner=None)) == ()
    assert tag(make_horse(ability=4)) == ()


def test_two_maiden_secondary_tag_is_reference_and_not_bet_prompt():
    h = make_horse(ability=2)
    result = tag(h)
    assert len(result) == 1 and result[0]["level"] == "reference"
    assert "買い推奨" not in result[0]["label"]


def test_no_two_year_rule_in_2year_1win_open_or_graded():
    for raw in ("サラ系２歳 １勝クラス", "サラ系２歳 オープン",
                "サラ系２歳 オープン G3"):
        assert tag(make_horse(raw)) == ()


def test_no_automatic_badge_for_3year_only_or_grades_or_jump():
    for raw in ("サラ系３歳 未勝利", "サラ系３歳 OP",
                "サラ系３歳以上 オープン G1", "サラ系３歳以上 障害３勝クラス"):
        assert tag(make_horse(raw)) == ()


def test_named_races_use_race_data2_not_misleading_class_label():
    h = make_horse("4回 新潟 サラ系３歳以上 １勝クラス")
    h["race_context"]["race_name"] = "稲光特別"
    h["race_context"]["class_label"] = "A級"
    assert race_group(h) == "mixed1"
    assert [x["level"] for x in tag(h)] == ["support", "reference"]


def test_mixed2_requires_last_actual_race_top3_not_any_older_good_finish():
    h = make_horse("4回 京都 サラ系３歳以上 ２勝クラス", ability=2, last="4着")
    assert tag(h) == ()
    h["explorer_facts"]["runs"].append({"label":"2走前", "date":"2026-09-09", "finish":"1着"})
    assert tag(h) == ()
    h["explorer_facts"]["runs"][0]["finish"] = "3着"
    assert tag(h)[0]["level"] == "match"
    h["explorer_facts"]["runs"][0]["date"] = "未取得"
    assert tag(h) == ()


def test_mixed3_is_reference_and_nar_is_never_affected():
    h = make_horse("サラ系３歳以上 ３勝クラス", last="1着")
    assert tag(h)[0]["level"] == "reference"
    h["mode"] = "nar"
    assert tag(h) == ()


def test_html_color_is_not_probability_and_no_bet_action():
    h = make_horse()
    d = BeautifulSoup(pickup_html([h]), "html.parser")
    assert d.select(".pickup-card .evidence-match")
    assert "条件一致" in d.select_one(".evidence-match")["aria-label"]
    assert "2歳：" not in d.select_one(".evidence-match").get_text()
    assert "76.9%" not in d.get_text()  # explanation is in detail, not a purchase lure
    detail = BeautifulSoup(detail_html(h), "html.parser")
    assert detail.select(".detail-research-evidence .research-evidence-explanations")
    assert "26頭中20頭" in detail.get_text()
    listing = BeautifulSoup(lineup_html([h]), "html.parser")
    assert listing.select("td.col-materials .evidence-match")
    assert listing.select("td.col-materials .evidence-caution")
    assert "自分の✓" in listing.get_text()


def test_escaping_and_no_unmarked_auto_escalation():
    h = make_horse()
    old_rank, old_mark = h["rank"], h["mark"]
    html = badge_html(({"level":"match","label":"<script>alert(1)</script>",
                       "detail":"test\" onclick=\"x"},))
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    pickup_html([h])
    assert (h["rank"],h["mark"]) == (old_rank,old_mark)


def test_pickup_factual_features_are_colored_conservatively():
    h = make_horse()
    h["explorer_facts"]["features"] = [
        "東京芝1600m：3戦0回3着以内（近3走の範囲）",
        "休養明け（93日）",
        "調教A",
    ]
    doc = BeautifulSoup(pickup_html([h]), "html.parser")
    assert "3戦0回" in doc.select_one(".pickup-features .evidence-reference").get_text()
    assert "休養明け" in doc.select_one(".pickup-features .evidence-caution").get_text()
    assert "調教A" in doc.select_one(".pickup-features .evidence-support").get_text()
