"""User-triggered import of historical win/place odds from a public race page.

Read-only and limited to one saved JRA race at a time. A public web page is not
a stable API; failure must not change the saved prediction or reuse older odds.
No authentication, proxies, captcha handling, retries or automated polling.
"""
from datetime import datetime, date
import re
import unicodedata

from bs4 import BeautifulSoup

from .race_odds import JST, validate
from .jra_historical_odds_links import archived_odds_urls

VENUES = {"01": "札幌", "02": "函館", "03": "福島", "04": "新潟",
          "05": "東京", "06": "中山", "07": "中京", "08": "京都",
          "09": "阪神", "10": "小倉"}
SOURCE = "競馬ラボ・過去単勝複勝（掲載値）"
MAX_BYTES = 3_000_000
NUMBER = re.compile(r"^\d+(?:\.\d{1,2})?$")
STAMP = re.compile(r"※\s*(20\d{2})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2})時(\d{1,2})分現在")


def _clean(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value)))


def _num(value):
    s = _clean(value).replace(",", "").replace("倍", "")
    if not NUMBER.fullmatch(s):
        return None
    n = float(s)
    return n if 1 <= n <= 100000 else None


def _expected_race(identity, race_info):
    urls = archived_odds_urls(identity, race_info)
    rid = str(identity.get("race_id") or "")
    if not urls or rid[4:6] not in VENUES:
        raise ValueError("保存されたJRAレースの日付・IDを確認できません")
    race_date = str((race_info or {}).get("race_date") or (race_info or {}).get("date")).replace("/", "-")
    try:
        day = date.fromisoformat(race_date)
    except (ValueError, TypeError):
        raise ValueError("保存レースの日付が不明です") from None
    return urls["keibalab"], day, VENUES[rid[4:6]], int(rid[6:8]), int(rid[8:10]), int(rid[10:12])


