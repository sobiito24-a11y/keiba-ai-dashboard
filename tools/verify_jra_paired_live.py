"""Optional live Sportsnavi smoke check; no credentials and no app state writes.

Usage: python tools/verify_jra_paired_live.py
Reports external provider network/markup availability separately from unit tests.
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

from core.jra_body_weight_sports_history import parse_profile, parse_racecard_ids
from core.jra_body_weight_alternates import _norm

RACE_ID = "202605050711"
RACE_INFO = {"race_date": "2026-11-28", "racecourse": "東京", "start_time": "15:25"}
URL = "https://sports.yahoo.co.jp/keiba/race/denma/2605050711"
SAMPLES = {
    2: ("レッドシュヴェルト", "2020103517", (450, 476)),
    3: ("アドマイヤクワッズ", "2023105311", (472, 478)),
    4: ("マジックサンズ", "2022104772", (500, 514)),
    5: ("シャンパンカラー", "2020103075", (500, 502)),
    6: ("キョウエイブリッサ", "2020107001", (462, 488)),
    7: ("ウイントワイライト", "2022106232", (444, 464)),
}


def fetch(url):
    response = requests.get(
        url, headers={"User-Agent": "Mozilla/5.0",
                      "Cache-Control": "no-cache"},
        allow_redirects=False, timeout=13)
    print(f"HTTP {response.status_code} {url}")
    if response.status_code != 200:
        raise RuntimeError("Provider is not reachable from this runner")
    if len(response.content) > 4_000_000:
        raise RuntimeError("Provider response is too large")
    return response.content


def main():
    raw = fetch(URL)
    soup = BeautifulSoup(raw, "html.parser")
    saved = []
    for table in soup.find_all("table"):
        first = table.find("tr")
        if first is None:
            continue
        heads = [_norm(h.get_text(" ", strip=True)) for h in first.find_all("th", recursive=False)]
        ni = next((i for i, h in enumerate(heads) if h.startswith("馬番")), None)
        name_i = next((i for i, h in enumerate(heads) if h.startswith("馬名")), None)
        if ni is None or name_i is None:
            continue
        for tr in table.find_all("tr"):
            tds = tr.find_all("td", recursive=False)
            if len(tds) <= max(ni, name_i):
                continue
            number = _norm(tds[ni].get_text(" ", strip=True))
            if not re.fullmatch(r"\d{1,2}", number):
                continue
            name_cell = tds[name_i]
            # Ignore empty decorative icons before a linked horse name.
            links = [
                a for a in name_cell.find_all("a", href=True)
                if "/keiba/directory/horse/" in a["href"]
                and _norm(a.get_text(" ", strip=True))
            ]
            if links:
                horse = _norm(links[0].get_text(" ", strip=True))
            else:
                names = [
                    _norm(node.get_text(" ", strip=True)
                          if hasattr(node, "get_text") else str(node))
                    for node in name_cell.contents
                ]
                horse = next((v for v in names if v), "")
            saved.append({"horse_no": int(number), "name": horse})
        break
    print("Parsed racecard saved horses:", saved, flush=True)
    assert len(saved) == 18, f"Racecard runners: {len(saved)}"
    identity = {"race_id": RACE_ID, "mode": "jra", "horses": saved}
    mapping = parse_racecard_ids(raw, URL, identity, RACE_INFO)
    print(f"Verified profile IDs: {len(mapping)}/{len(saved)}")
    for no, (name, hid, expected) in SAMPLES.items():
        assert mapping[no] == (_norm(name), hid), (no, mapping.get(no))
        profile_url = f"https://sports.yahoo.co.jp/keiba/directory/horse/{hid}"
        history = parse_profile(
            fetch(profile_url), profile_url, expected_horse_id=hid,
            expected_name=name, race_day="20261128")
        measured = (history["paired_min_kg"], history["paired_max_kg"])
        print(f"{no} {name}: {measured}")
        assert measured == expected, (no, measured, expected)
    print("REAL PROVIDER SMOKE: OK")


if __name__ == "__main__":
    main()
