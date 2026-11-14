"""Same-day Sports Navi intermediate quote: independently checked, not 'real-time'.

No external network, no fake upstream timestamps, no score/rank/mark updates.
"""
from copy import deepcopy
from datetime import datetime
import pytest

from core import race_odds
from core.jra_sportsnavi_odds import (
    LIVE_SOURCE, fetch_live_once, parse_sportsnavi_html)
from tests.test_jra_sportsnavi_odds import NAMES, WIN, PLACE, odds_page

IDENTITY=dict(mode="jra",race_id="202605050311",
              horses=[dict(horse_no=i,name=name) for i,name in enumerate(NAMES,1)])
INFO=dict(race_date="2026-11-14")
NOW=datetime(2026,11,14,10,20,tzinfo=race_odds.JST)


def live_page(*, missing_no=None, wrong_no=None, status="中間オッズ",
              page_date="2026年11月14日（土）", update_text=""):
    rows=[]
    for no,(name,win,place) in enumerate(zip(NAMES,WIN,PLACE),1):
        if no==missing_no:
            continue
        if no==wrong_no:
            name="レース違いの馬"
        rows.append(f"<tr><td>{(no+1)//2}</td><td>{no}</td>"
                    f"<td>{name}</td><td>{win}</td><td>{place}</td></tr>")
    return (f"<html><body><main><nav>予想オッズ</nav><div>11R</div>"
            f"<div>{page_date}</div><div>5回東京3日</div>"
            f"<h2>武蔵野ステークス</h2><div>{status}</div>"
            "<table><tr><th>枠番</th><th>馬番</th><th>馬名</th>"
            "<th>単勝</th><th>複勝</th></tr>" +
            "".join(rows)+"</table>"+update_text+"</main></body></html>").encode()


def test_full_same_day_page_is_accepted_without_faking_update_timestamp():
    original=deepcopy(IDENTITY)
    q=parse_sportsnavi_html(live_page(),IDENTITY,INFO,now=NOW,odds_stage="intermediate")
    assert q["source"]==LIVE_SOURCE
    assert q["coverage"]["win"]["count"]==18
    assert q["coverage"]["place"]["count"]==18
    assert q["observed_at"] is None
    assert q["received_at"]==NOW.isoformat()
    assert q["availability"]=="unknown"
    assert q["price_status"]=="published_odds"
    assert q["acquisition_method"]=="sportsnavi_intermediate_html"
    assert any("直前" in msg for msg in q["warnings"])
    assert IDENTITY==original
    h=[dict(no=str(i),mark="◎",rank="S",score=90) for i in range(1,19)]
    before=deepcopy(h)
    applied=race_odds.overlay(h,q,"当日掲載")
    assert applied[8]["odds"]=="5.7"
    assert applied[8]["place_odds"]=="1.8〜2.3"
    assert h==before
    assert all(a["rank"]==b["rank"] and a["mark"]==b["mark"]
               for a,b in zip(applied,before))


@pytest.mark.parametrize("modified",[
    dict(missing_no=8),dict(wrong_no=8),dict(status="確定オッズ"),
    dict(status="予想オッズ"),dict(page_date="2026年11月15日（日）"),
])
def test_reject_wrong_horse_wrong_day_missing_or_non_intermediate(modified):
    with pytest.raises(ValueError):
        parse_sportsnavi_html(live_page(**modified),IDENTITY,INFO,
                              now=NOW,odds_stage="intermediate")


def test_live_only_on_race_day_and_never_relabel_past_as_current():
    with pytest.raises(ValueError,match="開催当日"):
        parse_sportsnavi_html(live_page(),IDENTITY,INFO,
                              now=datetime(2026,11,15,10,20,tzinfo=race_odds.JST),
                              odds_stage="intermediate")
    with pytest.raises(ValueError,match="開催日"):
        fetch_live_once(IDENTITY,INFO,get=lambda *_a,**_kw:None,
                        now=datetime(2026,11,13,10,20,tzinfo=race_odds.JST))
    with pytest.raises(ValueError,match="確定オッズ"):
        parse_sportsnavi_html(live_page(),IDENTITY,INFO,now=NOW)


def test_one_read_no_redirect_or_rate_limit_bypass():
    calls=[]
    class Response:
        content=live_page()
        status_code=200
    def getter(url,**kwargs):
        calls.append((url,kwargs))
        return Response()
    q=fetch_live_once(IDENTITY,INFO,get=getter,now=NOW)
    assert q["coverage"]["place"]["count"]==18
    assert len(calls)==1
    assert calls[0][0].endswith("/2605050311")
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["timeout"]==12


@pytest.mark.parametrize("http_code",[400,403,429,500])
def test_http_failure_is_reported_without_any_prices(http_code):
    class Response:
        status_code=http_code
        content=b""
    with pytest.raises(ValueError,match="HTTP "+str(http_code)):
        fetch_live_once(IDENTITY,INFO,get=lambda *_a,**_kw:Response(),now=NOW)


def test_feed_time_can_be_read_but_not_invented():
    html=live_page(update_text="<p>2026/11/14 10:05 更新</p>")
    q=parse_sportsnavi_html(html,IDENTITY,INFO,now=NOW,odds_stage="intermediate")
    assert q["observed_at"]=="2026-11-14T10:05:00+09:00"
    with pytest.raises(ValueError,match="更新日"):
        parse_sportsnavi_html(live_page(update_text="<p>2026/11/13 23:00 更新</p>"),
                              IDENTITY,INFO,now=NOW,odds_stage="intermediate")


def test_fallback_history_parser_behavior_still_requires_confirmed_odds():
    from tests.test_jra_sportsnavi_odds import ID, INFO as HIST, NOW as HIST_NOW
    page=odds_page()
    quote=parse_sportsnavi_html(page,ID,HIST,now=HIST_NOW)
    assert quote["availability"]=="closed"
    assert quote["coverage"]["place"]["count"]==18
