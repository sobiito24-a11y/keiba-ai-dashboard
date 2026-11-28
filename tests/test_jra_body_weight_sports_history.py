"""JRA paired weight display: Sportsnavi career history regression."""
from copy import deepcopy

import pytest

from core import jra_body_weight_sports_history as sports
from core import jra_body_weight_history as history

RACE = {"race_id": "202605050711", "mode": "jra", "horses": [
    {"horse_no": 2, "name": "レッドシュヴェルト"},
    {"horse_no": 3, "name": "アドマイヤクワッズ"},
]}
INFO = {"race_date": "2026-11-28", "racecourse": "東京", "start_time": "15:25"}
CARD = "https://sports.yahoo.co.jp/keiba/race/denma/2605050711"
IDS = {2: "2020103517", 3: "2023105311"}


def card_html(name_override=None, wrong_date=False):
    day = "27" if wrong_date else "28"
    rows = []
    for no, name in ((2, "レッドシュヴェルト"), (3, "アドマイヤクワッズ")):
        if name_override and no == 3:
            name = name_override
        rows.append(
            "<tr><td>1</td><td>" + str(no) + "</td>"
            "<td><a href='https://sports.yahoo.co.jp/keiba/directory/horse/"
            + IDS[no] + "/'>" + name + "</a><p>牡6/芦毛</p></td>"
            "<td>騎手</td><td>調教師</td><td>血統</td><td>478(0)</td><td>人気</td></tr>"
        )
    return (
        "<html><head><title>東京11R</title></head><body>"
        f"<p>11R</p><p>2026年11月{day}日（土）</p><p>5回東京7日</p>"
        "<table><thead><tr><th>枠番</th><th>馬番</th>"
        "<th>馬名<p>性齢/毛色</p></th><th>騎手名</th><th>調教師</th>"
        "<th>血統</th><th>馬体重</th><th>人気(オッズ)</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></body></html>"
    )


def profile_html(name, runs):
    rows = "".join(
        f"<tr><td>{date}</td><td>レース名</td>"
        f"<td>{finish}</td><td>2</td><td>{wt}</td></tr>"
        for date, finish, wt in runs
    )
    return (
        "<html><body><h2><ruby>" + name + "</ruby></h2>"
        "<table><thead><tr><th>連対時の馬体重</th><th>連対時の斤量</th>"
        "</tr></thead><tbody><tr><td>450kg 〜 476kg</td>"
        "<td>55.0kg</td></tr></tbody></table>"
        "<table><thead><tr><th>日付</th><th>レース</th><th>着順</th>"
        "<th>馬番</th><th>馬体重</th></tr></thead><tbody>"
        + rows + "</tbody></table></body></html>"
    )


RUNS = {
    IDS[2]: profile_html("レッドシュヴェルト", [
        ("2026/09/27", "3", "478(0)"),
        ("2026/05/02", "11", "476(+4)"),
        ("2025/10/04", "1", "468(-10)"),
        ("2025/04/27", "2", "472(+2)"),
        ("2024/06/01", "1", "468(-6)"),
        ("2024/01/14", "2", "476(+14)"),
        ("2023/05/20", "1", "450(-12)"),
        ("2026/11/28", "1", "700(+1)"),
    ]),
    IDS[3]: profile_html("アドマイヤクワッズ", [
        ("2026/10/04", "17", "478(0)"),
        ("2026/05/10", "3", "478(-4)"),
        ("2025/11/15", "1", "478(+6)"),
        ("2025/10/18", "1", "472(0)"),
    ]),
}


def test_sports_racecard_maps_horse_ids_not_order():
    ids = sports.parse_racecard_ids(card_html(), CARD, RACE, INFO)
    assert ids == {
        2: ("レッドシュヴェルト", IDS[2]),
        3: ("アドマイヤクワッズ", IDS[3]),
    }


def test_badge_before_horse_name_does_not_hide_verified_profile_id():
    page = card_html().replace(
        "<td><a href='https://sports.yahoo.co.jp/keiba/directory/horse/",
        "<td><span class='badge'></span><a href='https://sports.yahoo.co.jp/keiba/directory/horse/")
    ids = sports.parse_racecard_ids(page, CARD, RACE, INFO)
    assert ids[2] == ("レッドシュヴェルト", IDS[2])
    assert ids[3] == ("アドマイヤクワッズ", IDS[3])


def test_wrong_day_name_or_race_refused():
    with pytest.raises(ValueError):
        sports.parse_racecard_ids(card_html(wrong_date=True), CARD, RACE, INFO)
    with pytest.raises(ValueError):
        sports.parse_racecard_ids(card_html(name_override="別馬"), CARD, RACE, INFO)
    with pytest.raises(ValueError):
        sports.parse_racecard_ids(card_html(), CARD.replace("050711", "050712"), RACE, INFO)


def test_sports_full_career_as_of_day_not_todays_outcome():
    r = sports.parse_profile(
        RUNS[IDS[2]], "https://sports.yahoo.co.jp/keiba/directory/horse/"+IDS[2],
        expected_horse_id=IDS[2], expected_name="レッドシュヴェルト",
        race_day="20261128")
    assert (r["paired_min_kg"], r["paired_max_kg"]) == (450, 476)
    assert r["paired_count"] == 5
    assert r["known_starts"] == 7
    assert r["paired_source"] == "sportsnavi"
    with pytest.raises(ValueError):
        sports.parse_profile(
            RUNS[IDS[2]], "https://sports.yahoo.co.jp/keiba/directory/horse/"+IDS[2],
            expected_horse_id=IDS[2], expected_name="別馬", race_day="20261128")


def test_sports_lookup_populates_verified_ranges_without_touching_current():
    prior = [
        dict(horse_no=2, name="レッドシュヴェルト", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None),
        dict(horse_no=3, name="アドマイヤクワッズ", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None),
    ]
    original = deepcopy(prior)
    calls = []

    class Response:
        status_code = 200
        def __init__(self, html):
            self.content = html.encode("utf-8")

    def get(url, **kwargs):
        calls.append(url)
        if url == CARD:
            return Response(card_html())
        horse_id = url.strip("/").rsplit("/", 1)[-1]
        return Response(RUNS[horse_id])

    cache = {}
    result, n = sports.enrich(prior, RACE, INFO, get=get, cache=cache, max_workers=1)
    assert n == 2
    assert prior == original
    assert [(r["paired_min_kg"], r["paired_max_kg"]) for r in result] == [
        (450, 476), (472, 478)]
    assert [(r["current_kg"], r["change_kg"]) for r in result] == [(478, 0), (478, 0)]
    assert len(calls) == 3
    calls.clear()
    again, n_again = sports.enrich(prior, RACE, INFO, get=get, cache=cache)
    assert n_again == 2 and again == result
    assert len(calls) == 1


def test_jra_history_prefers_sports_and_does_not_request_netkeiba_when_complete():
    class Response:
        status_code = 200
        def __init__(self, html):
            self.content = html.encode("utf-8")

    def get(url, **kwargs):
        if url == CARD:
            return Response(card_html())
        horse_id = url.strip("/").rsplit("/", 1)[-1]
        return Response(RUNS[horse_id])

    original = [
        dict(horse_no=2, name="レッドシュヴェルト", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None),
        dict(horse_no=3, name="アドマイヤクワッズ", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None),
    ]
    updated, checked = history.enrich(original, RACE, INFO, get=get, cache={}, max_workers=1)
    assert checked == 2
    assert updated[0]["paired_source"] == "sportsnavi"
    assert updated[1]["paired_min_kg"] == 472
