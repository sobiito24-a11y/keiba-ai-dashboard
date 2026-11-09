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
                 netkeiba_start_rank=2, netkeiba_corner4_rank=15,
                 market_ability_score=90, market_ability_rank=13),
            dict(馬番=12, 馬名="逃げ馬", 枠番=6, running_style_market="逃",
                 netkeiba_start_rank=1, netkeiba_corner4_rank=1,
                 market_ability_score=80, market_ability_rank=1),
        ]
        predictions = prediction_table_records(source, source, info, mode)
        before = deepcopy((source, predictions))
        view = build_view(source, predictions, source, mode, info)
        assert (source, predictions) == before
        h = next(h for h in view if str(h["no"]) == "6")
        assert h["start_rank"] == 2
        assert h["corner"] == 15
        cells = records(view)["6"]
        assert cells["start_rank"] == 2
        assert cells["corner"] == 15
        assert cells["ability_rank"] == 13
        doc = BeautifulSoup(lineup_html(view), "html.parser")
        row = doc.select_one('tr[data-horse="6"]')
        assert row.select_one('.col-style .position-two-line strong').text == "2番手"
        assert row.select_one('.col-style .position-two-line small').text == "先行"
        assert row.select_one('.col-corner .position-two-line strong').text == "15番手"
        assert row.select_one('.col-corner .position-two-line small').text == "能力13位"
        assert doc.select_one('th[data-column="style"] .column-label').text == "序盤傾向"
        assert doc.select_one('th[data-column="corner"] .column-label').text == "4角想定"
        # Corner remains numeric; saved source ranks are reused without extra columns.
        assert next(x for x in columns(view) if x["key"] == "corner")["type"] == "rank"
        assert not any(x['key'] == 'start_rank' for x in columns(view))
        assert len(doc.select("thead th")) == len([s for s in columns(view) if not s.get("table_hidden")])


@pytest.mark.parametrize("start", [None, 0, -1, "NaN", "未取得", True, "7.5"])
def test_missing_or_invalid_start_never_fabricated(start):
    h = {"no": "6", "name": "確認馬", "mode": "nar", "style": "逃",
         "start_rank": start, "corner": 4, "ability_rank": None}
    cells = records([h])["6"]
    assert cells["start_rank"] is None
    style = BeautifulSoup(_cell(h, cells, "style"), "html.parser")
    assert "未取得" in style.get_text(" ")
    assert "逃げ" in style.get_text(" ")
    corner = BeautifulSoup(_cell(h, cells, "corner"), "html.parser")
    assert "4番手" in corner.get_text(" ")
    assert "能力順位未取得" in corner.get_text(" ")
