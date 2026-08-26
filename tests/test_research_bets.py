from __future__ import annotations

from core.research_bets import build_research_bet


def row(no: int, rank: int, mark: str, odds: float | str | None = None, current_rank: int | None = None) -> dict:
    data = {
        "馬番": no,
        "馬名": f"Horse{no}",
        "market_ability_rank": rank,
        "market_ability_score": 100 - (rank * 3),
        "ai_current_mark": mark,
        "current_evaluation_rank": current_rank or rank,
    }
    if odds is not None:
        data["odds_at_prediction"] = odds
    return data


def marked_rows(axis_odds: float | None = None) -> list[dict]:
    return [
        row(1, 1, "◎", axis_odds),
        row(2, 2, "○", 4.1),
        row(3, 3, "▲", 8.0),
        row(4, 4, "△", 12.0),
        row(5, 5, "☆", 20.0),
    ]


def test_jra_mobile_research_bet_odds_boundaries():
    assert build_research_bet(marked_rows(4.9), "jra", context="mobile")["total"] == 500
    assert build_research_bet(marked_rows(5.0), "jra", context="mobile")["total"] == 1000
    assert build_research_bet(marked_rows(9.9), "jra", context="mobile")["total"] == 1000
    assert build_research_bet(marked_rows(10.0), "jra", context="mobile")["total"] == 500
    assert build_research_bet(marked_rows(None), "jra", context="mobile")["total"] == 500


def test_jra_dashboard_guide_does_not_use_saved_odds_for_total():
    guide = build_research_bet(marked_rows(6.4), "jra", context="dashboard")
    assert guide["research_rule_id"] == "JRA_DASH_GUIDE_V1"
    assert guide["total"] == 500
    assert guide["trio_condition"] == "3連複は参考候補"
    assert guide["title"] == "🧪 JRA Dashboard研究ガイド"
    assert any("3連複研究候補" in line for line in guide["lines"])


def test_jra_dashboard_guide_is_invariant_across_saved_odds():
    without_odds = build_research_bet(marked_rows(None), "jra", context="dashboard")
    zero_odds = build_research_bet(marked_rows(0.0), "jra", context="dashboard")
    mid_odds = build_research_bet(marked_rows(6.4), "jra", context="dashboard")
    high_odds = build_research_bet(marked_rows(10.0), "jra", context="dashboard")

    assert without_odds["total"] == zero_odds["total"] == mid_odds["total"] == high_odds["total"] == 500
    assert without_odds["lines"] == zero_odds["lines"] == mid_odds["lines"] == high_odds["lines"]
    assert without_odds["trio_condition"] == zero_odds["trio_condition"] == mid_odds["trio_condition"] == high_odds["trio_condition"]


def test_nar_research_bet_uses_ability_rank_quinella_when_axis_odds_low():
    research = build_research_bet(marked_rows(2.4), "nar", context="mobile")
    assert research["research_rule_id"] == "NAR_VER4_AXIS_ML_2_4_V1"
    assert research["research_status"] == "eligible"
    assert research["total"] == 400
    assert research["ticket_lines"] == [
        "◎－○ 1-2 100円",
        "◎－▲ 1-3 100円",
        "◎－△ 1-4 100円",
        "◎－☆ 1-5 100円",
    ]
    assert all("単勝 500円" not in line for line in research["lines"])
    assert "3連複" not in "\n".join(research["lines"])

    missing = build_research_bet([row(1, 2, "◎", 3.0)], "nar", context="mobile")
    assert missing["show"] is False


def test_nar_dashboard_guide_shows_rule_without_odds_and_never_adds_trio():
    no_odds = build_research_bet(marked_rows(None), "nar", context="dashboard")
    zero_odds = build_research_bet(marked_rows(0.0), "nar", context="dashboard")

    for guide in (no_odds, zero_odds):
        assert guide["show"] is True
        assert guide["title"] == "🧪 NAR Ver4研究ガイド"
        assert guide["research_status"] == "waiting_odds"
        assert guide["total"] == 0
        assert any("オッズ確定後" in line for line in guide["lines"])
        assert "3連複" not in "\n".join(guide["lines"])
        assert guide["trio_condition"] == ""


def test_nar_research_bet_marks_out_of_rule_and_boundaries():
    for odds in (2.39, 2.4, 2.40):
        assert build_research_bet(marked_rows(odds), "nar", context="dashboard")["research_status"] == "eligible"
    for odds in (2.41, 2.5, 3.0):
        assert build_research_bet(marked_rows(odds), "nar", context="dashboard")["research_status"] == "out_of_rule"
    for odds in (0, 0.0, "0", "0倍", "—", "未取得", float("nan"), -1, "bad"):
        assert build_research_bet(marked_rows(odds), "nar", context="dashboard")["research_status"] == "waiting_odds"


def test_nar_monitor_tags_do_not_change_research_eligibility():
    rows = [
        row(1, 1, "◎", 2.4, current_rank=5),
        row(2, 2, "○", 4.1, current_rank=4),
        row(3, 3, "▲", 8.0, current_rank=3),
        row(4, 4, "△", 12.0, current_rank=2),
        row(5, 5, "☆", 20.0, current_rank=1),
    ]
    rows[0]["axis_confidence"] = "A"
    rows[0]["market_ability_score"] = 100
    rows[1]["market_ability_score"] = 80
    research = build_research_bet(rows, "nar", context="dashboard")
    assert research["research_status"] == "eligible"
    assert research["monitor_flags"]["axis_confidence_a"] is True
    assert research["monitor_flags"]["ability_gap_1_2_ge_10"] is True
    assert research["monitor_flags"]["ability_current_top5_match"] is False
