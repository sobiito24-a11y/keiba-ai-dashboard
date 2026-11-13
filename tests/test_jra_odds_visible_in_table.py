"""End-to-end: published Yuma HTML -> verified quote -> overlay -> actual JRA main table.

This exercises the normal A table (not the old B-only card) and keeps source
prediction, saved marks, and all archived input rows untouched.
"""
from copy import deepcopy
import json
from bs4 import BeautifulSoup

from core import race_odds
from core.game_race_ui import document
from core.race_explorer_columns import records
from core.jra_yuma_odds import parse_yuma_pages
from tests.test_jra_yuma_odds import ID, INFO, NOW, html
from tests.test_race_explorer_ui import field


def test_historical_odds_reach_actual_table_not_just_import_preview():
    _rows, _records, info, view = field("jra",14)
    for horse, expected in zip(view, ID["horses"]):
        assert int(horse["no"]) == expected["horse_no"]
        horse["name"] = expected["name"]
    initial=deepcopy(view)
    quote=parse_yuma_pages({"tan":html("tan"),"fuk":html("fuk")}, ID, INFO, now=NOW)
    shown=race_odds.overlay(view,quote,"過去掲載単複")
    parsed=records(shown)
    assert parsed["2"]["odds"] == 2.7
    assert parsed["2"]["place_odds"] == 1.2
    assert parsed["2"]["place_odds_high"] == 1.5
    page=BeautifulSoup(document(shown,info["race_id"]),"html.parser")
    table=page.select_one("#lineup-workspace .explorer-table")
    assert table is not None
    headers={th.get("data-column"):th.get_text(" ",strip=True) for th in table.select("thead th")}
    assert "odds" in headers and "place_odds" not in headers
    assert "オッズ単複" in headers["odds"]
    horse2=table.select_one('tbody tr[data-horse="2"]')
    assert "2.7倍" in horse2.select_one(".col-odds").get_text(" ",strip=True)
    assert "1.2〜1.5倍" in horse2.select_one(".col-odds").get_text(" ",strip=True)
    assert len(table.select("tbody tr[data-horse]"))==14
    source_payload=json.loads(page.select_one("#race-data").string)
    second=next(h for h in source_payload["horses"] if str(h["no"])=="2")
    assert second["values"]["place_odds"]==1.2
    assert second["values"]["place_odds_high"]==1.5
    assert "複勝 14/14頭" in page.get_text(" ", strip=True)
    assert view==initial
    assert all(a["score"]==b["score"] and a["rank"]==b["rank"]
               and a["mark"]==b["mark"] for a,b in zip(initial,shown))


def test_win_only_does_not_create_false_place_price_in_main_table():
    _rows, _records, info, view=field("jra",14)
    for horse, expected in zip(view, ID["horses"]):
        horse["name"]=expected["name"]
    q=parse_yuma_pages({"tan":html("tan")},ID,INFO,now=NOW)
    shown=race_odds.overlay(view,q,"過去単勝だけ")
    soup=BeautifulSoup(document(shown,info["race_id"]),"html.parser")
    horse2=soup.select_one('#lineup-workspace tbody tr[data-horse="2"]')
    assert "2.7倍" in horse2.select_one(".col-odds").text
    assert "複 未取得" in horse2.select_one(".col-odds").text
    assert "複勝 0/14頭" in soup.get_text(" ",strip=True)
