"""Sports Navi 2026 Tokyo 11R published odds structure and three-source failover.

The 18 saved horse names and displayed odds are used as representative
local fixtures. Every test is offline; live Streamlit access is unverified.
"""
from copy import deepcopy
from datetime import datetime
import pytest

from core import race_odds
from core.jra_sportsnavi_odds import parse_sportsnavi_html, fetch_once
from core.jra_historical_odds_failover import fetch_once as failover
from core.jra_odds_connection_errors import describe_connection

NAMES = [
    "ジーティーダーリン", "ビザンチンドリーム", "マイネルエンペラー",
    "ミラージュナイト", "ドゥラドーレス", "ファミリータイム",
    "ファイアンクランツ", "ジョイボーイ", "レッドバンデ",
    "ボーンディスウェイ", "ウエストナウ", "メイショウゲキリン",
    "マイネルカンパーナ", "ミクニインスパイア", "ホーエリート",
    "キングズパレス", "キングスコール", "ミステリーウェイ",
]
WIN = [52.3,10.6,18.2,5.7,7.1,74.2,5.8,10.6,5.7,105.1,12.5,36.9,
       128.8,15.6,37.9,28.1,20.3,67.4]
PLACE = [
    "14.5 - 19.7","3.9 - 5.2","4.8 - 6.4","2.0 - 2.5","2.1 - 2.7",
    "14.9 - 20.2","1.9 - 2.4","3.0 - 4.0","1.8 - 2.3","15.6 - 21.1",
    "3.4 - 4.4","9.0 - 12.2","20.5 - 27.7","5.4 - 7.2","7.7 - 10.3",
    "5.7 - 7.6","5.2 - 6.9","16.2 - 22.0",
]
ID = dict(mode="jra", race_id="202605050211",
          horses=[dict(horse_no=i,name=name) for i,name in enumerate(NAMES,1)])
INFO = dict(race_date="2026-11-08")
NOW = datetime(2026,11,13,9,30,tzinfo=race_odds.JST)


def odds_page(*, venue="東京", race_no=11, day="2026年11月8日（日）",
              meeting=5, course_day=2, wrong_no=None, missing_no=None,
              confirmed=True):
    entries=[]
    for no,(name,win,place) in enumerate(zip(NAMES,WIN,PLACE),1):
        if no == missing_no:
            continue
        if no == wrong_no:
            name = "知らない馬"
        entries.append(
            f'<tr><td>{(no+1)//2}</td><td>{no}</td><td><a>{name}</a></td>'
            f'<td>{win}</td><td>{place}</td></tr>'
        )
    return (f'<html><head><title>競馬 - 2026年アルゼンチン共和国杯 オッズ - スポーツナビ</title>'
            f'</head><body><main><section><ul><li>1R</li><li>11R</li><li>12R</li></ul>'
            f'<p>{race_no}R</p><p>{day}</p><p>{meeting}回{venue}{course_day}日</p>'
            f'<h2>アルゼンチン共和国杯 GII</h2></section><section>'
            + ('<p>確定オッズ</p>' if confirmed else '<p>予想オッズ</p>') +
            '<table><thead><tr><th>枠番</th><th>馬番</th><th>馬名</th>'
            '<th>単勝</th><th>複勝</th></tr></thead><tbody>'
            + ''.join(entries) + '</tbody></table></section>'
            '<p>2026/11/8 15:40 更新</p></main></body></html>'
           ).encode("utf-8")


def test_actual_sports_navi_tfw_url_for_saved_2026_11_08_tokyo11():
    from core.jra_historical_odds_links import archived_odds_urls
    assert archived_odds_urls(ID, INFO)["sportsnavi"] == (
        "https://sports.yahoo.co.jp/keiba/race/odds/tfw/2605050211")


def test_sportsnavi_18_horse_published_win_and_place_and_overlay():
    q = parse_sportsnavi_html(odds_page(),ID,INFO,now=NOW)
    assert q["horse_count"] == q["expected_horses"] == 18
    assert q["coverage"]["win"]["count"] == 18
    assert q["coverage"]["place"]["count"] == 18
    assert q["observed_at"] == "2026-11-08T15:40:00+09:00"
    bykind = {(x["kind"],x["horses"][0]):x for x in q["prices"]}
    assert bykind[("win",9)]["low"] == 5.7
    assert bykind[("place",9)]["low"] == 1.8
    assert bykind[("place",9)]["high"] == 2.3
    assert bykind[("win",18)]["low"] == 67.4
    assert bykind[("place",18)]["high"] == 22.0
    source = [dict(no=str(i),name=name,score=i*2,rank="C",mark="✓",odds="999")
              for i,name in enumerate(NAMES,1)]
    before = deepcopy(source)
    overlay = race_odds.overlay(source,q,"過去確定単複")
    assert overlay[8]["odds"] == "5.7"
    assert overlay[8]["place_odds"] == "1.8〜2.3"
    assert all(o["rank"]==b["rank"] and o["mark"]==b["mark"]
               and o["score"]==b["score"] for o,b in zip(overlay,before))
    assert source == before


