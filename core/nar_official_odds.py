"""User-requested NAR official *daily* ZIP/CSV odds, read-only.

Official entry: https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop
CSV schema: https://www.keiba.go.jp/pdf/manual/data_pdf_manual.pdf (May 2026)
No crawler, automatic polling, guessed horse names, or public redistribution.
The ZIP filename's Unix timestamp is a *file creation* estimate, NOT the
publisher's actual odds-update time.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import math
import re
import unicodedata
from zipfile import ZipFile, BadZipFile
from urllib.parse import unquote
from .race_odds import JST, validate

OFFICIAL_URL = "https://www.keiba.go.jp/KeibaWeb/DataDownload/OddsDataDownload?type=daily"
OFFICIAL_PAGE = "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop"
ZIP_LIMIT = 50_000_000
CSV_LIMIT = 150_000_000
KNOWN_RACE_CODES = {
    "30": "門別", "35": "盛岡", "42": "浦和", "43": "船橋",
    "44": "大井", "45": "川崎", "46": "金沢", "47": "笠松",
    "48": "名古屋", "50": "園田",
}
KIND = {
    "単勝": "win", "複勝": "place", "馬複": "quinella",
    "馬連": "quinella", "馬連複": "quinella", "ワイド": "wide",
}
HEADER = {
    "競馬場": ("競馬場",), "競走年月日": ("競走年月日",),
    "レース番号": ("レース番号",), "賭式": ("賭式",),
    "番号1": ("番号1",), "番号2": ("番号2",),
    "番号3": ("番号3",), "オッズ": ("オッズ",),
    "オッズ(最大)": ("オッズ(最大)", "オッズ最大"),
    "人気": ("人気",),
}


def _normal(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip().replace("﨑", "崎")


def _text(value):
    return re.sub(r"\s+", "", _normal(value))


def _positive_number(value):
    x = _normal(value).replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", x):
        return None
    y = float(x)
    return y if math.isfinite(y) and 1 <= y <= 999999 else None


def _horse_number(value):
    s = _normal(value)
    if not re.fullmatch(r"\d{1,2}", s):
        return None
    n = int(s)
    return n if n > 0 else None


def locator(identity, race_info):
    """Refuse a non-NAR race, incompatible race date or known venue mismatch."""
    if identity.get("mode") != "nar":
        raise ValueError("NAR公式の当日ZIPは地方競馬だけが対象です")
    race_id = str(identity.get("race_id", ""))
    if not re.fullmatch(r"20\d{10}", race_id):
        raise ValueError("12桁の保存レースIDがありません")
    year, month_day, rr = race_id[:4], race_id[6:10], race_id[10:12]
    day = year + month_day
    try:
        datetime.strptime(day, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("保存レースの日付を確認できません") from exc
    venue = _text((race_info or {}).get("racecourse") or
                  (race_info or {}).get("venue") or (race_info or {}).get("場名"))
    if not venue:
        raise ValueError("保存レースの開催場が取得できません")
    mapped = KNOWN_RACE_CODES.get(race_id[4:6])
    if mapped and venue != mapped:
        raise ValueError("レースIDと保存されている競馬場が一致しません")
    stated = _text((race_info or {}).get("race_date") or (race_info or {}).get("date"))
    if stated and re.sub(r"[^0-9]", "", stated) != day:
        raise ValueError("レースIDと保存日付が一致しません")
    return venue, day, int(rr)


def _zip_time(filename, target_date):
    basename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    m = re.fullmatch(r"(20\d{6})_(\d{9,11})_odds\.zip", basename, re.I)
    if not m:
        raise ValueError("公式の当日オッズZIP形式（YYYYMMDD_timestamp_odds.zip）ではありません")
    if m[1] != target_date:
        raise ValueError("オッズZIPの日付が表示中のレースと一致しません")
    try:
        time = datetime.fromtimestamp(int(m[2]), JST)
    except (ValueError, OSError, OverflowError) as exc:
        raise ValueError("ZIP作成時刻を読み取れません") from exc
    if time.strftime("%Y%m%d") != target_date:
        raise ValueError("ZIP作成日と対象日が一致しません")
    return time


def _decode(data):
    for encoding in ("utf-8-sig", "cp932"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("オッズCSVの文字コードを識別できません")


def _pick(row, key):
    return next((row[n] for n in HEADER[key] if n in row), "")


def parse_daily_zip(raw, filename, identity, race_info, *, now=None):
    """Convert only the exact saved venue/date/race into validated prices.

    Odds CSV has *horse numbers only*, not names. We verify those numbers
    against the saved pre-race lineup, but cannot independently attest names.
    """
    now = now or datetime.now(JST)
    venue, day, race_no = locator(identity, race_info)
    snapshot_time = _zip_time(filename, day)
    if len(raw) > ZIP_LIMIT:
        raise ValueError("公式ZIPが大きすぎます（50MB上限）")
    if not raw.startswith(b"PK"):
        raise ValueError("公式のZIPデータを取得できません（HTML応答の可能性）")
    try:
        with ZipFile(io.BytesIO(raw)) as zf:
            entries = zf.infolist()
            if len(entries) > 30:
                raise ValueError("ZIPの中身が想定より多すぎます")
            candidates = [x for x in entries
                          if re.fullmatch(rf"{day}_odds\.csv", x.filename.replace("\\", "/").rsplit("/",1)[-1], re.I)]
            if len(candidates) != 1:
                raise ValueError("当日分の公式オッズCSVを一意に確認できません")
            info = candidates[0]
            if info.file_size > CSV_LIMIT or info.file_size > 500 * max(1, info.compress_size):
                raise ValueError("CSVの展開容量が大きすぎます")
            data = zf.read(info)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("オッズZIPの展開に失敗しました") from exc
    reader = csv.DictReader(io.StringIO(_decode(data)))
    if not reader.fieldnames:
        raise ValueError("オッズCSVに見出しがありません")
    reader.fieldnames = [_text(x) for x in reader.fieldnames]
    required = ("競馬場", "競走年月日", "レース番号", "賭式", "番号1", "オッズ")
    if not all(any(alias in reader.fieldnames for alias in HEADER[key]) for key in required):
        raise ValueError("公式CSVに必要な列がありません（仕様変更の可能性）")
    saved = {int(h["horse_no"]): h["name"] for h in identity["horses"]}
    prices, popularity, seen, candidates_count = [], {}, {}, 0
    for i, original in enumerate(reader, 1):
        if i > 1_000_000:
            raise ValueError("CSVの行数が多すぎます")
        row = {_text(k): value for k, value in original.items() if k is not None}
        if (_text(_pick(row, "競馬場")) != venue or
            re.sub(r"[^0-9]", "", _normal(_pick(row, "競走年月日"))) != day or
            _horse_number(_pick(row, "レース番号")) != race_no):
            continue
        candidates_count += 1
        kind = KIND.get(_text(_pick(row, "賭式")))
        if kind is None:
            continue
        a = _horse_number(_pick(row, "番号1"))
        b = _horse_number(_pick(row, "番号2")) if kind in ("quinella", "wide") else None
        ns = [a, b] if b is not None else [a]
        if a is None or (kind in ("wide", "quinella") and b is None) or len(ns) != len(set(ns)):
            continue
        if any(n not in saved for n in ns):
            raise ValueError("CSVに保存出走馬と一致しない馬番があります（出走表を確認）")
        lo = _positive_number(_pick(row, "オッズ"))
        hi = _positive_number(_pick(row, "オッズ(最大)")) or lo
        if lo is None:
            continue
        if hi < lo or (kind in ("win", "quinella") and hi != lo):
            raise ValueError("公式CSVの券種・オッズ上限が不正です")
        key = (kind, tuple(sorted(ns)))
        if key in seen:
            if seen[key] != (lo, hi):
                raise ValueError("同じ買い目に異なる価格が混在しています")
            continue
        seen[key] = lo, hi
        prices.append(dict(kind=kind, horses=ns, low=lo, high=hi))
        if kind == "win":
            pop = _horse_number(_pick(row, "人気"))
            if pop is not None and pop <= len(saved):
                popularity[str(a)] = pop
    if not candidates_count or not prices:
        raise ValueError("この開催場・レースの有効な発売オッズが見つかりません")
    q = dict(
        race_id=identity["race_id"], mode="nar",
        identities={str(k): v for k, v in saved.items()},
        prices=prices, popularity=popularity, withdrawn=[],
        observed_at=snapshot_time.isoformat(),
        received_at=now.isoformat(),
        source="NAR公式オッズZIP",
        source_url=OFFICIAL_URL,
        price_status="official_zip_snapshot",
        acquisition_method="nar_official_zip",
        timestamp_kind="zip_file_created_not_odds_updated",
        warnings=["ZIP作成時刻は個別オッズ発表時刻ではありません",
                  "公式CSVに馬名はないため、保存した馬番一覧でのみ照合しています",
                  "欠損買い目は過去の値で補完しません"],
    )
    return validate(q, identity)


def _download_filename(response):
    cd = response.headers.get("Content-Disposition", "")
    match = re.search(r"filename\*?=(?:UTF-8''|[\"'])?([^\"';\s]+)", cd, re.I)
    return unquote(match[1]) if match else ""


def fetch_daily(*, get=None):
    """One explicit user action; never background-poll the NAR site."""
    if get is None:
        import requests
        get = requests.get
    try:
        response = get(OFFICIAL_URL, headers={
            "Accept": "application/zip,application/octet-stream",
            "User-Agent": "KeibaPersonalOdds/1.0 (one-shot private-session access)",
            "Referer": OFFICIAL_PAGE,
        }, stream=True, timeout=20, allow_redirects=False)
        with response:
            if response.status_code != 200:
                raise ValueError(f"公式サイト応答 HTTP {response.status_code}")
            name = _download_filename(response)
            if not name:
                raise ValueError("公式ZIPの作成日時を含むファイル名を確認できません")
            buf = bytearray()
            for chunk in response.iter_content(chunk_size=262144):
                buf.extend(chunk)
                if len(buf) > ZIP_LIMIT:
                    raise ValueError("公式オッズZIPが上限50MBを超えました")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("NAR公式サイトへの接続に失敗しました") from exc
    return name, bytes(buf)
