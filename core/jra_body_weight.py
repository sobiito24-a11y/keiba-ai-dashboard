"""JRA official racecard body weights, for display only (never a model input).

An explicit user click navigates the official site. The JRA CNAME checksum is
not guessed: a live racecard link is discovered by the official browser menu.
Missing current weights / previous 1st-2nd finishes are never fabricated.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from html import unescape
import math
import os
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

from bs4 import BeautifulSoup, NavigableString

from .race_odds import JST

VENUES = {
    "01": "札幌", "02": "函館", "03": "福島", "04": "新潟", "05": "東京",
    "06": "中山", "07": "中京", "08": "京都", "09": "阪神", "10": "小倉",
}
OFFICIAL_HOSTS = {"www.jra.go.jp", "jra.jp", "app.jra.jp"}
CNAME = re.compile(
    r"^pw01dde(?:10|01)(\d{2})(20\d{2})(\d{2})(\d{2})(\d{2})(20\d{6})/([0-9A-Fa-f]{2})$"
)
WEIGHT = re.compile(r"(?<!\d)(\d{3})\s*kg\s*\(\s*([+-]\d{1,2}|0|±0|初出走)\s*\)")
PAST_WEIGHT = re.compile(r"(?<!\d)(\d{3})\s*kg(?!\d)")
FINISH = re.compile(r"(?<!\d)([12])\s*着(?!\d)")


def _norm(value):
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or ""))).replace("﨑", "崎")


def race_facts(identity, info):
    """Resolve explicit date / saved JRA race ID; never infer today's meeting."""
    rid = str(identity.get("race_id") or "")
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", rid):
        raise ValueError("JRAの12桁レースIDが確認できません")
    venue = VENUES.get(rid[4:6])
    if not venue:
        raise ValueError("保存レースのJRA開催場を特定できません")
    source_day = str((info or {}).get("race_date") or (info or {}).get("date") or "")
    day_digits = re.sub(r"\D", "", source_day)
    if not re.fullmatch(r"20\d{6}", day_digits):
        raise ValueError("保存した開催日が確認できません")
    try:
        datetime.strptime(day_digits, "%Y%m%d")
    except ValueError as exc:
        raise ValueError("開催日の形式が不正です") from exc
    described = _norm((info or {}).get("racecourse") or (info or {}).get("venue") or "")
    if described and venue not in described:
        raise ValueError("保存レースIDと開催場が一致しません")
    return rid, venue, day_digits, int(rid[6:8]), int(rid[8:10]), int(rid[10:12])


def is_today(identity, info, now=None):
    now = now or datetime.now(JST)
    return now.strftime("%Y%m%d") == race_facts(identity, info)[2]


def _check_source(url, identity, info):
    rid, venue, day, meeting, meeting_day, race_no = race_facts(identity, info)
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.path != "/JRADB/accessD.html":
        raise ValueError("JRA公式出馬表のHTTPSページではありません")
    cname = parse_qs(parsed.query).get("CNAME", [""])[0]
    match = CNAME.fullmatch(cname)
    if not match:
        raise ValueError("JRA公式出馬表の識別情報を確認できません")
    venue_code, year, mr, dr, rr, date, _checksum = match.groups()
    if (venue_code != rid[4:6] or year != rid[:4] or
        (int(mr), int(dr), int(rr)) != (meeting, meeting_day, race_no) or date != day):
        raise ValueError("JRA出馬表の競馬場・開催日・Rが保存予想と一致しません")


def _horse_name(cell):
    # The JRA card starts the horse cell with a direct text node; owner,
    # trainer and pedigree are separate descendants and must not be a name.
    direct = [_norm(x) for x in cell.contents if isinstance(x, NavigableString) and _norm(x)]
    if direct:
        return direct[0]
    anchor = cell.select_one("a")
    return _norm(anchor.get_text(" ", strip=True)) if anchor else ""


