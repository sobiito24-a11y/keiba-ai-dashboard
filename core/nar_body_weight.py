"""NAR Rakuten race-card body weights: separate, read-only prestart observations.

No grade, ranking, marks, win probabilities, odds, or betting calculations
are written back to PredictionResult. An observed fetch time is NOT the
publisher's underlying update time or proof of a prestart market snapshot.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import hashlib
import json
import math
import re
import unicodedata
from urllib.parse import urlparse
from collections.abc import Mapping

from bs4 import BeautifulSoup

from . import race_odds
from .nar_official_odds import locator
from .independent_ai_sabcd import MODEL_ID

SCHEMA = "nar_body_weight_research_v1"
BASE_URL = "https://keiba.rakuten.co.jp"
# Rakuten course codes are different from the 12-digit netkeiba/NAR codes.
# Only verified public racecard routes; unsupported venues fail closed.
RAKUTEN_CODES = {
    "盛岡": "10", "水沢": "11", "浦和": "18", "船橋": "19",
    "大井": "20", "川崎": "21", "金沢": "22", "笠松": "23",
    "名古屋": "24", "園田": "27", "高知": "31", "佐賀": "32",
    "門別": "36",
}
GRADES = ("S", "A", "B", "C", "D")
BANDS = ("範囲内", "範囲外")


def _norm(value):
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", "", value).replace("﨑", "崎")


def _integer(value, low=1, high=20):
    try:
        text = str(value).strip()
        if not re.fullmatch(r"\d{1,3}", text):
            return None
        x = int(text)
        return x if low <= x <= high else None
    except (ValueError, TypeError):
        return None


def _timestamp(value):
    try:
        t = datetime.fromisoformat(str(value))
        return t if t.tzinfo is not None and t.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def _date_race(identity, info):
    venue, day, race = locator(identity, info or {})
    if venue not in RAKUTEN_CODES:
        raise ValueError("楽天競馬の自動照合に未対応の開催場です：" + venue)
    return venue, day, race


def racecard_url(identity, info):
    venue, day, race = _date_race(identity, info)
    return f"{BASE_URL}/race_card/list/RACEID/{day}{RAKUTEN_CODES[venue]}000000{race:02d}"


def result_url(identity, info):
    return racecard_url(identity, info).replace("/race_card/", "/race_performance/")


def _check_page(soup, source_url, identity, info, *, result=False):
    venue, day, race = _date_race(identity, info)
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.netloc != "keiba.rakuten.co.jp":
        raise ValueError("楽天競馬のHTTPS公開ページ以外は取り込みません")
    section = "race_performance" if result else "race_card"
    m = re.fullmatch(rf"/{section}/list/RACEID/(20\d{{16}})(?:/mode/[01])?/?", parsed.path)
    if not m:
        raise ValueError("出走表／競走成績の正式なRACEID付きURLではありません")
    key = m[1]
    if key[:8] != day or key[8:10] != RAKUTEN_CODES[venue] or int(key[-2:]) != race:
        raise ValueError("楽天競馬の開催日・競馬場・レース番号が保存予想と一致しません")
    title = _norm(soup.title.get_text(" ", strip=True) if soup.title else "")
    expected_day = f"{day[:4]}/{int(day[4:6]):02d}/{int(day[6:]):02d}"
    if (venue + "競馬場") not in title or expected_day not in title or not re.search(
        rf"(?<!\d){race}R(?!\d)", title):
        raise ValueError("ページのタイトルと保存予想の日付・開催場・Rが一致しません")
    if ("競走成績" if result else "出馬表") not in title:
        raise ValueError("異なる種類の楽天競馬ページです")


def _weight(text):
    text = _norm(text)
    match = re.fullmatch(r"(\d{3})(?:kg|k)?(?:([+-]\d{1,2}|±0))?", text)
    if not match:
        return None, None
    kg = int(match[1])
    if not 250 <= kg <= 750:
        return None, None
    change = match[2]
    return kg, (0 if change == "±0" else int(change) if change is not None else None)


def _range(text):
    values = re.findall(r"(?<!\d)\d{3}(?!\d)", _norm(text))
    if len(values) not in (1, 2):
        return None, None
    low, high = int(values[0]), int(values[-1])
    if 250 <= low <= high <= 750:
        return low, high
    return None, None


def _classify(kg, low, high):
    if kg is None or low is None or high is None:
        return "判定不能", None
    distance = low-kg if kg < low else kg-high if kg > high else 0
    return ("範囲内" if distance == 0 else "範囲外"), distance


def _table(soup, result=False):
    needed = ("着順", "馬番") if result else ("馬番", "連対時馬体重", "馬体重増減")
    for table in soup.find_all("table"):
        th = [_norm(t.get_text(" ", strip=True)) for t in table.find_all("th", limit=25)]
        if all(any(label in item for item in th) for label in needed):
            return table
    raise ValueError("楽天競馬の対象テーブルを確認できません（ページ形式変更の可能性）")


def _expected_names(identity):
    names = {}
    for h in identity["horses"]:
        no = _integer(h["horse_no"])
        if no is None or no in names or not _norm(h["name"]):
            raise ValueError("保存予想の馬番・馬名に重複または欠損があります")
        names[no] = str(h["name"])
    return names


def parse_card(html, source_url, identity, info):
    """Parse only the exact race and named horses; missing weights stay missing."""
    if identity.get("mode") != "nar":
        raise ValueError("地方競馬の出走表のみ対応")
    soup = BeautifulSoup(html, "html.parser")
    _check_page(soup, source_url, identity, info)
    table = _table(soup)
    names = _expected_names(identity)
    rows = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) < 7:
            continue
        no = _integer(cells[1].get_text(" ", strip=True))
        if no is None or no not in names:
            continue
        # Sire/dam and the horse name share this table cell. Match the
        # frozen exact horse name; ambiguous substring matches are rejected.
        horse_text = _norm(cells[3].get_text(" ", strip=True))
        matching = [n for n in names.values() if _norm(n) in horse_text]
        if len(matching) != 1 or _norm(matching[0]) != _norm(names[no]):
            continue
        if no in rows:
            raise ValueError("楽天競馬出走表内に同じ馬番が重複しています")
        low, high = _range(cells[5].get_text(" ", strip=True))
        kg, delta = _weight(cells[6].get_text(" ", strip=True))
        band, distance = _classify(kg, low, high)
        rows[no] = dict(horse_no=no, name=names[no], current_kg=kg,
                        change_kg=delta, paired_min_kg=low, paired_max_kg=high,
                        band=band, distance_from_range_kg=distance)
    if len(rows) < max(1, math.ceil(len(names) * .6)):
        raise ValueError(f"出走馬の照合が不足しています（{len(rows)}/{len(names)}頭）。馬名やページ形式を確認してください")
    return [rows.get(no, dict(horse_no=no, name=name, current_kg=None,
                              change_kg=None, paired_min_kg=None, paired_max_kg=None,
                              band="判定不能", distance_from_range_kg=None))
            for no, name in sorted(names.items())]


def parse_result(html, source_url, identity, info):
    """After-the-race official finishes are kept separate from prestart data."""
    soup = BeautifulSoup(html, "html.parser")
    _check_page(soup, source_url, identity, info, result=True)
    table = _table(soup, result=True)
    names = _expected_names(identity)
    results = {}
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if len(cells) < 4:
            continue
        position = _integer(cells[0].get_text(" ", strip=True), high=30)
        no = _integer(cells[2].get_text(" ", strip=True))
        if position is None or no is None or no not in names:
            continue
        if no in results:
            raise ValueError("確定着順に同一馬番が重複しています")
        results[no] = position
    if not any(n == 1 for n in results.values()) or not any(n == 2 for n in results.values()) or not any(n == 3 for n in results.values()):
        raise ValueError("確定した1〜3着を確認できません")
    if len(results) < max(3, math.ceil(len(names) * .6)):
        raise ValueError("着順の照合頭数が不足しています")
    return {str(k): v for k, v in sorted(results.items())}


def fetch_page(url, *, session=None):
    """One operator-triggered public GET. No crawling, login or retries."""
    import requests
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.netloc != "keiba.rakuten.co.jp":
        raise ValueError("楽天競馬の公開ページ以外へアクセスしません")
    client = session if session is not None else requests
    response = client.get(url, headers={"User-Agent": "KeibaAI-Research/1.0 (manual one-shot)"},
                          timeout=9, allow_redirects=False)
    if response.status_code != 200:
        raise ValueError(f"楽天競馬の公開ページから取得できません（HTTP {response.status_code}）")
    body = response.content
    if not body or len(body) > 4_000_000:
        raise ValueError("HTMLのサイズが想定範囲外です")
    for encoding in ("utf-8-sig", "cp932", "euc-jp"):
        try:
            return body.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("HTMLの文字コードを確認できません")


def _prestart(result, now):
    start = _timestamp(race_odds.start_from_result(result))
    return start, bool(start and now < start)


def _grade(horse):
    independent = horse.get("independent_ai_sabcd") or {}
    unified = horse.get("unified_sabcd") or {}
    if not isinstance(independent, Mapping) or not isinstance(unified, Mapping):
        return None
    grade = independent.get("grade")
    if (grade in GRADES and independent.get("source_model_id") == MODEL_ID
            and unified.get("grade") == grade):
        return grade
    return None


def make_observation(result, view, source_url, html, *, now=None, method="one_click_public_html"):
    identity = race_odds.identity_from_result(result)
    venue, day, rr = _date_race(identity, result.race_info or {})
    now = now or datetime.now(race_odds.JST)
    if now.tzinfo is None:
        raise ValueError("取得時刻にはタイムゾーンが必要です")
    rows = parse_card(html, source_url, identity, result.race_info or {})
    start, prestart = _prestart(result, now)
    by_no = {int(h["no"]): h for h in view}
    if set(by_no) != {x["horse_no"] for x in rows}:
        raise ValueError("予想画面と馬体重の出走馬が一致しません")
    for row in rows:
        row["sabcd"] = _grade(by_no[row["horse_no"]]) if prestart else None
    body = dict(race_id=identity["race_id"], mode="nar", race_date=day,
                venue=venue, race_number=rr, source_url=source_url,
                method=method, retrieved_at=now.isoformat(),
                publisher_updated_at=None, post_time=start.isoformat() if start else None,
                prestart_observed=prestart, rows=rows)
    body["observation_id"] = _hash(body)
    return body


def empty_book():
    return dict(schema=SCHEMA, races={})


def _valid_record(record):
    if not isinstance(record, Mapping) or record.get("mode") != "nar":
        return False
    if not re.fullmatch(r"20\d{10}", str(record.get("race_id") or "")):
        return False
    if not isinstance(record.get("rows"), list) or not _timestamp(record.get("retrieved_at")):
        return False
    return record.get("observation_id") == _hash({k: v for k, v in record.items()
                                                  if k != "observation_id"})


def add_observation(book, observation):
    """Append-only across race days; existing observations are unchanged."""
    if not _valid_record(observation):
        raise ValueError("馬体重観測レコードの形式・ハッシュが一致しません")
    out = deepcopy(book)
    races = out.setdefault("races", {})
    race = races.setdefault(observation["race_id"], dict(
        race_date=observation["race_date"], venue=observation["venue"],
        race_number=observation["race_number"], observations=[], result=None))
    for key in ("race_date", "venue", "race_number"):
        if race.get(key) != observation[key]:
            raise ValueError("同一レースIDの日時・開催場が食い違っています")
    existing = {x["observation_id"] for x in race["observations"]}
    if observation["observation_id"] not in existing:
        race["observations"].append(deepcopy(observation))
    return out


def latest_observation(book, race_id):
    race = (book.get("races") or {}).get(race_id) or {}
    values = race.get("observations") or []
    if not values:
        return None
    return max(values, key=lambda v: v["retrieved_at"])


def attach_result(book, race_id, ranks, *, source_url, now=None):
    """Result is never attached to a prediction or to a prestart observation."""
    now = now or datetime.now(race_odds.JST)
    out = deepcopy(book)
    race = (out.get("races") or {}).get(race_id)
    if race is None or not race.get("observations"):
        raise ValueError("先に発走前の馬体重観測を保存してください")
    if race.get("result") is not None:
        if race["result"].get("finishes") != ranks:
            raise ValueError("保存済み結果を上書きしません")
        return out
    race["result"] = dict(finishes=deepcopy(ranks), source_url=source_url,
                          recorded_at=now.isoformat(), source="rakuten_race_performance")
    return out


def merge_book(book, uploaded):
    """Import a previously downloaded book without overwriting existing rows."""
    if not isinstance(uploaded, dict) or uploaded.get("schema") != SCHEMA:
        raise ValueError("研究用の馬体重JSONではありません")
    out = deepcopy(book)
    for rid, race in (uploaded.get("races") or {}).items():
        for obs in race.get("observations", []):
            if obs.get("race_id") != rid:
                raise ValueError("JSON内のレースIDが一致しません")
            out = add_observation(out, obs)
        saved = race.get("result")
        if saved:
            own = out["races"][rid]
            if own["result"] and own["result"] != saved:
                raise ValueError("既に保存された確定着順とインポート内容が異なります")
            own["result"] = deepcopy(saved)
    return out


def cohort_rows(book):
    """Study one LAST prestart weight observation per race; no result leakage."""
    rows = []
    for rid, race in (book.get("races") or {}).items():
        result = race.get("result") or {}
        finishes = result.get("finishes") or {}
        if result.get("source") != "rakuten_race_performance":
            continue
        earlier = [o for o in race.get("observations", [])
                   if o.get("prestart_observed") and _valid_record(o)
                   and _timestamp(o.get("post_time"))
                   and _timestamp(o.get("retrieved_at")) < _timestamp(o.get("post_time"))]
        if not earlier:
            continue
        obs = max(earlier, key=lambda o: o["retrieved_at"])
        for h in obs["rows"]:
            grade = h.get("sabcd")
            band = h.get("band")
            position = finishes.get(str(h["horse_no"]))
            if grade not in GRADES or band not in BANDS or not isinstance(position, int) or position < 1:
                continue
            rows.append(dict(race_id=rid, race_date=obs["race_date"],
                             venue=obs["venue"], horse_no=h["horse_no"],
                             sabcd=grade, band=band, finish=position,
                             distance_from_range_kg=h["distance_from_range_kg"],
                             weight_change_kg=h["change_kg"]))
    return rows


def grade_summary(rows):
    counts = {}
    for h in rows:
        key = h["sabcd"], h["band"]
        cell = counts.setdefault(key, {"sabcd": key[0], "band": key[1],
                                       "count": 0, "win": 0, "top2": 0, "top3": 0})
        cell["count"] += 1
        cell["win"] += h["finish"] == 1
        cell["top2"] += h["finish"] <= 2
        cell["top3"] += h["finish"] <= 3
    return [counts.get((g,b), {"sabcd": g, "band": b, "count": 0,
                               "win": 0, "top2": 0, "top3": 0})
            for g in GRADES for b in BANDS]


def heldout_value(rows):
    """Prospective chronological comparison; never change ranks automatically.

    Fit grade-only and grade+weight two-place rates on EARLIER race days.
    Examine later distinct race days only. A positive delta alone is NOT a
    validated score adjustment (sampling error and selection remain).
    """
    days = sorted({r["race_date"] for r in rows})
    if len(days) < 10:
        return dict(status="insufficient", message="異なるレース日が10日未満。未使用期間で検証できません。")
    cut = max(1, int(len(days) * .7))
    train_days = set(days[:cut])
    train = [h for h in rows if h["race_date"] in train_days]
    test = [h for h in rows if h["race_date"] not in train_days]
    if len({h["race_id"] for h in train}) < 25 or len({h["race_id"] for h in test}) < 10:
        return dict(status="insufficient", message="学習25R・未使用10Rが揃っていません。")
    by_grade = {}
    by_detail = {}
    total = sum(h["finish"] <= 2 for h in train)
    overall = (total + 1) / (len(train) + 2)
    for h in train:
        for key, table in ((h["sabcd"], by_grade), ((h["sabcd"], h["band"]), by_detail)):
            pair = table.setdefault(key, [0, 0])
            pair[0] += 1
            pair[1] += h["finish"] <= 2
    baseline = extended = 0.
    for h in test:
        g = by_grade.get(h["sabcd"], [0,0])
        grade_rate = (g[1] + 10*overall)/(g[0]+10)
        a = by_detail.get((h["sabcd"], h["band"]), [0,0])
        weight_rate = (a[1] + 25*grade_rate)/(a[0]+25)
        actual = int(h["finish"] <= 2)
        baseline += (grade_rate - actual)**2
        extended += (weight_rate - actual)**2
    return dict(status="evaluated", train_horses=len(train), test_horses=len(test),
                train_days=len(train_days), test_days=len(days)-len(train_days),
                base_brier=round(baseline/len(test), 5),
                weight_brier=round(extended/len(test), 5),
                improvement_pct=round((baseline-extended)/baseline*100, 2) if baseline else 0,
                message="後半30%の開催日を未使用期間として比較。改善しても自動ランク変更は行いません。")
