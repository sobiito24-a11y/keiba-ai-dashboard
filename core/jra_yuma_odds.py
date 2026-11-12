"""Read-only, user-triggered import of historical JRA win/place published odds.

Source: two distinct, publicly viewable 優馬JAPAN tables. Not an API.
An HTTP rejection is reported, never bypassed with proxies or credentials.
Race date, venue, race number AND all saved horse names/numbers are checked.
"""
from datetime import datetime, date
import re
import unicodedata
from urllib.parse import urlparse, urljoin

from bs4 import BeautifulSoup

from .race_odds import JST, validate
from .jra_historical_odds_links import archived_odds_urls

VENUES = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
          "05": "東京", "06": "中山", "07": "中京", "08": "京都",
          "09": "阪神", "10": "小倉"}
SOURCE = "優馬JAPAN・過去の単勝複勝（公開掲載値）"
MAX_BYTES = 3_000_000
NUMBER = re.compile(r"^\d+(?:\.\d{1,2})?$")
PLACE_RANGE = re.compile(r"^(\d+(?:\.\d{1,2})?)[-~](\d+(?:\.\d{1,2})?)$")


def _clean(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def _number(value):
    s = _clean(value).replace(",", "").replace("倍", "")
    if not NUMBER.fullmatch(s):
        return None
    n = float(s)
    return n if 1 <= n <= 100000 else None


def _range(value):
    v = _clean(value).replace(",", "").replace("倍", "")
    for sign in ("～", "〜", "−", "―", "ー", "‐", "–", "—", "－", "ｰ"):
        v = v.replace(sign, "-")
    match = PLACE_RANGE.fullmatch(v)
    if not match:
        return None
    lo, hi = (_number(match.group(1)), _number(match.group(2)))
    return (lo, hi) if lo is not None and hi is not None and lo <= hi else None


def _race(identity, race_info):
    urls = archived_odds_urls(identity, race_info)
    rid = str(identity.get("race_id") or "")
    if not urls or rid[4:6] not in VENUES:
        raise ValueError("JRAレースIDまたは開催日が確認できません")
    daytext = str((race_info or {}).get("race_date") or (race_info or {}).get("date") or "").replace("/", "-")
    try:
        day = date.fromisoformat(daytext)
    except ValueError:
        raise ValueError("開催日が確認できません") from None
    return urls, day, VENUES[rid[4:6]], int(rid[10:12])


def parse_yuma_pages(htmls, identity, race_info, *, now=None):
    """Parse {tan: HTML, fuk: HTML}; accept a genuine partial one-kind batch.

    A provider page may have a decorative '印' column and select options;
    parse only the header-aligned cells, never arbitrary page-wide numbers.
    """
    now = now or datetime.now(JST)
    urls, day, venue, race_no = _race(identity, race_info)
    expected = {int(h["horse_no"]): _clean(h["name"]) for h in identity.get("horses", [])}
    if not expected:
        raise ValueError("保存された出走馬がありません")
    if not isinstance(htmls, dict) or not htmls:
        raise ValueError("過去単複の取得内容がありません")
    prices, missing = [], []
    for kind, column, quote_kind in (("tan", "単勝オッズ", "win"), ("fuk", "複勝オッズ", "place")):
        raw = htmls.get(kind)
        if raw is None:
            missing.append(quote_kind)
            continue
        soup = BeautifulSoup(raw, "html.parser")
        title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
        # Date and venue in this page's title are the independent race check.
        match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日(.+?)(\d{1,2})R", title)
        if (not match or tuple(map(int, match.group(1, 2, 3))) !=
                (day.year, day.month, day.day) or
                match.group(4) != venue or int(match.group(5)) != race_no):
            raise ValueError(f"優馬JAPANの{column}ページが保存レースと一致しません")
        if "予想オッズ" in title:
            raise ValueError("予想オッズは過去の実オッズとして反映しません")
        found = False
        observed = set()
        for table in soup.find_all("table"):
            head_row = table.find("tr")
            if head_row is None:
                continue
            heads = [_clean(c.get_text(" ", strip=True)) for c in head_row.find_all(["th", "td"], recursive=False)]
            if not all(h in heads for h in ("馬番", "馬名", column)):
                continue
            found = True
            indices = [heads.index(x) for x in ("馬番", "馬名", column)]
            for row in table.find_all("tr"):
                cells = [_clean(c.get_text(" ", strip=True)) for c in row.find_all(["th", "td"], recursive=False)]
                if len(cells) <= max(indices):
                    continue
                horse_num = cells[indices[0]]
                if not horse_num.isdecimal():
                    continue
                no = int(horse_num)
                if no not in expected or cells[indices[1]] != expected[no]:
                    raise ValueError(f"{column}の馬番・馬名が保存レースと一致しません（馬番{no}）")
                if no in observed:
                    raise ValueError(f"{column}の馬番{no}が重複しています")
                observed.add(no)
                value = cells[indices[2]]
                if quote_kind == "win":
                    val = _number(value)
                    if val is not None:
                        prices.append(dict(kind="win", horses=[no], low=val, high=val))
                else:
                    ran = _range(value)
                    if ran is not None:
                        prices.append(dict(kind="place", horses=[no], low=ran[0], high=ran[1]))
            break
        if not found:
            raise ValueError(f"{column}の表を読み取れません（HTML仕様変更の可能性）")
        if observed != set(expected):
            raise ValueError(f"{column}の馬番・馬名照合が不完全です（{len(observed)}/{len(expected)}頭）")
    if not prices:
        raise ValueError("有効な過去の単勝・複勝オッズを確認できません")
    return validate(dict(
        race_id=identity["race_id"], mode="jra",
        identities={str(h["horse_no"]): h["name"] for h in identity["horses"]},
        prices=prices, popularity={},
        observed_at=None, received_at=now.isoformat(),
        source=SOURCE, source_url=(urls["yuma_win"] if "tan" in htmls else urls["yuma_place"]),
        price_status="published_odds", availability="closed",
        acquisition_method="yuma_historical_html",
        missing_kinds=["quinella", "wide", *missing],
        warnings=["終了レースの掲載値。最終確定オッズと一致するかは別途照合してください",
                  "配信元の更新時刻は確認できません。受信日時はオッズ発表日時ではありません",
                  "元の予想スナップショット・ランク・印を変更しません"],
    ), identity)


def _get_page(get, url, kind):
    """Read only from the approved source, following at most one same-site redirect."""
    try:
        response = get(url, timeout=12, allow_redirects=False,
                       headers={"Accept": "text/html,application/xhtml+xml"})
    except Exception as exc:
        raise ValueError("優馬JAPANのサイトに接続できません") from exc
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get("Location", "")
        target = urljoin(url, location)
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.hostname not in ("www.keiba.jp", "keiba.jp"):
            raise ValueError("取得先が想定外のサイトへ移動したため中止しました")
        try:
            response = get(target, timeout=12, allow_redirects=False,
                           headers={"Accept": "text/html,application/xhtml+xml"})
        except Exception as exc:
            raise ValueError("優馬JAPANの移動先に接続できません") from exc
    if response.status_code != 200:
        raise ValueError(f"優馬JAPANの{kind}ページがHTTP {response.status_code}を返しました")
    if len(response.content) > MAX_BYTES:
        raise ValueError("取得ページのサイズが大きすぎます")
    return response.content


def fetch_once(identity, race_info, *, get=None, now=None):
    """One user action: exactly one win and one place page request, no polling."""
    urls, day, _, _ = _race(identity, race_info)
    now = now or datetime.now(JST)
    if day >= now.date():
        raise ValueError("終了済みの過去レースのみ取込対象です")
    if get is None:
        import requests
        get = requests.get
    htmls = {}
    htmls["tan"] = _get_page(get, urls["yuma_win"], "単勝")
    try:
        htmls["fuk"] = _get_page(get, urls["yuma_place"], "複勝")
    except ValueError as exc:
        # If only the second page fails, present known win odds as partial,
        # never copy place odds from saved predictions.
        quote = parse_yuma_pages(htmls, identity, race_info, now=now)
        quote["warnings"].append("複勝ページ未取得：" + str(exc))
        return quote
    return parse_yuma_pages(htmls, identity, race_info, now=now)
