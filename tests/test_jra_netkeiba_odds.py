"""Public netkeiba page JSON shape: test cases only, no live network in CI."""
from copy import deepcopy
from datetime import datetime, timedelta
import pytest

from core import race_odds
from core import jra_netkeiba_odds as jra

ID = dict(race_id="202605050211", mode="jra",
          horses=[dict(horse_no=i, name=f"馬{i}") for i in (1, 2, 3)])
INFO = dict(race_date="2026-11-08", start_time="15:40")
CLOCK = datetime(2026, 11, 8, 15, 39, 30, tzinfo=race_odds.JST)


def responses(time="2026-11-08 15:39:00"):
    return {
        "1": dict(status="result", data=dict(official_datetime=time, odds={
            "1": {"01": ["2.3", "0.0", "1"], "02": ["12.5", "0.0", "3"],
                  "03": ["4.6", "0.0", "2"]},
            "2": {"01": ["1.2", "1.6", "1"], "02": ["2.3", "3.4", "2"],
                  "03": ["1.9", "2.1", "3"]},
        })),
        "4": dict(status="result", data=dict(official_datetime=time, odds={
            "4": {"0102": ["21.4", "0.0", "5"], "0103": ["7.7", "0.0", "1"],
                  "0203": ["31.6", "0.0", "8"]},
        })),
        "5": dict(status="result", data=dict(official_datetime=time, odds={
            "5": {"0102": ["4.1", "5.0", "5"], "0103": ["2.0", "3.0", "1"],
                  "0203": ["8.3", "11.6", "8"]},
        })),
    }


def test_all_four_kinds_from_known_page_schema_pre_race():
    payload=responses()
    untouched=deepcopy(payload)
    q=jra.parse_responses(payload, ID, INFO, now=CLOCK)
    assert payload==untouched
    assert q["source"]=="netkeiba無料オッズ（取得試験）"
    assert q["price_status"]=="published_odds"
    assert q["horse_count"]==3 and q["expected_horses"]==3
    assert q["collection_status"]=="complete"
    assert {k:v["count"] for k,v in q["coverage"].items()}=={
        "win":3, "place":3, "quinella":3, "wide":3
    }
    p={(o["kind"],tuple(o["horses"])):o for o in q["prices"]}
    assert p[("win",(2,))]["low"]==12.5
    assert p[("place",(1,))]["high"]==1.6
    assert p[("quinella",(1,3))]["low"]==7.7
    assert p[("wide",(1,2))]["low"]==4.1
    assert p[("wide",(1,2))]["high"]==5.0
    assert q["popularity"]=={"1":1,"2":3,"3":2}
    assert "netkeiba無料配信の参考価格" in race_odds.freshness(
        q, "2026-11-08T15:40:00+09:00", now=CLOCK)
    assert "古い観測" in race_odds.freshness(
        q, "2026-11-08T17:00:00+09:00", now=CLOCK + timedelta(minutes=8))
    assert "発走後" in race_odds.freshness(
        q, "2026-11-08T15:40:00+09:00", now=CLOCK + timedelta(minutes=3))
    assert "netkeiba無料配信" in race_odds.received_label(q)


def test_yoso_predictions_never_become_real_odds():
    p=responses()
    p["1"]["status"]="yoso"
    with pytest.raises(ValueError,match="予想オッズ"):
        jra.parse_responses(p,ID,INFO,now=CLOCK)
    # A real source can include numeric predicted entries. Never convert them.


@pytest.mark.parametrize("bad",[
    lambda p:p["1"].update(status="NG"),
    lambda p:p["1"]["data"].update(official_datetime=None),
    lambda p:p["1"]["data"].update(official_datetime="2026-11-09 15:39:00"),
    lambda p:p["1"]["data"].update(official_datetime="2026-11-08 23:58:00"),
    lambda p:p["1"]["data"]["odds"]["1"].update({"04":["3.2","0.0","4"]}),
])
def test_wrong_status_date_unknown_horse_or_future_rejected(bad):
    p=responses();bad(p)
    with pytest.raises(ValueError):
        jra.parse_responses(p,ID,INFO,now=CLOCK)


def test_older_pair_kinds_must_not_be_merged_with_new_win():
    p=responses()
    p["4"]["data"]["official_datetime"]="2026-11-08 15:12:00"
    p["5"]["data"]["official_datetime"]="2026-11-08 15:01:00"
    q=jra.parse_responses(p,ID,INFO,now=CLOCK)
    assert {o["kind"] for o in q["prices"]}=={"win","place"}
    assert q["coverage"]["wide"]["count"]==0
    assert "wide" in q["missing_kinds"]


