from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.dashboard_cards import (
    DashboardDetailError,
    filtered_summary_counts,
    load_detail_json,
    prepare_race_card,
    prepare_race_cards,
    resolve_detail_path,
    today_best_five,
)


ROOT = Path(__file__).resolve().parents[1]


def write_detail(analysis_dir: Path, relative: str = "results/race.json") -> Path:
    target = analysis_dir / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(
            {
                "race_mode": "jra",
                "race_name": "新潟1R",
                "race_info": {
                    "racecourse": "新潟",
                    "race_data": "15:45発走 芝1600m",
                },
                "horse_evaluation": [
                    {"馬番": "1.0", "馬名": "アルファ", "表示印": "◎", "AI点": 0, "能力帯": "SS", "能力評価値": 0},
                    {"馬番": 3, "馬名": "ベータ", "display_mark": "○", "normalized_ai_score": 82.5, "ability_band": "A"},
                    {"馬番": 7, "馬名": "ガンマ", "old_final_mark": "▲", "AI点": 79, "ability_display_score": 68.2},
                ],
                "overall_table": [
                    {"馬番": 1, "馬名": "アルファ", "old_final_mark": "◎", "AI点": 0, "ability_band": "SS", "ability_display_score": 0},
                    {"馬番": "3", "馬名": "ベータ", "old_final_mark": "○", "AI点": 83, "ability_band": "A", "ability_display_score": 71},
                    {"馬番": 7.0, "馬名": "ガンマ", "old_final_mark": "▲", "AI点": 79, "ability_display_score": 68.2},
                ],
                "status": "ok",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return target


class DashboardCardTest(unittest.TestCase):
    def test_buy_cards_are_sorted_by_strategy_score_descending(self) -> None:
        summary = {
            "buy": [
                {"race_id": "low", "strategy_score": 65, "venue": "札幌", "race_number": "2R"},
                {"race_id": "high", "strategy_score": "91", "venue": "札幌", "race_number": "1R"},
                {"race_id": "middle", "strategy_score": 80, "venue": "新潟", "race_number": "1R"},
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            cards = prepare_race_cards(summary, tmp, source="JRA Weekend")
        self.assertEqual([card.race_id for card in cards], ["high", "middle", "low"])

    def test_cards_can_be_filtered_by_venue_and_sorted_by_race_number(self) -> None:
        summary = {
            "buy": [
                {"race_id": "s2", "strategy_score": 70, "venue": "札幌", "race_number": "2R"},
                {"race_id": "n1", "strategy_score": 95, "venue": "新潟", "race_number": "1R"},
                {"race_id": "s1", "strategy_score": 60, "venue": "札幌", "race_number": "1R"},
            ],
            "hold": [{"race_id": "s3", "venue": "札幌"}],
            "skip": [{"race_id": "n2", "venue": "新潟"}],
        }
        with tempfile.TemporaryDirectory() as tmp:
            cards = prepare_race_cards(summary, tmp, source="JRA Weekend", venue="札幌", sort_mode="race")
        self.assertEqual([card.race_id for card in cards], ["s1", "s2"])
        self.assertEqual(filtered_summary_counts(summary, "札幌"), (2, 1, 0))

    def test_best_five_combines_sources_and_keeps_top_scores(self) -> None:
        jra = {"buy": [{"race_id": f"jra-{score}", "strategy_score": score} for score in (95, 70, 60)]}
        nar = {"buy": [{"race_id": f"nar-{score}", "strategy_score": score} for score in (99, 88, 77, 55)]}
        with tempfile.TemporaryDirectory() as tmp:
            cards = today_best_five((("JRA Weekend", jra, tmp), ("NAR Daily", nar, tmp)))
        self.assertEqual([card.strategy_score for card in cards], [99, 95, 88, 77, 70])
        self.assertEqual([card.source for card in cards], ["NAR Daily", "JRA Weekend", "NAR Daily", "NAR Daily", "JRA Weekend"])

    def test_card_uses_existing_detail_json_for_marks_ai_and_ability(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "analysis"
            write_detail(analysis)
            item = {
                "race_id": "202604021111",
                "venue": "新潟",
                "race_number": "11",
                "ticket": "ワイド SS-A",
                "strategy_score": 91,
                "expected_roi": 179.3,
                "confidence": "★★★★☆",
                "reason": "サンプル20R以上 / 過去回収実績",
                "detail_path": "results/race.json",
            }
            card = prepare_race_card(item, analysis, source="JRA Weekend")

        self.assertEqual(card.venue, "新潟")
        self.assertEqual(card.race_number, "11R")
        self.assertEqual(card.post_time, "15:45")
        self.assertEqual(card.roi, "179.3%")
        self.assertEqual(card.investment_rank, "★★★★☆")
        self.assertEqual(card.condition_match, "SS-A")
        self.assertEqual(card.adopted_strategy, "ワイド SS-A")
        self.assertTrue(card.detail_available)
        self.assertEqual([(horse.mark, horse.number, horse.name) for horse in card.horses], [
            ("◎", "1", "アルファ"),
            ("○", "3", "ベータ"),
            ("▲", "7", "ガンマ"),
        ])
        self.assertEqual(card.horses[0].ai_score, "0")
        self.assertEqual(card.horses[0].ability, "SS / 0")
        self.assertEqual(card.horses[1].ai_score, "83")
        self.assertEqual(card.horses[1].ability, "A / 71")

    def test_daily_summary_fields_are_used_without_recalculation(self) -> None:
        item = {
            "race_type": "nar",
            "race_id": "nar-race",
            "venue": "門別",
            "race_number": "10R",
            "post_time": "20:05",
            "ticket": "馬連 SS-A",
            "strategy_score": 84,
            "expected_roi": 172,
            "investment_rank": "S",
            "horses": [
                {"number": 3, "name": "ホースA", "role": "◎", "group": "SS"},
                {"number": 7, "name": "ホースB", "role": "○", "group": "A"},
                {"number": 9, "name": "ホースC", "role": "▲", "group": "A"},
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            card = prepare_race_card(item, tmp, source="NAR Daily")
        self.assertEqual((card.venue, card.race_number, card.post_time), ("門別", "10R", "20:05"))
        self.assertEqual(card.investment_rank, "S")
        self.assertEqual(card.condition_match, "SS-A")
        self.assertEqual(card.adopted_strategy, "馬連 SS-A")
        self.assertEqual([horse.mark for horse in card.horses], ["◎", "○", "▲"])
        self.assertTrue(all(horse.ai_score == "—" for horse in card.horses))
        self.assertFalse(card.detail_available)

    def test_detail_loader_rejects_paths_outside_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            analysis = Path(tmp) / "analysis"
            analysis.mkdir()
            with self.assertRaises(DashboardDetailError):
                resolve_detail_path(analysis, "../secret.json")
            with self.assertRaises(DashboardDetailError):
                load_detail_json(analysis, "/tmp/secret.json")

    def test_mobile_ui_contains_filter_sort_collapsed_hold_skip_count_and_detail_switch(self) -> None:
        source = (ROOT / "core" / "dashboard_ui.py").read_text(encoding="utf-8")
        detail_source = (ROOT / "pages" / "3_Race_Detail.py").read_text(encoding="utf-8")
        self.assertIn('st.subheader("今日のBEST5")', source)
        self.assertIn('st.selectbox("開催場"', source)
        self.assertIn('st.radio("表示順"', source)
        self.assertIn('filtered_summary_counts(summary, selected_venue)', source)
        self.assertIn('st.markdown("**買う理由**")', source)
        self.assertIn('st.write(f"条件一致：{card.condition_match}")', source)
        self.assertIn('st.write(f"採用戦略：{card.adopted_strategy}")', source)
        self.assertIn('st.download_button(', source)
        self.assertIn('"本日の予想履歴を一括ダウンロード"', source)
        self.assertIn('with st.expander(f"HOLD {hold_count}R", expanded=False)', source)
        self.assertIn('st.caption(f"SKIP {skip_count}R（件数のみ表示）")', source)
        self.assertIn('st.switch_page(DETAIL_PAGE)', source)
        self.assertIn('load_detail_json(ANALYSIS_DIR, detail_path)', detail_source)


if __name__ == "__main__":
    unittest.main()
