"""Regression: track-course letters A/B/C must never become a JRA race class.

Examples below are pre-race headers from saved 2026-11-07/08/14 JRA
snapshots that were incorrectly stored as legacy A級/B級, despite
explicit JRA classes in RaceData02.
"""
import pytest
from bs4 import BeautifulSoup

from core.jra_notebook_logic import (
    race_class_info_from_soup,
    parse_current_race_info,
)


@pytest.mark.parametrize(
    "name,track,conditions,expected",
    [
        ("木津川特別", "芝1600m 右 外 B", "サラ系3歳以上 2勝クラス", (40, "2勝")),
        ("ノベンバーS", "芝2000m 左 B", "サラ系3歳以上 3勝クラス", (50, "3勝")),
        ("三春駒特別", "芝2000m 右 A", "サラ系3歳以上 1勝クラス", (30, "1勝")),
        ("飯坂温泉特別", "芝1200m 右 A", "サラ系3歳以上 2勝クラス", (40, "2勝")),
        ("キビタキS", "芝1200m 右 A", "サラ系3歳以上 3勝クラス", (50, "3勝")),
        ("清水S", "芝1600m 右 外 B", "サラ系3歳以上 3勝クラス", (50, "3勝")),
        ("百日草特別", "芝2000m 左 B", "サラ系2歳 1勝クラス", (30, "1勝")),
        ("二本松特別", "芝1800m 右 A", "サラ系3歳以上 1勝クラス", (30, "1勝")),
        ("みちのくS", "芝1200m 右 A", "サラ系3歳以上 オープン", (60, "OP")),
        ("奥多摩S", "芝1400m 左 B", "サラ系3歳以上 3勝クラス", (50, "3勝")),
        ("土湯温泉特別", "芝1800m 右 A", "サラ系3歳以上 1勝クラス", (30, "1勝")),
    ],
)
def test_saved_jra_course_a_b_c_is_not_local_class(name, track, conditions, expected):
    html = (
        '<div class="RaceName">' + name + '</div>'
        '<div class="RaceData01">14:05発走 / ' + track + '</div>'
        '<div class="RaceData02">3回 福島 3日目 ' + conditions + '</div>'
    )
    soup = BeautifulSoup(html, "html.parser")
    assert race_class_info_from_soup(soup) == expected
    info = parse_current_race_info(html)
    assert (info["class_rank"], info["class_label"]) == expected


@pytest.mark.parametrize("letter", ["A", "B", "C"])
def test_course_letter_without_class_stays_unknown(letter):
    soup = BeautifulSoup(
        '<div class="RaceName">特別競走</div>'
        '<div class="RaceData01">芝1800m 右 ' + letter + '</div>',
        "html.parser",
    )
    assert race_class_info_from_soup(soup) == (None, "")


@pytest.mark.parametrize(
    "local_class,expected",
    [("A級", (64, "A級")), ("B級", (50, "B級")),
     ("C級", (30, "C級")), ("A1", (70, "A1")), ("B2", (50, "B2"))],
)
def test_explicit_local_classes_still_parse(local_class, expected):
    soup = BeautifulSoup(
        '<div class="RaceName">' + local_class + '</div>', "html.parser",
    )
    assert race_class_info_from_soup(soup) == expected


def test_graded_venue_icon_still_takes_priority():
    soup = BeautifulSoup(
        '<div class="RaceName"><span class="Icon_GradeType1"></span>'
        '重賞レース</div>'
        '<div class="RaceData01">芝2000m 左 B</div>'
        '<div class="RaceData02">サラ系3歳以上 オープン</div>',
        "html.parser",
    )
    assert race_class_info_from_soup(soup) == (90, "G1")


def test_fallback_conditions_from_current_race_header():
    soup = BeautifulSoup('<div class="RaceData01">芝1600m 右 B</div>', "html.parser")
    assert race_class_info_from_soup(
        soup, "芝1600m 右 B", "サラ系3歳以上 2勝クラス"
    ) == (40, "2勝")
