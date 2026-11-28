"""Sportsnavi as-of-race all-career 1st/2nd bodyweight evidence.

A fallback to the independent netkeiba history source. Both racecard and
profile horse identity are checked before touching display-only weight ranges.
Neither current weight nor pre-race predictions are modified.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .jra_body_weight_alternates import _heading, _norm, _validate_source


PROFILE = re.compile(r"^/keiba/directory/horse/(20\d{8})/?$")
DATE = re.compile(r"^20\d{2}/\d{1,2}/\d{1,2}$")
WEIGHT = re.compile(r"^(\d{3})(?:\((?:[+-]?\d{1,3}|±0|初出走)\))?$")
HOST = "sports.yahoo.co.jp"


def parse_racecard_ids(html, url, identity, info):
    """Map racecard horse numbers to profile IDs, never by link order."""
    _validate_source(url, "sportsnavi", identity, info)
    soup = BeautifulSoup(html, "html.parser")
    _heading(soup, "sportsnavi", identity, info)
    saved = {}
    for horse in identity.get("horses") or ():
        no = int(horse["horse_no"])
        name = _norm(horse["name"])
        if not 1 <= no <= 20 or no in saved or not name:
            raise ValueError("保存された出走馬の識別情報が不正です")
        saved[no] = name
    if not saved:
        raise ValueError("保存出走馬がありません")
    mapped = None
    for table in soup.select("table"):
        tr = table.find("tr")
        if tr is None:
            continue
        headers = [_norm(x.get_text(" ", strip=True)) for x in tr.find_all("th", recursive=False)]
        no_i = next((i for i, x in enumerate(headers) if x.startswith("馬番")), None)
        name_i = next((i for i, x in enumerate(headers) if x.startswith("馬名")), None)
        if no_i is None or name_i is None:
            continue
        result = {}
        for row in table.find_all("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) <= max(no_i, name_i):
                continue
            no_text = _norm(cells[no_i].get_text(" ", strip=True))
            if not re.fullmatch(r"\d{1,2}", no_text):
                continue
            no = int(no_text)
            if no not in saved or no in result:
                raise ValueError("保存馬番にない馬または馬番重複があります")
            name_cell = cells[name_i]
            # Some JRA horse cards place an empty icon/badge before the
            # linked horse name. The FIRST HTML node is not necessarily
            # the horse name: compare exact nonempty rendered text nodes
            # and exact linked names, never a substring of the full cell.
            candidates = [
                _norm(node.get_text(" ", strip=True)
                      if hasattr(node, "get_text") else str(node))
                for node in name_cell.contents
            ]
            candidates += [
                _norm(node.get_text(" ", strip=True))
                for node in name_cell.find_all(["a", "strong", "p"])
            ]
            if saved[no] not in candidates:
                raise ValueError(f"馬番{no}の馬名が一致しません")
            ids = []
            for link in name_cell.find_all("a", href=True):
                full = urlsplit(urljoin(url, link["href"]))
                m = PROFILE.fullmatch(full.path)
                if (full.scheme == "https" and full.hostname == HOST
                        and not full.query and m
                        and _norm(link.get_text(" ", strip=True)) == saved[no]):
                    ids.append(m.group(1))
            if len(set(ids)) > 1:
                raise ValueError("同一馬に複数のプロフィールIDがあります")
            result[no] = (saved[no], ids[0] if ids else None)
        if len(result) >= max(1, (len(saved) * 7 + 9) // 10):
            mapped = result
            break
    if mapped is None:
        raise ValueError("レースの全馬識別情報を確認できません")
    verified = {no: pair for no, pair in mapped.items() if pair[1]}
    if len({p[1] for p in verified.values()}) != len(verified):
        raise ValueError("別の馬に同一プロフィールIDが割当てられています")
    return verified


def parse_profile(html, url, *, expected_horse_id, expected_name, race_day):
    """Rebuild range from every dated 1st/2nd BEFORE the saved race date."""
    parts = urlsplit(url)
    match = PROFILE.fullmatch(parts.path)
    if (parts.scheme != "https" or parts.hostname != HOST or parts.query
            or not match or match.group(1) != expected_horse_id):
        raise ValueError("スポーツナビの馬IDが不一致です")
    soup = BeautifulSoup(html, "html.parser")
    title = soup.select_one("h2 ruby") or soup.find("h2")
    if not title or _norm(title.get_text(" ", strip=True)) != _norm(expected_name):
        raise ValueError("競走馬プロフィールの馬名が不一致です")
    cutoff = datetime.strptime(race_day, "%Y%m%d").date()
    paired, observed = [], 0
    table_found = False
    for table in soup.select("table"):
        headings = [_norm(x.get_text(" ", strip=True)) for x in table.select("thead th")]
        try:
            date_i, finish_i, weight_i = [headings.index(x) for x in ("日付", "着順", "馬体重")]
        except ValueError:
            continue
        table_found = True
        for row in table.select("tbody tr"):
            tds = row.find_all("td", recursive=False)
            if len(tds) <= max(date_i, finish_i, weight_i):
                continue
            dt = _norm(tds[date_i].get_text(" ", strip=True))
            if not DATE.fullmatch(dt):
                continue
            try:
                actual_day = datetime.strptime(dt, "%Y/%m/%d").date()
            except ValueError:
                continue
            if actual_day >= cutoff:
                continue
            observed += 1
            finish = _norm(tds[finish_i].get_text(" ", strip=True))
            kg_match = WEIGHT.fullmatch(_norm(tds[weight_i].get_text(" ", strip=True)))
            if finish in ("1", "2") and kg_match:
                kg = int(kg_match.group(1))
                if 250 <= kg <= 750:
                    paired.append(kg)
        break
    if not table_found or observed == 0:
        raise ValueError("出走日付を伴う全走成績が確認できません")
    return dict(
        name=_norm(expected_name), horse_id=expected_horse_id,
        paired_min_kg=min(paired) if paired else None,
        paired_max_kg=max(paired) if paired else None,
        paired_count=len(paired), known_starts=observed,
        paired_scope="career", paired_source="sportsnavi",
        paired_source_url=url, cutoff_day=race_day,
    )


def enrich(rows, identity, info, *, get, cache=None, max_workers=4, timeout=7):
    """Best-effort Sportsnavi lookup; never erase existing known weight ranges."""
    from .jra_body_weight import race_facts
    from .jra_body_weight_alternates import sources
    from .jra_body_weight_history import _response
    _rid, _venue, day, *_ = race_facts(identity, info)
    racecard_url = dict(sources(identity, info))["sportsnavi"]
    card = _response(get, racecard_url, timeout=timeout)
    mapping = parse_racecard_ids(card, racecard_url, identity, info)
    existing = {int(r["horse_no"]): r for r in rows}
    done = {}
    to_fetch = []
    for no, (name, horse_id) in mapping.items():
        if no not in existing or _norm(existing[no].get("name")) != name:
            continue
        key = f"sportsnavi:{horse_id}:{day}"
        saved = cache.get(key) if cache is not None else None
        if (isinstance(saved, dict) and saved.get("name") == name
                and saved.get("horse_id") == horse_id and saved.get("cutoff_day") == day
                and saved.get("paired_scope") == "career"):
            done[no] = saved
        else:
            to_fetch.append((no, name, horse_id, key))

    def task(item):
        no, name, horse_id, key = item
        url = f"https://{HOST}/keiba/directory/horse/{horse_id}"
        try:
            raw = _response(get, url, timeout=timeout)
            result = parse_profile(raw, url, expected_horse_id=horse_id,
                                   expected_name=name, race_day=day)
            return no, key, result
        except Exception:
            return None

    if to_fetch:
        with ThreadPoolExecutor(max_workers=max(1, min(4, max_workers))) as pool:
            for result in pool.map(task, to_fetch):
                if result is not None:
                    no, key, item = result
                    done[no] = item
                    if cache is not None:
                        cache[key] = item

    out = [dict(row) for row in rows]
    for row in out:
        record = done.get(int(row["horse_no"]))
        if record and record["name"] == _norm(row["name"]):
            for key in ("paired_min_kg", "paired_max_kg", "paired_count",
                        "paired_scope", "paired_source_url", "paired_source"):
                row[key] = record[key]
    return out, len(done)
