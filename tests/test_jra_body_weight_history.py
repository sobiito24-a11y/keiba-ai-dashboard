"""JRA all-career paired weight regression: Tokyo11 on 2026-11-28."""
from copy import deepcopy

import pytest

from core import jra_body_weight_history as history


RACE = {"race_id": "202605050711", "mode": "jra", "horses": [
    {"horse_no": 2, "name": "レッドシュヴェルト"},
    {"horse_no": 3, "name": "アドマイヤクワッズ"},
]}
INFO = {"race_date": "2026-11-28", "racecourse": "東京", "start_time": "15:25"}
CARD = "https://race.netkeiba.com/race/shutuba.html?race_id=202605050711"
IDS = {2: "2020103517", 3: "2023105311"}


def racecard(*, bad_name=False, cross_host=False):
    rows = []
    for no, name in [(2, "レッドシュヴェルト"), (3, "アドマイヤクワッズ")]:
        link = (f"https://{'example.org' if cross_host else 'db.netkeiba.com'}/"
                f"horse/{IDS[no]}/")
        if bad_name and no == 3:
            name = "別の馬"
        rows.append(
            f"<tr><td>1</td><td>{no}</td><td>-</td>"
            f"<td><p><a href='{link}'>{name}</a></p></td>"
            "<td>牡</td></tr>")
    return (
        "<html><head><title>東京11R 2026年11月28日</title></head>"
        "<body><p>5回 東京 7日目</p><h1>キャピタルS</h1>"
        "<table><thead><tr><th>枠</th><th><p>馬<br/>番</p></th>"
        "<th>印</th><th>馬名</th><th>性齢</th></tr></thead>"
        + "".join(rows) + "</table></body></html>")


def career(name, rows):
    """Minimal netkeiba result table with date, finish and bodyweight."""
    return ("<html><body><h1>" + name + "</h1>"
            "<table><thead><tr><th>日付</th><th>着<br/>順</th>"
            "<th>馬体重</th><th>レース</th></tr></thead><tbody>"
            + "".join(
                f"<tr><td>{date}</td><td>{finish}</td><td>{kg}</td><td>レース</td></tr>"
                for date, finish, kg in rows)
            + "</tbody></table></body></html>")


OLD_RED = [
    ("2026/09/27", "3", "478(0)"),
    ("2026/08/22", "10", "478(+4)"),
    ("2026/06/14", "6", "474(-2)"),
    ("2026/05/02", "11", "476(+4)"),
    ("2025/10/04", "1", "468(-10)"),
    ("2025/04/27", "2", "472(+2)"),
    ("2023/05/20", "1", "450(-12)"),
    ("2024/01/14", "2", "476(+14)"),
]
OLD_QUADS = [
    ("2026/10/04", "17", "478(0)"),
    ("2026/05/10", "3", "478(-4)"),
    ("2026/04/19", "15", "482(+2)"),
    ("2026/03/08", "3", "480(+2)"),
    ("2025/11/15", "1", "478(+6)"),
    ("2025/10/18", "1", "472(0)"),
]
CAREERS = {
    IDS[2]: career("レッドシュヴェルト", OLD_RED),
    IDS[3]: career("アドマイヤクワッズ", OLD_QUADS),
}


def test_racecard_associates_ids_with_correct_number_and_exact_name():
    found = history.racecard_ids(racecard(), CARD, RACE, INFO)
    assert found == {
        2: ("レッドシュヴェルト", IDS[2]),
        3: ("アドマイヤクワッズ", IDS[3]),
    }


def test_no_cross_host_or_wrong_racehorse_associations():
    with pytest.raises(ValueError, match="馬名"):
        history.racecard_ids(racecard(bad_name=True), CARD, RACE, INFO)
    with pytest.raises(ValueError):
        history.racecard_ids(racecard(), CARD.replace("050711", "050712"), RACE, INFO)
    assert history.racecard_ids(racecard(cross_host=True), CARD, RACE, INFO) == {}


def test_career_result_looks_beyond_four_most_recent_and_excludes_today():
    page = CAREERS[IDS[2]].replace(
        "</tbody>", "<tr><td>2026/11/28</td><td>1</td>"
        "<td>700(+1)</td><td>当日</td></tr></tbody>")
    record = history.career_pair_weights(
        page, f"https://db.netkeiba.com/horse/result/{IDS[2]}/",
        expected_horse_id=IDS[2], expected_name="レッドシュヴェルト",
        race_day="20261128")
    assert record["paired_min_kg"] == 450
    assert record["paired_max_kg"] == 476
    assert record["paired_count"] == 4
    assert record["known_starts"] == len(OLD_RED)
    assert record["paired_scope"] == "career"


@pytest.mark.parametrize("incorrect", [
    ("https://db.netkeiba.com/horse/result/2020109999/", "レッドシュヴェルト"),
    ("https://db.netkeiba.com/horse/result/2020103517/", "別の馬"),
    ("https://evil.example/horse/result/2020103517/", "レッドシュヴェルト"),
])
def test_wrong_horse_or_source_never_populates_paired_range(incorrect):
    url, name = incorrect
    with pytest.raises(ValueError):
        history.career_pair_weights(
            CAREERS[IDS[2]], url, expected_horse_id=IDS[2],
            expected_name=name, race_day="20261128")


