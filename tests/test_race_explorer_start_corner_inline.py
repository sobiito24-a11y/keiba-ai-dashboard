"""Display-only start/4corner inline ranks: no new race predictions or scores."""
from copy import deepcopy

from bs4 import BeautifulSoup
import pytest

from core.game_race_ui import build_view
from core.prediction_table_ui import prediction_table_records
from core.race_explorer_columns import records, columns
from core.race_explorer_ui import _cell, lineup_html


def test_saved_start_and_corner_display_two_lines_without_prediction_mutation():
    for mode in ("jra", "nar"):
        info = {"race_id": "202611080101", "venue": "東京", "distance": 1800, "surface": "ダ"}
        source = [
            dict(馬番=6, 馬名="先行馬", 枠番=3, running_style_market="先",
                 netkeiba_start_rank=2, netkeiba_corner3_rank=5, netkeiba_corner4_rank=15,
                 market_ability_score=90, market_ability_rank=13),
            dict(馬番=12, 馬名="逃げ馬", 枠番=6, running_style_market="逃",
                 netkeiba_start_rank=1, netkeiba_corner3_rank=1, netkeiba_corner4_rank=1,
                 market_ability_score=80, market_ability_rank=1),
        ]
        predictions = prediction_table_records(source, source, info, mode)
        before = deepcopy((source, predictions))
        view = build_view(source, predictions, source, mode, info)
        assert (source, predictions) == before
        h = next(h for h in view if str(h["no"]) == "6")
        assert h["start_rank"] == 2
        assert h["third_rank"] == 5
        assert h["corner"] == 15
        cells = records(view)["6"]
        assert cells["start_rank"] == 2
        assert cells["corner"] == 15
        assert cells["ability_rank"] == 13
        doc = BeautifulSoup(lineup_html(view), "html.parser")
        row = doc.select_one('tr[data-horse="6"]')
        assert 'running-style-square-active' in row.select_one(
            '.col-style .running-style-square:nth-child(2)')['class']
        assert row.select_one('.col-style .running-style-position').text == "序盤2 / 4角15"
        assert not row.select('.col-corner')
        assert doc.select_one('th[data-column="style"] .column-label').text == "脚質・位置"
        # The independent pre-race corner remains numeric/filterable but not a second wide column.
        assert next(x for x in columns(view) if x["key"] == "corner")["type"] == "rank"
        assert next(x for x in columns(view) if x["key"] == "corner")["table_hidden"] is True
        assert not any(x['key'] == 'start_rank' for x in columns(view))
        assert len(doc.select("thead th")) == len([s for s in columns(view) if not s.get("table_hidden")])


@pytest.mark.parametrize("start", [None, 0, -1, "NaN", "未取得", True, "7.5"])
def test_missing_or_invalid_start_never_fabricated(start):
    h = {"no": "6", "name": "確認馬", "mode": "nar", "style": "逃",
         "start_rank": start, "corner": 4, "ability_rank": None}
    cells = records([h])["6"]
    assert cells["start_rank"] is None
    style = BeautifulSoup(_cell(h, cells, "style"), "html.parser")
    assert "序盤— / 4角4" in style.get_text(" ")
    assert "保存脚質 逃げ" in style.select_one(".running-style-squares")['aria-label']
    corner = BeautifulSoup(_cell(h, cells, "corner"), "html.parser")
    assert "4番手" in corner.get_text(" ")
    assert "能力順位未取得" in corner.get_text(" ")



@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_saved_netkeiba_third_rank_wires_through_game_view_to_board(mode):
    """Use the same canonical newspaper key persisted in .keiba snapshots."""
    from core.race_development_positions import layout
    from core.race_development_board import board_html
    info = {"race_id":"202611080101","venue":"東京","surface":"芝","distance":1600}
    source = [
        dict(馬番=1, 馬名="先頭馬", 枠番=1, netkeiba_start_rank=1,
             netkeiba_corner3_rank=3, netkeiba_corner4_rank=1,
             market_ability_score=80, market_ability_rank=1),
        dict(馬番=2, 馬名="追い上げ馬", 枠番=1, netkeiba_start_rank=3,
             netkeiba_corner3_rank=1, netkeiba_corner4_rank=2,
             market_ability_score=70, market_ability_rank=2),
        dict(馬番=3, 馬名="中団馬", 枠番=2, netkeiba_start_rank=2,
             netkeiba_corner3_rank=2, netkeiba_corner4_rank=3,
             market_ability_score=60, market_ability_rank=3),
    ]
    predictions = prediction_table_records(source, source, info, mode)
    before = deepcopy((source, predictions))
    view = build_view(source, predictions, source, mode, info)
    assert (source, predictions) == before
    assert [h["third_rank"] for h in view] == [3, 1, 2]
    lineup = layout(view, course_turn="left")["third"]
    assert lineup["saved_count"] == 3
    assert lineup["interpolated_count"] == 0
    assert [h["no"] for h in lineup["runners"]] == [2, 3, 1]
    dom = BeautifulSoup(board_html(view), "html.parser")
    group = dom.select_one("#ka-pace-scene-third")
    assert "保存予測 3頭／補間 0頭" in group.text
    assert "保存3角予測" in group.select_one(
        '[data-pace-runner="2"]')["aria-label"]
