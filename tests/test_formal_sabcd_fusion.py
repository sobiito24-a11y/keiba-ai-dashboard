"""The experimental fusion must never become another visible grade or alter bets."""
from copy import deepcopy

import pytest
from bs4 import BeautifulSoup

from core.formal_sabcd_fusion import (
    VERSION, assign_to_view, evaluate_race, research_score,
)
from core.game_race_ui import build_view, document
from core.prediction_table_ui import prediction_table_records


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_frozen_research_score_monotonic_and_no_missing_inference(mode):
    assert VERSION.startswith("formal-sabcd-fusion-shadow")
    a = research_score(mode, 1, 0.8, 12)
    b = research_score(mode, 9, 0.2, 12)
    assert 0 < b < a < 1
    for rank, score, field_size in [
        (None, 0.5, 10), (1, None, 10), (2, 0.5, 2),
        (99, 0.5, 12), (0, 0.5, 12), (1, -1, 12),
        (1, float("nan"), 12), ("?", 0.5, 12)
    ]:
        assert research_score(mode, rank, score, field_size) is None


def test_read_only_diagnostics_do_not_change_formal_rank_or_grade():
    view = []
    for n in range(1, 9):
        view.append(dict(
            no=str(n), mode="jra", rank=n,
            candidate_formal_score=100. - n,
            research_sabcd_weight_class={"score": .8 - n * .06, "grade": "A"},
            race_context={"race_date": "2026-11-16"}, mark="◎" if n == 1 else "",
        ))
    before = deepcopy(view)
    scored = evaluate_race(view)
    assert view == before
    assert len(scored) == len(view)
    assert all(scored[str(i)]["status"] == "research_only" for i in range(1, 9))
    assign_to_view(view)
    for original, current in zip(before, view):
        assert {k: v for k, v in current.items() if k != "research_formal_sabcd_fusion"} == original
        assert original["research_sabcd_weight_class"] == current["research_sabcd_weight_class"]
        assert "research_formal_sabcd_fusion" in current
    assert "研究" in view[0]["research_formal_sabcd_fusion"]["reason"]


def test_nar_reference_rank_cannot_be_misread_as_formal():
    view = [
        dict(no=str(n), mode="nar", rank=n,
             # No authentic formal score: reference ranks >5 cannot be promoted.
             candidate_formal_score=None if n > 5 else 100 - n,
             research_sabcd_weight_class={"score": .55, "grade": "B"},
             race_context={"race_date": "2026-11-15"})
        for n in range(1, 11)
    ]
    scored = evaluate_race(view)
    assert all(scored[str(i)]["score"] is not None for i in range(1, 6))
    assert all(scored[str(i)]["score"] is None for i in range(6, 11))
    assert all(scored[str(i)]["status"] == "insufficient_inputs" for i in range(6, 11))


def test_ui_has_one_grade_column_and_fusion_only_inside_optional_details():
    rows = [
        dict(馬番=n, 馬名=f"テスト馬{n}", 枠番=1,
             jra_top5_score=100 - n, jra_top5_rank=n,
             ver3_ability_core=90 - n, market_ability_rank=n,
             netkeiba_corner4_rank=n, netkeiba_start_rank=n,
             netkeiba_running_style="先", netkeiba_pace="M",
             距離指数=85 - n, コース指数=80 - n, 平均指数=75 - n)
        for n in range(1, 9)
    ]
    info = dict(race_id="202611160101", race_date="2026-11-16",
                venue="東京", surface="ダート", distance=1600)
    records = prediction_table_records(rows, rows, info, "jra")
    view = build_view(rows, records, rows, "jra", info)
    assert all("research_formal_sabcd_fusion" in h for h in view)
    page = BeautifulSoup(document(view, info["race_id"]), "html.parser")
    lineup = page.select_one("#lineup-workspace")
    assert lineup is not None
    assert len(lineup.select("th.col-research_sabcd")) == 1
    assert not lineup.select(".col-rank, .col-research_formal_sabcd_fusion")
    assert not lineup.find(string=lambda text: bool(text and "統合試験値" in text))
    # Research text must require an explicit horse detail click, never under S/A/B/C/D.
    details = page.select(".detail-research-model")
    assert len(details) == len(view)
    assert all(not detail.has_attr("open") for detail in details)
    assert all("正式×SABCD統合試験値（未採用）" in detail.get_text() for detail in details)