def parse_card(html, source_url, identity, info):
    """Extract only a matching JRA race and the matching saved horses."""
    _check_source(source_url, identity, info)
    rid, venue, day, meeting, meeting_day, race_no = race_facts(identity, info)
    soup = BeautifulSoup(html, "html.parser")
    heading = _norm(" ".join(h.get_text(" ", strip=True) for h in soup.select("h1")))
    date_mark = f"{int(day[:4])}年{int(day[4:6])}月{int(day[6:])}日"
    if (not all(s in heading for s in
                ("出馬表", date_mark, f"{meeting}回{venue}{meeting_day}日",
                 f"{race_no}レース")) or "パラメータエラー" in soup.get_text(" ", strip=True)):
        raise ValueError("JRA公式ページの開催日・開催場・Rを確認できません")
    saved = {}
    for horse in identity.get("horses") or ():
        try:
            no = int(horse["horse_no"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("保存出走馬の馬番が不正です") from exc
        name = _norm(horse.get("name"))
        if not 1 <= no <= 20 or not name or no in saved:
            raise ValueError("保存出走馬の馬番・馬名に欠損または重複があります")
        saved[no] = name
    if not saved:
        raise ValueError("保存レースの出走馬がありません")
    table = None
    for candidate in soup.select("table"):
        headers = [_norm(th.get_text(" ", strip=True)) for th in candidate.select("thead th")]
        if any("馬番" in h for h in headers) and any("馬名" in h for h in headers) and any("前走" in h for h in headers):
            table = candidate
            break
    if table is None:
        raise ValueError("JRA公式出馬表の馬柱を確認できません（ページ形式変更の可能性）")
    found = {}
    for tr in table.select("tbody tr"):
        cells = tr.find_all("td", recursive=False)
        if len(cells) < 8:
            continue
        raw_no = _norm(cells[1].get_text(" ", strip=True))
        if not re.fullmatch(r"\d{1,2}", raw_no):
            # The official page can show a withdrawn horse as just "除外".
            continue
        no = int(raw_no)
        if no not in saved:
            raise ValueError("JRA出馬表に保存予想と異なる馬番があります")
        name = _horse_name(cells[2])
        if name != saved[no] or no in found:
            raise ValueError("JRA出馬表の馬番・馬名が不一致または重複しています")
        candidate_weights = [WEIGHT.search(p.get_text(" ", strip=True))
                             for p in cells[2].find_all("p")]
        body_match = next((m for m in candidate_weights if m is not None), None)
        kg = int(body_match.group(1)) if body_match else None
        if kg is not None and not 250 <= kg <= 750:
            raise ValueError("JRA馬体重が想定範囲外です")
        label = body_match.group(2) if body_match else None
        change = (int(label) if label not in (None, "初出走", "±0") else
                  0 if label == "±0" else None)
        # Count only previous 1st/2nd, with a known physical weight.
        paired = []
        for past in cells[4:8]:
            texts = past.get_text(" ", strip=True)
            rank = FINISH.search(texts)
            weight = PAST_WEIGHT.search(texts)
            if rank and weight and 250 <= int(weight.group(1)) <= 750:
                paired.append(int(weight.group(1)))
        found[no] = dict(
            horse_no=no, name=name, current_kg=kg, change_kg=change,
            change_label="初出走" if label == "初出走" else None,
            paired_min_kg=min(paired) if paired else None,
            paired_max_kg=max(paired) if paired else None,
            paired_count=len(paired),
        )
    if len(found) < max(1, math.ceil(len(saved) * 0.70)):
        raise ValueError(f"保存馬番・馬名の照合が不足（{len(found)}/{len(saved)}頭）。反映を中止します")
    return [found.get(no, dict(
        horse_no=no, name=name, current_kg=None, change_kg=None,
        change_label=None, paired_min_kg=None, paired_max_kg=None, paired_count=0))
        for no, name in sorted(saved.items())]


def overlay(view, observation):
    """Read-only view decoration. Never changes rank, prediction, odds or marks."""
    if not observation:
        return view
    out = deepcopy(view)
    by_no = {str(r["horse_no"]): r for r in observation["rows"]}
    for horse in out:
        row = by_no.get(str(horse.get("no")))
        if row and _norm(horse.get("name")) == row["name"]:
            horse["jra_body_weight_research"] = dict(
                row, retrieved_at=observation["retrieved_at"],
                source_url=observation["source_url"],
                prestart_observed=observation["prestart_observed"])
    return out


async def fetch_once(identity, info, *, now=None):
    """One explicit button press, one official navigation; no polling or login."""
    from playwright.async_api import async_playwright
    now = now or datetime.now(JST)
    if not is_today(identity, info, now):
        raise ValueError("JRAの当日開催レースのみ更新できます")
    rid, venue, day, meeting, meeting_day, race_no = race_facts(identity, info)
    async with async_playwright() as playwright:
        kwargs = dict(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        if os.path.isfile("/usr/bin/chromium"):
            kwargs["executable_path"] = "/usr/bin/chromium"
        try:
            browser = await playwright.chromium.launch(**kwargs)
        except Exception as exc:
            raise ValueError("JRA取得用ブラウザを起動できません（Chromium設定を確認）") from exc
        try:
            page = await browser.new_page()
            page.set_default_timeout(12000)
            await page.goto("https://www.jra.go.jp/", wait_until="domcontentloaded", timeout=20000)
            await page.get_by_role("link", name="出馬表", exact=True).first.click()
            await page.get_by_role("link", name=f"{meeting}回{venue}{meeting_day}日").first.click()
            await page.get_by_role("link", name=f"{race_no}レース", exact=True).first.click()
            await page.wait_for_load_state("domcontentloaded")
            url, html = page.url, await page.content()
            rows = parse_card(html, url, identity, info)
            return dict(race_id=rid, mode="jra", source_url=url,
                        retrieved_at=now.isoformat(), prestart_observed=(
                            _post_time_before_now(info, now)), rows=rows)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("JRA公式出馬表に到達できません（掲載前・画面変更・通信制限の可能性）") from exc
        finally:
            await browser.close()


def _post_time_before_now(info, now):
    """True only when a saved, timezone-aware post-time is later than now."""
    from .race_odds import start_from_result
    # This function accepts race_info, avoiding mutating a PredictionResult.
    class _Race:
        race_info = info
    raw = start_from_result(_Race)
    if not raw:
        return False
    try:
        start = datetime.fromisoformat(raw)
        return start.tzinfo is not None and now < start
    except (ValueError, TypeError):
        return False
