"""Only display changes: no source projection, rank, sort or filter modification."""
from copy import deepcopy

from bs4 import BeautifulSoup

from core.race_explorer_ui import _cell, _position_path, lineup_html
from core.race_explorer_columns import columns, records


def item(no, style="先", corner=15, ability_rank=13):
    return {
        "no": str(no), "name": f"馬{no}", "mode": "jra",
        "age": "牡4", "style": style, "corner": corner,
        "ability": 80.0 + no, "ability_rank": ability_rank,
        "formal_member": False, "rank": None, "frame": (no % 8) + 1,
        "explorer_facts": {},
    }


def test_corner_shows_saved_ability_rank_without_replacing_corner_sort():
    horse = item(6)
    cells = records([horse])["6"]
    before = deepcopy(cells)
    html = BeautifulSoup(_cell(horse, cells, "corner", 18), "html.parser")
    assert "15番手" in html.get_text(" ")
    assert "能力13位" in html.get_text(" ")
    assert cells == before
    assert cells["corner"] == 15
    assert cells["ability_rank"] == 13
    assert next(c for c in columns([horse]) if c["key"] == "corner")["type"] == "rank"


def test_style_to_corner_flags_large_position_disagreement_without_inference():
    h = BeautifulSoup(_position_path(dict(style="先", corner=15), 18), "html.parser")
    assert "先行型" in h.get_text(" ")
    assert "後方想定" in h.get_text(" ")
    assert "差あり" in h.get_text(" ")
    h = BeautifulSoup(_position_path(dict(style="逃", corner=1), 18), "html.parser")
    assert "前方想定" in h.get_text(" ")
    assert "差あり" not in h.get_text(" ")
    h = BeautifulSoup(_position_path(dict(style="先", corner=12), 18), "html.parser")
    assert "中団想定" in h.get_text(" ")
    assert "差あり" in h.get_text(" ")


def test_missing_corner_and_ability_do_not_invent_values():
    cells = dict(style="差", corner=None, ability_rank=None)
    style = BeautifulSoup(_position_path(cells, 18), "html.parser")
    assert "4角未取得" in style.get_text(" ")
    assert "差あり" not in style.get_text(" ")
    corner = BeautifulSoup(_cell(item(2), cells, "corner", 18), "html.parser")
    assert "未取得" in corner.get_text(" ")
    assert "能力順位 未取得" in corner.get_text(" ")
    assert "None位" not in corner.get_text(" ")


def test_normal_table_keeps_source_values_and_existing_column_count():
    view = [item(i, style=("先" if i == 6 else "差"), corner=i,
                 ability_rank=i) for i in range(1, 19)]
    view[5]["corner"] = 15
    previous = deepcopy(view)
    before = records(view)
    html = BeautifulSoup(lineup_html(view), "html.parser")
    assert len(html.select("tr[data-horse]")) == 18
    assert len(html.select("thead th")) == len([s for s in columns(view) if not s.get("table_hidden")])
    assert html.select_one('[data-column="style"] .column-label').text == "序盤傾向→4角"
    target = html.select_one('tr[data-horse="6"]')
    assert "15番手" in target.select_one(".col-corner").get_text(" ")
    assert "能力6位" in target.select_one(".col-corner").get_text(" ")
    assert "先行型" in target.select_one(".col-style").get_text(" ")
    assert records(view) == before
    assert view == previous
