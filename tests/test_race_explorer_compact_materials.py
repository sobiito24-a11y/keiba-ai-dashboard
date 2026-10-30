"""Compact evidence badges must work for BOTH central and local racing."""
from copy import deepcopy
from pathlib import Path

from bs4 import BeautifulSoup

from core.race_explorer_compact_materials import clean_short, chips, feature_chips
from core.race_explorer_signal_rules import badge_html
from core.race_explorer_cards import pickup_html, detail_html
from core.race_explorer_ui import lineup_html


def horse(mode="jra", ability_rank=2, training="B"):
    metrics = dict(ability=dict(value=89, rank=ability_rank),
                   course=dict(value=64, rank=1), distance=dict(value=75, rank=1),
                   style="差", corner=4, average=74, maximum=99,
                   plus="今回調教B / 近走同回り好走",
                   caution="休養明けに注意")
    return dict(no="2", name="コンパクト確認馬", age="牡2", mode=mode,
                frame=1, mark="—", rank=2, formal_member=True,
                candidate_formal_score=82, jockey="騎手",
                race_context=dict(race_data2="4回 京都 サラ系２歳 未勝利",
                                  race_name="かけっこ", race_date="2026-10-30"),
                final_metrics=metrics,
                explorer_facts=dict(metrics=deepcopy(metrics), training=training,
                    current_jockey="騎手", rest_label="中3週",
                    weight_label="55kg", weight_delta_label="+0kg",
                    features=["京都ダ1800m：3戦0回3着以内（近3走の範囲）",
                              "調教B", "休養明け（90日）"],
                    runs=[dict(label="前走", date="2026-10-10",
                               finish="4", time_index=65, condition="京都ダ1800m")],
                    plus=metrics["plus"], caution=metrics["caution"]))


def test_user_screenshot_example_redundant_prefix_and_training_are_removed():
    h = horse()
    before = deepcopy(h)
    doc = BeautifulSoup(lineup_html([h]), "html.parser")
    col = doc.select_one("td.col-materials")
    assert col is not None
    shown = col.get_text(" ", strip=True)
    assert "能力Top3×調教AB×4角前方" in shown
    assert "近走同回り好走" in shown
    assert "2歳：" not in shown
    assert "保存材料：" not in shown
    assert "今回調教B" not in shown
    assert col.select(".evidence-reference")
    assert col.select(".evidence-support")
    assert col.select(".evidence-caution")
    assert h == before
    # The untouched source is available in the expanded horse detail.
    detail = BeautifulSoup(detail_html(h), "html.parser")
    assert "今回調教B / 近走同回り好走" in detail.get_text(" ", strip=True)


def test_nar_compacts_saved_evidence_and_removes_duplicate_visible_course_distance():
    h = horse(mode="nar")
    h["explorer_facts"]["plus"] = (
        "参考材料：Hペース想定×4角6番手 / コース1位 / 距離1位 / 近走同回り好走 / 騎手上位"
    )
    h["explorer_facts"]["caution"] = "調教C注意 / 斤量増"
    before = deepcopy(h)
    col = BeautifulSoup(lineup_html([h]), "html.parser").select_one("td.col-materials")
    shown = col.get_text(" ", strip=True)
    assert "Hペース×4角6番手" in shown
    assert "近走同回り好走" in shown
    assert "コース1位" not in shown  # already in existing dedicated course cell
    assert "距離1位" not in shown
    assert "保存材料" not in shown
    assert col.select_one(".evidence-more")  # other facts still reachable in details
    assert col.select(".evidence-caution")
    assert h == before


def test_pickup_training_duplicate_hidden_but_caution_explicit_in_nar_and_jra():
    for mode in ("jra", "nar"):
        h = horse(mode=mode)
        if mode == "nar":
            # NAR has no training-grade column; do not invent one.
            h["explorer_facts"]["features"][1] = "距離変更"
        html = BeautifulSoup(pickup_html([h]), "html.parser")
        features = html.select_one(".pickup-features")
        assert features and "調教B" not in features.get_text()
        assert "休養明け" in features.get_text()
        assert features.select(".evidence-caution")
        assert "3戦0回" in features.get_text()
        assert not features.select(".evidence-support")  # zero 3着以内 != positive


def test_very_long_reasons_are_shortened_only_in_badges_and_safe():
    source = '<img src=x onerror="evil()"> / 近走同回り好走 / 逃げ前方'
    rendered = chips(source, limit=1)
    doc = BeautifulSoup(rendered, "html.parser")
    assert not doc.select("img,[onerror]")
    assert "ほか2件" in doc.get_text()
    assert "近走同回り好走" in doc.select_one(".evidence-more")["title"]
    assert "onerror" in doc.select_one(".evidence-chip")["title"]  # original source preserved
    assert len(clean_short("今回調教B")) < len("今回調教B")


def test_reference_badge_is_short_without_misrepresenting_status():
    html = badge_html((dict(level="reference", label="2歳：能力Top3×調教AB×4角前方",
                            detail="26頭中20頭3着内。ただし研究中"),))
    doc = BeautifulSoup(html, "html.parser")
    badge = doc.select_one(".evidence-reference")
    assert badge.text == "能力Top3×調教AB×4角前方"
    assert "研究参考" in badge["aria-label"]
    assert "研究中" in badge["title"]


def test_visible_columns_do_not_get_wider_or_reclamped():
    css = (Path(__file__).resolve().parents[1] / "core" / "game_ui_assets" /
           "race_comparison.css").read_text(encoding="utf-8")
    assert ".col-materials{width:220px" in css
    assert ".col-materials{width:176px}" in css
    assert ".comparison-snippet.material-chip-list" in css
    assert "-webkit-line-clamp:unset" in css
    assert ".col-materials{min-width:0" in css
