from __future__ import annotations

from core.research_bets import build_research_bet


def row(no: int, rank: int, mark: str, odds: float | None = None) -> dict:
    data = {
        "馬番": no,
        "馬名": f"Horse{no}",
        "market_ability_rank": rank,
        "market_ability_score": 90 - no,
        "ai_current_mark": mark,
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


def test_nar_research_bet_is_axis_win_only_and_requires_ability_rank_one():
    research = build_research_bet(marked_rows(6.4), "nar", context="mobile")
    assert research["research_rule_id"] == "NAR_V4_R100_V1"
    assert research["total"] == 500
    assert research["lines"] == ["◎1 Horse1 単勝 500円"]

    missing = build_research_bet([row(1, 2, "◎", 3.0)], "nar", context="mobile")
    assert missing["show"] is False


def test_nar_dashboard_guide_shows_without_odds_and_never_adds_trio():
    no_odds = build_research_bet(marked_rows(None), "nar", context="dashboard")
    zero_odds = build_research_bet(marked_rows(0.0), "nar", context="dashboard")

    for guide in (no_odds, zero_odds):
        assert guide["show"] is True
        assert guide["title"] == "🧪 NAR Ver4研究ガイド"
        assert guide["total"] == 500
        assert guide["lines"] == ["◎1 Horse1 単勝 500円"]
        assert "3連複" not in "\n".join(guide["lines"])
        assert guide["trio_condition"] == ""
