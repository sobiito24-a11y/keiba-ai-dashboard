"""Public, user-opened historical JRA odds page links (never scraping).

Race identifiers for these two named sites use YYYYMMDD + venue(2) + race(2).
Only construct links when an explicit date and a valid JRA race ID are present.
"""
from datetime import date
import re


def archived_odds_urls(identity, race_info):
    rid = str(identity.get("race_id") or "")
    if identity.get("mode") != "jra" or not re.fullmatch(r"20\d{10}", rid):
        return {}
    day = str((race_info or {}).get("race_date") or (race_info or {}).get("date") or "").replace("/", "-")
    if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day):
        return {}
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        return {}
    if str(parsed.year) != rid[:4]:
        return {}
    venue, race = rid[4:6], rid[10:12]
    if venue not in {f"{i:02}" for i in range(1,11)} or not 1 <= int(race) <= 12:
        return {}
    key = parsed.strftime("%Y%m%d") + venue + race
    return {
        "keibalab": f"https://www.keibalab.jp/db/race/{key}/odds.html",
        "yuma_win": f"https://www.keiba.jp/db/race/{key}/odds.html?kind=tan",
        "yuma_place": f"https://www.keiba.jp/db/race/{key}/odds.html?kind=fuk",
    }