def test_enrich_completes_all_career_ranges_without_changing_current_weight():
    old = [
        dict(horse_no=2, name="レッドシュヴェルト", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None,
             paired_count=0),
        dict(horse_no=3, name="アドマイヤクワッズ", current_kg=478,
             change_kg=0, paired_min_kg=None, paired_max_kg=None,
             paired_count=0),
    ]
    saved = deepcopy(old)
    cache = {}
    calls = []

    class Response:
        status_code = 200
        def __init__(self, html):
            self.content = html.encode("utf-8")

    def get(url, **kwargs):
        calls.append(url)
        if url == CARD:
            return Response(racecard())
        horse_id = url.split("/horse/result/")[-1].strip("/")
        return Response(CAREERS[horse_id])

    enriched, checked = history.enrich(
        old, RACE, INFO, get=get, cache=cache, max_workers=1)
    assert checked == 2
    assert old == saved
    assert len(calls) == 4  # Sportsnavi first, then netkeiba fallback
    assert enriched[0]["current_kg"] == 478
    assert enriched[0]["change_kg"] == 0
    assert (enriched[0]["paired_min_kg"], enriched[0]["paired_max_kg"]) == (450, 476)
    assert (enriched[1]["paired_min_kg"], enriched[1]["paired_max_kg"]) == (472, 478)
    assert enriched[0]["paired_scope"] == "career"
    calls.clear()
    repeat, rechecked = history.enrich(
        old, RACE, INFO, get=get, cache=cache, max_workers=1)
    assert rechecked == 2
    assert len(calls) == 2  # both cards rechecked; netkeiba histories cached
    assert repeat == enriched


def test_a_blocked_horse_history_preserves_existing_official_paired_weights():
    old = [dict(horse_no=2, name="レッドシュヴェルト", current_kg=478,
                change_kg=0, paired_min_kg=468, paired_max_kg=472,
                paired_count=2),
           dict(horse_no=3, name="アドマイヤクワッズ", current_kg=478,
                change_kg=0, paired_min_kg=None, paired_max_kg=None,
                paired_count=0)]
    class Response:
        status_code = 200
        def __init__(self, data):
            self.content = data.encode("utf-8")
    def get(url, **kwargs):
        if url == CARD:
            return Response(racecard())
        raise ConnectionError("blocked")
    before = deepcopy(old)
    # A fully blocked source is now surfaced so the UI can show why the
    # all-career range is missing. Existing JRA values remain unchanged.
    with pytest.raises(ValueError, match="スポーツナビ"):
        history.enrich(old, RACE, INFO, get=get, max_workers=1)
    assert old == before



def test_jra_fetch_once_integrates_career_ranges_and_preserves_live_weight():
    """Complete end-to-end without any external HTTP calls."""
    import asyncio
    from datetime import datetime

    from core import jra_body_weight as bw
    head = "<h1>出馬表2026年11月28日（土曜）5回東京7日 11レース</h1>"
    columns = ["枠", "馬番", "馬名 / 単勝オッズ(人気) 馬体重",
               "性齢", "前走", "前々走", "3走前", "4走前"]
    th = "".join(f"<th>{col}</th>" for col in columns)
    official_rows = "".join(
        f"<tr><td>1</td><td>{no}</td><td>{name}<p>478kg(0)</p></td>"
        "<td>牡</td><td></td><td></td><td></td><td></td></tr>"
        for no, name in [(2, "レッドシュヴェルト"), (3, "アドマイヤクワッズ")])
    official_html = (f"<html>{head}<table><thead><tr>{th}</tr></thead>"
                     f"<tbody>{official_rows}</tbody></table></html>")

    class Response:
        status_code = 200
        def __init__(self, content):
            self.content = content.encode("utf-8")

    urls = []
    def get(url, **kwargs):
        urls.append(url)
        if "jra.go.jp" in url or "jra.jp" in url:
            return Response(official_html)
        if url == CARD:
            return Response(racecard())
        if "/horse/result/" in url:
            horse_id = url.split("/horse/result/")[-1].strip("/")
            return Response(CAREERS[horse_id])
        raise AssertionError("Unexpected source")

    original = deepcopy(RACE)
    observation = asyncio.run(bw.fetch_once(
        RACE, INFO, now=datetime(2026, 11, 28, 15, 18, tzinfo=bw.JST),
        request_get=get, browser_fallback=False, history_cache={}))
    assert observation["current_count"] == 2
    assert observation["paired_career_checked"] == 2
    assert observation["verified_by"] == "http"
    assert [(x["current_kg"], x["change_kg"]) for x in observation["rows"]] == [
        (478, 0), (478, 0)]
    assert [(x["paired_min_kg"], x["paired_max_kg"]) for x in observation["rows"]] == [
        (450, 476), (472, 478)]
    assert len(urls) == 5  # official, Sportsnavi attempt, netkeiba card, two careers
    assert RACE == original
