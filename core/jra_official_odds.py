"""Experimental, user-triggered JRA official win/place odds via browser navigation.

No unattended polling. This is not an official API. The source page does not
expose a trustworthy quote timestamp: mark the observation time as unknown.
"""
from datetime import datetime
from io import StringIO
import os
import re

from .race_odds import JST, validate
from .jra_netkeiba_odds import _source_date_bounds


def parse_table(html, identity, race_info, *, now=None):
    from bs4 import BeautifulSoup
    now = now or datetime.now(JST)
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", str(identity.get("race_id", ""))):
        raise ValueError("JRAレースIDが不正です")
    bounds = _source_date_bounds(race_info)
    if bounds is None or not (bounds[0] <= now < bounds[1]):
        raise ValueError("開催日前後以外のオッズは公式ページから取得しません")
    saved = {int(h["horse_no"]): str(h["name"]) for h in identity["horses"]}
    soup = BeautifulSoup(html, "html.parser")
    if soup.find(string=re.compile("予想オッズ|発売開始前")):
        raise ValueError("発売前の可能性があるため実オッズとして反映しません")
    prices = []
    matched = set()
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if not rows:
            continue
        headers = [c.get_text(" ", strip=True).replace(" ", "") for c in rows[0].find_all(["th", "td"])]
        if not {"馬番", "馬名", "単勝"}.issubset(headers):
            continue
        show_idx = next((i for i,h in enumerate(headers) if h.startswith("複勝")), None)
        if show_idx is None:
            continue
        for tr in rows[1:]:
            cells = [c.get_text(" ", strip=True) for c in tr.find_all(["th", "td"])]
            if len(cells) != len(headers):
                continue
            row = dict(zip(headers, cells))
            raw_no = row.get("馬番", "").strip()
            if not raw_no.isdecimal():
                continue
            no = int(raw_no)
            if no not in saved:
                raise ValueError("公式ページの馬番が保存レースと一致しません")
            name = re.sub(r"\s+", "", row["馬名"])
            if re.sub(r"\s+", "", saved[no]) != name:
                raise ValueError("公式ページの馬名が保存レースと一致しません")
            if no in matched:
                raise ValueError("公式オッズ表に重複馬番があります")
            matched.add(no)
            win = row["単勝"].replace(",", "").replace("倍", "").strip()
            if re.fullmatch(r"\d+(?:\.\d+)?", win) and float(win) >= 1:
                val = float(win)
                prices.append(dict(kind="win", horses=[no], low=val, high=val))
            place = cells[show_idx].replace("～", "-").replace("−", "-").replace("－", "-").replace("倍", "").replace(",", "")
            m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*", place)
            if m:
                low, high = map(float, m.groups())
                if 1 <= low <= high:
                    prices.append(dict(kind="place", horses=[no], low=low, high=high))
        if matched:
            break
    if not matched or not prices:
        raise ValueError("JRA公式の単複表を解析できません（掲載前・ページ変更の可能性）")
    if matched != set(saved):
        raise ValueError("公式ページの全出走馬を照合できません。反映を中止します")
    return validate(dict(
        race_id=identity["race_id"], mode="jra",
        identities={str(k):v for k,v in saved.items()},
        prices=prices, popularity={},
        observed_at=None, received_at=now.isoformat(),
        source="JRA公式オッズ（ブラウザ取得試験）",
        acquisition_method="jra_official_browser",
        price_status="published_odds",
        warnings=["配信元の更新時刻は未確認です。取得時刻を配信元更新時刻として扱いません",
                  "購入前にJRA公式のオッズを再確認してください"],
        missing_kinds=["quinella", "wide"],
    ), identity)


async def fetch_once(identity, race_info, *, now=None):
    from playwright.async_api import async_playwright
    rid = str(identity.get("race_id", ""))
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", rid):
        raise ValueError("JRAの12桁レースIDが必要です")
    # netkeiba-style race ID: year(4), venue(2), meeting(2), day(2), race(2).
    venues = {"01":"札幌","02":"函館","03":"福島","04":"新潟","05":"東京",
              "06":"中山","07":"中京","08":"京都","09":"阪神","10":"小倉"}
    venue = venues.get(rid[4:6])
    if not venue:
        raise ValueError("JRA開催場を特定できません")
    meeting, day, race = int(rid[6:8]), int(rid[8:10]), int(rid[10:12])
    async with async_playwright() as p:
        kwargs = dict(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        if os.path.isfile("/usr/bin/chromium"):
            kwargs["executable_path"] = "/usr/bin/chromium"
        try:
            browser = await p.chromium.launch(**kwargs)
        except Exception as exc:
            raise ValueError("公式取得用ブラウザを起動できません。サーバーのChromium設定を確認してください") from exc
        try:
            page = await browser.new_page()
            page.set_default_timeout(12000)
            await page.goto("https://www.jra.go.jp/", wait_until="domcontentloaded", timeout=20000)
            await page.get_by_role("link", name="オッズ", exact=True).first.click()
            link = page.get_by_role("link", name=f"{meeting}回{venue}{day}日").first
            await link.wait_for(state="attached")
            await link.click()
            await page.get_by_role("link", name=f"{race}レース", exact=True).first.click()
            await page.wait_for_load_state("domcontentloaded")
            return parse_table(await page.content(), identity, race_info, now=now)
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("JRA公式のオッズ画面に到達できません（開催未掲載・画面変更・通信制限の可能性）") from exc
        finally:
            await browser.close()
