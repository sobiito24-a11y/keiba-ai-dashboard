"""Verified all-career 1st/2nd finish weights for JRA racecard display.

This is a user-triggered READ-ONLY supplement. Racecard horse-id links must
match saved race number+name and each career history must match its exact
horse's name. Dated career finishes on/after the target race are excluded.
A failed public request never changes a prediction or overwrites official
short-history evidence.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import re
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from .jra_body_weight_alternates import _heading, _norm, _validate_source

PROFILE = re.compile(r"^/horse/(20\d{8})/?$")
RESULT = re.compile(r"^/horse/result/(20\d{8})/?$")
DATE = re.compile(r"^20\d\d[/\-]\d{1,2}[/\-]\d{1,2}$")
BODY = re.compile(r"^(\d{3})(?:\((?:[+-]?\d{1,2}|±0|初出走)\))?$")


def _response(get, url, *, timeout=7):
    response = get(
        url,
        headers={"User-Agent": "Mozilla/5.0 (KeibaAI; manual race history lookup)",
                 "Cache-Control": "no-cache, max-age=0"},
        timeout=timeout, allow_redirects=False)
    if response.status_code != 200 or not 0 < len(response.content) <= 4_000_000:
        raise ValueError("競走成績の公開ページを取得できません")
    return response.content


def racecard_ids(html, url, identity, info):
    """Horse-id discovery, from a verified racecard's exact numbered horse rows.

    Never use link order as a horse identity, and never map by substring.
    """
    _validate_source(url, "netkeiba", identity, info)
    soup = BeautifulSoup(html, "html.parser")
    _heading(soup, "netkeiba", identity, info)
    saved = {}
    for h in identity.get("horses") or []:
        no = int(h["horse_no"])
        name = _norm(h["name"])
        if no in saved or not name or not 1 <= no <= 20:
            raise ValueError("保存された馬番・馬名が不正です")
        saved[no] = name
    if not saved:
        raise ValueError("出走馬を確認できません")

    found = {}
    for table in soup.find_all("table"):
        headers = table.find("tr")
        if not headers:
            continue
        th = headers.find_all("th", recursive=False)
        labels = [_norm(h.get_text(" ", strip=True)) for h in th]
        num_i = next((i for i, x in enumerate(labels) if x in ("馬番", "馬番(馬番)")), None)
        name_i = next((i for i, x in enumerate(labels) if x == "馬名"), None)
        if num_i is None or name_i is None:
            continue
        mapped = {}
        for tr in table.find_all("tr"):
            cells = tr.find_all("td", recursive=False)
            if max(num_i, name_i) >= len(cells):
                continue
            no_text = _norm(cells[num_i].get_text(" ", strip=True))
            if not re.fullmatch(r"\d{1,2}", no_text):
                continue
            no = int(no_text)
            if no not in saved:
                raise ValueError("別レースの馬番を検出しました")
            name_cell = cells[name_i]
            # Name can be wrapped by a <p> or <a>; exclude non-name notes.
            p = name_cell.find("p")
            row_name = _norm(p.get_text(" ", strip=True) if p else name_cell.get_text(" ", strip=True))
            if row_name != saved[no] or no in mapped:
                raise ValueError("保存馬番・馬名と出馬表が一致しません")
            links = []
            for a in name_cell.find_all("a", href=True):
                if _norm(a.get_text(" ", strip=True)) != saved[no]:
                    continue
                parsed = urlsplit(urljoin(url, a["href"]))
                match = PROFILE.fullmatch(parsed.path)
                if (parsed.scheme == "https" and parsed.hostname == "db.netkeiba.com"
                        and match and not parsed.query):
                    links.append(match.group(1))
            if len(set(links)) > 1:
                raise ValueError("同一馬に異なるIDが紐づいています")
            mapped[no] = (saved[no], links[0] if links else None)
        if len(mapped) >= max(1, (len(saved) * 7 + 9) // 10):
            found = mapped
            break
    if not found:
        raise ValueError("保存レースと照合できる馬番表がありません")
    ids = {no: (name, hid) for no, (name, hid) in found.items() if hid}
    if len(set(v[1] for v in ids.values())) != len(ids):
        raise ValueError("複数の馬が同じnetkeiba馬IDを示しています")
    return ids


def career_pair_weights(html, url, *, expected_horse_id, expected_name, race_day):
    """Collect 1st/2nd weight from ALL career starts dated BEFORE race day."""
    parsed = urlsplit(url)
    m = RESULT.fullmatch(parsed.path)
    if (parsed.scheme != "https" or parsed.hostname != "db.netkeiba.com"
            or parsed.query or not m or m.group(1) != expected_horse_id):
        raise ValueError("競走成績URLの馬IDが一致しません")
    soup = BeautifulSoup(html, "html.parser")
    h1 = soup.find("h1")
    if not h1 or _norm(h1.get_text(" ", strip=True)) != _norm(expected_name):
        raise ValueError("競走成績の馬名が保存名と一致しません")
    found_table = False
    observed = 0
    paired = []
    for table in soup.select("table"):
        th = table.select("thead th")
        headers = [_norm(h.get_text(" ", strip=True)) for h in th]
        try:
            date_i = headers.index("日付")
            finish_i = headers.index("着順")
            weight_i = headers.index("馬体重")
        except ValueError:
            continue
        found_table = True
        for tr in table.select("tbody tr"):
            tds = tr.find_all("td", recursive=False)
            if max(date_i, finish_i, weight_i) >= len(tds):
                continue
            raw_date = _norm(tds[date_i].get_text(" ", strip=True))
            if not DATE.fullmatch(raw_date):
                continue
            try:
                date = datetime.strptime(raw_date.replace("-", "/"), "%Y/%m/%d").date()
            except ValueError:
                continue
            if date >= datetime.strptime(race_day, "%Y%m%d").date():
                continue
            observed += 1
            finish = _norm(tds[finish_i].get_text(" ", strip=True))
            weight = _norm(tds[weight_i].get_text(" ", strip=True))
            m_kg = BODY.fullmatch(weight)
            if finish in ("1", "2") and m_kg:
                kg = int(m_kg.group(1))
                if 250 <= kg <= 750:
                    paired.append(kg)
        break
    if not found_table or not observed:
        raise ValueError("日付の確認できる過去走がありません")
    return dict(
        name=_norm(expected_name),
        horse_id=expected_horse_id,
        paired_min_kg=min(paired) if paired else None,
        paired_max_kg=max(paired) if paired else None,
        paired_count=len(paired),
        known_starts=observed,
        paired_scope="career",
        paired_source_url=url,
        cutoff_day=race_day,
    )


def enrich(rows, identity, info, *, get, cache=None, timeout=7, max_workers=4):
    """Fill all-career paired ranges without modifying current weight/delta.

    The caller owns an optional per-session cache. Cache values remain valid
    only for the same horse name+id and as-of race date.
    """
    from .jra_body_weight import race_facts
    from .jra_body_weight_alternates import sources
    _rid, _venue, day, *_unused = race_facts(identity, info)
    url = dict(sources(identity, info))["netkeiba"]
    html = _response(get, url, timeout=timeout)
    mapping = racecard_ids(html, url, identity, info)
    by_no = {int(r["horse_no"]): r for r in rows}
    tasks = []
    results = {}
    for no, (name, horse_id) in mapping.items():
        if no not in by_no or _norm(by_no[no].get("name")) != name:
            continue
        key = f"{horse_id}:{day}"
        old = cache.get(key) if cache is not None else None
        if (isinstance(old, dict) and old.get("name") == name
                and old.get("horse_id") == horse_id and old.get("cutoff_day") == day
                and old.get("paired_scope") == "career"):
            results[no] = old
        else:
            tasks.append((no, name, horse_id, key))

    def fetch(task):
        no, name, horse_id, key = task
        url = f"https://db.netkeiba.com/horse/result/{horse_id}/"
        raw = _response(get, url, timeout=timeout)
        return no, key, career_pair_weights(
            raw, url, expected_horse_id=horse_id, expected_name=name, race_day=day)

    if tasks:
        with ThreadPoolExecutor(max_workers=max(1, min(4, max_workers))) as pool:
            for task, outcome in zip(tasks, pool.map(_try_fetch(fetch), tasks)):
                if outcome is not None:
                    no, key, record = outcome
                    results[no] = record
                    if cache is not None:
                        cache[key] = record
    updated = [dict(row) for row in rows]
    for row in updated:
        record = results.get(int(row["horse_no"]))
        if record and record["name"] == _norm(row["name"]):
            for key in ("paired_min_kg", "paired_max_kg", "paired_count",
                        "paired_scope", "paired_source_url"):
                row[key] = record[key]
    return updated, len(results)


def _try_fetch(func):
    def wrapped(task):
        try:
            return func(task)
        except (ValueError, TypeError, OSError, TimeoutError, Exception):
            # One blocked horse page must never invalidate current weights
            # or the paired ranges already verified from official JRA.
            return None
    return wrapped
