"""The requested compact two-line display must preserve saved source ranks and sort keys."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.game_race_ui import _saved_start_rank
from core.race_explorer_ui import _cell, _start_style_cell, lineup_html
from core.race_explorer_columns import columns, records


def item(no, style="先", start=2, corner=15, ability_rank=13):
    return {
        "no": str(no), "name": f"馬{no}", "mode": "jra",
        "age": "牡4", "style": style, "start": start, "corner": corner,
        "ability": 80.0 + no, "ability_rank": ability_rank,
        "formal_member": False, "rank": None, "frame": (no % 8) + 1,
        "explorer_facts": {},
    }


def test_corner_shows_saved_ability_rank_without_replacing_corner_sort():
    horse = item(6)
    cells = records([horse])["6"]
    before = deepcopy(cells)
    html = BeautifulSoup(_cell(horse, cells, "corner", 18), "html.parser")
    assert html.select_one(".corner-position-main").get_text(" ", strip=True) == "15番手"
    assert html.select_one(".corner-ability-cell small").get_text(" ", strip=True) == "能力13位"
    assert cells == before
    assert cells["corner"] == 15
    assert cells["ability_rank"] == 13
    assert next(c for c in columns([horse]) if c["key"] == "corner")["type"] == "rank"


def test_start_cell_shows_saved_start_rank_and_small_historical_style():
    for input_style, label in (("逃","逃げ"), ("先","先行"), ("差","差し"), ("追","追込")):
        horse = item(6, style=input_style, start=2)
        cells = records([horse])["6"]
        html = BeautifulSoup(_start_style_cell(cells), "html.parser")
        assert html.select_one(".early-position-main").get_text(" ", strip=True) == "2番手"
        assert html.select_one(".early-style-cell small").get_text(" ", strip=True) == label
        assert "差あり" not in html.get_text(" ", strip=True)


def test_missing_values_do_not_invent_start_or_ability():
    cells = dict(style="差", start=None, corner=None, ability_rank=None)
    start = BeautifulSoup(_start_style_cell(cells), "html.parser")
    assert "未取得" in start.get_text(" ", strip=True)
    assert "差し" in start.get_text(" ", strip=True)
    corner = BeautifulSoup(_cell(item(2), cells, "corner", 18), "html.parser")
    assert "未取得" in corner.get_text(" ", strip=True)
    assert "能力順位 未取得" in corner.get_text(" ", strip=True)
    assert "None位" not in corner.get_text(" ", strip=True)


def test_only_explicit_saved_start_rank_accepted():
    assert _saved_start_rank({"netkeiba_start_rank": "4"}) == 4
    assert _saved_start_rank({"netkeiba_start_rank": 1.0}) == 1
    for row in ({}, {"netkeiba_start_rank": None}, {"netkeiba_start_rank": True},
                {"netkeiba_start_rank": -1}, {"netkeiba_start_rank": "1.5"},
                {"netkeiba_corner4_rank": 1}):
        assert _saved_start_rank(row) is None


def test_full_table_keeps_numeric_sort_and_filters_separate_from_style():
    view = [item(i, style=("先" if i == 6 else "差"), start=i,
                 corner=i, ability_rank=i) for i in range(1, 19)]
    view[5]["start"] = 2
    view[5]["corner"] = 15
    original = deepcopy(view)
    before = records(view)
    doc = BeautifulSoup(lineup_html(view), "html.parser")
    specs = columns(view)
    shown = [s for s in specs if not s.get("table_hidden")]
    assert len(doc.select("tr[data-horse]")) == 18
    assert len(doc.select("thead th")) == len(shown)
    assert doc.select_one('[data-column="start"] .column-label').text == "序盤傾向"
    assert doc.select_one('[data-column="corner"] .column-label').text == "4角想定"
    assert next(x for x in specs if x["key"] == "start")["type"] == "rank"
    assert next(x for x in specs if x["key"] == "style")["table_hidden"] is True
    row = doc.select_one('tr[data-horse="6"]')
    assert "2番手" in row.select_one(".col-start").get_text(" ")
    assert "先行" in row.select_one(".col-start").get_text(" ")
    assert "15番手" in row.select_one(".col-corner").get_text(" ")
    assert "能力6位" in row.select_one(".col-corner").get_text(" ")
    assert before["6"]["start"] == 2
    assert before["6"]["corner"] == 15
    assert before["6"]["style"] == "先"
    assert records(view) == before
    assert view == original
