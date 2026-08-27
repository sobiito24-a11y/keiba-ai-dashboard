from __future__ import annotations

from core.v1_logic import build_v1_evaluations, jra_reproducibility, nar_reproducibility, pace_evaluation, state_evaluation


def test_nar_reproducibility_ranks_same_venue_distance_results() -> None:
    current = {"venue": "船橋", "distance": 2200}
    assert nar_reproducibility(
        [
            {"racecourse": "船橋", "distance": 2200, "position": 1},
            {"racecourse": "船橋", "distance": 2200, "position": 3},
        ],
        current,
    )["rank"] == "S"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 2200, "position": 2}], current)["rank"] == "A"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 2200, "position": 8}], current)["rank"] == "C"
    assert nar_reproducibility([{"racecourse": "船橋", "distance": 1600, "position": 2}], current)["rank"] == "B"
    assert nar_reproducibility([{"racecourse": "大井", "distance": 1200, "position": 2}], current)["rank"] == "—"


def test_jra_reproducibility_uses_surface_distance_turn_before_turn_only() -> None:
    current = {"venue": "中京", "surface": "芝", "distance": 2000, "turn": "左"}
    assert jra_reproducibility(
        [
            {"racecourse": "東京", "surface": "芝", "distance": 2000, "direction": "左", "position": 2},
            {"racecourse": "新潟", "surface": "芝", "distance": 2000, "direction": "左", "position": 3},
        ],
        current,
    )["rank"] == "S"
    assert jra_reproducibility([{"racecourse": "東京", "surface": "芝", "distance": 2000, "direction": "左", "position": 2}], current)["rank"] == "A"
    assert jra_reproducibility([{"racecourse": "阪神", "surface": "芝", "distance": 2000, "direction": "右", "position": 2}], current)["rank"] == "B"
    assert jra_reproducibility([{"racecourse": "東京", "surface": "芝", "distance": 1600, "direction": "左", "position": 2}], current)["rank"] == "C"
    assert jra_reproducibility([{"racecourse": "阪神", "surface": "ダート", "distance": 1400, "direction": "右", "position": 2}], current)["rank"] == "—"


def test_pace_and_state_evaluations_are_display_axes_only() -> None:
    assert pace_evaluation({"corner4_group": "front", "running_style": "逃げ"}) == {"rank": "○", "reason": "4角前方想定（逃げ）"}
    assert pace_evaluation({"corner4_group": "back"})["rank"] == "×"
    assert state_evaluation(
        {
            "training": "A/好調",
            "stable_comment": "順調で期待",
            "jockey_change": "継続",
            "weight_diff": -1,
        },
        [],
        "jra",
    )["rank"] == "A"
    assert state_evaluation({"interval": "休み明け", "weight_diff": 2}, [], "nar")["rank"] == "C"


def test_build_v1_evaluations_assigns_star_and_check_without_odds() -> None:
    rows = [
        {"horse_no": "1", "horse_name": "A", "venue": "船橋", "distance": 2200, "ability_value": 100, "ability_rank": 1, "ai_current_rank": 1, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "2", "horse_name": "B", "venue": "船橋", "distance": 2200, "ability_value": 95, "ability_rank": 2, "ai_current_rank": 2, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "3", "horse_name": "C", "venue": "船橋", "distance": 2200, "ability_value": 90, "ability_rank": 3, "ai_current_rank": 3, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 2}]},
        {"horse_no": "4", "horse_name": "D", "venue": "船橋", "distance": 2200, "ability_value": 10, "ability_rank": 8, "ai_current_rank": 7, "recent_runs": [{"racecourse": "船橋", "distance": 2200, "position": 1}]},
        {"horse_no": "5", "horse_name": "E", "venue": "船橋", "distance": 2200, "ability_value": 9, "ability_rank": 9, "ai_current_rank": 8, "corner4_group": "front", "recent_runs": [{"racecourse": "船橋", "distance": 1600, "position": 2}]},
        {"horse_no": "6", "horse_name": "F", "venue": "船橋", "distance": 2200, "ability_value": 8, "ability_rank": 10, "ai_current_rank": 9, "corner4_group": "front", "recent_runs": []},
    ]
    result = build_v1_evaluations(rows, "nar")
    marks = {row["horse_no"]: row["v1_mark"] for row in result["rows"]}
    assert marks["1"] == "◎"
    assert "☆" in marks.values()
    assert "✔︎" in marks.values()
    assert all(row.get("odds") is None for row in result["rows"])
