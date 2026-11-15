"""Regression from 2026-11-15 frozen NAR 2yo classes (8 mistaken B1).

The legacy parser must not take a B1 class belonging to an unrelated past
race, sidebar, or other horse when current conditions explicitly say 2歳.
No old .keiba record is rewritten.
"""
import pytest
from bs4 import BeautifulSoup

from core.jra_notebook_logic import (
    parse_current_race_info, race_class_info_from_soup,
)


@pytest.mark.parametrize("name,conditions", [
    ("2歳ー7組", "サラ系２歳 2歳 8頭"),
    ("2歳ー6組", "サラ系２歳 2歳 8頭"),
    ("なりきり同好会賞(2歳)", "サラ系２歳 2歳 7頭"),
    ("2歳5", "サラ系２歳 2歳 9頭"),
    ("くーたんお誕生日記念(2歳)", "サラ系２歳 2歳 9頭"),
    ("プリムラ賞(2歳)", "サラ系２歳 2歳 11頭"),
    ("2歳ー5", "サラ系２歳 2歳 8頭"),
    ("2歳ー4", "サラ系２歳 2歳 10頭"),
])
def test_current_nar_2yo_class_not_unrelated_b1(name, conditions):
    html = (
        '<div class="RaceName">' + name + '</div>'
        '<div class="RaceData01">16:30発走 / ダ1400m (右)</div>'
        '<div class="RaceData02">' + conditions + '</div>'
        '<div class="PastRace"><div class="RaceName">B1 3歳以上</div></div>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert race_class_info_from_soup(soup, name, conditions) == (None, "2歳")
    info = parse_current_race_info(html)
    assert info["class_label"] == "2歳"
    assert info["class_rank"] is None


def test_explicit_open_grade_and_jra_wins_take_priority():
    for name, cond, expected in [
        ("2歳未勝利", "サラ系２歳 未勝利", (20, "未勝利")),
        ("2歳新馬", "サラ系２歳 新馬", (10, "新馬")),
        ("黄菊賞", "サラ系２歳 1勝クラス", (30, "1勝")),
        ("福島2歳S", "サラ系２歳 オープン", (60, "OP")),
        ("2歳G1", "サラ系２歳 オープン", (90, "G1")),
        ("一般B1", "サラ系３歳以上 B1", (55, "B1")),
        ("一般C1", "サラ系３歳以上 C1", (40, "C1")),
    ]:
        icon = '<span class="Icon_GradeType1"></span>' if name == "2歳G1" else ""
        html = (f'<div class="RaceName">{name}{icon}</div>'
                f'<div class="RaceData02">{cond}</div>')
        assert race_class_info_from_soup(BeautifulSoup(html, "html.parser")) == expected


def test_three_year_old_restricted_does_not_inherit_unrelated_b1():
    soup = BeautifulSoup(
        '<div class="RaceName">3歳7組</div>'
        '<div class="RaceData02">サラ系3歳 3歳</div>'
        '<div class="PastRace"><div class="RaceName">B1</div></div>',
        "html.parser",
    )
    assert race_class_info_from_soup(soup) == (None, "3歳")
