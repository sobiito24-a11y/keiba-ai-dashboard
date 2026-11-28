"""Public JRA bodyweight fallback tests: never invent missing values."""
from copy import deepcopy
import asyncio
from datetime import datetime

import pytest

from core import jra_body_weight as official
from core import jra_body_weight_alternates as alt


RACE = {"race_id": "202608050707", "mode": "jra", "horses": [
    {"horse_no": 1, "name": "カラペルソナ"},
    {"horse_no": 2, "name": "コスモフィレンツェ"},
]}
INFO = {"race_date": "2026-11-28", "racecourse": "京都", "start_time": "13:25"}


def sports_html(*, wrong_name=False, wrong_date=False, missing=False):
    date = "2026年11月27日" if wrong_date else "2026年11月28日"
    rows = [
        (1, "別の馬" if wrong_name else "カラペルソナ", "446(+6)"),
        (2, "コスモフィレンツェ", "496(+14)"),
    ]
    body = "".join(
        f"<tr><td>1</td><td>{no}</td>"
        f"<td>{name}<p>牝3/黒鹿毛</p></td><td>騎手</td>"
        f"<td>調教師</td><td>血統</td><td><p>{'' if missing else kg}</p></td>"
        "<td>人気</td></tr>" for no, name, kg in rows)
    return (
        "<html><body><p>7R</p><p>" + date + "（土）</p><p>5回京都7日</p>"
        "<table><thead><tr>"
        "<th>枠番</th><th>馬番</th><th>馬名<p>性齢/毛色</p></th>"
        "<th>騎手名</th><th>調教師</th><th>血統</th>"
        "<th>馬体重</th><th>人気(オッズ)</th>"
        "</tr></thead><tbody>" + body + "</tbody></table></body></html>")


def netkeiba_html():
    rows = [
        (1, "カラペルソナ", "446", "+6"),
        (2, "コスモフィレンツェ", "496", "+14"),
    ]
    html_rows = "".join(
        "<tr><td>1</td><td>" + str(no) + "</td><td>印</td>"
        "<td><p>" + name + "</p></td><td>牝3</td><td>54</td>"
        "<td>騎手</td><td>厩舎</td><td>" + kg + "<small>(" + delta + ")</small></td>"
        "</tr>"
        for no, name, kg, delta in rows)
    return (
        "<html><head><title>３歳以上１勝クラス 出馬表 | "
        "2026年11月28日 京都7R レース情報(JRA) - netkeiba</title></head>"
        "<body><p>5回 京都 7日目</p><table><thead><tr>"
        "<th>枠</th><th>馬番</th><th>印</th><th>馬名</th><th>性齢</th>"
        "<th>斤量</th><th>騎手</th><th>厩舎</th><th>馬体重(増減)</th>"
        "</tr></thead>" + html_rows + "</table></body></html>")


def test_both_public_provider_urls_derived_only_from_saved_race():
    assert alt.sources(RACE, INFO) == [
        ("sportsnavi", "https://sports.yahoo.co.jp/keiba/race/denma/2608050707"),
        ("netkeiba", "https://race.netkeiba.com/race/shutuba.html?race_id=202608050707"),
    ]


@pytest.mark.parametrize("provider,html", [
    ("sportsnavi", sports_html()),
    ("netkeiba", netkeiba_html()),
])
def test_current_weight_and_delta_are_preserved_without_paired_history(provider, html):
    url = dict(alt.sources(RACE, INFO))[provider]
    snapshot = deepcopy(RACE)
    rows = alt.parse_card(html, url, provider, RACE, INFO)
    assert len(rows) == 2
    assert [(r["current_kg"], r["change_kg"]) for r in rows] == [(446, 6), (496, 14)]
    assert all(r["paired_min_kg"] is None for r in rows)
    assert all(r["paired_max_kg"] is None for r in rows)
    assert RACE == snapshot


@pytest.mark.parametrize("url,provider,html", [
    ("https://sports.yahoo.co.jp/keiba/race/denma/2608050708", "sportsnavi", sports_html()),
    ("https://sports.yahoo.co.jp/keiba/race/denma/2608050707", "sportsnavi", sports_html(wrong_date=True)),
    ("https://sports.yahoo.co.jp/keiba/race/denma/2608050707", "sportsnavi", sports_html(wrong_name=True)),
    ("https://race.netkeiba.com/race/shutuba.html?race_id=202608050708", "netkeiba", netkeiba_html()),
])
def test_never_take_a_wrong_race_date_or_horse(url, provider, html):
    with pytest.raises(ValueError):
        alt.parse_card(html, url, provider, RACE, INFO)


def test_unpublished_alternate_weight_is_missing_not_prior_result():
    rows = alt.parse_card(
        sports_html(missing=True), alt.sources(RACE, INFO)[0][1], "sportsnavi", RACE, INFO)
    assert len(rows) == 2
    assert all(r["current_kg"] is None for r in rows)
    assert all(r["change_kg"] is None for r in rows)


def test_zero_weight_official_then_sportsnavi_recovers_with_verified_history():
    """A stale official page cannot suppress a fresh alternate; paired history survives."""
    info = dict(INFO)
    identity = dict(RACE)
    # Build an official card with the same two horses and empty current weights,
    # but a saved prior 1st-place at 440 kg for the first horse.
    title = "<h1>出馬表2026年11月28日（土曜）5回京都7日 7レース</h1>"
    th = "".join(f"<th>{h}</th>" for h in (
        "枠", "馬番", "馬名 / 馬体重", "性齢", "前走", "前々走", "3走前", "4走前"))
    tr1 = ("<tr><td>1</td><td>1</td><td>カラペルソナ</td><td>牝3</td>"
           "<td><p>1着</p><p>440kg</p></td><td></td><td></td><td></td></tr>")
    tr2 = ("<tr><td>1</td><td>2</td><td>コスモフィレンツェ</td><td>牡3</td>"
           "<td></td><td></td><td></td><td></td></tr>")
    official_html = (f"<html>{title}<table><thead><tr>{th}</tr></thead>"
                     f"<tbody>{tr1}{tr2}</tbody></table></html>").encode()
    calls = []

    class Response:
        status_code = 200
        def __init__(self, content):
            self.content = content

    def get(url, **kwargs):
        calls.append(url)
        if "jra.go.jp/" in url or "jra.jp/" in url:
            return Response(official_html)
        if "sports.yahoo.co.jp" in url:
            return Response(sports_html().encode("utf-8"))
        raise AssertionError("Netkeiba should not be needed")

    result = asyncio.run(official.fetch_once(
        identity, info, now=datetime(2026, 11, 28, 13, 19, tzinfo=official.JST),
        request_get=get, browser_fallback=False))
    assert len(calls) == 3
    assert result["verified_by"] == "sportsnavi"
    assert result["current_count"] == 2
    assert result["source_url"].startswith("https://sports.yahoo.co.jp/")
    assert result["rows"][0]["current_kg"] == 446
    assert result["rows"][1]["change_kg"] == 14
    assert result["rows"][0]["paired_min_kg"] == 440
    assert result["rows"][1]["paired_min_kg"] is None
