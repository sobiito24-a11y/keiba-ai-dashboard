from copy import deepcopy
from types import SimpleNamespace

from bs4 import BeautifulSoup

from core.game_race_ui import race_header
from core.race_tendency import assess, as_html


def field(scores, *, missing=None, retro=False):
    missing = set(missing or ())
    return [
        dict(no=str(i), mode="jra",
             mark="◎" if i == 1 else "—",
             odds="100.0", actual_finish=1,
             research_sabcd_weight_class={
                 "grade": ("S" if p >= .7 else "A" if p >= .5 else
                           "B" if p >= .3 else "C" if p >= .15 else "D"),
                 "score": None if i in missing else p,
                 "retro": retro,
             })
        for i, p in enumerate(scores, start=1)
    ]


def test_s_and_one_runner_do_not_automatically_mean_trusted_axis():
    # Two good model scores close together: not an "axis" classification.
    data = assess(field([.81, .77, .48, .2, .1]))
    assert data["label"] == "上位拮抗"
    assert data["tone"] == "mixed"


def test_axis_requires_both_high_top_score_and_clear_gap():
    data = assess(field([.83, .52, .40, .23, .08]))
    assert data["label"] == "軸候補が浮上"
    assert "0.830 / 0.520 / 0.400" in data["detail"]


def test_low_and_close_top_scores_mean_mixed_but_not_always():
    assert assess(field([.46, .43, .40, .22, .08]))["label"] == "混戦傾向"
    assert assess(field([.45, .22, .12, .07, .04]))["label"] == "軸候補不在"
    assert assess(field([.62, .44, .37, .22, .1]))["label"] == "軸は要比較"


def test_missing_or_duplicate_inputs_cause_hold():
    assert assess(field([.9, .6, .4, .3]))["label"] == "判定保留"
    assert assess(field([.9, .6, .4, .3, .2], missing={4}))["label"] == "判定保留"
    horses = field([.9, .6, .4, .3, .2])
    horses[2]["no"] = horses[0]["no"]
    assert assess(horses)["label"] == "判定保留"
    assert assess([])["label"] == "判定保留"


def test_race_grade_does_not_read_odds_outcomes_or_change_view():
    horses = field([.81, .46, .44, .23, .15])
    saved = deepcopy(horses)
    baseline = assess(horses)
    for h in horses:
        h["odds"] = "0.1"
        h["actual_finish"] = 50
        h["mark"] = "×"
    assert assess(horses) == baseline
    assert saved[0]["odds"] == "100.0"


def test_header_shows_single_label_under_name_and_marks_retrospective():
    result = SimpleNamespace(
        race_info=dict(race_number=11, race_date="2026-11-08", venue="東京",
                       surface="芝", distance=2500, netkeiba_pace="S",
                       post_time="15:30"),
        race_name="アルゼンチン共和国杯", race_mode="jra", overall_table=None,
    )
    horses = field([.45, .43, .38, .2, .12], retro=True)
    page = BeautifulSoup(race_header(result, horses), "html.parser")
    title = page.select_one(".game-race-header h2")
    tag = page.select_one(".game-race-tendency")
    assert title.text == "アルゼンチン共和国杯"
    assert tag is not None and tag.select_one("strong").text == "混戦傾向"
    assert "後日算出" in tag.text
    assert page.select_one(".game-race-meta") is not None
    assert page.select_one("h2").find_next_sibling()["class"] == ["game-race-tendency"]
    assert BeautifulSoup(race_header(result), "html.parser").select_one(".game-race-tendency") is None


def test_html_does_not_insert_untrusted_marks_or_tags():
    horses = field([.83, .48, .4, .2, .1])
    horses[0]["research_sabcd_weight_class"]["reason"] = "<img src=x onerror=alert(1)>"
    assert "<img" not in as_html(horses)
