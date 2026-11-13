"""Combined regressions for the outstanding JRA odds, display, and grade audit.

This is an offline integration test, not proof that Streamlit Cloud can
connect to public odds providers. No changes to model predictions are allowed.
"""
import json
from copy import deepcopy
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from core import race_odds
from core.game_race_ui import document
from core.jra_graded_tendency_ui import tendency
from core.jra_sportsnavi_odds import parse_sportsnavi_html
from core.race_explorer_columns import columns, records
from tests.test_jra_sportsnavi_odds import ID, INFO, NOW, odds_page
from tests.test_race_explorer_ui import field

ROOT = Path(__file__).resolve().parents[1]


def test_sportsnavi_18_prices_reach_actual_jra_main_table_without_touching_ai():
    _rows, _records, info, view = field("jra", 18)
    assert len(view) == len(ID["horses"]) == 18
    for horse, expected in zip(view, ID["horses"]):
        assert int(horse["no"]) == expected["horse_no"]
        horse["name"] = expected["name"]
    before = deepcopy(view)
    quote = parse_sportsnavi_html(odds_page(), ID, INFO, now=NOW)
    assert quote["coverage"]["win"]["count"] == 18
    assert quote["coverage"]["place"]["count"] == 18
    copied = race_odds.overlay(view, quote, "過去確定オッズ")
    payload = records(copied)
    assert payload["9"]["odds"] == 5.7
    assert (payload["9"]["place_odds"], payload["9"]["place_odds_high"]) == (1.8, 2.3)
    doc = BeautifulSoup(document(copied, info["race_id"]), "html.parser")
    rows = doc.select("#lineup-workspace tbody tr[data-horse]")
    assert len(rows) == 18
    nine = doc.select_one('#lineup-workspace tbody tr[data-horse="9"]')
    assert nine is not None
    assert "単 5.7倍" in nine.select_one(".col-odds").get_text(" ", strip=True)
    assert "複 1.8〜2.3倍" in nine.select_one(".col-odds").get_text(" ", strip=True)
    assert view == before
    assert all((a["rank"], a["mark"], a["score"]) ==
               (b["rank"], b["mark"], b["score"]) for a, b in zip(copied, before))


@pytest.mark.parametrize("mode", ["jra", "nar"])
def test_workout_is_adjacent_to_saved_running_style_only_for_jra(mode):
    _rows, _records, info, view = field(mode, 4)
    if mode == "jra":
        for horse, grade in zip(view, "ABCD"):
            horse["explorer_facts"]["training"] = grade
    before = deepcopy(view)
    visible = [s["key"] for s in columns(view) if not s.get("table_hidden")]
    doc = BeautifulSoup(document(view, info["race_id"]), "html.parser")
    headings = [x["data-column"] for x in doc.select("#lineup-workspace th[data-column]")]
    assert headings == visible
    assert ("training" in headings) == (mode == "jra")
    if mode == "jra":
        assert headings.index("training") == headings.index("style") + 1
        for horse, grade in zip(view, "ABCD"):
            row = doc.select_one(f'#lineup-workspace tr[data-horse="{horse["no"]}"]')
            assert row is not None
            assert grade in row.select_one(".col-training").get_text(" ", strip=True)
    else:
        assert not doc.select(".col-training")
    assert view == before


def test_graded_research_never_claims_full_five_years_from_partial_source():
    source = json.loads((ROOT / "data/jra_graded_trends_2021_2025.json").read_text(encoding="utf-8"))
    assert source["all_graded_calendar_events"] == 695
    assert source["matched_graded_events"] == 293
    assert source["year_matched_counts"]["2021"] == 0
    assert source["year_matched_counts"]["2022"] == 0
    assert source["has_corner_positions"] is False
    assert source["has_quinella_payouts"] is False
    assert source["brier_2025_winner10"]["n"] == 115


def test_pre_race_graded_note_does_not_look_at_its_own_year():
    earlier = tendency("アルゼンチン共和国杯", mode="jra",
                       race_date="2024-11-03", venue="東京",
                       distance="芝2500m", surface="芝")
    later = tendency("アルゼンチン共和国杯", mode="jra",
                     race_date="2026-11-08", venue="東京",
                     distance="芝2500m", surface="芝")
    assert earlier["years"] == [2021, 2022, 2023]
    assert later["years"] == [2021, 2022, 2023, 2024, 2025]
    assert earlier["scoring_effect"] == later["scoring_effect"] == 0
    assert earlier["rank_effect"] == later["rank_effect"] == 0


def test_jra_graded_notes_do_not_apply_to_non_grade_or_nar():
    kwargs = dict(race_date="2026-11-08", venue="東京", distance="芝2500m", surface="芝")
    assert tendency("アルゼンチン共和国杯", mode="nar", **kwargs) is None
    assert tendency("3勝クラス", mode="jra", **kwargs) is None