def parse_keibalab_html(raw_html, identity, race_info, *, now=None):
    """Parse one known race's printed single/place table and its quote timestamp.

    Every horse number AND name must match the saved field; mixed/wrong race
    pages, truncated tables and predicted odds are rejected atomically.
    """
    now = now or datetime.now(JST)
    url, race_day, venue, meeting, course_day, race_no = _expected_race(identity, race_info)
    soup = BeautifulSoup(raw_html, "html.parser")
    title = _clean(soup.title.get_text(" ", strip=True) if soup.title else "")
    race_label = f"{race_day.year}年{race_day.month}月{race_day.day}日{venue}{race_no}R"
    if race_label not in title or "オッズ" not in title:
        raise ValueError("公開ページの開催日・競馬場・Rが保存レースと一致しません")
    # Ensure a race-specific page and not a redirect to an odds index/login.
    header_text = _clean(soup.get_text(" ", strip=True))
    marker = f"{meeting}回{venue}{course_day}日目"
    if marker not in header_text:
        raise ValueError("開催回・開催日が保存レースと一致しません")
    if "予想オッズ" in title or "発売開始前" in header_text[:1000]:
        raise ValueError("予想オッズ・発売前表示は実オッズとして反映しません")

    expected = {int(h["horse_no"]): _clean(h["name"]) for h in identity["horses"]}
    if not expected:
        raise ValueError("保存レースに出走馬がありません")
    prices, popularity, matched = [], {}, set()
    found_table = False
    for table in soup.find_all("table"):
        heads = _clean(" ".join(th.get_text(" ", strip=True) for th in table.find_all("th", limit=15)))
        if not all(token in heads for token in ("馬番", "馬名", "単勝", "複勝")):
            continue
        found_table = True
        for row in table.find_all("tr"):
            cells = [_clean(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"], recursive=False)]
            if len(cells) < 5:
                continue
            # Identify horse by the saved name, not just a bare table number.
            names = [(i, no) for i, text in enumerate(cells) for no, name in expected.items() if text == name]
            if len(names) != 1:
                continue
            ni, no = names[0]
            if ni < 1 or ni + 1 >= len(cells) or str(no) not in cells[:ni]:
                raise ValueError("馬名と馬番が一致しません")
            if no in matched:
                raise ValueError("同じ馬番が複数掲載されています")
            matched.add(no)
            win = _num(cells[ni + 1])
            if win is not None:
                prices.append(dict(kind="win", horses=[no], low=win, high=win))
            # Exclude the final popularity column. The place range can be
            # one cell ('1.2-1.5') or three cells ('1.2','-','1.5').
            tail = cells[ni + 2:]
            if tail and tail[-1].isdigit():
                pop = int(tail[-1])
                if 1 <= pop <= len(expected):
                    popularity[str(no)] = pop
                tail = tail[:-1]
            ranges = []
            for fragment in tail:
                ranges.extend(_num(x) for x in re.findall(r"\d+(?:\.\d+)?", fragment))
            ranges = [x for x in ranges if x is not None]
            if len(ranges) == 2 and ranges[0] <= ranges[1]:
                prices.append(dict(kind="place", horses=[no], low=ranges[0], high=ranges[1]))
        if found_table:
            break
    if not found_table:
        raise ValueError("単勝・複勝の表を発見できません（サイト仕様変更の可能性）")
    if matched != set(expected):
        raise ValueError(f"出走馬照合が不完全です（{len(matched)}/{len(expected)}頭）。反映しません")
    if not prices:
        raise ValueError("有効な単勝・複勝オッズがありません")
    stamp = STAMP.search(soup.get_text(" ", strip=True))
    observed_at = None
    if stamp:
        try:
            observed = datetime(*map(int, stamp.groups()), tzinfo=JST)
            if observed.date() != race_day or observed > now:
                raise ValueError("掲載更新日時が保存レースと一致しません")
            observed_at = observed.isoformat()
        except ValueError as exc:
            raise ValueError("掲載更新日時が正しくありません") from exc
    return validate(dict(
        race_id=identity["race_id"], mode="jra",
        identities={str(h["horse_no"]): h["name"] for h in identity["horses"]},
        prices=prices, popularity=popularity, observed_at=observed_at,
        received_at=now.isoformat(), source=SOURCE, source_url=url,
        acquisition_method="keibalab_historical_html",
        price_status="published_odds", availability="closed",
        warnings=["過去に掲載された単複価格で、確定最終オッズと同一かは未検証",
                  "予想時点の価格に置き換えず、振り返り用の別観測として保持"],
        missing_kinds=["quinella", "wide"],
    ), identity)


def fetch_once(identity, race_info, *, get=None, now=None):
    """One explicit per-race HTTP request; blocked access is reported honestly."""
    url, race_day, *_ = _expected_race(identity, race_info)
    now = now or datetime.now(JST)
    if now.date() <= race_day:
        raise ValueError("過去レース用の取得機能です。開催中は既存のJRAオッズを使用してください")
    if get is None:
        import requests
        get = requests.get
    try:
        response = get(url, timeout=12, allow_redirects=False,
                       headers={"Accept": "text/html,application/xhtml+xml"})
    except Exception as exc:
        raise ValueError("競馬ラボに接続できません。公開ページのHTML保存取込をご利用ください") from exc
    if response.status_code != 200:
        if response.status_code in (401, 403, 429):
            raise ValueError(f"競馬ラボからHTTP {response.status_code}。アクセス制限を迂回しません")
        raise ValueError(f"競馬ラボからHTTP {response.status_code}。ページを取得できません")
    if len(response.content) > MAX_BYTES:
        raise ValueError("ページサイズが大きすぎるため取込を中止しました")
    content = response.content
    if not content or b"<" not in content[:300]:
        raise ValueError("オッズHTMLが取得できませんでした")
    return parse_keibalab_html(content, identity, race_info, now=now)
