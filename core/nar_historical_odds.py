"""Past NAR *final* win/place odds from the official monthly CSV download.

NAR publishes monthly ZIP archives containing finalized prices, split into
10-day odds CSV parts. The current-day ZIP is never valid for past races.
Fetch only when the user explicitly requests; no continuous collection.
"""
from __future__ import annotations

import csv
from datetime import datetime
import io
import re
from zipfile import ZipFile, BadZipFile

from . import nar_official_odds as official
from .race_odds import JST, validate

MONTHLY_URL = (
    "https://www.keiba.go.jp/KeibaWeb/DataDownload/OddsDataDownload"
)
MONTHLY_PAGE = (
    "https://www.keiba.go.jp/KeibaWeb/MonthlyConveneInfo/MonthlyConveneInfoTop"
)
MAX_ZIP_BYTES = 100_000_000
MAX_PART_BYTES = 220_000_000


def _period(day: str) -> str:
    return "01" if int(day[-2:]) <= 10 else "02" if int(day[-2:]) <= 20 else "03"


def parse_monthly_zip(raw, filename, identity, race_info, *, now=None):
    """Select the exact ten-day CSV and venue/day/race, without mixing prices."""
    venue, day, race_no = official.locator(identity, race_info)
    now = now or datetime.now(JST)
    when = datetime.strptime(day, "%Y%m%d").date()
    if when >= now.date():
        raise ValueError("当日または未来のレースは過去オッズ取得の対象外です")
    if when < datetime(2026, 3, 1).date():
        raise ValueError("NAR公式の月次オッズは2026年3月以降が対象です")
    month = day[:6]
    name = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    match = re.fullmatch(r"(20\d{4})_(\d{9,11})_odds\.zip", name, re.I)
    if not match or match.group(1) != month:
        raise ValueError("対象年月と公式の月次オッズZIP名が一致しません")
    if not raw.startswith(b"PK") or len(raw) > MAX_ZIP_BYTES:
        raise ValueError("月次オッズZIPが不正または上限100MBを超過しています")
    part = f"{month}_{_period(day)}_odds.csv"
    try:
        with ZipFile(io.BytesIO(raw)) as zf:
            entries = zf.infolist()
            if len(entries) > 60:
                raise ValueError("月次ZIPのファイル数が想定より多すぎます")
            found = [item for item in entries
                     if item.filename.replace("\\", "/").rsplit("/", 1)[-1].lower()
                     == part.lower()]
            if len(found) != 1:
                raise ValueError("該当日を含む10日単位の公式オッズCSVがありません")
            meta = found[0]
            if (meta.file_size > MAX_PART_BYTES
                    or meta.file_size > 500 * max(1, meta.compress_size)):
                raise ValueError("公式オッズCSVの展開容量が上限を超過しています")
            data = zf.read(meta)
    except (BadZipFile, OSError, RuntimeError) as exc:
        raise ValueError("公式月次ZIPの展開に失敗しました") from exc

    decoded = official._decode(data)
    reader = csv.DictReader(io.StringIO(decoded))
    if not reader.fieldnames:
        raise ValueError("公式月次CSVの列名を確認できません")
    reader.fieldnames = [official._text(x) for x in reader.fieldnames]
    required = ("競馬場", "競走年月日", "レース番号", "賭式", "番号1", "オッズ")
    if not all(any(alias in reader.fieldnames for alias in official.HEADER[k]) for k in required):
        raise ValueError("公式月次CSVの列構成が変更されています")

    saved = {int(h["horse_no"]): h["name"] for h in identity["horses"]}
    prices, popularity, seen = [], {}, {}
    matched_rows = 0
    for line, original in enumerate(reader, 1):
        if line > 2_500_000:
            raise ValueError("公式月次CSVの行数が上限を超過しました")
        row = {official._text(k): v for k, v in original.items() if k is not None}
        if (official._text(official._pick(row, "競馬場")) != venue
                or re.sub(r"\D", "", official._normal(
                    official._pick(row, "競走年月日"))) != day
                or official._horse_number(
                    official._pick(row, "レース番号")) != race_no):
            continue
        matched_rows += 1
        kind = official.KIND.get(official._text(official._pick(row, "賭式")))
        if kind not in ("win", "place"):
            continue
        no = official._horse_number(official._pick(row, "番号1"))
        if no is None:
            continue
        if no not in saved:
            raise ValueError(f"保存されていない馬番{no}を公式CSVで検出しました")
        low = official._positive_number(official._pick(row, "オッズ"))
        high = official._positive_number(official._pick(row, "オッズ(最大)")) or low
        if low is None:
            continue
        if high < low or (kind == "win" and low != high):
            raise ValueError("月次CSVに不正な単勝・複勝の上下限があります")
        price_key = (kind, no)
        if price_key in seen:
            if seen[price_key] != (low, high):
                raise ValueError("同一馬番・券種に異なる確定オッズがあります")
            continue
        seen[price_key] = (low, high)
        prices.append(dict(kind=kind, horses=[no], low=low, high=high))
        if kind == "win":
            pop = official._horse_number(official._pick(row, "人気"))
            if pop is not None and pop <= len(saved):
                popularity[str(no)] = pop
    if not matched_rows or not prices:
        raise ValueError("指定レースの確定単勝・複勝オッズが月次CSVにありません")
    return validate(dict(
        race_id=identity["race_id"], mode="nar",
        identities={str(k): v for k, v in saved.items()},
        prices=prices, popularity=popularity, withdrawn=[],
        observed_at=None, received_at=now.isoformat(),
        source="NAR公式月次ZIP・確定単複オッズ",
        source_url=MONTHLY_PAGE,
        price_status="final_historical_odds",
        acquisition_method="nar_official_monthly_zip",
        availability="closed",
        warnings=["公式月次CSVに馬名がないため保存馬番との照合です",
                  "確定最終オッズは購入直前のオッズとは異なります",
                  "ファイル作成時刻を個別オッズの発表時刻として扱いません"],
        missing_kinds=["quinella", "wide"],
    ), identity)


