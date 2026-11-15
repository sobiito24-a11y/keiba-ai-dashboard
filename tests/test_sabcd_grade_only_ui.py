"""Mobile table shows the grade alone; voluntary detail keeps all research."""
from bs4 import BeautifulSoup
from core.race_explorer_ui import _cell
from core.race_explorer_cards import detail_html


def horse(mode):
    return {
        "no": "3", "name": "検証馬", "mode": mode, "frame": 2,
        "research_sabcd_weight_class": {
            "grade": "B", "score": 0.431, "reason": "クラス補正の検証値",
            "retro": True,
        },
        "research_positioning": {
            "label": "軸候補", "reason": "研究用ラベルで未検証",
        },
        "research_suitability_attention": {
            "label": "適性注目", "reason": "距離の過去実績",
        },
        "jra_race_day_check": {
            "role": "3評価一致", "reasons": ["研究Bと今回評価の一致"],
        },
        "nar_race_day_check": {
            "role": "Top5外再確認", "reasons": ["純能力6位、4角2番手"],
        },
    }


def test_single_grade_without_betting_labels_for_both_modes():
    for mode in ("jra", "nar"):
        h = horse(mode)
        cells = {
            "research_sabcd": "B",
            "research_sabcd_score": .431,
            "research_sabcd_reason": "クラス補正の検証値",
            "research_sabcd_retro": True,
            "research_positioning_label": "軸候補",
            "research_positioning_reason": "研究用ラベルで未検証",
            "research_suitability_label": "適性注目",
            "research_suitability_reason": "距離の過去実績",
        }
        html = _cell(h, cells, "research_sabcd")
        parsed = BeautifulSoup(html, "html.parser")
        assert parsed.get_text(" ", strip=True) == "B"
        assert len(parsed.select(".research-sabcd-B")) == 1
        assert not parsed.select(".research-role-inline")
        for label in ("軸候補", "軸比較", "押さえ", "V3一致", "N再確認", "適性注目", "後日算出"):
            assert label not in parsed.get_text(" ", strip=True)
        assert h["research_positioning"]["label"] == "軸候補"
        assert h["research_sabcd_weight_class"]["grade"] == "B"


def test_missing_grade_is_only_unknown_not_research_suggestion():
    h = horse("jra")
    html = _cell(h, {"research_sabcd": None, "research_positioning_label": "軸候補"},
                 "research_sabcd")
    assert BeautifulSoup(html, "html.parser").get_text(strip=True) == "判定不可"
    assert "軸候補" not in html


def test_research_details_only_after_click_and_voluntary_expand():
    for mode in ("jra", "nar"):
        html = detail_html(horse(mode))
        parsed = BeautifulSoup(html, "html.parser")
        details = parsed.select_one("details.detail-research-model")
        assert details is not None
        assert details.get("open") is None  # Closed by default.
        assert "研究評価の詳細（任意）" in details.summary.get_text()
        assert "軸候補" in details.get_text()
        assert "研究Bと今回評価の一致" in details.get_text() if mode == "jra" else "純能力6位、4角2番手" in details.get_text()
        basic = parsed.select_one("dl.detail-basic")
        assert basic is not None
        assert "軸候補" not in basic.get_text()
        assert "研究上の位置づけ" not in basic.get_text()
