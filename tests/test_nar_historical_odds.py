"""Official monthly NAR final win/place odds; no external HTTP requests in tests."""
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from zipfile import ZipFile, ZIP_DEFLATED
import csv
import pytest

from core import race_odds
from core import nar_historical_odds as historical

DATE = datetime(2026, 11, 13, 9, 13, tzinfo=race_odds.JST)
DAY = "20261112"
FILENAME = f"202611_{int(DATE.timestamp())}_odds.zip"
IDENTITY = dict(race_id="202648111201", mode="nar",
                horses=[dict(horse_no=i, name=name) for i, name in enumerate([
                    "フランキンローズ", "シングンラオウ", "メイショウソラル",
                    "グレーターグレイ", "アンジェララヴ", "インサラータ",
                    "クリコメリー", "ナガノキングダイヤ", "フライデイゼーン",
                    "フェイントライト", "フィロンドール",
                ], 1)])
INFO = dict(racecourse="名古屋", race_date="2026-11-12")
WINS = [317.5, 22.3, 1.5, 70.3, 270.6, 162.6, 24.3, 2.7, 9.6, 157.5, 111.1]
PLACES = [(19.1,45.9),(1.7,3.3),(1.0,1.1),(2.3,5.0),(25.0,60.2),
          (7.3,17.1),(2.4,5.1),(1.1,1.9),(1.2,2.4),(11.8,28.2),(6.4,14.9)]


def csv_bytes(rows=None, encoding="utf-8-sig"):
    dst=StringIO()
    writer=csv.writer(dst)
    writer.writerow(["競馬場","競走年月日","レース番号","賭式",
                     "番号１","番号２","番号３","オッズ","オッズ（最大）","人気"])
    if rows is None:
        rows=[]
        for i,win in enumerate(WINS,1):
            rows.append(("名古屋",DAY,1,"単勝",i,"","",win,"",i))
        for i,(low,high) in enumerate(PLACES,1):
            rows.append(("名古屋",DAY,1,"複勝",i,"","",low,high,i))
        rows += [("名古屋","20261111",1,"単勝",1,"","",999,"",1),
                 ("園田",DAY,1,"単勝",1,"","",999,"",1),
                 ("名古屋",DAY,2,"単勝",1,"","",999,"",1)]
    writer.writerows(rows)
    return dst.getvalue().encode(encoding)


def zip_bytes(body=None, *, member="202611_02_odds.csv"):
    b=BytesIO()
    with ZipFile(b,"w",ZIP_DEFLATED) as z:
        z.writestr("202611_01_odds.csv",csv_bytes([("名古屋","20261101",1,"単勝",1,"","",9,"",1)]))
        z.writestr(member,csv_bytes() if body is None else body)
        z.writestr("202611_03_odds.csv",csv_bytes([("名古屋","20261121",1,"単勝",1,"","",9,"",1)]))
    return b.getvalue()


@pytest.mark.parametrize("encoding", ["utf-8-sig","cp932"])
def test_nagoya_nov12_11_horses_final_win_and_place(encoding):
    q=historical.parse_monthly_zip(
        zip_bytes(csv_bytes(encoding=encoding)), FILENAME, IDENTITY, INFO, now=DATE)
    assert q["source"]=="NAR公式月次ZIP・確定単複オッズ"
    assert q["observed_at"] is None
    assert q["coverage"]["win"]["count"] == 11
    assert q["coverage"]["place"]["count"] == 11
    assert q["coverage"]["wide"]["count"] == 0
    prices={(p["kind"],p["horses"][0]):p for p in q["prices"]}
    assert prices[("win",1)]["low"] == 317.5
    assert prices[("win",3)]["low"] == 1.5
    assert prices[("place",3)]["low"] == 1.0
    assert prices[("place",3)]["high"] == 1.1
    assert prices[("win",8)]["low"] == 2.7
    assert prices[("place",8)]["high"] == 1.9
    before=[dict(no=str(i), rank="A", score=i*4, odds="999") for i in range(1,12)]
    overlaid=race_odds.overlay(before,q,"過去NAR公式単複")
    assert overlaid[2]["odds"] == "1.5"
    assert overlaid[2]["place_odds"] == "1.0〜1.1"
    assert overlaid[7]["place_odds"] == "1.1〜1.9"
    assert all(a["score"]==b["score"] and a["rank"]==b["rank"] for a,b in zip(before,overlaid))
    assert all(a["odds"]=="999" for a in before)


def test_wrong_month_and_part_are_rejected():
    with pytest.raises(ValueError,match="対象年月"):
        historical.parse_monthly_zip(zip_bytes(), "202610_1790000000_odds.zip", IDENTITY, INFO, now=DATE)
    with pytest.raises(ValueError,match="10日単位"):
        historical.parse_monthly_zip(zip_bytes(member="202611_04_odds.csv"),
                                     FILENAME,IDENTITY,INFO,now=DATE)


@pytest.mark.parametrize("mutated", [
    [("名古屋",DAY,1,"単勝",12,"","",9.9,"",1)],
    [("名古屋",DAY,1,"単勝",1,"","",2.1,"",1),
     ("名古屋",DAY,1,"単勝",1,"","",4.2,"",1)],
])
def test_wrong_horse_or_conflicting_odds_do_not_change_predictions(mutated):
    with pytest.raises(ValueError):
        historical.parse_monthly_zip(zip_bytes(csv_bytes(mutated)), FILENAME,
                                     IDENTITY, INFO, now=DATE)


def test_only_source_day_and_track_match():
    with pytest.raises(ValueError,match="日付"):
        historical.parse_monthly_zip(zip_bytes(),FILENAME,IDENTITY,
                                     dict(INFO,race_date="2026-11-11"),now=DATE)
    with pytest.raises(ValueError,match="競馬場"):
        historical.parse_monthly_zip(zip_bytes(),FILENAME,IDENTITY,
                                     dict(INFO,racecourse="笠松"),now=DATE)
    with pytest.raises(ValueError,match="過去"):
        historical.parse_monthly_zip(zip_bytes(),FILENAME,IDENTITY,INFO,
                                     now=datetime(2026,11,12,9,tzinfo=race_odds.JST))


def test_one_official_monthly_request_with_exact_year_month():
    class Response:
        status_code=200
        headers={"Content-Disposition":f'attachment; filename="{FILENAME}"'}
        def __enter__(self):return self
        def __exit__(self,*_):return False
        def iter_content(self,chunk_size):yield zip_bytes()
    calls=[]
    def getter(url,**kw):
        calls.append((url,kw))
        return Response()
    q=historical.fetch_once(IDENTITY,INFO,get=getter,now=DATE)
    assert q["horse_count"]==11
    assert len(calls)==1
    assert calls[0][0]==historical.MONTHLY_URL
    assert calls[0][1]["params"]=={"k_year":"2026","k_month":"11","type":"monthly"}
    assert calls[0][1]["allow_redirects"] is False