def fetch_monthly(*, year: int, month: int, get=None):
    """One official download on a user action; never retry, proxy or bypass."""
    if not (2026 <= year <= 2100 and 1 <= month <= 12):
        raise ValueError("取得年月が不正です")
    if get is None:
        import requests
        get = requests.get
    params = {"k_year": str(year), "k_month": str(month), "type": "monthly"}
    try:
        response = get(MONTHLY_URL, params=params, headers={
            "Accept": "application/zip,application/octet-stream",
            "User-Agent": "KeibaPersonalOdds/1.0 (one-shot private-session access)",
            "Referer": MONTHLY_PAGE,
        }, stream=True, timeout=35, allow_redirects=False)
        with response:
            if response.status_code != 200:
                raise ValueError(f"公式月次ZIPがHTTP {response.status_code}を返しました")
            filename = official._download_filename(response)
            if not filename:
                raise ValueError("公式の月次ZIPファイル名を確認できません")
            buf = bytearray()
            for chunk in response.iter_content(chunk_size=262144):
                buf.extend(chunk)
                if len(buf) > MAX_ZIP_BYTES:
                    raise ValueError("公式月次ZIPが100MBを超過しています")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("NAR公式の月次ZIPに接続できません") from exc
    return filename, bytes(buf)


def fetch_once(identity, race_info, *, get=None, now=None):
    """Read final monthly odds for one saved past race, using its own date."""
    _, day, _ = official.locator(identity, race_info)
    now = now or datetime.now(JST)
    if datetime.strptime(day, "%Y%m%d").date() >= now.date():
        raise ValueError("過去レースではありません")
    filename, payload = fetch_monthly(year=int(day[:4]), month=int(day[4:6]), get=get)
    return parse_monthly_zip(payload, filename, identity, race_info, now=now)
