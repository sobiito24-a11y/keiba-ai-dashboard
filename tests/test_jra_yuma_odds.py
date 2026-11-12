"""Tests based on the actual column arrangement of 優馬JAPAN odds pages.

The HTML here is a deliberately small local fixture, NOT a network response.
"""
from datetime import datetime
import pytest

from core import race_odds
from core.jra_yuma_odds import parse_yuma_pages, fetch_once

HORSES = [
    "シュライアハフト", "テリオスベラ", "ナムラポピー", "リケアワルツ",
    "スマートメモリー", "ナンヨーカルチャー", "リワナグ", "ベイビーブラザー",
    "ランスオブナイト", "ゼイン", "ワイドウィンザー", "レグルスロウ",
    "ツーハーツ", "キタノゲートウェイ",
]
WIN = [11.9,2.7,38.6,217.2,5.1,66.6,8.3,42.3,8.6,500.6,36.9,16.1,4.6,568.8]
PLACE = ["2.6-4.2","1.2-1.5","8.5-14.7","23.2-40.5","1.8-2.8",
         "12.0-20.9","1.8-2.8","5.0-8.4","1.9-3.1","69.3-121.5",
         "5.5-9.3","3.2-5.3","1.5-2.1","84.9-148.9"]
ID = dict(race_id="202608050201", mode="jra",
          horses=[dict(horse_no=i+1, name=name) for i,name in enumerate(HORSES)])
INFO = dict(race_date="2026-11-08")
NOW = datetime(2026,11,13,8,30,tzinfo=race_odds.JST)


def html(kind, *, name_override=None, date_text="2026年11月8日京都1R", missing=None):
    header = "単勝オッズ" if kind == "tan" else "複勝オッズ"
    values = WIN if kind == "tan" else PLACE
    rows = []
    for i,(name,value) in enumerate(zip(HORSES, values),1):
        if i == missing:
            continue
        if i == 2 and name_override:
            name = name_override
        # Real site has an extra '印' cell with nested options.
        rows.append(f"<tr><td>{i}</td><td><select><option>◎</option>"
                    f"<option>○</option></select></td><td><h3>{name}</h3></td>"
                    f"<td>{value}</td></tr>")
    return (f"<html><head><title>サラ系2歳未勝利のオッズ【{date_text}】 | 優馬JAPAN</title>"
            f"</head><body><main><p>京都 1R</p><table><thead><tr><th>馬番</th>"
            f"<th>印</th><th>馬名</th><th>{header}</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></main></body></html>").encode("utf8")


def test_realistic_14_horse_yuma_tables_overlay_all():
    quote = parse_yuma_pages({"tan":html("tan"),"fuk":html("fuk")},ID,INFO,now=NOW)
    assert quote["horse_count"] == 14
    assert quote["coverage"]["win"]["count"] == 14
    assert quote["coverage"]["place"]["count"] == 14
    assert quote["observed_at"] is None
    assert quote["availability"] == "closed"
    bykind = {(p["kind"],tuple(p["horses"])):p for p in quote["prices"]}
    assert bykind[("win",(2,))]["low"] == 2.7
    assert bykind[("place",(2,))]["low"] == 1.2
    assert bykind[("place",(2,))]["high"] == 1.5
    assert bykind[("place",(14,))]["high"] == 148.9
    original = [dict(no=str(i), rank="A", score=i*4, odds="999") for i in range(1,15)]
    overlay = race_odds.overlay(original,quote,"過去単複")
    assert overlay[1]["odds"] == "2.7"
    assert overlay[1]["place_odds"] == "1.2〜1.5"
    assert all(a["rank"] == b["rank"] and a["score"] == b["score"]
               for a,b in zip(original, overlay))


@pytest.mark.parametrize("kind,argument",[
    ("tan",dict(date_text="2026年11月8日東京1R")),
    ("fuk",dict(date_text="2026年11月7日京都1R")),
    ("fuk",dict(name_override="違う馬")),
    ("tan",dict(missing=14)),
])
def test_wrong_race_or_incomplete_table_rejected(kind,argument):
    payload={"tan":html("tan"),"fuk":html("fuk")}
    payload[kind] = html(kind,**argument)
    with pytest.raises(ValueError):
        parse_yuma_pages(payload,ID,INFO,now=NOW)


def test_partial_kind_does_not_fabricate_missing_place():
    quote=parse_yuma_pages({"tan":html("tan")},ID,INFO,now=NOW)
    assert quote["coverage"]["win"]["count"] == 14
    assert quote["coverage"]["place"]["count"] == 0
    assert "place" in quote["missing_kinds"]


def test_fetch_one_per_kind_with_actual_query():
    class Response:
        status_code=200
        headers={}
        def __init__(self,kind):self.content=html(kind)
    calls=[]
    def getter(url,**kw):
        calls.append((url,kw))
        return Response("fuk" if "kind=fuk" in url else "tan")
    quote=fetch_once(ID,INFO,get=getter,now=NOW)
    assert quote["horse_count"]==14
    assert len(calls)==2
    assert "kind=tan" in calls[0][0] and "kind=fuk" in calls[1][0]
    assert all(not call[1]["allow_redirects"] for call in calls)


def test_fetch_403_no_fake_success():
    class Denied:
        status_code=403
        headers={}
        content=b""
    with pytest.raises(ValueError,match="HTTP 403"):
        fetch_once(ID,INFO,get=lambda *_a,**_kw:Denied(),now=NOW)
