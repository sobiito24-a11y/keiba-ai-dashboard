"""One-shot historical JRA single/place odds from Sports Navi's public race page.

No authentication, polling, retries, proxies or access-control bypass. The
record is a separately sourced, past-race price observation; it does not alter
AI grades, predictions or marks. A race must match date, venue, meeting/day,
race number, and every saved horse number AND name before any price is used.
"""
from datetime import datetime, date
from urllib.parse import urljoin, urlparse
import re
import unicodedata

from bs4 import BeautifulSoup

from .race_odds import JST, validate
from .jra_historical_odds_links import archived_odds_urls
from .jra_yuma_odds import VENUES

SOURCE = "スポーツナビ・過去の確定単勝複勝（公開掲載値）"
LIVE_SOURCE = "スポーツナビ・当日の中間単勝複勝（公開掲載値）"
MAX_BYTES = 3_000_000
NUM = re.compile(r"^\d+(?:\.\d{1,2})?$")
RANGE = re.compile(r"^(\d+(?:\.\d{1,2})?)-(\d+(?:\.\d{1,2})?)$")
UPDATED = re.compile(r"(20\d{2})[/-](\d{1,2})[/-](\d{1,2})\s+(\d{1,2}):(\d{2})\s*更新")


def _clean(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def _number(value):
    value = _clean(value).replace(",", "").replace("倍", "")
    if not NUM.fullmatch(value):
        return None
    number = float(value)
    return number if 1 <= number <= 100000 else None


def _range(value):
    value = _clean(value).replace("倍", "")
    for sign in ("～", "〜", "−", "―", "ー", "‐", "–", "—", "－", "ｰ", "~"):
        value = value.replace(sign, "-")
    match = RANGE.fullmatch(value)
    if not match:
        return None
    low, high = (_number(match.group(1)), _number(match.group(2)))
    return (low, high) if low is not None and high is not None and low <= high else None


def _race(identity, race_info):
    urls = archived_odds_urls(identity, race_info)
    rid = str(identity.get("race_id") or "")
    if not urls or "sportsnavi" not in urls or rid[4:6] not in VENUES:
        raise ValueError("JRAレースIDまたは開催日が不正です")
    daytext = str((race_info or {}).get("race_date") or
                  (race_info or {}).get("date") or "").replace("/", "-")
    try:
        day = date.fromisoformat(daytext)
    except (TypeError, ValueError):
        raise ValueError("保存レースの開催日が不明です") from None
    meeting, course_day, race_no = (int(rid[6:8]), int(rid[8:10]), int(rid[10:12]))
    if not 1 <= meeting <= 10 or not 1 <= course_day <= 12:
        raise ValueError("開催回・開催日が正しくありません")
    return urls["sportsnavi"], day, VENUES[rid[4:6]], meeting, course_day, race_no


def parse_sportsnavi_html(raw_html, identity, race_info, *, now=None, odds_stage="historical"):
    now = now or datetime.now(JST)
    if odds_stage not in ("historical", "intermediate"):
        raise ValueError("スポーツナビのオッズ種別が不正です")
    url, race_day, venue, meeting, course_day, race_no = _race(identity, race_info)
    if odds_stage == "intermediate" and race_day != now.date():
        raise ValueError("当日掲載オッズは保存レースの開催当日のみ対象です")
    soup = BeautifulSoup(raw_html, "html.parser")
    main = soup.find("main")
    if main is None:
        raise ValueError("スポーツナビのレース本文が見つかりません")
    text = _clean(main.get_text(" ", strip=True))
    formatted_day = f"{race_day.year}年{race_day.month}月{race_day.day}日"
    marker = f"{meeting}回{venue}{course_day}日"
    # This sequence appears in the current-race header; simply finding '11R'
    # in the page navigation would not be sufficient.
    heading = re.escape(f"{race_no}R{formatted_day}") + r"(?:\([^)]{1,4}\))?" + re.escape(marker)
    if re.search(heading, text) is None:
        raise ValueError("スポーツナビの開催日・会場・回次・Rが保存レースと一致しません")
    if odds_stage == "historical" and "確定オッズ" not in text:
        raise ValueError("確定オッズ表示を確認できないため反映しません")
    if odds_stage == "intermediate" and "中間オッズ" not in text:
        raise ValueError("当日の中間オッズ表示を確認できないため反映しません")
    # This race page can contain the words "予想オッズ" in a navigation or
    # related-items area even when the current race's table is explicitly
    # labelled "確定オッズ". The complete race identity and table contents
    # below are still independently validated; do not reject based on
    # unrelated surrounding text.
    saved = {int(h["horse_no"]): _clean(h["name"]) for h in identity["horses"]}
    if not saved:
        raise ValueError("保存済み出走馬がありません")
    matches = set()
    prices = []
    table_found = False
    for table in main.find_all("table"):
        first = table.find("tr")
        if first is None:
            continue
        heads = [_clean(c.get_text(" ", strip=True))
                 for c in first.find_all(["th", "td"], recursive=False)]
        if not all(token in heads for token in ("馬番", "馬名", "単勝", "複勝")):
            continue
        table_found = True
        indices = [heads.index(key) for key in ("馬番", "馬名", "単勝", "複勝")]
        for tr in table.find_all("tr"):
            cells = [_clean(c.get_text(" ", strip=True))
                     for c in tr.find_all(["th", "td"], recursive=False)]
            if len(cells) <= max(indices):
                continue
            value = cells[indices[0]]
            if not value.isdecimal():
                continue
            no = int(value)
            if no not in saved or cells[indices[1]] != saved[no]:
                raise ValueError(f"スポーツナビの馬番・馬名が一致しません（馬番{no}）")
            if no in matches:
                raise ValueError(f"同じ馬番{no}が重複しています")
            matches.add(no)
            win = _number(cells[indices[2]])
            if win is not None:
                prices.append(dict(kind="win", horses=[no], low=win, high=win))
            place = _range(cells[indices[3]])
            if place is not None:
                prices.append(dict(kind="place", horses=[no], low=place[0], high=place[1]))
        break
    if not table_found:
        raise ValueError("単勝・複勝の公開表を読み取れません（表示変更の可能性）")
    if matches != set(saved):
        raise ValueError(f"出走馬の照合が不完全です（{len(matches)}/{len(saved)}頭）。反映を中止します")
    if not prices:
        raise ValueError("有効な単勝・複勝オッズがありません")
    if odds_stage == "intermediate":
        win_numbers = {p["horses"][0] for p in prices if p["kind"] == "win"}
        place_numbers = {p["horses"][0] for p in prices if p["kind"] == "place"}
        if win_numbers != set(saved) or place_numbers != set(saved):
            raise ValueError("当日単勝・複勝の全頭価格が揃っていません。反映を中止します")
    observed_at = None
    match = UPDATED.search(main.get_text(' ', strip=True))
    if match:
        try:
            published = datetime(*map(int, match.groups()), tzinfo=JST)
            if published.date() != race_day or published > now:
                raise ValueError("公開ページの更新日が開催日と一致しません")
            observed_at = published.isoformat()
        except ValueError as exc:
            raise ValueError("公開ページの更新日が不正です") from exc
    quote = dict(
        race_id=identity["race_id"], mode="jra",
        identities={str(h["horse_no"]): h["name"] for h in identity["horses"]},
        prices=prices, popularity={}, withdrawn=[],
        source=(LIVE_SOURCE if odds_stage == "intermediate" else SOURCE),
        source_url=url, observed_at=observed_at,
        received_at=now.isoformat(),
        acquisition_method=("sportsnavi_intermediate_html" if odds_stage == "intermediate"
                            else "sportsnavi_historical_html"),
        price_status="published_odds",
        availability=("unknown" if odds_stage == "intermediate" else "closed"),
        missing_kinds=["quinella", "wide"],
        warnings=([
            "当日の中間オッズで、購入直前の最新価格と一致する保証はありません",
            "サイトの更新時刻がない場合、取得時刻を価格更新時刻と扱いません",
            "必ず購入直前にJRA公式のオッズを再確認してください",
        ] if odds_stage == "intermediate" else [
            "スポーツナビが公表する終了レースの確定オッズ。予想時点の価格とは異なります",
            "サイトの掲載時刻が取得できない場合、受信時刻を配信更新時刻として扱いません",
        ]) + ["保存予想・ランク・純能力・印は変更していません"],
    )
    return validate(quote, identity)


def fetch_once(identity, race_info, *, get=None, now=None):
    now = now or datetime.now(JST)
    url, day, *_ = _race(identity, race_info)
    if day >= now.date():
        raise ValueError("終了済みの過去レースのみ対象です")
    if get is None:
        import requests
        get = requests.get

    def request(address):
        try:
            return get(address, timeout=12, allow_redirects=False,
                       headers={"Accept": "text/html,application/xhtml+xml"})
        except Exception as exc:
            from .jra_odds_connection_errors import describe_connection
            raise ValueError("スポーツナビへ接続できません（" +
                             describe_connection(exc) + "）") from exc

    response = request(url)
    if response.status_code in (301, 302, 303, 307, 308):
        target = urljoin(url, (getattr(response, "headers", {}) or {}).get("Location", ""))
        original, next_url = urlparse(url), urlparse(target)
        if (next_url.scheme != "https"
                or next_url.hostname != "sports.yahoo.co.jp"
                or next_url.path != original.path
                or next_url.query != original.query):
            raise ValueError("スポーツナビの移動先が保存レースと異なります")
        response = request(target)
    if response.status_code != 200:
        raise ValueError(f"スポーツナビの公開オッズ画面はHTTP {response.status_code}です")
    if len(response.content) > MAX_BYTES or not response.content:
        raise ValueError("スポーツナビのHTMLが空または3MB超過です")
    return parse_sportsnavi_html(response.content, identity, race_info, now=now)

def fetch_live_once(identity, race_info, *, get=None, now=None):
    """One explicit request for SAME-DAY public intermediate win/place odds.

    Never claim the download time is the odds update time. Strictly verify
    the saved race header and every saved horse number/name and BOTH prices.
    No automatic polling, proxies, retries or private API endpoints.
    """
    now = now or datetime.now(JST)
    url, day, *_ = _race(identity, race_info)
    if day != now.date():
        raise ValueError("スポーツナビの当日中間オッズは開催日のみ取得できます")
    if get is None:
        import requests
        get = requests.get
    try:
        response = get(url, timeout=12, allow_redirects=False,
                       headers={"Accept": "text/html,application/xhtml+xml"})
    except Exception as exc:
        from .jra_odds_connection_errors import describe_connection
        raise ValueError("スポーツナビ当日オッズに接続できません（"
                         + describe_connection(exc) + "）") from exc
    if response.status_code != 200:
        raise ValueError(f"スポーツナビ当日オッズはHTTP {response.status_code}です")
    if not response.content or len(response.content) > MAX_BYTES:
        raise ValueError("スポーツナビの当日HTMLが空または3MB超過です")
    return parse_sportsnavi_html(response.content, identity, race_info,
                                 now=now, odds_stage="intermediate")
