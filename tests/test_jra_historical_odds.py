"""Historical single/place import; all tests use local representative HTML."""
from datetime import datetime

import pytest

from core import race_odds
from core.jra_historical_odds import parse_keibalab_html, fetch_once

ID = dict(race_id="202608050201", mode="jra",
          horses=[dict(horse_no=1, name="シュライアハフト"),
                  dict(horse_no=2, name="テリオスベラ")])
INFO = dict(race_date="2026-11-08")
CLOCK = datetime(2026, 11, 13, 8, 30, tzinfo=race_odds.JST)


def page(rows=None, *, title="単勝・複勝オッズ〖2026年11月8日京都1R〗",
         meeting="5回京都2日目", stamp="※2026年11月8日10時11分現在のオッズです。"):
    rows = rows or [
        "<tr><td>1</td><td>1</td><td>シュライアハフト</td><td>11.9</td><td>2.6 - 4.2</td><td>6</td></tr>",
        "<tr><td>2</td><td>2</td><td>テリオスベラ</td><td>2.7</td><td>1.2</td><td>-</td><td>1.5</td><td>1</td></tr>",
    ]
    return (f"<html><head><title>{title}</title></head><body><div>{meeting}</div>"
            "<table><tr><th>枠番</th><th>馬番</th><th>馬名</th><th>単勝</th><th>複勝</th><th>人気</th></tr>"
            + "".join(rows) + f"</table><p>{stamp}</p></body></html>").encode()


def test_single_place_overlay_only_changes_prices_not_ai():
    q = parse_keibalab_html(page(), ID, INFO, now=CLOCK)
    assert q["horse_count"] == 2
    assert q["coverage"]["win"]["count"] == 2
    assert q["coverage"]["place"]["count"] == 2
    assert q["observed_at"] == "2026-11-08T10:11:00+09:00"
    original = [dict(no="1", odds="99", rank="S", score=70),
                dict(no="2", odds="99", rank="B", score=53)]
    shown = race_odds.overlay(original, q, "過去掲載単複")
    assert shown[0]["odds"] == "11.9" and shown[0]["place_odds"] == "2.6〜4.2"
    assert shown[1]["odds"] == "2.7" and shown[1]["place_odds"] == "1.2〜1.5"
    assert [x["rank"] for x in shown] == ["S", "B"]
    assert [x["score"] for x in shown] == [70,53]


@pytest.mark.parametrize("bad", [
    lambda: page(title="単勝・複勝オッズ〖2026年11月8日東京1R〗"),
    lambda: page(meeting="5回京都3日目"),
    lambda: page(rows=["<tr><td>2</td><td>2</td><td>テリオスベラ</td><td>2.7</td><td>1.2-1.5</td><td>1</td></tr>"]),
    lambda: page(stamp="※2026年11月9日10時11分現在のオッズです。"),
])
def test_wrong_or_incomplete_page_is_never_imported(bad):
    with pytest.raises(ValueError):
        parse_keibalab_html(bad(), ID, INFO, now=CLOCK)


def test_one_request_only_no_block_bypass():
    class Response:
        status_code = 200
        content = page()
    calls=[]
    def get(url, **kw):
        calls.append((url,kw))
        return Response()
    quote = fetch_once(ID, INFO, get=get, now=CLOCK)
    assert quote["horse_count"]==2 and len(calls)==1
    assert "202611080801" in calls[0][0]
    assert calls[0][1]["allow_redirects"] is False


def test_403_stops_cleanly_without_fake_data():
    class Denied:
        status_code=403
        content=b"denied"
    with pytest.raises(ValueError,match="HTTP 403"):
        fetch_once(ID, INFO, get=lambda *_a,**_kw: Denied(), now=CLOCK)
