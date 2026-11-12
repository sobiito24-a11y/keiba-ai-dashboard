"""Synthetic official-schema ZIP fixtures: no NAR network request in CI."""
from __future__ import annotations

from datetime import datetime, timedelta
from io import BytesIO
import csv
import zipfile
import pytest

from core import race_odds
from core import nar_official_odds as official

DAY = "20261112"
DATE = datetime(2026, 11, 12, 14, 10, tzinfo=race_odds.JST)
FILENAME = f"{DAY}_{int(DATE.timestamp())}_odds.zip"
IDENTITY = dict(
    race_id="202645111207", mode="nar",
    horses=[dict(horse_no=n, name=f"テスト馬{n}") for n in (1, 2, 3)],
)
INFO = dict(racecourse="川崎", race_date="2026-11-12")


def make_csv(rows, *, encoding="utf-8-sig"):
    buf = BytesIO()
    fields = ["競馬場", "競走年月日", "レース番号", "賭式", "番号１",
              "番号２", "番号３", "オッズ", "オッズ（最大）", "人気"]
    import io
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    for kind, a, b, low, high, pop in rows:
        writer.writerow({
            "競馬場": "川﨑", "競走年月日": DAY, "レース番号": "7",
            "賭式": kind, "番号１": str(a), "番号２": str(b or ""),
            "番号３": "", "オッズ": str(low), "オッズ（最大）": str(high or ""),
            "人気": str(pop or "")
        })
    text = out.getvalue().encode(encoding)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{DAY}_odds.csv", text)
    return buf.getvalue()


ROWS = [
    ("単勝", 1, None, "2.3", None, 1),
    ("単勝", 2, None, "11.0", None, 3),
    ("単勝", 3, None, "3.6", None, 2),
    ("複勝", 1, None, "1.2", "1.5", 1),
    ("馬複", 1, 2, "8.9", None, 5),
    ("ワイド", 1, 3, "2.1", "2.5", 2),
]


@pytest.mark.parametrize("encoding", ["utf-8-sig", "cp932"])
def test_daily_zip_all_four_kinds_by_date_venue_race(encoding):
    raw = make_csv(ROWS, encoding=encoding)
    actual = official.parse_daily_zip(raw, FILENAME, IDENTITY, INFO, now=DATE + timedelta(seconds=15))
    assert actual["price_status"] == "official_zip_snapshot"
    assert actual["timestamp_kind"] == "zip_file_created_not_odds_updated"
    assert actual["source"] == "NAR公式オッズZIP"
    assert actual["horse_count"] == 3
    assert actual["popularity"] == {"1": 1, "2": 3, "3": 2}
    prices = {(p["kind"], tuple(p["horses"])): p for p in actual["prices"]}
    assert prices[("win", (2,))]["low"] == 11
    assert prices[("place", (1,))]["high"] == 1.5
    assert prices[("quinella", (1,2))]["low"] == 8.9
    assert prices[("wide", (1,3))]["high"] == 2.5
    assert "参考価格" in race_odds.freshness(
        actual, "2026-11-12T16:00:00+09:00", now=DATE + timedelta(seconds=20))
    assert "発走後" in race_odds.freshness(
        actual, "2026-11-12T14:05:00+09:00", now=DATE + timedelta(minutes=1))


def test_no_wrong_venue_day_race_or_source_identity():
    raw = make_csv(ROWS)
    wrong = dict(INFO, racecourse="園田")
    with pytest.raises(ValueError, match="レースID"):
        official.parse_daily_zip(raw, FILENAME, IDENTITY, wrong)
    with pytest.raises(ValueError, match="日付"):
        official.parse_daily_zip(raw, "20261111_1794456600_odds.zip", IDENTITY, INFO)
    with pytest.raises(ValueError, match="地方競馬"):
        official.parse_daily_zip(raw, FILENAME, dict(IDENTITY, mode="jra"), INFO)
    wrong_date = dict(INFO, race_date="2026-11-13")
    with pytest.raises(ValueError, match="日付"):
        official.parse_daily_zip(raw, FILENAME, IDENTITY, wrong_date)


def test_only_matching_race_and_no_old_price_blending():
    # Other track and other round are valid rows, but must not be imported.
    rows = ROWS.copy()
    raw = make_csv(rows)
    import io
    with zipfile.ZipFile(BytesIO(raw)) as z:
        body = z.read(f"{DAY}_odds.csv").decode("utf-8-sig")
    body += f"園田,{DAY},7,単勝,1,,,100,,\n"
    body += f"川崎,{DAY},8,単勝,1,,,100,,\n"
    buf=BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"{DAY}_odds.csv", body.encode("utf-8-sig"))
    q=official.parse_daily_zip(buf.getvalue(), FILENAME, IDENTITY, INFO)
    assert len(q["prices"]) == len(ROWS)
    assert q["coverage"]["quinella"]["count"] == 1
    # A partial new batch never inherits stale odds from an older batch.
    view=[dict(no="1",odds="100",score=5,mark="◎"),
          dict(no="2",odds="200",score=4,mark="○")]
    only=make_csv([ROWS[0]])
    q2=official.parse_daily_zip(only,FILENAME,IDENTITY,INFO)
    shown=race_odds.overlay(view,q2,"更新")
    assert shown[1]["odds"] == "—"
    assert shown[1]["mark"] == "○" and shown[0]["score"] == 5


@pytest.mark.parametrize("mutate", [
    lambda x: x.replace(b"PK", b"xx", 1),
    lambda x: b"not zip",
])
def test_invalid_archive_not_interpreted_as_live_odds(mutate):
    with pytest.raises(ValueError):
        official.parse_daily_zip(mutate(make_csv(ROWS)), FILENAME, IDENTITY, INFO)


def test_missing_or_invalid_quote_must_fail_closed():
    with pytest.raises(ValueError,match="有効"):
        official.parse_daily_zip(make_csv([("単勝",1,None,"0",None,1)]),FILENAME,IDENTITY,INFO)
    with pytest.raises(ValueError,match="馬番"):
        official.parse_daily_zip(make_csv([("単勝",9,None,"5.5",None,1)]),FILENAME,IDENTITY,INFO)
    with pytest.raises(ValueError,match="異なる価格"):
        official.parse_daily_zip(make_csv([ROWS[0],("単勝",1,None,"6.7",None,1)]),FILENAME,IDENTITY,INFO)


def test_download_only_official_fixed_url_and_file_name_from_headers():
    class Response:
        status_code=200
        headers={"Content-Disposition": f'attachment; filename="{FILENAME}"'}
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def iter_content(self, chunk_size): yield make_csv(ROWS)
    calls=[]
    def fake_get(url, **kw):
        calls.append((url,kw))
        return Response()
    name, raw=official.fetch_daily(get=fake_get)
    assert name==FILENAME and raw[:2]==b"PK"
    assert calls[0][0]==official.OFFICIAL_URL
    assert calls[0][1]["allow_redirects"] is False
    assert calls[0][1]["timeout"] == 20


def test_download_rejects_html_or_missing_timestamp():
    class Response:
        status_code=200
        headers={}
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def iter_content(self,chunk_size): yield b"<html>not a zip</html>"
    with pytest.raises(ValueError,match="ファイル名"):
        official.fetch_daily(get=lambda *_a,**_kw:Response())