@pytest.mark.parametrize("alter",[
    dict(venue="京都"),
    dict(race_no=10),
    dict(day="2026年11月7日（土）"),
    dict(meeting=4),
    dict(course_day=3),
    dict(wrong_no=9),
    dict(missing_no=12),
    dict(confirmed=False),
])
def test_wrong_race_or_saved_horse_mismatch_never_imported(alter):
    with pytest.raises(ValueError):
        parse_sportsnavi_html(odds_page(**alter),ID,INFO,now=NOW)


def test_sportsnavi_single_request_no_redirect_and_no_proxy_bypass():
    class Response:
        status_code=200
        headers={}
        content=odds_page()
    calls=[]
    def getter(url,**kw):
        calls.append((url,kw))
        return Response()
    q=fetch_once(ID,INFO,get=getter,now=NOW)
    assert q["coverage"]["place"]["count"] == 18
    assert len(calls) == 1
    assert calls[0][0].endswith("2605050211")
    assert calls[0][1]["allow_redirects"] is False


@pytest.mark.parametrize("status",[403,429,404])
def test_sportsnavi_http_rejection_reported_without_using_fake_prices(status):
    class Response:
        headers={}
        content=b""
        def __init__(self,n):self.status_code=n
    with pytest.raises(ValueError,match=f"HTTP {status}"):
        fetch_once(ID,INFO,get=lambda *_a,**_k:Response(status),now=NOW)


def test_sportsnavi_redirect_to_other_race_is_rejected():
    class Redirect:
        status_code=302
        content=b""
        headers={"Location":"https://sports.yahoo.co.jp/keiba/race/odds/tfw/2605050210"}
    with pytest.raises(ValueError,match="移動先"):
        fetch_once(ID,INFO,get=lambda *_a,**_k:Redirect(),now=NOW)


def test_first_two_blocked_then_sportsnavi_full_is_selected():
    calls=[]
    def blocked(name, status):
        def fn(*_a, **_kw):
            calls.append(name)
            raise ValueError(f"HTTP {status}")
        return fn
    def valid(*_a, **_kw):
        calls.append("sports")
        return parse_sportsnavi_html(odds_page(), ID, INFO, now=NOW)
    q=failover(ID,INFO,now=NOW,
               yuma_fetch=blocked("yuma",403),
               keibalab_fetch=blocked("lab",429),
               sportsnavi_fetch=valid)
    assert calls == ["yuma","lab","sports"]
    assert q["fallback_used"] is True
    assert q["coverage"]["place"]["count"] == 18
    assert "スポーツナビ" in q["source"]
    assert "優馬JAPAN" in " ".join(q["warnings"])
    assert "競馬ラボ" in " ".join(q["warnings"])


def test_both_blocked_sportsnavi_wrong_horse_stays_unavailable():
    def denied(*_a, **_kw):
        raise ValueError("HTTP 403")
    def mismatch(*_a, **_kw):
        return parse_sportsnavi_html(odds_page(wrong_no=9),ID,INFO,now=NOW)
    with pytest.raises(ValueError,match="3サイト"):
        failover(ID,INFO,now=NOW, yuma_fetch=denied,
                 keibalab_fetch=denied, sportsnavi_fetch=mismatch)


def test_connection_diagnostics_are_precise_without_urls_or_secrets():
    class ConnectTimeout(Exception): pass
    class ReadTimeout(Exception): pass
    class ConnectionError(Exception): pass
    class SSLError(Exception): pass
    class ProxyError(Exception): pass
    assert "タイムアウト" in describe_connection(ConnectTimeout("secret"))
    assert "タイムアウト" in describe_connection(ReadTimeout("secret"))
    assert "DNS" in describe_connection(ConnectionError("NameResolutionError"))
    assert "SSL" in describe_connection(SSLError("secret"))
    assert "プロキシ" in describe_connection(ProxyError("secret"))
    assert "secret" not in describe_connection(ConnectionError("secret"))