def test_partial_prices_never_inherit_prior_saved_quotes():
    p=responses();p.pop("5");p.pop("4")
    q=jra.parse_responses(p,ID,INFO,now=CLOCK)
    original=[dict(no="1",odds="100",mark="◎",score=50),
              dict(no="2",odds="500",mark="○",score=40)]
    # Simulate a new batch with one missing win number.
    q["prices"]=[x for x in q["prices"] if x["horses"] != [2]]
    q=race_odds.validate(q,ID)
    shown=race_odds.overlay(original,q,"更新")
    assert shown[0]["odds"]=="2.3"
    assert shown[1]["odds"]=="—"
    assert shown[0]["mark"]=="◎" and shown[1]["score"]==40


def test_unknown_race_or_date_and_malformed_number_fail():
    with pytest.raises(ValueError,match="JRA"):
        jra.parse_responses(responses(),dict(ID,mode="nar"),INFO,now=CLOCK)
    with pytest.raises(ValueError,match="開催日"):
        jra.parse_responses(responses(),ID,dict(INFO,race_date="2026-11-15"),now=CLOCK)
    p=responses()
    p["1"]["data"]["odds"]["1"]["01"]=["---.-","0","1"]
    q=jra.parse_responses(p,ID,INFO,now=CLOCK)
    assert not any(x["kind"]=="win" and x["horses"]==[1] for x in q["prices"])


def test_private_free_fetch_makes_only_known_limited_gets():
    class Response:
        status_code=200
        def __init__(self,data): self._data=data;self.content=b"x"*100
        def json(self): return self._data
    calls=[]
    data=responses()
    def getter(url,**kw):
        calls.append((url,kw))
        return Response(data[kw["params"]["type"]])
    q=jra.fetch_once(ID,INFO,get=getter,now=CLOCK)
    assert q["horse_count"]==3
    assert [x[1]["params"]["type"] for x in calls]==["1","4","5"]
    assert all(x[0]==jra.ENDPOINT for x in calls)
    assert all(x[1]["params"]["action"]=="init" for x in calls)
    assert all(x[1]["allow_redirects"] is False for x in calls)


def test_fetch_bails_after_first_yoso_and_does_not_exhaust_quota():
    class Response:
        status_code=200
        content=b"{}"
        def json(self): return dict(status="yoso",data=dict(
            official_datetime="2026-11-08 13:40:00",
            odds={"1":{"01":["2.3","", "1"]}}))
    calls=[]
    def getter(url, **kw):
        calls.append(kw["params"]["type"])
        return Response()
    with pytest.raises(ValueError,match="予想オッズ"):
        jra.fetch_once(ID,INFO,get=getter,now=CLOCK)
    assert calls==["1"]


def test_extra_or_wrong_status_pair_data_never_gives_false_prices():
    p=responses()
    p["5"]=dict(status="NG",data="",reason="quota limit")
    q=jra.parse_responses(p,ID,INFO,now=CLOCK)
    assert {x["kind"] for x in q["prices"]}=={"win","place","quinella"}
    assert q["coverage"]["wide"]["count"]==0


def test_comma_thousands_are_accepted_no_synthetic_numbers():
    p=responses()
    p["4"]["data"]["odds"]["4"]["0102"]=["1,234.5","0.0","5"]
    q=jra.parse_responses(p,ID,INFO,now=CLOCK)
    assert next(x["low"] for x in q["prices"] if x["kind"]=="quinella" and x["horses"]==[1,2])==1234.5


@pytest.mark.parametrize("http,phrase", [
    (403, "HTTP 403"),
    (429, "HTTP 429"),
    (503, "HTTP 503"),
])
def test_free_source_http_failures_have_safe_useful_diagnostics(http, phrase):
    class Response:
        status_code=http
        content=b"<html>not authenticated</html>"
        def json(self):
            raise AssertionError("Non-200 response must not be parsed as odds")
    with pytest.raises(ValueError,match=phrase):
        jra.fetch_once(ID,INFO,get=lambda *_a,**_kw:Response(),now=CLOCK)


def test_html_from_free_source_is_reported_not_imported():
    class Response:
        status_code=200
        content=b"<html>please wait</html>"
        def json(self): raise ValueError("Expected JSON")
    with pytest.raises(ValueError,match="JSON以外"):
        jra.fetch_once(ID,INFO,get=lambda *_a,**_kw:Response(),now=CLOCK)
