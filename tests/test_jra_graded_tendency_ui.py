"""Historical graded races are displayed as strictly past, auditable notes.

No race score, tier, formal mark, predicted position or odds is changed.
"""
from copy import deepcopy
from types import SimpleNamespace

from core.jra_graded_tendency_ui import tendency, render
from core.game_race_ui import race_header


def test_2026_argentina_uses_only_2023_2025_available_matching_conditions():
    note=tendency("第64回アルゼンチン共和国杯",mode="jra",
                  race_date="2026-11-08",venue="東京",distance="芝2500m",surface="芝")
    assert note is not None
    assert note["n"]==3 and note["years"]==[2023,2024,2025]
    assert note["winner_10x"]==2 and note["winner_20x"]==2
    assert note["missing_years"]==[2021,2022]
    assert note["scoring_effect"]==0 and note["rank_effect"]==0
    assert note["verified_corner"] is False and note["verified_quinella"] is False
    html=render("アルゼンチン共和国杯",mode="jra",race_date="2026-11-08",
                venue="東京",distance="2500m",surface="芝")
    assert "研究／ランク未反映" in html
    assert "4角・脚質・馬連/ワイドの荒れは未検証" in html
    assert "単勝10倍以上の勝ち馬 2／3開催" in html


def test_older_saved_race_does_not_see_later_winner_outcomes():
    note=tendency("アルゼンチン共和国杯",mode="jra",
                  race_date="2024-11-03",venue="東京",distance="2500",surface="芝")
    assert note is not None
    assert note["n"]==1 and note["years"]==[2023]
    assert note["winner_10x"]==0 and note["winner_20x"]==0


def test_not_grade_or_nar_or_wrong_course_returns_nothing():
    kwargs=dict(race_date="2026-11-08",venue="東京",distance="芝2500m",surface="芝")
    assert tendency("アルゼンチン共和国杯",mode="nar",**kwargs) is None
    assert tendency("C11組",mode="jra",**kwargs) is None
    assert tendency("アルゼンチン共和国杯",mode="jra",**dict(kwargs,venue="京都")) is None
    assert tendency("アルゼンチン共和国杯",mode="jra",**dict(kwargs,distance="1800")) is None
    assert tendency("アルゼンチン共和国杯",mode="jra",**dict(kwargs,surface="ダート")) is None


def test_readonly_header_adds_note_only_for_jra_and_does_not_mutate():
    info=dict(race_date="2026-11-08",racecourse="東京",race_number=11,
              distance_label="芝2500m",surface="芝",post_time="15:30",pace_prediction="S")
    result=SimpleNamespace(race_name="アルゼンチン共和国杯",race_info=info,
                           race_mode="jra",overall_table=None)
    before=deepcopy(info)
    html=race_header(result)
    assert "JRA重賞・過去の参考傾向" in html
    assert info==before
    result.race_mode="nar"
    assert "JRA重賞・過去の参考傾向" not in race_header(result)
