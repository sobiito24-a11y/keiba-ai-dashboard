"""JRA official racecard body weights, for display only (never a model input).

A user click fetches the exact saved race card from official JRA hosts.
The race URL and each horse's number/name are checked before accepting data.
Unpublished current weights stay missing; historical paired weights can
still be displayed separately. No scores, ranks or odds are changed.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
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


def official_card_url(identity, info):
    """Verified 2026 JRA racecard address; never brute-force checksum values.

    JRA's CNAME carries a one-byte check value. This formula was compared
    against official cards on multiple 2026 race dates. Verify the response
    identity again after download: an HTTP 200 alone proves nothing.
    """
    rid, venue, day, meeting, meeting_day, race_no = race_facts(identity, info)
    if rid[:4] != "2026":
        raise ValueError("2026年以外のJRA出馬表URLは未検証です")
    v = int(rid[4:6])
    month, date = int(day[4:6]), int(day[6:8])
    hi_lo = lambda n: divmod(n, 10)
    vt, vo = hi_lo(v)
    dt, do = hi_lo(meeting_day)
    mt, mo = hi_lo(month)
    xt, xo = hi_lo(date)
    code = (
        vt * 0x29 + vo * 0x4A + meeting * 0x31 +
        dt * 0x10 + do * 0x73 + xt * 0x5A + xo * 0xBD +
        mt * 0x18 + mo * 0x7B + 0x4B
    ) % 256
    for earlier_race in range(1, race_no):
        code = (code - (0x0B if earlier_race == 9 else 0x4B)) % 256
    name = f"pw01dde01{rid[4:6]}{rid[:4]}{rid[6:8]}{rid[8:10]}{rid[10:12]}{day}/{code:02X}"
    return "https://www.jra.go.jp/JRADB/accessD.html?CNAME=" + name


def _official_variants(primary_url):
    """Only identical racecard paths on official hosts; preserve CNAME exactly."""
    parsed = urlsplit(primary_url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS or parsed.path != "/JRADB/accessD.html":
        raise ValueError("JRA出馬表以外のURLは取得しません")
    path_query = parsed.path + "?" + parsed.query
    return [f"https://{host}{path_query}" for host in ("www.jra.go.jp", "jra.jp")]


def _retrieval_status(rows):
    confirmed = sum(row.get("current_kg") is not None for row in rows)
    return "published" if confirmed else "unpublished"


def _published_count(rows):
    return sum(row.get("current_kg") is not None for row in rows)


async def fetch_once(identity, info, *, now=None, request_get=None, browser_fallback=True):
    """Refresh the exact saved JRA race, independently of predicted rankings.

    A valid card containing ZERO current weights might be an outdated cached
    response. Never interpret one such HTTP response as proof of nonpublication:
    retry the other official host, and then the installed browser. Keep the
    validated response with the greatest number of actual current weights.
    """
    now = now or datetime.now(JST)
    if not is_today(identity, info, now):
        raise ValueError("JRAの当日開催レースのみ更新できます")
    rid, _venue, _day, _meeting, _meeting_day, _race_no = race_facts(identity, info)
    import requests
    get = request_get or requests.get
    candidates = _official_variants(official_card_url(identity, info))
    errors = []
    best = None

    def consider(url, rows, channel):
        nonlocal best
        count = _published_count(rows)
        if best is None or count > best[2]:
            best = (url, rows, count, channel)
        return count

    for url in candidates:
        try:
            response = get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (KeibaAI; manual official racecard)",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "Pragma": "no-cache",
                },
                timeout=9, allow_redirects=False)
            if response.status_code != 200:
                raise ValueError(f"HTTP {response.status_code}")
            if not 0 < len(response.content) <= 4_000_000:
                raise ValueError("出馬表の応答サイズが不正")
            rows = parse_card(response.content, url, identity, info)
            count = consider(url, rows, "http")
            if count == len(rows):
                # Every declared horse has a measured current weight.
                break
        except (ValueError, TypeError, OSError, TimeoutError, requests.RequestException) as exc:
            errors.append(f"{urlsplit(url).hostname}: {str(exc)[:85]}")

    if best is None or best[2] < len(best[1]):
        # The official page may be stale even though its race identity
        # validates. Use *separate* public providers for today's actual
        # measurements, but only after matching the full saved race identity
        # and every matched horse number + name. They are not model inputs.
        from .jra_body_weight_alternates import sources as alternate_sources
        from .jra_body_weight_alternates import parse_card as parse_alternate
        official_rows = (best[1] if best and best[3] in ("http", "browser") else ())
        official_by_no = {r["horse_no"]: r for r in official_rows}
        for provider, alternate_url in alternate_sources(identity, info):
            try:
                response = get(
                    alternate_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; KeibaAI/1.0; manual racecard)",
                        "Cache-Control": "no-cache, max-age=0",
                        "Pragma": "no-cache",
                    },
                    timeout=9, allow_redirects=False)
                if response.status_code != 200:
                    raise ValueError(f"HTTP {response.status_code}")
                if not 0 < len(response.content) <= 4_000_000:
                    raise ValueError("出馬表の応答サイズが不正")
                extra = parse_alternate(response.content, alternate_url, provider, identity, info)
                # Third-party pages supply only today's weights. Preserve the
                # past 1st/2nd ranges, separately verified from official JRA.
                for row in extra:
                    prior = official_by_no.get(row["horse_no"])
                    if prior and row["name"] == prior["name"]:
                        for field in ("paired_min_kg", "paired_max_kg", "paired_count"):
                            row[field] = prior.get(field)
                count = consider(alternate_url, extra, provider)
                if count == len(extra):
                    break
            except (ValueError, TypeError, OSError, TimeoutError, requests.RequestException) as exc:
                errors.append(f"{provider}: {str(exc)[:85]}")

    if (best is None or best[2] == 0) and browser_fallback:
        # A valid but unpopulated HTTP card still needs browser verification;
        # otherwise we can falsely report "unpublished" six minutes before
        # the start even though weights are published on JRA's current page.
        try:
            from playwright.async_api import async_playwright
            async with async_playwright() as playwright:
                kwargs = dict(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
                if os.path.isfile("/usr/bin/chromium"):
                    kwargs["executable_path"] = "/usr/bin/chromium"
                try:
                    browser = await playwright.chromium.launch(**kwargs)
                except Exception:
                    errors.append("Chromiumを起動できません")
                else:
                    try:
                        context = await browser.new_context(extra_http_headers={
                            "Cache-Control": "no-cache, no-store, max-age=0",
                            "Pragma": "no-cache",
                        })
                        page = await context.new_page()
                        page.set_default_timeout(12000)
                        for candidate in candidates:
                            try:
                                await page.goto(candidate, wait_until="domcontentloaded", timeout=20000)
                                rows = parse_card(await page.content(), page.url, identity, info)
                                count = consider(page.url, rows, "browser")
                                if count:
                                    break
                            except Exception as exc:
                                errors.append(
                                    f"ブラウザ({urlsplit(candidate).hostname}): {str(exc)[:85]}")
                    finally:
                        await browser.close()
        except Exception as exc:
            errors.append(f"ブラウザ再確認不可: {type(exc).__name__}")

    if best is None:
        raise ValueError("JRA公式出馬表に接続・照合できません。"
                         + " / ".join(errors[:4])[:360])
    url, rows, count, channel = best
    return dict(race_id=rid, mode="jra", source_url=url,
                retrieved_at=now.isoformat(),
                prestart_observed=_post_time_before_now(info, now),
                publication_status=_retrieval_status(rows),
                current_count=count, verified_by=channel,
                # Zero may mean unannounced weights OR a stale provider cache.
                publication_uncertain=(count == 0),
                rows=rows)


def _post_time_before_now(info, now):
    """True only when a saved, timezone-aware post-time is later than now."""
    from types import SimpleNamespace
    from .race_odds import start_from_result
    raw = start_from_result(SimpleNamespace(race_info=info))
    if not raw:
        return False
    try:
        start = datetime.fromisoformat(raw)
        return start.tzinfo is not None and now < start
    except (ValueError, TypeError):
        return False
