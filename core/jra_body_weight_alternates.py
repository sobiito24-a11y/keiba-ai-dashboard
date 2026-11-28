"""Read-only fallback for current JRA horse weights from public racecards.

Sportsnavi is the first alternative; netkeiba is the second.
Accept current weights only when date, meeting, race number, horse number and
horse name match the saved prediction. No guessing from previous races.
Never updates predictions, ranks, odds or saved race snapshots.
"""
from __future__ import annotations

import math
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, NavigableString


HOSTS = {
    "sportsnavi": "sports.yahoo.co.jp",
    "netkeiba": "race.netkeiba.com",
}
CURRENT = re.compile(r"^(\d{3})\(([+-]?\d{1,2}|±0|初出走|[-—―]+)\)$")


def _norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).replace("﨑", "崎")


def sources(identity, info):
    """Use a saved JRA race ID only; never build a URL from a guessed date."""
    from .jra_body_weight import race_facts
    rid, _venue, _day, _meeting, _meeting_day, _race_no = race_facts(identity, info)
    return [
        ("sportsnavi", f"https://sports.yahoo.co.jp/keiba/race/denma/{rid[2:]}"),
        ("netkeiba", f"https://race.netkeiba.com/race/shutuba.html?race_id={rid}"),
    ]


def _validate_source(url, origin, identity, info):
    from .jra_body_weight import race_facts
    rid, venue, day, meeting, meeting_day, race_no = race_facts(identity, info)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOSTS.get(origin):
        raise ValueError("検証対象外の馬体重提供元です")
    if origin == "sportsnavi":
        if parsed.path != f"/keiba/race/denma/{rid[2:]}":
            raise ValueError("スポーツナビのレースIDが一致しません")
    elif origin == "netkeiba":
        if (parsed.path != "/race/shutuba.html"
                or parse_qs(parsed.query).get("race_id") != [rid]):
            raise ValueError("netkeibaのレースIDが一致しません")
    else:
        raise ValueError("未登録の馬体重提供元です")
    return rid, venue, day, meeting, meeting_day, race_no


def _heading(soup, origin, identity, info):
    rid, venue, day, meeting, meeting_day, race_no = _validate_source(
        sources(identity, info)[0 if origin == "sportsnavi" else 1][1],
        origin, identity, info)
    body = _norm(soup.get_text(" ", strip=True))
    title = _norm(soup.title.get_text(" ", strip=True)) if soup.title else ""
    combined = body + title
    date = f"{int(day[:4])}年{int(day[4:6])}月{int(day[6:8])}日"
    # A saved historical page, wrong meeting or pre-entry "expected starters"
    # must not become live bodyweight evidence.
    if (date not in combined or f"{meeting}回{venue}{meeting_day}日" not in combined
            or not any(f"{race_no}{unit}" in combined for unit in ("R", "レース"))):
        raise ValueError("別日・別競馬場・別レースの出馬表です")
    if "出走想定" in combined and "仮想の出馬表" in combined:
        raise ValueError("出走想定は当日馬体重として使用しません")


def _headings(table):
    for tr in table.find_all("tr"):
        headers = tr.find_all("th", recursive=False)
        if not headers:
            continue
        found = [_norm(h.get_text(" ", strip=True)) for h in headers]
        indices = {}
        for key in ("馬番", "馬名", "馬体重"):
            indices[key] = next((i for i, h in enumerate(found) if h.startswith(key)), None)
        if all(v is not None for v in indices.values()):
            return indices
    return None


def _name(cell):
    direct = _norm(" ".join(str(n) for n in cell.contents if isinstance(n, NavigableString)))
    if direct:
        return direct
    for tag in ("p", "a", "strong"):
        child = cell.find(tag)
        if child:
            return _norm(child.get_text(" ", strip=True))
    return ""


def parse_card(html, url, origin, identity, info):
    """Produce complete verified entries with current mass and delta only.

    A previous 1st/2nd bodyweight is NOT inferred from this source; the JRA
    official past-results columns remain a separate provenance.
    """
    _validate_source(url, origin, identity, info)
    soup = BeautifulSoup(html, "html.parser")
    _heading(soup, origin, identity, info)
    saved = {}
    for horse in identity.get("horses") or ():
        try:
            no = int(horse["horse_no"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("保存馬番が不正です") from exc
        name = _norm(horse.get("name"))
        if not 1 <= no <= 20 or not name or no in saved:
            raise ValueError("保存馬番・馬名が欠損または重複しています")
        saved[no] = name
    if not saved:
        raise ValueError("出走馬の保存データがありません")

    found = None
    for table in soup.find_all("table"):
        indices = _headings(table)
        if indices is None:
            continue
        selected = {}
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if len(cells) <= max(indices.values()):
                continue
            raw_no = _norm(cells[indices["馬番"]].get_text(" ", strip=True))
            if not re.fullmatch(r"\d{1,2}", raw_no):
                continue
            no = int(raw_no)
            if no not in saved:
                raise ValueError("出馬表に保存予想と異なる馬番があります")
            name = _name(cells[indices["馬名"]])
            if name != saved[no] or no in selected:
                raise ValueError(f"馬番{no}の馬名不一致または重複")
            raw_weight = _norm(cells[indices["馬体重"]].get_text(" ", strip=True))
            m = CURRENT.fullmatch(raw_weight)
            kg = int(m.group(1)) if m else None
            if kg is not None and not 250 <= kg <= 750:
                raise ValueError("馬体重が想定範囲外です")
            change_text = m.group(2) if m else None
            change = int(change_text) if change_text and re.fullmatch(r"[+-]?\d{1,2}", change_text) else (
                0 if change_text == "±0" else None)
            selected[no] = dict(
                horse_no=no, name=name, current_kg=kg, change_kg=change,
                change_label=("初出走" if change_text and
                              (change_text == "初出走" or set(change_text) <= {"-", "—", "―"})
                              else None),
                paired_min_kg=None, paired_max_kg=None, paired_count=0,
            )
        if len(selected) >= max(1, math.ceil(len(saved) * 0.70)):
            found = selected
            break
    if found is None:
        raise ValueError("保存馬番・馬名と照合できる出馬表がありません")
    return [found.get(no, dict(
        horse_no=no, name=name, current_kg=None, change_kg=None,
        change_label=None, paired_min_kg=None, paired_max_kg=None, paired_count=0
    )) for no, name in sorted(saved.items())]
