from __future__ import annotations

import unittest

import pandas as pd

from core.models import PredictionResult
from core.race_investment_strategy import load_jra_strategy_selection, select_jra_investment_strategy
from core.weekend_summary import build_weekend_summary


def jra_result(rows: list[dict]) -> PredictionResult:
    return PredictionResult(
        race_mode="jra",
        race_name="テスト1R",
        race_info={"racecourse": "札幌", "race_number": "1R"},
        overall_table=pd.DataFrame(rows),
        status="ok",
    )


class JraRaceLevelDecisionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = load_jra_strategy_selection()

    def test_jra_strategy_json_produces_buy_only_for_formal_matching_strategy(self) -> None:
        result = jra_result([
            {"horse_no": 1, "horse_name": "SS馬", "display_group": "SS", "ai_rank": 1, "normalized_ai_score": 99, "odds": 3.2},
            {"horse_no": 2, "horse_name": "A馬", "display_group": "A", "ai_rank": 2, "normalized_ai_score": 94, "odds": 12.0},
            {"horse_no": 3, "horse_name": "B馬", "display_group": "B", "ai_rank": 3, "normalized_ai_score": 88, "odds": 18.0},
        ])
        payload = select_jra_investment_strategy(result, self.strategy)
        self.assertEqual(payload["decision"], "BUY")
        self.assertEqual(payload["strategy_id"], "wide_ss_b")
        self.assertEqual(payload["combinations"], ["1-3"])
        self.assertEqual(payload["points"], 1)
        self.assertEqual(payload["investment"], 100)

    def test_ai1_short_odds_avoid_condition_prevents_buy(self) -> None:
        result = jra_result([
            {"horse_no": 1, "horse_name": "SS馬", "display_group": "SS", "ai_rank": 1, "normalized_ai_score": 99, "odds": 1.5},
            {"horse_no": 2, "horse_name": "A馬", "display_group": "A", "ai_rank": 2, "normalized_ai_score": 94, "odds": 4.8},
            {"horse_no": 3, "horse_name": "B馬", "display_group": "B", "ai_rank": 3, "normalized_ai_score": 88, "odds": 18.0},
        ])
        payload = select_jra_investment_strategy(result, self.strategy)
        self.assertNotEqual(payload["decision"], "BUY")
        candidates = payload["strategy_audit"]["candidates"]
        wide = next(item for item in candidates if item["strategy_id"] == "wide_ss_b")
        self.assertIn("AI1オッズ2倍未満", wide["avoid_matches"])

    def test_strategy_is_skip_when_no_formal_or_reference_condition_matches(self) -> None:
        result = jra_result([
            {"horse_no": 1, "horse_name": "SS馬", "display_group": "SS", "ai_rank": 1, "normalized_ai_score": 99, "odds": 1.6},
            {"horse_no": 2, "horse_name": "A馬", "display_group": "A", "ai_rank": 2, "normalized_ai_score": 94, "odds": 3.0},
            {"horse_no": 3, "horse_name": "Z馬", "display_group": "Z", "ai_rank": 3, "normalized_ai_score": 88, "odds": 4.0},
        ])
        payload = select_jra_investment_strategy(result, self.strategy)
        self.assertEqual(payload["decision"], "SKIP")
        self.assertEqual(payload["investment"], 0)

    def test_weekend_summary_uses_race_level_decision_and_keeps_one_strategy(self) -> None:
        result = jra_result([
            {"horse_no": 1, "horse_name": "SS馬", "display_group": "SS", "ai_rank": 1, "normalized_ai_score": 99, "odds": 3.2},
            {"horse_no": 2, "horse_name": "A馬", "display_group": "A", "ai_rank": 2, "normalized_ai_score": 94, "odds": 12.0},
            {"horse_no": 3, "horse_name": "B馬", "display_group": "B", "ai_rank": 3, "normalized_ai_score": 88, "odds": 18.0},
        ])
        summary = build_weekend_summary([("202601010101", result)], summary_date="2026-08-09")
        self.assertEqual(len(summary.buy), 1)
        self.assertEqual(summary.buy[0].strategy_id, "wide_ss_b")
        self.assertEqual(summary.buy[0].combinations, ("1-3",))
        self.assertEqual(summary.buy[0].decision, "BUY")
        self.assertEqual(summary.hold, ())
        self.assertEqual(summary.skip, ())


if __name__ == "__main__":
    unittest.main()
